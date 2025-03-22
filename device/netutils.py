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
