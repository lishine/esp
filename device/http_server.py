import json
import _thread
import machine
import os
import gc
import esp
import sys

from log import (
    log,
    read_log_file_content,
    get_latest_log_index,
    clear_logs,
    get_log_write_stats,
)

from wifi import (
    is_connected,
    get_ip,
    save_wifi_config,
    load_wifi_config,  # Import the function instead of the variable
    get_current_network,
)

from fs import (
    get_hierarchical_list_with_sizes,
    get_hierarchical_json,
    exists,
    remove_if_empty_or_file,
    remove_empty_parents,
)
from netutils import get_client_ip, get_device_info
from upload import handle_upload

import io_local.gps_config as gps_config
from io_local.buzzer import register_buzzer_routes

from io_local import adc as adc_module  # Import the ADC module (device/ is root)

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_INTERNAL_ERROR = 500

from server_framework import app, Response, Request, error_response, success_response


@app.route("/ping")
def ping(request):
    """Simple ping endpoint to check if the server is running"""
    return Response(
        body=json.dumps({"status": "ok"}), headers={"Content-Type": "application/json"}
    )


@app.route("/upload/", methods=["POST"])
def upload_file(request: Request):
    target_path = None
    route_prefix = "/upload/"
    if request.path.startswith(route_prefix):
        target_path = request.path[len(route_prefix) :]

    if not target_path:
        body, status = error_response("Missing target path in URL")
        return Response(
            body=body, status=status, headers={"Content-Type": "application/json"}
        )

    try:
        body, status = handle_upload(request, target_path)

        return Response(
            body=body, status=status, headers={"Content-Type": "application/json"}
        )

    except Exception as e:
        log(f"Unhandled error during upload processing for {target_path}: {e}")
        body, status = error_response(
            f"Server error during upload processing: {str(e)}", HTTP_INTERNAL_ERROR
        )
        return Response(
            body=body, status=status, headers={"Content-Type": "application/json"}
        )


@app.route("/reset", methods=["GET", "POST"])
def reset(request):
    import _thread
    import time

    def delayed_reset():
        time.sleep(0.1)
        machine.reset()

    _thread.start_new_thread(delayed_reset, ())
    return "Device resetting..."


@app.route("/la")
def list_files_hierarchical(request):
    try:
        files = get_hierarchical_list_with_sizes()
        return Response(
            body="\n".join(files), headers={"Content-Type": "text/plain; charset=utf-8"}
        )
    except Exception as e:
        log(f"Error listing files for /la: {e}")
        return Response(
            body=f"Error listing files: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/view/", methods=["GET"])
def view_file(request: Request):
    filename = None
    route_prefix = "/view/"
    if request.path.startswith(route_prefix):
        filename = request.path[len(route_prefix) :]

    if not filename:
        return Response(body="Missing filename in URL", status=HTTP_BAD_REQUEST)

    if not exists(filename):
        return Response(body=f"File not found: {filename}", status=HTTP_NOT_FOUND)

    try:
        # Read the entire file content (buffered)
        with open(filename, "rb") as f:
            content = f.read()

        return Response(body=content, status=HTTP_OK, headers={"Content-Type": ""})
    except Exception as e:
        log(f"Error reading file for view {filename}: {e}")
        return Response(
            body=f"Error reading file: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/settings", methods=["GET"])
def get_settings(request):
    """Serves the main settings HTML page."""
    settings_file = "settings.html"
    if not exists(settings_file):
        return Response(body="Settings page not found.", status=HTTP_NOT_FOUND)

    try:
        # Read the entire file content (buffered)
        with open(settings_file, "r") as f:  # Read as text
            content = f.read()
        gc.collect()
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log(f"Error reading {settings_file}: {e}")
        return Response(
            body=f"Error reading settings page: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/settings/save", methods=["POST"])
