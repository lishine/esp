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
    read_file,
    write_file,
    exists,
    remove_if_empty_or_file,
    remove_empty_parents,
)

# Create app with standard Microdot
app = Microdot()


# Upload routes - only support path-based uploads
@app.route("/upload/<path:target_path>", methods=["POST"])
async def upload_file(request, target_path):
    return await handle_upload(request, target_path)


@app.route("/verify/<path:filename>")
def verify_upload(request, filename):
    """Verify an uploaded file exists and return its size"""
    try:
        if not exists(filename):
            return Response(
                json.dumps({"success": False, "error": "File not found"}), 404
            )

        # Get file size
        size = os.stat(filename)[6]  # st_size
        return Response(
            json.dumps({"success": True, "filename": filename, "size": size}), 200
        )
    except OSError as e:
        log(f"Error verifying file: {e}")
        return Response(json.dumps({"success": False, "error": str(e)}), 500)


@app.route("/reset", methods=["POST"])
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


@app.route("/list")
def list_files(request):
    files = get_file_list()
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
    html_content = read_file("settings.html")
    if html_content is None:
        return "Settings file not found", 404

    context = {
        "is_connected": str(is_connected()),
        "ip_address": get_ip(),
        "ssid": wifi_config.get("ssid", ""),
    }

    rendered_html = render_template(html_content, **context)

    return Response(body=rendered_html, headers={"Content-Type": "text/html"})


@app.route("/rm/<path:target_path>")
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


@app.route("/settings", methods=["POST"])
def save_settings(request):
    config = request.json
    save_wifi_config(config)
    _thread.start_new_thread(wifi_connect_thread, ())

    return json.dumps({"success": True, "message": "Settings saved"})


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
    return Response(status_code=302, headers={"Location": "/settings"})


# Captive portal detection endpoints for various operating systems
@app.route("/generate_204")
@app.route("/connecttest.txt")
@app.route("/ncsi.txt")
def captive_portal_detector(request):
    # Redirect to settings page
    return Response(status_code=302, headers={"Location": "/settings"})


# Apple-specific captive portal detection endpoints
@app.route("/hotspot-detect.html")
@app.route("/library/test/success.html")
@app.route("/success.txt")
def apple_captive_portal_detector(request):
    # For macOS captive portal detection, we need to return a non-success response
    # that doesn't contain the string "<SUCCESS>" to trigger the captive portal window
    if request.path.endswith(".txt"):
        # For .txt files, return a non-success response
        return Response(body="Not Success", headers={"Content-Type": "text/plain"})
    else:
        # For HTML files, return a minimal HTML that doesn't contain "<SUCCESS>"
        # but includes a redirect to our settings page
        apple_response = """
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Captive Portal</title>
    <meta http-equiv="refresh" content="0;url=/settings">
</head>
<body>
    <h1>Please wait...</h1>
    <p>You are being redirected to the ESP32 settings page.</p>
    <script>
        // Redirect immediately to settings page
        window.location.href = "/settings";
    </script>
</body>
</html>
"""
        return Response(body=apple_response, headers={"Content-Type": "text/html"})


# Handle full domain paths that macOS might send
@app.route("/<path:domain>/hotspot-detect.html")
@app.route("/<path:domain>/library/test/success.html")
def apple_domain_captive_portal_detector(request, domain):
    # Return a non-success response to trigger the captive portal
    apple_response = """
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Captive Portal</title>
    <meta http-equiv="refresh" content="0;url=/settings">
</head>
<body>
    <h1>Please wait...</h1>
    <p>You are being redirected to the ESP32 settings page.</p>
    <script>
        // Redirect immediately to settings page
        window.location.href = "/settings";
    </script>
</body>
</html>
"""
    return Response(body=apple_response, headers={"Content-Type": "text/html"})


# Special handlers for specific Apple domains
@app.route("/captive.apple.com/hotspot-detect.html")
@app.route("/www.apple.com/library/test/success.html")
@app.route("/www.itools.info/library/test/success.html")
@app.route("/www.ibook.info/library/test/success.html")
def captive_apple_detector(request):
    # For domain-specific requests, ensure we're handling captive.apple.com properly
    apple_response = """
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Captive Portal</title>
    <meta http-equiv="refresh" content="0;url=/settings">
</head>
<body>
    <h1>Please wait...</h1>
    <p>You are being redirected to the ESP32 settings page.</p>
    <script>
        // Redirect immediately to settings page
        window.location.href = "/settings";
    </script>
</body>
</html>
"""
    return Response(body=apple_response, headers={"Content-Type": "text/html"})


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


# Helper functions for request information
def get_client_ip(request):
    return (
        request.client_addr[0]
        if hasattr(request, "client_addr") and request.client_addr
        else "unknown"
    )


def get_device_info(request):
    """Extract device information from User-Agent header"""
    user_agent = request.headers.get("User-Agent", "unknown")

    # Identify device type based on User-Agent
    device_type = "Unknown"

    if "iPhone" in user_agent or "iPad" in user_agent:
        device_type = "iOS"
    elif "Mac OS X" in user_agent:
        device_type = "macOS"
    elif "Android" in user_agent:
        device_type = "Android"
    elif "Windows" in user_agent:
        device_type = "Windows"
    elif "Linux" in user_agent:
        device_type = "Linux"

    # Extract browser information
    browser = "Unknown"
    if (
        "Safari" in user_agent
        and "Chrome" not in user_agent
        and "Edge" not in user_agent
    ):
        browser = "Safari"
    elif "Chrome" in user_agent and "Edge" not in user_agent:
        browser = "Chrome"
    elif "Firefox" in user_agent:
        browser = "Firefox"
    elif "Edge" in user_agent:
        browser = "Edge"

    return f"{device_type} ({browser})"


def start_server():
    _thread.start_new_thread(lambda: app.run(port=80), ())
    log("Web server started")
