# Quick Upload Debugging Guide

Based on the analysis of your ESP32 file upload issue, here's a focused plan to quickly add logging that will help identify why the upload route isn't being accessed.

## Minimal Implementation Changes

### 1. Add HTTP Request Logging in server.py

The most critical change is to add logging at the HTTP request parsing level to see if the request is reaching the server at all:

```python
# In server.py, modify the parse_request method:
def parse_request(self, client_socket, client_addr):
    try:
        # Log the start of request parsing
        log(f"DEBUG: Request parsing from {client_addr[0]}")

        # Receive request line and headers
        request_data = b""
        while b"\r\n\r\n" not in request_data:
            chunk = client_socket.recv(1024)
            if not chunk:
                log("DEBUG: No chunk data received")
                break
            request_data += chunk

        if not request_data:
            log("DEBUG: Empty request received")
            return None

        # Log the first line of the request to see the method and path
        try:
            first_line = request_data.split(b"\r\n")[0].decode('utf-8')
            log(f"DEBUG: Request first line: {first_line}")
        except:
            log("DEBUG: Could not decode first line")

        # Continue with normal processing...
```

### 2. Log Route Matching in handle_client

```python
# In server.py, add logging to handle_client:
def handle_client(self, client_socket, addr):
    try:
        log(f"DEBUG: Client connection from {addr[0]}")
        request = self.parse_request(client_socket, addr)
        if not request:
            log("DEBUG: No valid request parsed")
            return

        # Check for exact route match
        log(f"DEBUG: Looking for route match: {request.method} {request.path}")
        handler_info = self.routes.get(request.path)

        if handler_info and request.method in handler_info["methods"]:
            log(f"DEBUG: Found exact route match for {request.path}")
            # Continue with normal processing...
        else:
            # Check for prefix routes (e.g., /upload/)
            log(f"DEBUG: Checking prefix routes for {request.path}")
            for route, route_info in self.routes.items():
                if (
                    route.endswith("/")
                    and request.path.startswith(route)
                    and request.method in route_info["methods"]
                ):
                    log(f"DEBUG: Found prefix route match: {route}")
                    # Continue with normal processing...
```

### 3. Add Logging to Upload Handlers

```python
# In server.py, add immediate logging to upload route handlers:
@app.route("/upload", methods=["POST"])
def upload_file_direct(request):
    log("DEBUG: Direct upload route accessed (/upload)")
    log(f"DEBUG: Headers: {request.headers}")
    # Continue with normal processing...

@app.route("/upload/", methods=["POST"])
def upload_file(request):
    log("DEBUG: Path upload route accessed (/upload/)")
    target_path = request.path[len("/upload/") :]
    log(f"DEBUG: Target path: {target_path}")
    # Continue with normal processing...
```

### 4. Add Logging to upload_sync.py

```python
# At the top of handle_upload in upload_sync.py:
def handle_upload(request, target_path=None):
    """Handle file uploads, including chunked uploads"""
    try:
        log(f"DEBUG: handle_upload called with target: {target_path}")
        log(f"DEBUG: Content-Type: {request.headers.get('Content-Type', 'none')}")
        # Continue with normal processing...
```

## Testing Procedure

1. Make these minimal changes to add logging
2. Reset the ESP32 device
3. Run the upload script:
   ```
   ./upload_chunked.sh up.txt
   ```
4. Immediately check the logs:
   ```
   curl http://192.168.1.102/log
   ```

## Expected Results

The logs should show:

- If the HTTP request is reaching the server
- If the route matching is finding the upload route
- If the upload handler is being called

## Next Steps

Based on what the logs show:

1. **If no HTTP request log appears**: Check network connectivity and ensure the curl command is pointing to the correct IP address

2. **If HTTP request appears but no route match**: Check the URL formatting and route registration

3. **If route match appears but upload handler fails**: Check the upload handler logic

4. **If everything appears in logs but still fails**: Examine the specific error in the upload handling code

Once the issue is identified, we can switch to Code mode to implement a proper fix.
