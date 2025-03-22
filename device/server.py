import json
import _thread
import machine
import os
import socket
import io

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
from upload_sync import handle_upload
from netutils import get_client_ip, get_device_info

# HTTP status codes
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_INTERNAL_ERROR = 500


class Request:
    def __init__(self, method, path, headers, body=None):
        self.method = method
        self.path = path
        self.headers = headers
        self.body = body
        self.client_addr = None  # Will be set by the server


class Response:
    def __init__(self, body="", status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}

    @classmethod
    def redirect(cls, location, status=302):
        return cls(body="", status=status, headers={"Location": location})


def render_template(template_content, **context):
    try:
        for key, value in context.items():
            template_content = template_content.replace("{{" + key + "}}", str(value))
        return template_content
    except Exception as e:
        log(f"Error rendering template: {e}")
        return f"Error rendering template: {str(e)}"


class HTTPServer:
    def __init__(self, port=80):
        self.port = port
        self.routes = {}
        self.before_request_handlers = []

    def route(self, path, methods=None):
        if methods is None:
            methods = ["GET"]

        def decorator(handler):
            self.routes[path] = {"handler": handler, "methods": methods}
            return handler

        return decorator

    def before_request(self, handler):
        self.before_request_handlers.append(handler)
        return handler

    def parse_request(self, client_socket, client_addr):
        try:
            # Receive request line and headers
            request_data = b""
            while b"\r\n\r\n" not in request_data:
                chunk = client_socket.recv(1024)
                if not chunk:
                    break
                request_data += chunk

            if not request_data:
                return None

            # Split headers from body
            header_end = request_data.find(b"\r\n\r\n")
            headers_data = request_data[:header_end].decode("utf-8")

            # Parse request line
            request_line, *header_lines = headers_data.split("\r\n")
            method, path, _ = request_line.split(" ", 2)

            # Parse headers
            headers = {}
            for line in header_lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip()] = value.strip()

            # Get content length
            content_length = int(headers.get("Content-Length", "0"))

            # Read body if needed
            body = request_data[header_end + 4 :]

            # If we need more data for the body
            while len(body) < content_length:
                chunk = client_socket.recv(1024)
                if not chunk:
                    break
                body += chunk

            request = Request(method, path, headers, body)
            request.client_addr = client_addr
            return request
        except Exception as e:
            log(f"Error parsing request: {e}")
            return None

    def send_response(self, client_socket, response):
        try:
            status_text = {
                200: "OK",
                302: "Found",
                400: "Bad Request",
                404: "Not Found",
                500: "Internal Server Error",
            }.get(response.status, "Unknown")

            # Prepare headers
            headers = response.headers.copy()

            # Convert body to bytes if it's a string
            if isinstance(response.body, str):
                response_body = response.body.encode("utf-8")
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "text/html; charset=utf-8"
            else:
                response_body = response.body
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/octet-stream"

            # Add Content-Length header
            headers["Content-Length"] = str(len(response_body))

            # Prepare response line and headers
            response_line = f"HTTP/1.1 {response.status} {status_text}\r\n"
            header_lines = "".join(
                f"{key}: {value}\r\n" for key, value in headers.items()
            )

            # Send response line and headers
            client_socket.send(response_line.encode("utf-8"))
            client_socket.send(header_lines.encode("utf-8"))
            client_socket.send(b"\r\n")

            # Send body
            client_socket.send(response_body)
        except Exception as e:
            log(f"Error sending response: {e}")

    def handle_client(self, client_socket, addr):
        try:
            request = self.parse_request(client_socket, addr)
            if not request:
                return

            # Run before_request handlers
            for handler in self.before_request_handlers:
                result = handler(request)
                if result:
                    response = result
                    self.send_response(client_socket, response)
                    return

            # Initialize response variable
            response = None

            # Check for exact route match
            handler_info = self.routes.get(request.path)

            if handler_info and request.method in handler_info["methods"]:
                # Call the handler
                result = handler_info["handler"](request)

                # Process the result
                if isinstance(result, Response):
                    response = result
                elif isinstance(result, tuple) and len(result) == 2:
                    body, status = result
                    response = Response(body=str(body), status=status)
                else:
                    response = Response(body=str(result) if result is not None else "")
            else:
                # Check for prefix routes (e.g., /upload/)
                found = False
                for route, route_info in self.routes.items():
                    if (
                        route.endswith("/")
                        and request.path.startswith(route)
                        and request.method in route_info["methods"]
                    ):
                        try:
                            result = route_info["handler"](request)
                            found = True

                            # Process the result
                            if isinstance(result, Response):
                                response = result
                            elif isinstance(result, tuple) and len(result) == 2:
                                body, status = result
                                response = Response(body=str(body), status=status)
                            else:
                                response = Response(
                                    body=str(result) if result is not None else ""
                                )
                            break
                        except Exception as e:
                            log(f"Error in route handler: {e}")
                            response = Response(
                                body=f"Error: {str(e)}", status=HTTP_INTERNAL_ERROR
                            )
                            found = True
                            break

                if not found:
                    response = Response(body="Not Found", status=HTTP_NOT_FOUND)

            # Ensure we have a valid response
            if response is None:
                response = Response(
                    body="Internal Server Error", status=HTTP_INTERNAL_ERROR
                )

            self.send_response(client_socket, response)
        except Exception as e:
            log(f"Error handling client: {e}")
            try:
                error_response = Response(
                    body=f"Internal Server Error: {str(e)}", status=HTTP_INTERNAL_ERROR
                )
                self.send_response(client_socket, error_response)
            except:
                pass
        finally:
            try:
                client_socket.close()
            except:
                pass

    def run(self, port=None):
        if port is not None:
            self.port = port

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            server_socket.bind(("0.0.0.0", self.port))
            server_socket.listen(5)
            log(f"Server started on port {self.port}")

            while True:
                client_socket, addr = server_socket.accept()
                try:
                    _thread.start_new_thread(self.handle_client, (client_socket, addr))
                except:
                    try:
                        client_socket.close()
                    except:
                        pass
        except Exception as e:
            log(f"Server error: {e}")
        finally:
            server_socket.close()