def save_settings(request: Request):
    """Saves WiFi configuration received as JSON."""
    try:
        config = json.loads(request.body)
        if not isinstance(config, dict):
            raise ValueError("Invalid JSON data format")

        save_wifi_config(config)

        return Response(
            body=json.dumps({"success": True, "message": "Settings saved"}),
            status=HTTP_OK,
            headers={"Content-Type": "application/json"},
        )

    except ValueError as e:
        log(f"Error parsing JSON for settings save: {e}")
        return Response(
            body=json.dumps({"success": False, "error": f"Invalid JSON data: {e}"}),
            status=HTTP_BAD_REQUEST,
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        log(f"Error saving wifi config: {e}")
        return Response(
            body=json.dumps(
                {"success": False, "error": f"Error saving settings: {str(e)}"}
            ),
            status=HTTP_INTERNAL_ERROR,
            headers={"Content-Type": "application/json"},
        )


@app.route("/rm/", methods=["DELETE"])
def remove_file(request: Request):
    target_path = None
    route_prefix = "/rm/"
    if request.path.startswith(route_prefix):
        target_path = request.path[len(route_prefix) :]

    if not target_path:
        return Response(body="Missing target path in URL", status=HTTP_BAD_REQUEST)

    try:
        if not exists(target_path):
            return Response(
                body=f"File or directory not found: {target_path}",
                status=HTTP_NOT_FOUND,
            )

        log(f"Attempting to remove: {target_path}")
        if not remove_if_empty_or_file(target_path):
            return Response(
                body=f"Failed to remove '{target_path}'. It might be a non-empty directory.",
                status=HTTP_BAD_REQUEST,
            )

        remove_empty_parents(target_path)

        log(f"Successfully removed {target_path}")
        return Response(body=f"Successfully removed {target_path}", status=HTTP_OK)

    except Exception as e:
        log(f"Error in remove endpoint for {target_path}: {e}")
        return Response(
            body=f"Error removing target: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/free")
def get_free_space(request):
    """Return free space information about the filesystem and flash."""
    try:
        # Filesystem stats
        fs_stat = os.statvfs("/")
        block_size = fs_stat[0]
        total_blocks = fs_stat[2]
        free_blocks = fs_stat[3]

        total_kb = (total_blocks * block_size) / 1024
        free_kb = (free_blocks * block_size) / 1024
        used_kb = total_kb - free_kb
        usage_percent = (used_kb / total_kb) * 100 if total_kb > 0 else 0

        # Flash stats
        flash_total_bytes = esp.flash_size()
        flash_total_kb = flash_total_bytes / 1024 if flash_total_bytes else 0

        # Implementation details
        impl_name = sys.implementation.name  # type: ignore # Pylance might not know .name from stubs
        impl_version = f"{sys.implementation.version[0]}.{sys.implementation.version[1]}.{sys.implementation.version[2]}"  # type: ignore # Pylance might not know .version from stubs
        impl_machine = getattr(
            sys.implementation, "_machine", "N/A"
        )  # getattr is safer for optional attributes

        data = {
            "fs_free_kb": round(free_kb, 2),
            "fs_total_kb": round(total_kb, 2),
            "fs_used_kb": round(used_kb, 2),
            "fs_usage_percent": round(usage_percent, 2),
            "flash_total_kb": round(flash_total_kb, 2),
            "implementation": {
                "name": impl_name,
                "version": impl_version,
                "_machine": impl_machine,
            },
        }
        gc.collect()  # Run GC before creating potentially large JSON string
        return Response(
            body=json.dumps(data), headers={"Content-Type": "application/json"}
        )

    except Exception as e:
        log(f"Error getting free space: {e}")
        return Response(
            body=f"Error getting free space: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/fs-list")
def list_files_json(request):
    """List files in a hierarchical JSON format"""
    try:
        files = get_hierarchical_json()
        return Response(
            body=json.dumps(files), headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        log(f"Error getting file list JSON: {e}")
        return Response(
            body=f"Error getting file list: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/api/settings/data")
def get_settings_data(request):
    try:
        current_network = get_current_network()
        # Load the config directly when the API is called
        loaded_config = load_wifi_config()
        data = {
            "is_connected": is_connected(),
            "ip_address": get_ip(),
            "current_ssid": current_network["ssid"] if current_network else "",
            "networks": loaded_config.get(
                "networks",
                [{"ssid": "", "password": ""}, {"ssid": "", "password": ""}],
            ),
        }
        return Response(
            body=json.dumps(data), headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        log(f"Error getting settings data: {e}")
        return Response(
            body=f"Error getting settings data: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


# --- GPS Settings Routes ---


@app.route("/gps-settings", methods=["GET"])
def get_gps_settings_page(request):
    """Serves the GPS settings HTML page."""
    gps_settings_file = "io_local/gps_settings.html"
    if not exists(gps_settings_file):
        return Response(body="GPS Settings page not found.", status=HTTP_NOT_FOUND)
    try:
        with open(gps_settings_file, "r") as f:
            content = f.read()
        gc.collect()
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log(f"Error reading {gps_settings_file}: {e}")
        return Response(
            body=f"Error reading GPS settings page: {str(e)}",
            status=HTTP_INTERNAL_ERROR,
        )


@app.route("/api/gps-settings/data", methods=["POST"])
def handle_gps_settings_data_route(request: Request):
    try:
        return gps_config.handle_gps_settings_data(request)
    except Exception as e:
        log(f"Error processing GPS settings data: {e}")
        try:
            error_body = json.dumps({"success": False, "error": str(e)})
            return Response(
                body=error_body,
                status=HTTP_INTERNAL_ERROR,
                headers={"Content-Type": "application/json"},
            )
        except Exception:  # Fallback if JSON fails
            return Response(
                body=f"Internal server error: {str(e)}", status=HTTP_INTERNAL_ERROR
            )


@app.route("/status")
def status(request):
    """Return device status including WiFi IP and log stats."""
    try:
        response_data = {}
        if is_connected():
            response_data["ip"] = get_ip()
        else:
            response_data["ip"] = None
        response_data["stat"] = get_log_write_stats()  # Add log stats
        return Response(
            body=json.dumps(response_data), headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        log(f"Error getting device status: {e}")
        return Response(
            body=f"Error getting status: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


# --- Live Data Routes ---


@app.route("/live-data", methods=["GET"])
def get_live_data_page(request: Request):
    """Serves the static HTML page for live data status."""
    live_data_html_path = "/io_local/live_data.html"  # Path on ESP32 filesystem
    try:
        # Check if file exists first
        os.stat(live_data_html_path)
        # Read the entire file content (buffered)
        with open(live_data_html_path, "r") as f:  # Read as text
            content = f.read()
        gc.collect()
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except OSError as e:
        if e.args[0] == 2:  # ENOENT - File not found
            log(f"Live data HTML file not found: {live_data_html_path}")
            return Response(body="Live Data page not found.", status=HTTP_NOT_FOUND)
        else:
            log(f"Error accessing {live_data_html_path}: {e}")
            return Response(
                body=f"Error accessing Live Data page: {str(e)}",
                status=HTTP_INTERNAL_ERROR,
            )
    except Exception as e:
        log(f"Error reading {live_data_html_path}: {e}")
        return Response(
            body=f"Error reading Live Data page: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/api/live-data", methods=["POST"])
def post_read_live_data(request: Request):
    """Reads the latest ADC voltages (uv and u16 based) and returns them as JSON."""
    try:
        # Get the pre-calculated voltages directly from the adc module
        voltage_uv = adc_module.get_latest_voltage_uv()
        voltage_u16 = adc_module.get_latest_voltage_u16()

        # Prepare JSON response
        response_data = {
            "adc_voltage_uv_2pt": voltage_uv,  # From read_uv with 2-point factor
            "adc_voltage_u16_linear": voltage_u16,  # From read_u16 with linear factor
        }
        # Could add other live data sources here in the future

        gc.collect()  # Optional GC before creating JSON string
        return Response(
            body=json.dumps(response_data),
            status=HTTP_OK,
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        log(f"Error getting live data for API: {e}")
        # Use the framework's error response helper if available, otherwise construct manually
        body, status = error_response(
            f"Error getting live data: {str(e)}", HTTP_INTERNAL_ERROR
        )
        return Response(
            body=body, status=status, headers={"Content-Type": "application/json"}
        )


# --- Log Viewer Routes ---


@app.route("/log/infinite")
def log_viewer(request):
    """Serves the HTML page for the infinite scrolling log viewer."""
    log_viewer_file = "log_viewer.html"
    if not exists(log_viewer_file):
        return Response(body="Log viewer page not found.", status=HTTP_NOT_FOUND)
    try:
        with open(log_viewer_file, "r") as f:
            content = f.read()
        gc.collect()
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log(f"Error reading {log_viewer_file}: {e}")
        return Response(
            body=f"Error reading log viewer page: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/api/log/chunk")
def api_log_chunk_file(request: Request):
    target_index = -1
    file_index_str = request.query_params.get("file_index")  # type: ignore

    log("file_index_str", file_index_str)

    if file_index_str is not None:
        # Parameter was found, try to parse it
        try:
            target_index = int(file_index_str)
        except ValueError:
            log(f"Invalid file_index parameter value: '{file_index_str}'")
            return Response(
                body="Invalid file_index parameter value", status=HTTP_BAD_REQUEST
            )
    else:
        # Parameter was not found, fetch the latest log index (no warning needed)
        try:
            target_index = get_latest_log_index()
        except Exception as e:
            log(f"Error getting latest log index: {e}")
            return Response(
                body="Server error getting latest log index", status=HTTP_INTERNAL_ERROR
            )

    log(f"Request for log chunk, target index: {target_index}")

    if target_index < 0:
        log(f"No log files found or invalid index requested ({target_index}).")
        return Response(
            body="", status=HTTP_NOT_FOUND, headers={"X-Log-File-Index": "-1"}
        )

    try:
        log("read_log_file_content1")
        log_content = read_log_file_content(target_index)
        log("read_log_file_content2")

        if log_content is None:
            log(f"Log file index {target_index} not found.")
            return Response(
                body="",
                status=HTTP_NOT_FOUND,
                headers={"X-Log-File-Index": str(target_index)},
            )

        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "X-Log-File-Index": str(target_index),
        }
        gc.collect()
        # Ensure log_content is string before passing to Response with text/plain
        if isinstance(log_content, bytes):
            try:
                log_content_str = log_content.decode("utf-8")
            except UnicodeError:
                log(
                    f"Warning: Log content for index {target_index} contains non-UTF8 data. Sending as lossy string."
                )
                log_content_str = log_content.decode(
                    "utf-8", "replace"
                )  # Replace invalid chars
        elif not isinstance(log_content, str):
            log_content_str = str(log_content)  # Fallback conversion for other types
        else:
            log_content_str = log_content  # Already a string

        return Response(body=log_content_str, headers=headers)

    except Exception as e:
        log(f"Error reading log content for index {target_index}: {e}")
        return Response(
            body=f"Error reading log content: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/log/clear", methods=["POST"])
def clear_log_files(request):
    try:
        if clear_logs():
            log("Log files cleared successfully via endpoint.")
            return Response(body="All log files cleared successfully.", status=HTTP_OK)
        else:
            log("Log clearing function reported an error.")
            return Response(
                body="Error occurred during log clearing.", status=HTTP_INTERNAL_ERROR
            )
    except Exception as e:
        log(f"Unexpected error in /log/clear endpoint: {e}")
        return Response(
            body=f"Unexpected error clearing log files: {e}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/log/add-test-entries", methods=["POST"])
def add_test_log_entries(request):
    try:
        count = 200
        log(f"Adding {count} test log entries...")
        for i in range(count):
            log(f"Test log entry {i+1}/{count}")
            # time.sleep_ms(1) # Optional delay
        log(f"Finished adding {count} test log entries.")
        return Response(
            body=f"Successfully added {count} test log entries.", status=HTTP_OK
        )
    except Exception as e:
        log(f"Error adding test log entries: {e}")
        return Response(
            body=f"Error adding test log entries: {e}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/")
def index(request: Request):
    host = request.headers.get("Host", "")
    log(f"Root Request: {request.method} {request.path} Host: {host}")

    # Simplified check for captive portal based on Microdot example
    # This might need adjustment based on specific device/client behavior
    is_captive_trigger = (
        "captive.apple.com" in host or "connectivitycheck" in request.path
    )

    if is_captive_trigger:
        log(
            f"Detected potential captive portal trigger. Host: {host}, Path: {request.path}"
        )
        # Redirect to settings page, assuming device IP is 192.168.4.1 in AP mode
        # Or use the actual device IP if known and in STA mode
        device_ip = get_ip() or "192.168.4.1"  # Fallback IP
        settings_url = f"http://{device_ip}/settings"
        log(f"Redirecting captive portal request to {settings_url}")
        return Response.redirect(settings_url)  # Use the redirect helper

    # Default action for root: redirect to settings
    return Response.redirect("/settings")


# --- Register component routes ---
from captive import register_captive_portal_routes

register_captive_portal_routes(app)
register_buzzer_routes(app)


# --- End Added Routes ---


def start_server():
    _thread.start_new_thread(lambda: app.run(port=80), ())
    log("Web server started")
