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

    # Handle domain paths that might be sent
    @app.route("/hotspot-detect.html")
    def apple_domain_captive_portal_detector(request):
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
    @app.route("/captive.apple.com")
    @app.route("/www.apple.com")
    @app.route("/www.itools.info")
    @app.route("/www.ibook.info")
    def captive_apple_detector(request):
        # For domain-specific requests, ensure we're handling captive.apple.com properly
        return Response.redirect("/settings")
