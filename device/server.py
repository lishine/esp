from microdot import Microdot, Response
import json
import _thread
import machine
import os
from upload import handle_upload

from log import log, log_buffer
from wifi import (
    is_connected,
    get_ip,
    save_wifi_config,
    load_wifi_config,
    wifi_config,
    wifi_connect_thread,
)
from fs import (
    get_file_list,
    get_file_details,
    get_hierarchical_list_with_sizes,
    read_file,
    write_file,
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
    content = read_file(filename)
    if content is None:
        return "File not found", 404
    return Response(
        body=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/la")
def list_files_hierarchical(request):
    """List files in a hierarchical format with sizes"""
    files = get_hierarchical_list_with_sizes()
    return "\n".join(files)


@app.route("/view/<path:filename>")
def view_file(request, filename):
    content = read_file(filename)
    if content is None:
        return "File not found", 404
    return content


def render_template(template_content, **context):
    for key, value in context.items():
        template_content = template_content.replace("{{" + key + "}}", str(value))
    return template_content


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
    return Response(
        body=json.dumps(
            {
                "is_connected": is_connected(),
                "ip_address": get_ip(),
                "ssid": wifi_config.get("ssid", ""),
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


@app.route("/log")
def show_log(request):
    return "\n".join(log_buffer.get_all())


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
