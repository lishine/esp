from microdot import Microdot, Response
import json
import _thread
import machine
from upload import handle_upload

from log import log, get_recent_logs
from wifi import (
    is_connected,
    get_ip,
    save_wifi_config,
    wifi_config,
    wifi_connect_thread,
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
def reset(request):
    import _thread
    import time

    def delayed_reset():
        time.sleep(0.1)
        machine.reset()

    _thread.start_new_thread(delayed_reset, ())
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


@app.route("/settings/save", methods=["POST"])
def save_settings(request):
    config = request.json
    save_wifi_config(config)
    _thread.start_new_thread(wifi_connect_thread, ())

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


@app.route("/log")
def show_log(request):
    # Use a smaller limit (e.g., 50) for better memory management on simple view
    # Return the generator directly for streaming response
    try:
        log_generator = get_recent_logs(limit=50)
        # Ensure generator is handled correctly by Response
        return Response(body=log_generator, headers={"Content-Type": "text/plain"})
    except Exception as e:
        log(f"Error creating log generator in /log route: {e}")
        return "Internal Server Error reading logs", 500


@app.route("/log/infinite")
def log_viewer(request):
    """Serve the HTML page for the infinite log viewer."""
    try:
        # Use send_file for potentially better memory management if available,
        # otherwise stream manually. Microdot might not have send_file.
        def generate_html():
            chunk_size = (
                1024  # Smaller chunks might be better for memory constrained devices
            )
            try:
                with open("log_viewer.html", "r") as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
            except OSError:
                yield "Log viewer HTML file not found."

        return Response(body=generate_html(), headers={"Content-Type": "text/html"})  # type: ignore
    except Exception as e:
        log(f"Error serving log_viewer.html: {e}")
        return "Error loading log viewer.", 500


@app.route("/api/log/chunk")
def api_log_chunk(request):
    """API endpoint to fetch log chunks with offset, limit, and timestamp filtering."""
    try:
        # Get query parameters, providing defaults and basic validation
        limit_str = request.args.get("limit", "50")  # Default to 50 lines
        offset_str = request.args.get("offset", "0")
        newer_than_str = request.args.get("newer_than_timestamp_ms")

        try:
            limit = int(limit_str)
            offset = int(offset_str)
        except ValueError:
            return "Invalid integer for limit or offset", 400

        # Cap limit to prevent excessive memory usage (e.g., max 100 lines per chunk)
        limit = max(0, min(limit, 100))
        offset = max(0, offset)  # Ensure offset is non-negative

        newer_than_timestamp_ms = None
        if newer_than_str:
            try:
                newer_than_timestamp_ms = int(newer_than_str)
            except ValueError:
                return "Invalid value for newer_than_timestamp_ms", 400

        # Get the generator
        log_lines_generator = get_recent_logs(
            limit=limit, offset=offset, newer_than_timestamp_ms=newer_than_timestamp_ms
        )

        # Return the generator directly for streaming response
        # Microdot handles iterating over the generator efficiently.
        # If the generator yields nothing, an empty 200 OK response is sent.
        return Response(
            body=log_lines_generator, headers={"Content-Type": "text/plain"}
        )

    except ValueError as e:
        # Handle specific errors like invalid int conversion
        log(f"Error in /api/log/chunk (Bad Request): {e}")
        return f"Bad Request: {e}", 400
    except Exception as e:
        # Log other unexpected errors for debugging on the device
        # Consider adding traceback logging if needed: import uio; import sys; s = uio.StringIO(); sys.print_exception(e, s); log(s.getvalue())
        log(f"Error in /api/log/chunk: {type(e).__name__} {e}")
        # Return a generic server error to the client
        return "Internal Server Error fetching log chunk", 500


@app.route("/free")
def get_free_space(request):
    """Return free space information about the filesystem"""
    try:
        import os

        fs_stat = os.statvfs("/")
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


# These functions are now imported from network.py


def start_server():
    _thread.start_new_thread(lambda: app.run(port=80), ())
    log("Web server started")
