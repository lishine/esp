import _thread
import socket
from log import log
from netutils import get_client_ip, get_device_info
import json

# HTTP status codes
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_INTERNAL_ERROR = 500


def error_response(message, status=400):
    return json.dumps({"success": False, "error": message}), status


def success_response(data=None):
    if data is None:
        data = {}
    result = {"success": True}
    result.update(data)
    return json.dumps(result), 200


class Request:
    def __init__(self, method, path, query_string, query_params, headers, body=None):
        self.method = method
        self.path = path  # Path part only
        self.query_string = query_string
        self.query_params = query_params
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


class HTTPServer:
    def __init__(self, port=80):
        self.port = port
        self.routes = {}
        self.before_request_handlers = []

    def route(self, path, methods=None):
        if methods is None:
            methods = ["GET"]

        def decorator(handler):
            # The wrapper no longer needs to parse query params,
            # as it's done in parse_request now.
            # It just calls the original handler.
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
            method, full_path, _ = request_line.split(" ", 2)

            # Split path and query string
            path_parts = full_path.split("?", 1)
            path = path_parts[0]
            query_string = path_parts[1] if len(path_parts) > 1 else ""

            # Parse query parameters
            query_params = {}
            if query_string:
                try:
                    for param in query_string.split("&"):
                        if not param:
                            continue
                        if "=" in param:
                            key, value = param.split("=", 1)
                            # Simple URL decoding
                            key = key.replace("+", " ")
                            value = value.replace("+", " ")
                            # Basic percent decoding (add more if needed)
                            for hex_seq in [
                                "%20",
                                "%21",
                                "%22",
                                "%23",
                                "%24",
                                "%25",
                                "%26",
                                "%27",
                                "%28",
                                "%29",
                            ]:
                                if hex_seq in key:
                                    key = key.replace(
                                        hex_seq, chr(int(hex_seq[1:], 16))
                                    )
                                if hex_seq in value:
                                    value = value.replace(
                                        hex_seq, chr(int(hex_seq[1:], 16))
                                    )
                            query_params[key] = value
                        else:
                            query_params[param] = True  # Flag parameters
                except Exception as e:
                    log(f"Error parsing query parameters in parse_request: {str(e)}")

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

            request = Request(method, path, query_string, query_params, headers, body)
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
            elif isinstance(response.body, bytes):
                response_body = response.body
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "application/octet-stream"
            else:  # Handle other types like JSON results converted to string
                response_body = str(response.body).encode("utf-8")
                if "Content-Type" not in headers:
                    headers["Content-Type"] = "text/plain; charset=utf-8"

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


app = HTTPServer()


# Register a before_request handler for logging
@app.before_request
def log_request(request):
    """Log all incoming requests with device information"""
    client_ip = get_client_ip(request)
    device_info = get_device_info(request)
    if not "live" in request.path:
        log(
            f"Request to {request.method} {request.path} from IP: {client_ip}, Device: {device_info}"
        )
