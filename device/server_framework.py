import _thread
import socket
from log import log
from netutils import get_client_ip, get_device_info
import json
import ssl  # Corrected from ussl

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

    def parse_request(self, client_socket, client_addr, is_ssl):  # Added is_ssl
        log(f"SF: ENTER parse_request for {client_addr} (SSL: {is_ssl})")
        try:
            # Receive request line and headers
            # Read headers line by line
            header_lines_bytes = []
            request_line_bytes = b""
            try:
                # Read the request line
                # readline should work for both plain and SSL sockets
                request_line_bytes = client_socket.readline()
                if not request_line_bytes:
                    return None

                # Read header lines
                while True:
                    # readline should work for both plain and SSL sockets
                    line = client_socket.readline()
                    if not line:  # Socket closed or error
                        return None  # Or raise an error
                    if line == b"\r\n":  # End of headers
                        break
                    header_lines_bytes.append(line)
            except Exception as e_read_headers:
                import sys

                sys.print_exception(e_read_headers)
                return None

            request_line_str = request_line_bytes.decode("utf-8").strip()
            method, full_path, http_version = request_line_str.split(" ", 2)
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
                    pass
            # Parse headers
            headers = {}
            for line_bytes in header_lines_bytes:
                line_str = line_bytes.decode("utf-8").strip()
                if ":" in line_str:
                    key, value = line_str.split(":", 1)
                    headers[key.strip()] = value.strip()

            content_length = int(headers.get("Content-Length", "0"))
            body = b""
            if content_length > 0:
                bytes_read = 0
                while bytes_read < content_length:
                    chunk = client_socket.read(min(content_length - bytes_read, 4096))
                    if not chunk:
                        break  # from while bytes_read < content_length
                    body += chunk
                    bytes_read += len(chunk)

            request = Request(method, path, query_string, query_params, headers, body)
            request.client_addr = client_addr
            return request
        except Exception as e:
            log(f"SF: Error parsing request: {e}. EXITING parse_request with None.")
            return None

    def send_response(self, client_socket, response, is_ssl):  # Added is_ssl
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
            if is_ssl:
                client_socket.write(response_line.encode("utf-8"))
                client_socket.write(header_lines.encode("utf-8"))
                client_socket.write(b"\r\n")
                if response_body:
                    client_socket.write(response_body)
            else:
                client_socket.send(response_line.encode("utf-8"))
                client_socket.send(header_lines.encode("utf-8"))
                client_socket.send(b"\r\n")
                if response_body:
                    client_socket.send(response_body)

        except Exception as e:
            log(f"Error sending response: {e}")
            import sys  # Ensure sys is imported for print_exception

            sys.print_exception(e)  # Add this for full traceback

    def handle_client(self, client_socket, addr, is_ssl):  # Added is_ssl
        try:
            request = self.parse_request(client_socket, addr, is_ssl)  # Pass is_ssl
            if request:
                pass
            else:  # request is None
                if client_socket:
                    client_socket.close()  # Ensure closed if parse failed early
                return

            # Run before_request handlers
            for br_handler in self.before_request_handlers:
                result = br_handler(request)
                if result and isinstance(
                    result, Response
                ):  # If a handler returns a Response
                    self.send_response(client_socket, result, is_ssl)  # Pass is_ssl
                    # client_socket is closed in send_response's finally or here if send_response fails
                    return

            response = None
            result = None  # Initialize result here to satisfy Pylance and ensure it's always defined
            handler_info = self.routes.get(request.path)

            if handler_info and request.method in handler_info["methods"]:
                try:
                    result = handler_info["handler"](request)
                except Exception as e_handler_exc:
                    import sys

                    sys.print_exception(e_handler_exc)
                    response = Response(
                        body=f"Error in handler: {str(e_handler_exc)}",
                        status=HTTP_INTERNAL_ERROR,
                    )
                    # Fall through to send this error response

                if response is None:  # if no exception in handler, process result
                    if isinstance(result, Response):
                        response = result
                    elif isinstance(result, tuple) and len(result) == 2:
                        body_content, status_code = (
                            result  # Renamed body to body_content
                        )
                        response = Response(body=str(body_content), status=status_code)
                    else:
                        response = Response(
                            body=str(result) if result is not None else ""
                        )
            else:
                # Check for prefix routes
                found_prefix = False
                for route_prefix_path, route_info_prefix in self.routes.items():
                    if (
                        route_prefix_path.endswith("/")
                        and request.path.startswith(route_prefix_path)
                        and request.method in route_info_prefix["methods"]
                    ):
                        try:
                            result = route_info_prefix["handler"](request)
                            found_prefix = True
                            if isinstance(result, Response):
                                response = result
                            elif isinstance(result, tuple) and len(result) == 2:
                                body, status_code = result
                                response = Response(body=str(body), status=status_code)
                            else:
                                response = Response(
                                    body=str(result) if result is not None else ""
                                )
                            break
                        except Exception as e_prefix_handler_exc:
                            import sys

                            sys.print_exception(e_prefix_handler_exc)
                            response = Response(
                                body=f"Error in prefix handler: {str(e_prefix_handler_exc)}",
                                status=HTTP_INTERNAL_ERROR,
                            )
                            found_prefix = True
                            break

                if not found_prefix:
                    response = Response(body="Not Found", status=HTTP_NOT_FOUND)

            if response is None:  # Should ideally be set by logic above
                response = Response(
                    body="Internal Server Error: Handler did not produce a response.",
                    status=HTTP_INTERNAL_ERROR,
                )

            self.send_response(client_socket, response, is_ssl)  # Pass is_ssl

        except Exception as e_handle_client:
            import sys

            sys.print_exception(e_handle_client)
            # Attempt to send a generic error response if possible and socket not already closed
            if client_socket and not getattr(
                client_socket, "_closed", True
            ):  # Check if socket might be open
                try:
                    error_resp_obj = Response(
                        body=f"Internal Server Error: {str(e_handle_client)}",
                        status=HTTP_INTERNAL_ERROR,
                    )
                    # Cannot call self.send_response here as it might recurse on error,
                    # and it was the source of the Pylance error "Argument missing for parameter 'is_ssl'".
                    # The minimal direct response logic below is already in place.
                    # This error_resp_obj was for a potential call to self.send_response(client_socket, error_resp_obj, is_ssl)
                    # which we are avoiding to prevent recursion.
                    pass  # Minimal direct response is handled below.

                    # Send a minimal direct response
                    err_send_data = b"HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/plain\r\nContent-Length: 21\r\nConnection: close\r\n\r\nInternal Server Error"
                    if is_ssl:  # Use write for SSL
                        if hasattr(client_socket, "write"):
                            client_socket.write(err_send_data)
                    else:  # Use send for plain HTTP
                        if hasattr(client_socket, "send"):
                            client_socket.send(err_send_data)
                except Exception as e_send_final_error:
                    log(
                        f"Failed to send final error response in handle_client for {addr} (SSL: {is_ssl}): {e_send_final_error}"
                    )
        finally:
            try:
                if client_socket:
                    client_socket.close()
            except Exception as e_final_close:
                pass

    def run(self, port=None, ssl_context=None):  # Added ssl_context parameter
        if port is not None:
            self.port = port

        server_type = "HTTPS" if ssl_context else "HTTP"
        log(f"Attempting to start {server_type} server on port {self.port}")

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            server_socket.bind(("0.0.0.0", self.port))
            server_socket.listen(5)  # Max 5 queued connections
            log(f"{server_type} server started on 0.0.0.0:{self.port}")

            while True:
                client_socket_orig, addr = server_socket.accept()
                # Log immediately after accept, before SSL wrap
                log(
                    f"{server_type} server: Accepted connection from {addr} on port {self.port}"
                )

                actual_client_socket = client_socket_orig
                if ssl_context:
                    try:
                        actual_client_socket = ssl_context.wrap_socket(
                            client_socket_orig, server_side=True
                        )
                        log(
                            f"{server_type} server: Socket successfully wrapped with SSL for {addr}"
                        )
                    except Exception as e_ssl_wrap:
                        log(
                            f"CRITICAL: Error wrapping socket with SSL for {addr}: {e_ssl_wrap}"
                        )
                        client_socket_orig.close()  # Close the original socket
                        continue  # Skip to next connection attempt

                try:
                    # Pass the (potentially SSL-wrapped) socket to handle_client, and is_ssl flag
                    _thread.start_new_thread(
                        self.handle_client,
                        (actual_client_socket, addr, bool(ssl_context)),
                    )
                except Exception as e_thread:
                    log(f"Error starting thread for client {addr}: {e_thread}")
                    try:
                        actual_client_socket.close()  # Close if thread failed to start
                    except:
                        pass  # Ignore errors on close
        except Exception as e_server:
            log(f"{server_type} server error on port {self.port}: {e_server}")
        finally:
            log(f"Closing {server_type} server socket on port {self.port}")
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
