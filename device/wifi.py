import json
import time
import _thread
import network
from machine import Pin

from log import log
from led import blink


def load_wifi_config():
    """Load WiFi configuration from wifi.json file"""
    try:
        with open("wifi.json", "r") as f:
            return json.loads(f.read())
    except:
        config = {"ssid": "", "password": ""}
        save_wifi_config(config)
        return config


def save_wifi_config(config):
    """Save WiFi configuration to wifi.json file"""
    with open("wifi.json", "w") as f:
        f.write(json.dumps(config))


sta = network.WLAN(network.STA_IF)
sta.active(True)

wifi_config = load_wifi_config()


def wifi_connect_thread():
    """Function to handle WiFi connection in a separate thread"""
    if not wifi_config.get("ssid") or not wifi_config.get("password"):
        log("No Wi-Fi credentials configured. Use settings page to configure.")
        return

    log(f"Connecting to {wifi_config['ssid']}")

    sta.connect(wifi_config["ssid"], wifi_config["password"])

    start_time = time.time()
    while not sta.isconnected() and time.time() - start_time < 10:
        time.sleep(1)
        Pin(8, Pin.OUT).value(not Pin(8, Pin.OUT).value())
        log("Waiting for WiFi connection...")

    if sta.isconnected():
        ip_address, subnet, gateway, dns = sta.ifconfig()
        log(
            f"""
WiFi connected successfully:
- IP Address: {ip_address}
- Subnet: {subnet}
- Gateway: {gateway}
- DNS: {dns}
        """
        )
        blink(3)
    else:
        log("WiFi connection failed")
        blink(1, 1, 0.1)


def start_wifi():
    """Start WiFi connection in a separate thread"""
    if wifi_config.get("ssid") and wifi_config.get("password"):
        _thread.start_new_thread(wifi_connect_thread, ())
    else:
        log("No Wi-Fi credentials configured. Use settings page to configure.")


def get_ip():
    """Get the current IP address of the station interface"""
    if sta.isconnected():
        return sta.ifconfig()[0]
    return "Not connected"


def is_connected():
    """Check if WiFi is connected"""
    return sta.isconnected()
