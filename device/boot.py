import sys
from log import log
import wifi
import ap
import server

log("\n" + "=" * 40)
log("ESP32 Device Starting...")
log("=" * 40)

try:
    ap.start_ap(essid="DDDEV", password="")
    wifi.start_wifi()
    server.start_server()
    log(
        f"""
Device is ready:
- AP mode: http://{ap.get_ap_ip()} (SSID: DDDEV)
- Station mode: http://{wifi.get_ip()} (if connected)
        """
    )

except Exception as e:
    log("Error during initialization:", e)
    sys.print_exception(e)