# Create app with standard HTTP server
app = HTTPServer()


# Register a before_request handler for logging
@app.before_request
def log_request(request):
    """Log all incoming requests with device information"""
    client_ip = get_client_ip(request)
    device_info = get_device_info(request)
    log(
        f"Request to {request.method} {request.path} from IP: {client_ip}, Device: {device_info}"
    )


# Captive portal routes are now in captive.py
# Uncomment the following lines to enable captive portal
# from captive import register_captive_portal_routes
# register_captive_portal_routes(app)


# Debug route to check if server is responding
@app.route("/ping")
def ping(request):
    return json.dumps({"success": True, "message": "Server is running"})


# Direct upload route (without path parameter)
@app.route("/upload", methods=["POST"])
def upload_file_direct(request):
    log("Direct upload request received (no trailing slash)")
    # Forward to the main upload handler with a default filename
    try:
        # Use the filename from Content-Disposition header if available
        filename = None
        content_disposition = request.headers.get("Content-Disposition", "")
        if "filename=" in content_disposition:
            filename = content_disposition.split("filename=")[1].strip("\"'")

        # Default filename if none provided
        if not filename:
            filename = "uploaded_file"

        log(f"Using filename: {filename}")
        result = handle_upload(request, filename)
        log(f"Direct upload result: {result}")
        return result
    except Exception as e:
        log(f"Direct upload error: {str(e)}")
        return json.dumps({"success": False, "error": str(e)}), 500


# Upload route with path parameter
@app.route("/upload/", methods=["POST"])
def upload_file(request):
    # Extract target_path from the actual path
    target_path = request.path[len("/upload/") :]

    log(f"Upload request received for path: {target_path}")

    if not target_path:
        log("No target path specified")
        return json.dumps({"success": False, "error": "No target path specified"}), 400

    try:
        result = handle_upload(request, target_path)
        log(f"Upload result: {result}")
        return result
    except Exception as e:
        log(f"Upload error: {str(e)}")
        return json.dumps({"success": False, "error": str(e)}), 500


@app.route("/reset", methods=["GET", "POST"])
def reset(request):
    import _thread
    import time

    def delayed_reset():
        time.sleep(0.1)
        machine.reset()

    _thread.start_new_thread(delayed_reset, ())
    return "Device resetting..."


@app.route("/download/", methods=["GET"])
def download(request):
    # Extract filename from the path
    filename = request.path[len("/download/") :]

    if not filename:
        return "No filename specified", 400

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


@app.route("/view/", methods=["GET"])
def view_file(request):
    # Extract filename from the path
    filename = request.path[len("/view/") :]

    if not filename:
        return "No filename specified", 400

    content = read_file(filename)
    if content is None:
        return "File not found", 404

    return content


@app.route("/settings", methods=["GET"])
def get_settings(request):
    try:
        log(1)
        html_content = read_file("settings.html")
        log(2)
        if html_content is None:
            return "Settings file not found", 404
        log(3)
        context = {
            "is_connected": str(is_connected()),
            "ip_address": get_ip(),
            "ssid": wifi_config.get("ssid", ""),
        }
        log(4)
        rendered_html = render_template(html_content, **context)
        log(5)
        return Response(body=rendered_html, headers={"Content-Type": "text/html"})
    except Exception as e:
        log(f"Error in settings page: {e}")
        return f"Error loading settings page: {str(e)}", 500


@app.route("/settings/save", methods=["POST"])
def save_settings(request):
    config = json.loads(request.body.decode())
    save_wifi_config(config)
    _thread.start_new_thread(wifi_connect_thread, ())

    return json.dumps({"success": True, "message": "Settings saved"})


#     return json.dumps({"success": True, "message": "Settings saved"})


@app.route("/rm/", methods=["GET"])
def remove_file(request):
    # Extract target_path from the path
    target_path = request.path[len("/rm/") :]

    if not target_path:
        return "No path specified", 400

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


def start_server():
    _thread.start_new_thread(lambda: app.run(port=80), ())
    log("Web server started")
