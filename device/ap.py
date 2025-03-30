import _thread
import network

from log import log
from led import blink_sequence

ap = network.WLAN(network.AP_IF)


def start_ap(essid="DDDEV", password=""):
    """Start the access point with the given ESSID and password"""
    ap.active(True)
    ap.config(essid=essid, password=password)
    try:
        blink_sequence(count=2)
    except Exception as e:
        log(f"Error during AP start blink: {e}")
    log(f"AP mode activated: {essid}")
    log(f"AP IP address: {ap.ifconfig()[0]}")
    # DNS server thread removed
    # _thread.start_new_thread(dns_server, ())


def get_ap_ip():
    """Get the IP address of the AP interface"""
    # Check if AP is active before getting config
    if ap.active():
        try:
            return ap.ifconfig()[0]
        except Exception as e:
            log(f"Error getting AP IP: {e}")
            return "Error"
    else:
        return "AP_Inactive"
