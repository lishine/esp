# ESP32 File Upload Debugging Plan

## Issue Description

The file upload functionality is failing with the following symptoms:

- When trying to upload a small file (`up.txt`) using `upload_chunked.sh`
- The script correctly detects the small file size and uses the simplified upload method
- The curl command runs but returns "Error uploading file"
- Most importantly, the upload route handler doesn't appear to be logging any activity

The specific curl command that's failing is:

```bash
curl -s -X POST \
  -H "X-Chunk-Index: 0" \
  -H "X-Total-Chunks: 1" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@${FILE_PATH}" \
  "$UPLOAD_URL"
```

## Debugging Approach

We need to add detailed logging at key points in the request handling flow to trace exactly what's happening when the upload request comes in:

### 1. Enhance Request Parsing in server.py

The issue likely involves either the request not reaching the server, not being properly parsed, or not being routed correctly to the upload handler.

```python
# In server.py, modify the parse_request method:
def parse_request(self, client_socket, client_addr):
    try:
        # Log the start of request parsing
        log(f"Request parsing started from {client_addr[0]}")

        # Receive request line and headers
        request_data = b""
        while b"\r\n\r\n" not in request_data:
            chunk = client_socket.recv(1024)
            if not chunk:
                log("No data received from client or connection closed")
                break
            request_data += chunk
            log(f"Received chunk, total bytes: {len(request_data)}")

        if not request_data:
            log("Empty request received")
            return None

        # Split headers from body
        header_end = request_data.find(b"\r\n\r\n")
        headers_data = request_data[:header_end].decode("utf-8")
        log(f"Headers received: {headers_data}")

        # Parse request line
        request_line, *header_lines = headers_data.split("\r\n")
        log(f"Request line: {request_line}")
        method, path, _ = request_line.split(" ", 2)
        log(f"Method: {method}, Path: {path}")

        # Parse headers
        headers = {}
        for line in header_lines:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()
        log(f"Parsed headers: {headers}")

        # Get content length
        content_length = int(headers.get("Content-Length", "0"))
        log(f"Content-Length: {content_length}")

        # Read body if needed
        body = request_data[header_end + 4 :]
        log(f"Initial body bytes received: {len(body)}")

        # If we need more data for the body
        while len(body) < content_length:
            log(f"Need more body data: {len(body)}/{content_length}")
            chunk = client_socket.recv(1024)
            if not chunk:
                log("Connection closed while reading body")
                break
            body += chunk
            log(f"Received body chunk, total now: {len(body)}")

        log(f"Final body size: {len(body)}")
        request = Request(method, path, headers, body)
        request.client_addr = client_addr
        return request
    except Exception as e:
        log(f"Error parsing request: {e}")
        import sys
        sys.print_exception(e)  # More detailed exception info
        return None
```

### 2. Enhance Route Matching in server.py

```python
# In server.py, modify the handle_client method:
def handle_client(self, client_socket, addr):
    try:
        log(f"Handling client connection from {addr[0]}")
        request = self.parse_request(client_socket, addr)
        if not request:
            log("No valid request parsed")
            return

        # Run before_request handlers
        log("Running before_request handlers")
        for handler in self.before_request_handlers:
            result = handler(request)
            if result:
                log("before_request handler returned a response, sending it")
                response = result
                self.send_response(client_socket, response)
                return

        # Initialize response variable
        response = None

        # Check for exact route match
        log(f"Looking for exact route match for: {request.method} {request.path}")
        handler_info = self.routes.get(request.path)

        if handler_info and request.method in handler_info["methods"]:
            log(f"Found exact route match: {request.path}")
            # Call the handler
            result = handler_info["handler"](request)
            # Process the result...
        else:
            log(f"No exact route match, checking prefix routes")
            # Check for prefix routes (e.g., /upload/)
            found = False
            for route, route_info in self.routes.items():
                log(f"Checking if {request.path} matches prefix route {route}")
                if (
                    route.endswith("/")
                    and request.path.startswith(route)
                    and request.method in route_info["methods"]
                ):
                    log(f"Found prefix route match: {route}")
                    try:
                        log(f"Calling handler for {route}")
                        result = route_info["handler"](request)
                        found = True
                        # Process the result...
                        break
                    except Exception as e:
                        log(f"Error in route handler: {e}")
                        import sys
                        sys.print_exception(e)  # More detailed exception info
                        response = Response(
                            body=f"Error: {str(e)}", status=HTTP_INTERNAL_ERROR
                        )
                        found = True
                        break

            if not found:
                log(f"No route found for {request.method} {request.path}")
                response = Response(body="Not Found", status=HTTP_NOT_FOUND)

        # Rest of the method...
```

