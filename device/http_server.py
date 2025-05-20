import json
import _thread
import machine
import os
import gc
import esp
import esp32  # Added for heap info
import sys

import log

from wifi import (
    is_connected,
    get_ip,
    get_current_network,
)
import settings_manager

from fs import (
    get_hierarchical_list_with_sizes,
    get_hierarchical_json,
    exists,
    remove_if_empty_or_file,
    remove_empty_parents,
    is_dir,  # Added for /la-data
)
from globals import SD_MOUNT_POINT  # Import from globals
from netutils import get_client_ip, get_device_info
from upload import handle_upload

import io_local.gps_config as gps_config
from io_local.buzzer import register_buzzer_routes

from io_local import adc as adc_module  # Import the ADC module (device/ is root)
from io_local import ds18b20 as ds18b20_module  # Import the DS18B20 module
from io_local import fan
from io_local.data_log import get_current_data_log_file_path  # For /api/data

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
        log.log(f"Unhandled error during upload processing for {target_path}: {e}")
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
def list_files_hierarchical(request: Request):
    try:
        folder_path = request.query_params.get("folder")
        log.log(f"/la requested. Folder path: {folder_path}")

        if folder_path:
            if not folder_path.startswith("/"):
                folder_path = "/" + folder_path

            files = get_hierarchical_list_with_sizes(path=folder_path)
        else:
            files = get_hierarchical_list_with_sizes()

        return Response(
            body="\n".join(files), headers={"Content-Type": "text/plain; charset=utf-8"}
        )
    except Exception as e:
        log.log(
            f"Error listing files for /la (folder: {request.query_params.get('folder')}): {e}"
        )
        return Response(
            body=f"Error listing files: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/view/", methods=["GET"])
def view_file(request: Request):
    log.log("ENTER /view/ handler")
    filename = None
    route_prefix = "/view/"
    if request.path.startswith(route_prefix):
        filename = request.path[len(route_prefix) :]
    log.log(
        f"/view/ requested. Raw path: {request.path}, extracted filename: '{filename}'"
    )

    if not filename:
        log.log("/view/: Missing filename in URL")
        return Response(body="Missing filename in URL", status=HTTP_BAD_REQUEST)

    file_exists = exists(filename)
    log.log(f"/view/: exists('{filename}') = {file_exists}")
    if not file_exists:
        return Response(body=f"File not found: {filename}", status=HTTP_NOT_FOUND)

    try:
        # Log file size before reading
        try:
            stat = os.stat(filename)
            log.log(f"/view/: File '{filename}' size: {stat[6]} bytes")
        except Exception as stat_e:
            log.log(f"/view/: Could not stat file '{filename}': {stat_e}")

        # Read the entire file content (buffered)
        with open(filename, "rb") as f:
            content = f.read()
        log.log(f"/view/: Read {len(content)} bytes from '{filename}'")

        log.log(
            f"/view/: Returning response with {len(content)} bytes for '{filename}'"
        )
        return Response(body=content, status=HTTP_OK, headers={"Content-Type": ""})
    except Exception as e:
        import sys

        log.log(f"Error reading file for view {filename}: {e} ")
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
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log.log(f"Error reading {settings_file}: {e}")
        return Response(
            body=f"Error reading settings page: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/settings/save", methods=["POST"])
