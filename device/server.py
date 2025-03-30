from microdot import Microdot, Response
import json

import uasyncio as asyncio
import machine
import uos
import gc
from upload import handle_upload

from log import log, read_log_file_content, get_latest_log_index, clear_logs
from wifi import (
    is_connected,
    get_ip,
    save_wifi_config,
    wifi_config,
    get_current_network,
)
from fs import (
    get_hierarchical_list_with_sizes,
    get_hierarchical_json,
    exists,
    remove_if_empty_or_file,
    remove_empty_parents,
)
from captive import register_captive_portal_routes

# Import network utilities
from netutils import get_client_ip, get_device_info

# Create app with standard Microdot
app = Microdot()

# Register captive portal routes
register_captive_portal_routes(app)


# Upload routes - only support path-based uploads
@app.route("/upload/<path:target_path>", methods=["POST"])
async def upload_file(request, target_path):
    return await handle_upload(request, target_path)


@app.route("/reset", methods=["GET", "POST"])
async def reset(request):  # Changed to async def

    async def delayed_reset_async():  # Changed to async def
        await asyncio.sleep(0.1)  # Use asyncio.sleep
        machine.reset()

    asyncio.create_task(delayed_reset_async())  # Use asyncio.create_task
    return "Device resetting..."


@app.route("/download/<path:filename>")
def download(request, filename):
    if not exists(filename):
        return "File not found", 404

    def generate_content():
        with open(filename, "rb") as f:
            while True:
                chunk = f.read(4096)  # 4KB chunks
                if not chunk:
                    break
                yield chunk

    return Response(
        body=generate_content(),  # type: ignore
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/octet-stream",
        },
    )


@app.route("/la")
def list_files_hierarchical(request):
    """List files in a hierarchical format with sizes"""
    files = get_hierarchical_list_with_sizes()
    return "\n".join(files)


@app.route("/fs-list")
def list_files_json(request):
    """List files in a hierarchical JSON format"""
    files = get_hierarchical_json()
    return Response(
        body=json.dumps(files), headers={"Content-Type": "application/json"}
    )


@app.route("/view/<path:filename>")
def view_file(request, filename):
    if not exists(filename):
        return "File not found", 404

    def generate_content():
        with open(filename, "rb") as f:
            while True:
                chunk = f.read(4096)  # 4KB chunks
                if not chunk:
                    break
                yield chunk

    return Response(body=generate_content())  # type: ignore


@app.route("/settings", methods=["GET"])
def get_settings(request):
    def generate_html():
        chunk_size = 4096
        try:
            with open("settings.html", "r") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except OSError:
            yield "Settings file not found"

    return Response(body=generate_html(), headers={"Content-Type": "text/html"})  # type: ignore


@app.route("/api/settings/data")
def get_settings_data(request):
    current_network = get_current_network()
    return Response(
        body=json.dumps(
            {
                "is_connected": is_connected(),
                "ip_address": get_ip(),
                "current_ssid": current_network["ssid"] if current_network else "",
                "networks": wifi_config.get(
                    "networks",
                    [{"ssid": "", "password": ""}, {"ssid": "", "password": ""}],
                ),
            }
        ),
        headers={"Content-Type": "application/json"},
    )


# Import the async version of the wifi connect function (assuming it will be created)


@app.route("/settings/save", methods=["POST"])
async def save_settings(request):  # Changed to async def
    config = request.json
    if not config:
        return "Invalid JSON data", 400

    save_wifi_config(config)  # This remains synchronous

    # Start the wifi connection attempt as an asyncio task
    # Make sure wifi_connect_task is defined as async def in wifi.py
    # asyncio.create_task(wifi_connect_task())

    return json.dumps({"success": True, "message": "Settings saved"})


@app.route("/rm/<path:target_path>", methods=["DELETE"])
def remove_file(request, target_path):
    try:
        if not exists(target_path):
            return f"File or directory not found: {target_path}", 404

        if not remove_if_empty_or_file(target_path):
            return (
                f"Failed to remove {target_path} (might be a non-empty directory)",
                400,
            )

        remove_empty_parents(target_path)

        return f"Successfully removed {target_path}"
    except Exception as e:
        log(f"Error in remove endpoint: {e}")
        return f"Error: {str(e)}", 500


@app.route("/ping")
def ping(request):
    """Simple ping endpoint to check if the server is running"""
    return json.dumps({"status": "ok"})


@app.route("/status")
def status(request):
    """Return device status including WiFi IP if connected"""
    response = {"status": "ok"}
    if is_connected():
        response["wifi_ip"] = get_ip()
    return json.dumps(response)


@app.route("/free")
def get_free_space(request):
    """Return free space information about the filesystem"""
    try:

        fs_stat = uos.statvfs("/")
        # Calculate free space in KB
        free_kb = (fs_stat[0] * fs_stat[3]) / 1024
        # Calculate total space in KB
        total_kb = (fs_stat[0] * fs_stat[2]) / 1024
        # Calculate used space in KB
        used_kb = total_kb - free_kb
        # Calculate usage percentage
        usage_percent = (used_kb / total_kb) * 100 if total_kb > 0 else 0

        return json.dumps(
            {
                "free_kb": round(free_kb, 2),
                "total_kb": round(total_kb, 2),
                "used_kb": round(used_kb, 2),
                "usage_percent": round(usage_percent, 2),
            }
        )
    except Exception as e:
        log(f"Error getting free space: {e}")
        return f"Error: {str(e)}", 500


