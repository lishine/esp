from microdot import Microdot, Response
import json
import _thread
import json
import machine

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

app = Microdot()


@app.route("/reset")
def reset(request):
    import _thread
    import time

    def delayed_reset():
        time.sleep(0.1)  # Very short delay to allow response to be sent
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
    log("in list")
    files = get_file_list()
    return "\n".join(files)


@app.route("/view/<path:filename>")
def view_file(request, filename):
    content = read_file(filename)
    if content is None:
        return "File not found", 404
    return content


def render_template(template_content, **context):
    """Replace {{variable}} patterns in the template with values from context"""
    for key, value in context.items():
        template_content = template_content.replace("{{" + key + "}}", str(value))
    return template_content


@app.route("/settings", methods=["GET"])
def get_settings(request):
    # Read the HTML file content using your fs module
    html_content = read_file("settings.html")
    if html_content is None:
        return "Settings file not found", 404

    # Get current WiFi status for template
    context = {
        "is_connected": str(is_connected()),
        "ip_address": get_ip(),
        "ssid": wifi_config.get("ssid", ""),
    }

    # Process template
    rendered_html = render_template(html_content, **context)

    # Return as response
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
    config = request.json  # Use json instead of form
    save_wifi_config(config)
    # Start a new thread to connect to wifi with new settings
    _thread.start_new_thread(wifi_connect_thread, ())

    return json.dumps({"success": True, "message": "Settings saved"})


@app.route("/log")
def show_log(request):
    return "\n".join(log_buffer.get_all())


@app.route("/upload/<path:target_path>", methods=["POST"])
async def upload_file(request, target_path):
    try:
        log(-1)
        log("target_path", target_path)

        size = int(request.headers.get("Content-Length", 0))
        if size == 0:
            log(0)
            return "Empty file", 400

        raw_content = await request.stream.read(size)

        boundary = b"--" + raw_content.split(b"\r\n")[0][2:]
        parts = raw_content.split(boundary)

        # Find the part containing the actual file content
        file_content = b""
        for part in parts:
            if b'filename="' in part:
                # Split headers from content
                headers, content = part.split(b"\r\n\r\n", 1)
                # Remove trailing boundary and whitespace
                file_content = content.rstrip(b"\r\n--")
                break

        if not file_content:
            log(1)
            return "No file content found", 400

        if write_file(target_path, file_content):
            return json.dumps(
                {"success": True, "path": target_path, "size": len(file_content)}
            )
        return "Failed to write file", 500

    except Exception as e:
        log(f"Upload error: {e}")
        return f"Upload failed: {e}", 500


def start_server():
    """Start the web server in a separate thread"""
    _thread.start_new_thread(lambda: app.run(port=80), ())
    log("Web server started")
