import json
import network
import uasyncio as asyncio
from machine import Pin  # Keep for potential direct use if needed
from log import log
import led  # Import led module for async functions

MAX_WAIT = 5


# --- Configuration Loading/Saving (Keep as is) ---
def load_wifi_config():
    """Load WiFi configuration from wifi.json file"""
    try:
        with open("wifi.json", "r") as f:
            return json.loads(f.read())
    except Exception as e:
        log(f"Error loading wifi.json: {e}. Creating default.")
        config = {
            "networks": [{"ssid": "", "password": ""}, {"ssid": "", "password": ""}]
        }
        save_wifi_config(config)
        return config


def save_wifi_config(config):
    """Save WiFi configuration to wifi.json file"""
    try:
        with open("wifi.json", "w") as f:
            f.write(json.dumps(config))
    except Exception as e:
        log(f"Error saving wifi.json: {e}")


# --- Network Interface Setup (Keep as is) ---
sta = network.WLAN(network.STA_IF)
sta.active(True)
# Load initial config, but manage_wifi_connection will reload it
wifi_config = load_wifi_config()
# This global might be less reliable if connection drops and reconnects outside the task's knowledge
# get_current_network might need refinement if strict index tracking is needed externally.
current_network_index = -1


# --- Async Connection Helper ---
async def _try_connect(network_index):
    """Attempt to connect to a specific network index asynchronously."""
    global current_network_index, wifi_config  # Need global wifi_config here

    if not wifi_config.get("networks") or len(wifi_config["networks"]) <= network_index:
        log(f"Network index {network_index} out of bounds or config missing.")
        return False

    network_info = wifi_config["networks"][network_index]
    ssid = network_info.get("ssid")
    password = network_info.get("password")

    if not ssid:  # Allow empty password for open networks
        log(f"SSID missing for network index {network_index}.")
        return False

    log(f"Attempting connection to network {network_index}: '{ssid}'")
    try:
        sta.connect(ssid, password)

        # Wait for connection with timeout
        max_wait = MAX_WAIT  # seconds
        wait_interval = 1  # second
        for _ in range(max_wait // wait_interval):
            if sta.isconnected():
                current_network_index = network_index
                ip_address, subnet, gateway, dns = sta.ifconfig()
                log(
                    f"""
WiFi connected successfully to '{ssid}':
- IP Address: {ip_address}
- Subnet: {subnet}
- Gateway: {gateway}
- DNS: {dns}
                    """
                )
                return True
            # Blink LED while waiting
            Pin(8, Pin.OUT).value(not Pin(8, Pin.OUT).value())
            await asyncio.sleep(wait_interval)

        # Timeout reached
        log(f"Connection attempt to '{ssid}' timed out after {max_wait}s.")
        sta.disconnect()  # Ensure disconnect if timeout occurred mid-attempt
        await asyncio.sleep(1)  # Give time for disconnect to settle
        return False

    except Exception as e:
        log(f"Error connecting to '{ssid}': {e}")
        try:
            sta.disconnect()  # Attempt disconnect on error
            await asyncio.sleep(1)
        except Exception as disconnect_e:
            log(f"Error during disconnect after connection failure: {disconnect_e}")
        return False


# --- Main Async WiFi Management Task ---
async def manage_wifi_connection():
    """Main task to manage WiFi connection, monitoring, and reconnection."""
    global current_network_index, wifi_config
    log("Starting WiFi Management Task...")
    initial_connection_done = False

    while True:
        wifi_config = (
            load_wifi_config()
        )  # Reload config in case it changed via settings page

        if not sta.isconnected():
            if (
                initial_connection_done
            ):  # Only log disconnect if we were previously connected
                log("WiFi connection lost. Attempting to reconnect...")
            else:
                log("WiFi not connected. Starting connection attempts...")

            led.stop_continuous_blink()  # Ensure blink stops on disconnect (Sync call)
            current_network_index = -1  # Reset index

            # Try primary network
            log("Trying primary network (index 0)...")
            connected = await _try_connect(0)

            # Try secondary network if primary failed
            if not connected:
                log("Primary network failed. Trying secondary network (index 1)...")
                await asyncio.sleep(1)  # Small delay before trying secondary
                connected = await _try_connect(1)

            if connected:
                log("WiFi connection established.")
                initial_connection_done = True
                led.blink_sequence(
                    count=3, on_time=0.1, off_time=0.1
                )  # Quick success blink (Sync call)
                led.start_continuous_blink(
                    3.0
                )  # Slow blink for connected state (Sync call)
                # Wait longer after successful connection before checking again
                await asyncio.sleep(15)
            else:
                log(
                    "All configured WiFi networks failed to connect. Retrying in 30s..."
                )
                initial_connection_done = True  # Mark initial attempt cycle as done
                # Use LED to signal connection failure state
                led.blink_sequence(
                    count=5, on_time=0.5, off_time=0.5
                )  # Error blink (Sync call)
                await asyncio.sleep(30)  # Wait before next full attempt cycle
        else:
            # Still connected, check again in 10 seconds
            # log("WiFi connection active.") # Optional: uncomment for debugging
            await asyncio.sleep(10)


# --- Helper Functions (Keep/Adapt as needed) ---
def get_ip():
    """Get the current IP address of the station interface"""
    if sta.isconnected():
        try:
            return sta.ifconfig()[0]
        except Exception as e:
            log(f"Error getting IP: {e}")
            return "Error"
    return "Not connected"


def is_connected():
    """Check if WiFi is connected"""
    return sta.isconnected()


def get_current_network():
    """Get the currently connected network information (best effort)"""
    global current_network_index  # Declare intention to use the global variable
    if not sta.isconnected():
        return None

    # If we have a known current network index from the last successful connect
    if current_network_index >= 0 and current_network_index < len(
        wifi_config.get("networks", [])
    ):
        network_info = wifi_config["networks"][current_network_index]
        # Verify if the current connection SSID actually matches the stored index SSID
        try:
            current_ssid = sta.config("essid")
            if network_info.get("ssid") == current_ssid:
                return {
                    "index": current_network_index,
                    "ssid": current_ssid,
                    "is_primary": current_network_index == 0,
                }
            else:
                # Discrepancy, fall through to SSID matching
                log(
                    f"Warning: Connected SSID '{current_ssid}' doesn't match expected index {current_network_index} SSID '{network_info.get('ssid')}'."
                )
        except Exception as e:
            log(f"Error getting current SSID: {e}")
            # Fall through

    # If index is unknown or mismatched, try to match the current SSID
    try:
        current_ssid = sta.config("essid")
        for i, net in enumerate(wifi_config.get("networks", [])):
            if net.get("ssid") == current_ssid:
                # Update index if we found a match (it's already global)
                current_network_index = i
                return {
                    "index": i,
                    "ssid": current_ssid,
                    "is_primary": i == 0,
                }
    except Exception as e:
        log(f"Error matching current SSID: {e}")
        return None  # Indicate error or inability to determine

    # Connected but not to a known/configured network?
    log(f"Connected to unknown network: {current_ssid}")
    return {
        "index": -1,
        "ssid": current_ssid,  # Report the actual SSID
        "is_primary": False,
    }
