# Code Reorganization Plan

## Task Requirements

1. Move all captive portal elements to `captive.py`
2. Move `get_client_ip` and `get_device_info` functions to `network-utils.py`
3. Remove the `verify_upload` route

## Implementation Details

### 1. Create `device/captive.py`

This file will contain all captive portal detection and handling routes from `server.py`:

```python
from microdot import Response

# Captive portal detection endpoints for various operating systems
def register_captive_portal_routes(app):
    """Register all captive portal related routes with the provided app"""

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
```

### 2. Create `device/network-utils.py`

This file will contain network utility functions:

```python
def get_client_ip(request):
    """Extract client IP address from request"""
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
```

### 3. Update `device/server.py`

The file needs to be updated to:

1. Import functions from the new modules
2. Remove the code moved to other files
3. Remove the `verify_upload` route
4. Register the captive portal routes

```python
# Add these imports at the top of the file
from captive import register_captive_portal_routes
from network_utils import get_client_ip, get_device_info

# Remove:
# - All captive portal routes (lines 184-275)
# - get_client_ip function (lines 294-299)
# - get_device_info function (lines 302-335)
# - verify_upload route (lines 36-52)

# Add this somewhere in the file, possibly after creating the app object
register_captive_portal_routes(app)
```

## Testing Strategy

After implementing these changes, the following should be tested:

1. Server startup - verify the server starts without errors
2. Captive portal functionality - ensure devices can connect and are redirected to the settings page
3. Upload functionality - confirm uploads work properly even without the verify_upload route

## File Changes Summary

1. **New Files to Create**:

   - `device/captive.py`
   - `device/network-utils.py`

2. **Files to Modify**:

   - `device/server.py` - remove specified code and add imports

3. **No Changes Required**:
   - All other files

## Next Steps

1. Switch to Code mode
2. Create `device/captive.py` and `device/network-utils.py` files
3. Update `device/server.py` to integrate the new modules
4. Test the changes
