import json
import time
import _thread
import network
from machine import Pin

from log import log
from led import blink_sequence, start_continuous_blink, stop_continuous_blink


def load_wifi_config():
    """Load WiFi configuration from wifi.json file"""
    try:
        with open("wifi.json", "r") as f:
            return json.loads(f.read())
    except:
        config = {
            "networks": [{"ssid": "", "password": ""}, {"ssid": "", "password": ""}]
        }
        save_wifi_config(config)
        return config


def save_wifi_config(config):
    """Save WiFi configuration to wifi.json file"""
    with open("wifi.json", "w") as f:
        f.write(json.dumps(config))


sta = network.WLAN(network.STA_IF)
sta.active(True)

wifi_config = load_wifi_config()
current_network_index = -1  # -1 means not connected


def connect_to_network(network_index):
    """Connect to a specific network by index"""
    global current_network_index

    if not wifi_config.get("networks") or len(wifi_config["networks"]) <= network_index:
        return False

    network = wifi_config["networks"][network_index]
    if not network.get("ssid") or not network.get("password"):
        return False

    log(f"Connecting to {network['ssid']}")
    sta.connect(network["ssid"], network["password"])

    start_time = time.time()
    while not sta.isconnected() and time.time() - start_time < 10:
        time.sleep(1)
        Pin(8, Pin.OUT).value(not Pin(8, Pin.OUT).value())
        log("Waiting for WiFi connection...")

    if sta.isconnected():
        current_network_index = network_index
        ip_address, subnet, gateway, dns = sta.ifconfig()
        log(
            f"""
WiFi connected successfully to {network['ssid']}:
- IP Address: {ip_address}
- Subnet: {subnet}
- Gateway: {gateway}
- DNS: {dns}
            """
        )
        blink_sequence(count=3)
        start_continuous_blink(3.0)
        return True
    else:
        log(f"WiFi connection to {network['ssid']} failed")
        return False


def wifi_connect_thread():
    """Function to handle WiFi connection in a separate thread with fallback"""
    # Try primary network
    if connect_to_network(0):
        return

    # If primary fails, disconnect, wait, then try secondary
    log("Primary network connection failed.")
    try:
        log("Disconnecting WiFi before trying secondary...")
        sta.disconnect()
        # Wait a moment for the disconnect to process
        time.sleep(1)
    except Exception as e:
        log(f"Error during disconnect: {e}")  # Log potential errors during disconnect

    log("Trying secondary network...")
    if connect_to_network(1):
        return

    # Both networks failed
    log("All WiFi connection attempts failed")
    blink_sequence(count=1, on_time=1, off_time=0.1)
    stop_continuous_blink()


def start_wifi():
    """Start WiFi connection in a separate thread"""
    if wifi_config.get("networks") and len(wifi_config["networks"]) > 0:
        _thread.start_new_thread(wifi_connect_thread, ())
        # Start WiFi monitoring thread
        _thread.start_new_thread(monitor_wifi_connection, ())
    else:
        log("No Wi-Fi credentials configured. Use settings page to configure.")


def monitor_wifi_connection():
    """Monitor WiFi connection status and handle disconnections"""
    prev_connected = False

    while True:
        current_connected = sta.isconnected()

        # Connection state changed
        if current_connected != prev_connected:
            if current_connected:
                log("WiFi connection restored")
                start_continuous_blink(3.0)
            else:
                log("WiFi connection lost")
                stop_continuous_blink()
                # Try to reconnect
                _thread.start_new_thread(wifi_connect_thread, ())

        prev_connected = current_connected
        time.sleep(5)  # Check every 5 seconds


def get_ip():
    """Get the current IP address of the station interface"""
    if sta.isconnected():
        return sta.ifconfig()[0]
    return "Not connected"


def is_connected():
    """Check if WiFi is connected"""
    return sta.isconnected()


def get_current_network():
    """Get the currently connected network information"""
    if not sta.isconnected():
        return None

    # If we have a known current network index, use that
    if current_network_index >= 0:
        return {
            "index": current_network_index,
            "ssid": wifi_config["networks"][current_network_index]["ssid"],
            "is_primary": current_network_index == 0,
        }

    # If we don't know the index but are connected, try to match the SSID
    current_ssid = sta.config("essid")
    for i, net in enumerate(wifi_config["networks"]):
        if net["ssid"] == current_ssid:
            return {
                "index": i,
                "ssid": current_ssid,
                "is_primary": i == 0,
            }

    # Connected but not to a configured network
    return {
        "index": -1,
        "ssid": current_ssid,
        "is_primary": False,
    }