### 3. Add Logging to Upload Handlers

```python
# In server.py, modify upload handlers:

@app.route("/upload", methods=["POST"])
def upload_file_direct(request):
    log("Direct upload request received (no trailing slash)")
    log(f"Request headers: {request.headers}")
    log(f"Request body size: {len(request.body)} bytes")
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
        log("Calling handle_upload from upload_file_direct")
        result = handle_upload(request, filename)
        log(f"Direct upload result: {result}")
        return result
    except Exception as e:
        log(f"Direct upload error: {str(e)}")
        import sys
        sys.print_exception(e)  # More detailed exception info
        return json.dumps({"success": False, "error": str(e)}), 500


@app.route("/upload/", methods=["POST"])
def upload_file(request):
    # Extract target_path from the actual path
    target_path = request.path[len("/upload/") :]

    log(f"Upload request received for path: {target_path}")
    log(f"Request headers: {request.headers}")
    log(f"Request body size: {len(request.body)} bytes")

    if not target_path:
        log("No target path specified")
        return json.dumps({"success": False, "error": "No target path specified"}), 400

    try:
        log(f"Calling handle_upload from upload_file with target_path={target_path}")
        result = handle_upload(request, target_path)
        log(f"Upload result: {result}")
        return result
    except Exception as e:
        log(f"Upload error: {str(e)}")
        import sys
        sys.print_exception(e)  # More detailed exception info
        return json.dumps({"success": False, "error": str(e)}), 500
```

### 4. Add Logging to upload_sync.py

```python
# In upload_sync.py, enhance the handle_upload function:
def handle_upload(request, target_path=None):
    """Handle file uploads, including chunked uploads"""
    try:
        log(f"handle_upload called with target_path: {target_path}")
        log(f"Request method: {request.method}")
        log(f"Request headers: {request.headers}")
        log(f"Request body size: {len(request.body)} bytes")

        # Check if this is a chunked upload
        chunk_index = request.headers.get("X-Chunk-Index")
        total_chunks = request.headers.get("X-Total-Chunks")
        is_complete = request.headers.get("X-Is-Complete") == "true"
        log(f"Upload parameters: chunk_index={chunk_index}, total_chunks={total_chunks}, is_complete={is_complete}")

        # Check for direct binary upload (small files)
        content_type = request.headers.get("Content-Type", "").lower()
        log(f"Content-Type: {content_type}")

        if (
            content_type == "application/octet-stream"
            and chunk_index is not None
            and total_chunks is not None
            and int(total_chunks) == 1
        ):
            log(f"Single chunk binary upload detected for {target_path}")

            # Rest of the function...
```

## Testing Steps

1. Make the above changes to add detailed logging
2. Reset the ESP32 device
3. Run the upload script to attempt uploading the file:
   ```
   ./upload_chunked.sh up.txt
   ```
4. Check the logs using:
   ```
   curl http://192.168.1.102/log
   ```
5. Look for:
   - Evidence that the request is reaching the server
   - Whether it's being correctly parsed
   - If it's reaching the correct route handler
   - Any exceptions or errors in the upload process

## Potential Issues and Solutions

1. **Missing Route Registration**: If the logs show the request is received but no route is matched, verify the route registrations.

2. **HTTP Parsing Issues**: If the logs show incomplete or corrupt HTTP parsing, investigate chunked or malformed request issues.

3. **Content-Type Handling**: If the logs show the content type check is failing, ensure the headers are being sent and received correctly.

4. **Request Size Limits**: If large files upload but small ones fail, there could be minimum size requirements or buffering issues.

5. **Header Case Sensitivity**: Check if headers like X-Chunk-Index are being compared in a case-sensitive way when they shouldn't be.

6. **Binary Data Handling**: Ensure binary data is being correctly read and written without text encoding/decoding issues.

## Implementation Strategy

After identifying the specific issue through enhanced logging, we can:

1. Fix the exact problem point
2. Add appropriate error handling to make the upload process more robust
3. Add permanent logging to help diagnose any future issues
4. Add validation to ensure all required parameters are present

Once the changes are implemented and debugged, we'll need to switch to Code mode to actually make the code modifications.
