from server_framework import Response
from log import log


# Captive portal detection endpoints for various operating systems
def register_captive_portal_routes(app):
    """Register captive portal routes with improved handling"""

    # Add our root handler for all incoming requests
    @app.route("/", methods=["GET"])
    def root_handler(request):
        # Get the Host header from the request
        host = request.headers.get("Host", "")

        # Log all requests with their Host header for debugging
        log(f"Captive Portal Request: {request.method} {request.path} Host: {host}")

        # Check if this is an Apple-related domain
        apple_domains = [
            "captive.apple.com",
            "www.apple.com",
            "apple.com",
            "gsp-ssl.ls.apple.com",
            "gspe1-ssl.ls.apple.com",
            "courier.push.apple.com",
            "push.apple.com",
        ]

        is_apple_domain = any(domain in host for domain in apple_domains)

        # If this is an Apple domain or specific captive portal path, return the captive portal page
        if is_apple_domain or request.path in [
            "/hotspot-detect.html",
            "/library/test/success.html",
            "/success.txt",
            "/generate_204",
            "/connecttest.txt",
            "/ncsi.txt",
        ]:
            # Return a non-Success response to trigger captive portal
            captive_response = """
<!DOCTYPE html>
<html>
<head>
    <title>Network Login Required</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
</head>
<body>
    <h1>Network Login Required</h1>
    <p>Click the button below to access the network.</p>
    <p><a href="http://192.168.4.1/settings" style="display: inline-block; background-color: #4CAF50; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Login to Network</a></p>
</body>
</html>
"""
            return Response(
                body=captive_response,
                headers={
                    "Content-Type": "text/html",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )

        # If it's a specific settings or API path, let it pass through to be handled by other routes
        if request.path.startswith("/settings") or request.path.startswith("/api/"):
            return None  # Let other routes handle these paths

        # For all other requests, redirect to settings
        return Response.redirect("/settings")

    # Keep specific routes for common captive portal detection endpoints
    # These are backups in case the root handler doesn't catch them

    @app.route("/hotspot-detect.html")
    @app.route("/library/test/success.html")
    @app.route("/success.txt")
    @app.route("/generate_204")
    @app.route("/connecttest.txt")
    @app.route("/ncsi.txt")
    def specific_captive_portal_detector(request):
        log(
            f"Specific captive portal endpoint: {request.path} Host: {request.headers.get('Host', '')}"
        )

        if request.path.endswith(".txt"):
            return Response(
                body="Not Success",
                headers={
                    "Content-Type": "text/plain",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        else:
            captive_response = """
<!DOCTYPE html>
<html>
<head>
    <title>Network Login Required</title>
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
</head>
<body>
    <h1>Network Login Required</h1>
    <p>Click the button below to access the network.</p>
    <p><a href="http://192.168.4.1/settings" style="display: inline-block; background-color: #4CAF50; color: white; padding: 10px 15px; text-decoration: none; border-radius: 4px;">Login to Network</a></p>
</body>
</html>
"""
            return Response(
                body=captive_response,
                headers={
                    "Content-Type": "text/html",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
