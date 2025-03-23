# ESP32 Captive Portal Fix Implementation Plan

## Problem Summary

When connecting a MacBook to the ESP32's "DDDEV" WiFi network, the captive portal popup doesn't automatically appear. Users have to manually navigate to 192.168.4.1 in their browser to access the settings page.

## Root Causes

After analyzing the code, the following issues were identified:

1. **Duplicate Route Handlers**: The `captive.py` file has duplicate route handlers for `/hotspot-detect.html` (at lines 16 and 48), causing conflicts in how requests are processed.

2. **Immediate Redirects**: The current implementation uses both meta refresh and JavaScript to immediately redirect to the `/settings` page:

   ```html
   <meta http-equiv="refresh" content="0;url=/settings" />
   <script>
     window.location.href = "/settings";
   </script>
   ```

   These immediate redirects confuse macOS's captive portal detection mechanism.

3. **Improper Response Format**: macOS expects a specific response format for captive portal detection, and the current implementation isn't properly triggering the system.

## How Captive Portal Detection Works on macOS

1. When a macOS device connects to a WiFi network, it sends HTTP requests to specific Apple domains (e.g., `captive.apple.com/hotspot-detect.html`).

2. If the response matches the expected "Success" page (`<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>`), macOS assumes internet connectivity exists and doesn't show a captive portal.

3. If the response doesn't match but returns a different HTML page, macOS displays that page in a captive portal popup.

4. Immediate redirects can confuse this mechanism by not providing a stable response.

## Code Changes Required

The following changes to `device/captive.py` are required:

```python
from server import Response


# Captive portal detection endpoints for various operating systems
def register_captive_portal_routes(app):
    """Register all captive portal related routes with the provided app"""

    @app.route("/generate_204")
    @app.route("/connecttest.txt")
    @app.route("/ncsi.txt")
    def captive_portal_detector(request):
        # Redirect to settings page
        return Response.redirect("/settings")

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
            # For HTML files, return a static page without redirects
            # This will trigger the captive portal popup properly
            apple_response = """
<!DOCTYPE html>
<html>
<head>
    <title>Network Login Required</title>
</head>
<body>
    <h1>Network Login Required</h1>
    <p>Click the button below to access the network.</p>
    <p><a href="/settings" style="display: inline-block; background-color: #4CAF50; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Login to Network</a></p>
</body>
</html>
"""
            return Response(body=apple_response, headers={"Content-Type": "text/html"})

    # Special handlers for specific Apple domains
    @app.route("/captive.apple.com")
    @app.route("/www.apple.com")
    @app.route("/www.itools.info")
    @app.route("/www.ibook.info")
    def captive_apple_detector(request):
        # For domain-specific requests, return the same static page as above instead of a redirect
        apple_response = """
<!DOCTYPE html>
<html>
<head>
    <title>Network Login Required</title>
</head>
<body>
    <h1>Network Login Required</h1>
    <p>Click the button below to access the network.</p>
    <p><a href="/settings" style="display: inline-block; background-color: #4CAF50; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Login to Network</a></p>
</body>
</html>
"""
        return Response(body=apple_response, headers={"Content-Type": "text/html"})
```

### Key Changes:

1. **Removed Duplicate Route Handler**: Eliminated the second `/hotspot-detect.html` route handler (previously at line 48).

2. **Removed Auto-Redirects**: Replaced the HTML with automatic redirects with a static HTML page that contains only a manual link to the settings page.

3. **Consistent Response Format**: Used the same static HTML response for both the main Apple captive portal detection endpoints and the domain-specific handlers to ensure consistent behavior.

## Implementation and Testing Process

1. Switch to Code mode to make the changes to `device/captive.py`
2. Use the `run` script to upload the modified file to the ESP32:
   ```bash
   ./run upload device/captive.py
   ```
3. Reset the ESP32 to apply the changes:
   ```bash
   ./run reset
   ```
4. Test by:
   - Disconnecting the MacBook from any WiFi networks
   - Connecting to the "DDDEV" WiFi network
   - Observing if the captive portal popup appears automatically
   - Verifying the portal shows the "Network Login Required" page
   - Testing that the "Login to Network" button navigates to the settings page

## Expected Outcome

- The MacBook should display a captive portal popup immediately upon connecting to the "DDDEV" WiFi network
- The popup should show the "Network Login Required" page with a green button
- Clicking the button should take the user to the ESP32 settings page