def save_settings(request: Request):
    """Saves WiFi configuration received as JSON."""
    try:
        config_data = json.loads(request.body)  # Renamed to avoid confusion
        if (
            not isinstance(config_data, dict)
            or "networks" not in config_data
            or not isinstance(config_data["networks"], list)
        ):
            log.log(f"Invalid settings save format: {config_data}")
            raise ValueError("Invalid JSON data format: Expected {'networks': [...]} ")

        # Assuming config_data is {"networks": [{"ssid": "...", "password": "..."}, ...]}
        # settings_manager.set_wifi_networks expects just the list.
        if not settings_manager.set_wifi_networks(config_data["networks"]):
            log.log("Failed to save wifi settings via settings_manager")
            raise Exception("Failed to save WiFi settings")

        return Response(
            body=json.dumps({"success": True, "message": "Settings saved"}),
            status=HTTP_OK,
            headers={"Content-Type": "application/json"},
        )

    except ValueError as e:
        log.log(f"Error parsing JSON for settings save: {e}")
        return Response(
            body=json.dumps({"success": False, "error": f"Invalid JSON data: {e}"}),
            status=HTTP_BAD_REQUEST,
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        log.log(f"Error saving wifi config: {e}")
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

        log.log(f"Attempting to remove: {target_path}")
        if not remove_if_empty_or_file(target_path):
            return Response(
                body=f"Failed to remove '{target_path}'. It might be a non-empty directory.",
                status=HTTP_BAD_REQUEST,
            )

        remove_empty_parents(target_path)

        log.log(f"Successfully removed {target_path}")
        return Response(body=f"Successfully removed {target_path}", status=HTTP_OK)

    except Exception as e:
        log.log(f"Error in remove endpoint for {target_path}: {e}")
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
        flash_total_bytes = esp.flash_size() or 0
        flash_total_mb = flash_total_bytes / (1024 * 1024)

        # Implementation details
        impl_name = getattr(sys.implementation, "name", "N/A")  # Safer access
        impl_version = f"{sys.implementation.version[0]}.{sys.implementation.version[1]}.{sys.implementation.version[2]}"  # type: ignore # Pylance might not know .version from stubs
        impl_machine = getattr(
            sys.implementation, "_machine", "N/A"
        )  # getattr is safer for optional attributes

        # --- Memory Heap Info ---
        idf_total_free = 0
        idf_max_block = 0
        idf_regions = 0
        upy_free = 0
        try:
            # Get IDF Heap Info
            heap_info = esp32.idf_heap_info(
                esp32.HEAP_DATA
            )  # List of (total, free, largest_free, min_free)
            idf_regions = len(heap_info)
            for heap in heap_info:
                idf_total_free += heap[1]
                if heap[2] > idf_max_block:
                    idf_max_block = heap[2]

            # Get MicroPython Heap Info
            upy_free = gc.mem_free()
        except Exception as heap_err:
            log.log(f"Error getting memory info within /free: {heap_err}")

        # --- Format values for output ---
        fs_free_mb = free_kb / 1024
        fs_total_mb = total_kb / 1024
        fs_used_mb = used_kb / 1024
        idf_total_free_mb = idf_total_free / (1024 * 1024)
        idf_max_alloc_mb = idf_max_block / (1024 * 1024)
        upy_free_mb = upy_free / (1024 * 1024)

        data = {
            "fs_free": f"{fs_free_mb:.2f} MB",
            "fs_total": f"{fs_total_mb:.2f} MB",
            "fs_used": f"{fs_used_mb:.2f} MB",
            "fs_usage": f"{usage_percent:.2f}%",
            "flash_total": f"{flash_total_mb:.2f} MB",
            "implementation": {
                "name": impl_name,
                "version": impl_version,
                "_machine": impl_machine,
            },
            "memory": {
                "idf_total_free": f"{idf_total_free_mb:.2f} MB",
                "idf_max_alloc": f"{idf_max_alloc_mb:.2f} MB",
                "idf_regions": idf_regions,
                "upy_free": f"{upy_free_mb:.2f} MB",
            },
        }
        return Response(
            body=json.dumps(data),  # ujson doesn't support indent
            headers={"Content-Type": "application/json"},
        )

    except Exception as e:
        log.log(f"Error getting free space: {e}")
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
        log.log(f"Error getting file list JSON: {e}")
        return Response(
            body=f"Error getting file list: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/api/settings/data")
def get_settings_data(request):
    try:
        current_network = get_current_network()
        # Load the config using settings_manager
        networks_list = settings_manager.get_wifi_networks()
        if (
            not networks_list
        ):  # Provide a default if empty, similar to old load_wifi_config
            networks_list = [{"ssid": "", "password": ""}, {"ssid": "", "password": ""}]

        data = {
            "is_connected": is_connected(),
            "ip_address": get_ip(),
            "current_ssid": current_network["ssid"] if current_network else "",
            "networks": networks_list,  # Directly use the list from settings_manager
        }
        return Response(
            body=json.dumps(data), headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        log.log(f"Error getting settings data: {e}")
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
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log.log(f"Error reading {gps_settings_file}: {e}")
        return Response(
            body=f"Error reading GPS settings page: {str(e)}",
            status=HTTP_INTERNAL_ERROR,
        )


@app.route("/api/gps-settings/data", methods=["POST"])
def handle_gps_settings_data_route(request: Request):
    try:
        return gps_config.handle_gps_settings_data(request)
    except Exception as e:
        log.log(f"Error processing GPS settings data: {e}")
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
        return Response(
            body=json.dumps(response_data), headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        log.log(f"Error getting device status: {e}")
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
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except OSError as e:
        if e.args[0] == 2:  # ENOENT - File not found
            log.log(f"Live data HTML file not found: {live_data_html_path}")
            return Response(body="Live Data page not found.", status=HTTP_NOT_FOUND)
        else:
            log.log(f"Error accessing {live_data_html_path}: {e}")
            return Response(
                body=f"Error accessing Live Data page: {str(e)}",
                status=HTTP_INTERNAL_ERROR,
            )
    except Exception as e:
        log.log(f"Error reading {live_data_html_path}: {e}")
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

        ds18_roms = ds18b20_module.get_ds18b20_roms()
        ds18_temps = ds18b20_module.get_ds18b20_temperatures()
        ds18_count = len(ds18_roms)
        ds18_sensors_data = []
        for i, rom in enumerate(ds18_roms):
            rom_hex = "".join("{:02x}".format(x) for x in rom)
            temp_c = ds18_temps[i] if i < len(ds18_temps) else None  # Safety check
            ds18_sensors_data.append({"rom": rom_hex, "temp_c": temp_c})
        response_data = {
            "adc_voltage_uv_2pt": voltage_uv,  # From read_uv with 2-point factor
            "adc_voltage_u16_linear": voltage_u16,  # From read_u16 with linear factor
            "ds18b20": {"count": ds18_count, "sensors": ds18_sensors_data},
        }
        # Could add other live data sources here in the future

        return Response(
            body=json.dumps(response_data),
            status=HTTP_OK,
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        log.log(f"Error getting live data for API: {e}")
        # Use the framework's error response helper if available, otherwise construct manually
        body, status = error_response(
            f"Error getting live data: {str(e)}", HTTP_INTERNAL_ERROR
        )
        return Response(
            body=body, status=status, headers={"Content-Type": "application/json"}
        )


@app.route("/api/data", methods=["POST"])
def api_get_data_log_file(request: Request):
    """
    Returns the content of the current JSONL data log file.
    The request body is ignored in this version but may be used for future enhancements
    (e.g., specifying date ranges or specific filenames).
    """
    try:
        current_file_path = get_current_data_log_file_path()

        # Removed explicit check for file existence as per feedback.
        # open() will raise OSError if file not found or path is None.

        if (
            not current_file_path
        ):  # Still check if path itself is None (e.g. data_log init failed)
            return Response(
                body=json.dumps(
                    {"success": False, "error": "Data log path not configured."}
                ),
                status=HTTP_INTERNAL_ERROR,  # Or HTTP_NOT_FOUND, depending on desired semantics
                headers={"Content-Type": "application/json"},
            )

        # Read the entire file content. For very large files, chunked transfer would be better.
        with open(current_file_path, "rb") as f:  # Read as binary
            content = f.read()

        filename_only = current_file_path.split("/")[-1]

        return Response(
            body=content,
            status=HTTP_OK,
            headers={
                "Content-Type": "application/jsonl",  # Standard MIME type for JSON Lines
                "Content-Disposition": f'attachment; filename="{filename_only}"',
            },
        )
    except Exception as e:
        log.log(
            f"Error in POST /api/data: {e}"
        )  # Ensure 'log' is available (it is, from top of file)
        return Response(
            body=json.dumps({"success": False, "error": f"Server error: {str(e)}"}),
            status=HTTP_INTERNAL_ERROR,
            headers={"Content-Type": "application/json"},
        )


@app.route("/log/infinite")
def log_viewer(request):
    """Serves the HTML page for the infinite scrolling log viewer."""
    log_viewer_file = "log_viewer.html"
    if not exists(log_viewer_file):
        return Response(body="Log viewer page not found.", status=HTTP_NOT_FOUND)
    try:
        with open(log_viewer_file, "r") as f:
            content = f.read()
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log.log(f"Error reading {log_viewer_file}: {e}")
        return Response(
            body=f"Error reading log viewer page: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/api/log/chunk")
def api_log_chunk_file(request: Request):
    current_log_file = log.get_current_log_filename()

    if not current_log_file:
        log.log("No current log file available.")
        return Response(
            body="", status=HTTP_NOT_FOUND, headers={"X-Log-File-Name": "None"}
        )

    log.log(f"Request for log chunk, target file: {current_log_file}")

    try:
        with open(current_log_file, "rb") as f:
            log_content_bytes = f.read()

        # Send raw bytes
        headers = {
            "Content-Type": "application/octet-stream",  # Indicate binary data
            "X-Log-File-Name": current_log_file.split("/")[-1],
            "Content-Disposition": f'attachment; filename="{current_log_file.split("/")[-1]}"',  # Suggest download
        }

        return Response(body=log_content_bytes, headers=headers)

    except OSError as e:
        if e.args[0] == 2:  # ENOENT - File not found
            log.log(f"Log file not found: {current_log_file}")
            return Response(
                body="",
                status=HTTP_NOT_FOUND,
                headers={"X-Log-File-Name": current_log_file.split("/")[-1]},
            )
        else:
            log.log(f"OSError reading log file {current_log_file}: {e}")
            return Response(
                body=f"Error reading log file: {str(e)}", status=HTTP_INTERNAL_ERROR
            )
    except Exception as e:
        log.log(f"Error reading log content for {current_log_file}: {e}")
        return Response(
            body=f"Error reading log content: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/log/clear", methods=["POST"])
def clear_log_files(request):
    try:
        if log.clear_logs():
            log.log("Log files cleared successfully via endpoint.")
            return Response(body="All log files cleared successfully.", status=HTTP_OK)
        else:
            log.log("Log clearing function reported an error.")
            return Response(
                body="Error occurred during log clearing.", status=HTTP_INTERNAL_ERROR
            )
    except Exception as e:
        log.log(f"Unexpected error in /log/clear endpoint: {e}")
        return Response(
            body=f"Unexpected error clearing log files: {e}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/data/clear", methods=["POST"])
def clear_data_log_files(request):
    try:
        # Import clear_data_logs locally to avoid circular import at module level if data_log imports http_server
        from io_local.data_log import clear_data_logs

        if clear_data_logs():
            log.log("Data log files cleared successfully via endpoint.")
            return Response(
                body="All data log files cleared successfully.", status=HTTP_OK
            )
        else:
            log.log("Data log clearing function reported an error.")
            return Response(
                body="Error occurred during data log clearing.",
                status=HTTP_INTERNAL_ERROR,
            )
    except Exception as e:
        log.log(f"Unexpected error in /data/clear endpoint: {e}")
        return Response(
            body=f"Unexpected error clearing data log files: {e}",
            status=HTTP_INTERNAL_ERROR,
        )


@app.route("/log/add-test-entries", methods=["POST"])
def add_test_log_entries(request):
    try:
        count = 200000
        log.log(f"Adding {count} test log entries...")
        for i in range(count):
            log.log(f"Test log entry {i+1}/{count}")
            # time.sleep_ms(1) # Optional delay
        log.log(f"Finished adding {count} test log entries.")
        return Response(
            body=f"Successfully added {count} test log entries.", status=HTTP_OK
        )
    except Exception as e:
        log.log(f"Error adding test log entries: {e}")
        return Response(
            body=f"Error adding test log entries: {e}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/")
def index(request: Request):
    host = request.headers.get("Host", "")
    log.log(f"Root Request: {request.method} {request.path} Host: {host}")

    # Simplified check for captive portal based on Microdot example
    # This might need adjustment based on specific device/client behavior
    # is_captive_trigger = (
    #     "captive.apple.com" in host or "connectivitycheck" in request.path
    # )

    # if is_captive_trigger:
    #     log.log(
    #         f"Detected potential captive portal trigger. Host: {host}, Path: {request.path}"
    #     )
    #     # Redirect to settings page, assuming device IP is 192.168.4.1 in AP mode
    #     # Or use the actual device IP if known and in STA mode
    #     device_ip = get_ip() or "192.168.4.1"  # Fallback IP
    #     settings_url = f"http://{device_ip}/settings"
    #     log.log(f"Redirecting captive portal request to {settings_url}")
    #     return Response.redirect(settings_url)  # Use the redirect helper

    # Default action for root: redirect to settings
    return Response.redirect("/settings")


# from captive import register_captive_portal_routes

# register_captive_portal_routes(app)
register_buzzer_routes(app)


@app.route("/control", methods=["GET"])
def control_page(request: Request):
    try:
        with open("control.html", "r") as f:
            content = f.read()
        return Response(
            body=content,
            status=HTTP_OK,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
    except Exception as e:
        log.log(f"Error in /control: {e}")
        return Response(
            body=f"Error reading control page: {str(e)}", status=HTTP_INTERNAL_ERROR
        )


@app.route("/api/control", methods=["POST"])
def api_control(request: Request):
    try:
        data = json.loads(request.body)
        on = data.get("on")
        if not isinstance(on, bool):
            return Response(
                body=json.dumps(
                    {"success": False, "error": "Missing or invalid 'on' parameter"}
                ),
                status=HTTP_BAD_REQUEST,
                headers={"Content-Type": "application/json"},
            )
        fan.set_fan(on)
        return Response(
            body=json.dumps({"success": True, "fan_on": on}),
            status=HTTP_OK,
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        log.log(f"Error in /api/control: {e}")
        return Response(
            body=json.dumps({"success": False, "error": str(e)}),
            status=HTTP_INTERNAL_ERROR,
            headers={"Content-Type": "application/json"},
        )


def start_server():
    _thread.start_new_thread(lambda: app.run(port=80), ())
    log.log("Web server started")