@app.route("/log/infinite")
def log_viewer(request):
    """Serves the HTML page for the infinite scrolling log viewer."""

    # Serve the static HTML file. Assumes it exists at 'log_viewer.html'
    # Microdot doesn't have a built-in static file server, so we read and return it.
    # Use a generator for potentially large files, though this HTML should be small.
    def generate_html():
        try:
            with open("log_viewer.html", "r") as f:
                while True:
                    chunk = f.read(1024)  # Read in 1KB chunks
                    if not chunk:
                        break
                    yield chunk
        except OSError:
            yield "<html><body><h1>Error</h1><p>Log viewer HTML file not found.</p></body></html>"

    return Response(body=generate_html(), headers={"Content-Type": "text/html"})  # type: ignore


# --- Updated /api/log/chunk route ---
@app.route("/api/log/chunk")
def api_log_chunk_file(request):
    """
    API endpoint to fetch a specific log file's content based on its index.
    If no index is provided, fetches the latest log file.
    """
    target_index = -1
    try:
        # Get optional file_index from query parameters
        file_index_str = request.args.get("file_index")
        if file_index_str is not None:
            target_index = int(file_index_str)
            # print(f"Requested log file index: {target_index}") # Debug
        else:
            # No index provided, get the latest one
            target_index = get_latest_log_index()
            # print(f"No index requested, fetching latest: {target_index}") # Debug
            # If get_latest_log_index returns 0 and no files exist, read will return None below.

    except ValueError:
        log(f"Invalid file_index parameter: {request.args.get('file_index')}")
        return "Invalid file_index parameter", 400
    except Exception as e:
        log(f"Error determining target log index: {e}")
        return "Server error determining log index", 500

    if target_index < 0:
        # This case handles when get_latest_log_index finds no files (-1) or invalid input
        log(f"No log files found or invalid index requested ({target_index}).")
        # Return 404 with the index -1 so client knows there are no logs
        # Use empty string "" for text/plain body
        return Response(body="", status_code=404, headers={"X-Log-File-Index": "-1"})

    # Fetch the content of the target log file
    log_content = read_log_file_content(target_index)

    if log_content is None:
        # Handle file not found (e.g., requested index doesn't exist)
        log(f"Log file index {target_index} not found.")
        # Return 404 but include the requested index for client context
        # Use empty string "" for text/plain body
        return Response(
            body="", status_code=404, headers={"X-Log-File-Index": str(target_index)}
        )

    # Send log content back
    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "X-Log-File-Index": str(target_index),  # Let client know which file this is
    }
    gc.collect()  # Good idea before sending potentially large response body
    return Response(body=log_content, headers=headers)


@app.route("/log/clear", methods=["POST"])
def clear_log_files(request):
    """Clears all log files in the log directory."""
    try:
        if clear_logs():  # Call the new function from log.py
            log("Log files cleared successfully via endpoint.")
            return "All log files cleared successfully.", 200
        else:
            log("Log clearing function reported an error.")
            return "Error occurred during log clearing.", 500
    except Exception as e:
        log(f"Unexpected error in /log/clear endpoint: {e}")
        return f"Unexpected error clearing log files: {e}", 500


@app.route("/log/add-test-entries", methods=["POST"])
def add_test_log_entries(request):
    """Adds 200 test log entries."""
    try:
        count = 200  # Changed from 1000
        log(f"Adding {count} test log entries...")
        for i in range(count):
            log(f"Test log entry {i+1}/{count}")
            # Optional small delay to prevent overwhelming the system if needed
            # import time
            # time.sleep_ms(1)
        log(f"Finished adding {count} test log entries.")
        return f"Successfully added {count} test log entries.", 200
    except Exception as e:
        log(f"Error adding test log entries: {e}")
        return f"Error adding test log entries: {e}", 500


@app.route("/")
def index(request):
    # Get the Host header from the request
    host = request.headers.get("Host", "")

    # Log all requests with their Host header for debugging
    log(f"Root Request: {request.method} {request.path} Host: {host}")

    # Check if this is an Apple-related domain
    apple_domains = [
        "captive.apple.com",
        "www.apple.com",
        "apple.com",
        "gsp-ssl.ls.apple.com",
        "gspe1-ssl.ls.apple.com",
        "courier.push.apple.com",
        "push.apple.com",
    ]

    is_apple_domain = any(domain in host for domain in apple_domains)

    # If this is an Apple domain, return the captive portal page
    if is_apple_domain:
        log(f"Detected Apple domain in Host header: {host}")
        # Return a non-Success response to trigger captive portal
        captive_response = """
<!DOCTYPE html>
<html>
<head>
    <title>Network Login Required</title>
</head>
<body>
    <h1>Network Login Required</h1>
    <p>Click the button below to access the network.</p>
    <p><a href="http://192.168.4.1/settings" style="display: inline-block; background-color: #4CAF50; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Login to Network</a></p>
</body>
</html>
"""
        return Response(body=captive_response, headers={"Content-Type": "text/html"})

    # For all other requests to the root, redirect to settings
    return Response(status_code=302, headers={"Location": "/settings"})


# Pre-route hook for request logging
@app.before_request
def before_request(request):
    """Log all incoming requests with device information"""
    # Skip logging for certain paths if needed
    # if request.path in ['/some/path/to/skip']:
    #    return

    client_ip = get_client_ip(request)
    device_info = get_device_info(request)
    log(
        f"Request to {request.method} {request.path} from IP: {client_ip}, Device: {device_info}"
    )


# This function now returns the configured app instance.
# The server will be started asynchronously in the main script.
def get_app():
    log("Microdot app configured")
    return app


# Remove the old start_server function entirely
# def start_server():
#     _thread.start_new_thread(lambda: app.run(port=80), ())
#     log("Web server started")
