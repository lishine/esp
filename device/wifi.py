import json
import network
import time
import _thread
from machine import Pin
from log import log
import led
import uasyncio as asyncio

# Using log function now, assuming it's thread-safe or handles it internally
# from log import log # Keep import if helper functions still use it

# --- Constants ---
MAX_WAIT_PER_ATTEMPT = 15  # Increased timeout per network attempt (seconds)
RETRY_DELAY_AFTER_FAIL = 30  # Delay after all networks fail (seconds)
CHECK_INTERVAL_CONNECTED = 10  # How often to check status when connected (seconds)

# --- Shared State and Lock ---
# This dictionary holds the current WiFi status accessible from other modules/threads.
# Use the lock to ensure thread-safe access.
wifi_state = {
    "connected": False,
    "connecting": False,
    "ssid": None,
    "ip": None,
    "subnet": None,
    "gateway": None,
    "dns": None,
    "current_network_index": -1,
    "error": None,
    "led_state": "disconnected",  # Add state for LED: 'disconnected', 'connecting', 'connected', 'error'
}
wifi_lock = None


def get_wifi_lock():
    global wifi_lock
    if not wifi_lock:
        wifi_lock = _thread.allocate_lock()
    return wifi_lock


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
# Load initial config, but wifi_thread_manager will reload it
# wifi_config = load_wifi_config() # Loaded within the thread loop now


# --- Synchronous Connection Helper (Runs in Thread) ---
def _try_connect_sync(network_index, config):
    """Synchronous attempt to connect to a specific network index."""
    global wifi_state  # Access global state dict

    if not config.get("networks") or len(config["networks"]) <= network_index:
        log(
            f"WiFi Thread: Network index {network_index} out of bounds or config missing."
        )
        return False, "Config Error"

    network_info = config["networks"][network_index]
    ssid = network_info.get("ssid")
    password = network_info.get("password")

    if not ssid:
        log(f"WiFi Thread: SSID missing for network index {network_index}.")
        return False, "SSID Missing"

    log(f"WiFi Thread: Attempting connection to network {network_index}: '{ssid}'")
    try:
        # Update state: Connecting
        with get_wifi_lock():
            wifi_state["connecting"] = True
            wifi_state["connected"] = False
            wifi_state["error"] = None
            wifi_state["current_network_index"] = network_index
            wifi_state["led_state"] = "connecting"  # Signal connecting state

        sta.connect(ssid, password)

        # Wait for connection with timeout (synchronous)
        wait_start_time = time.ticks_ms()
        while not sta.isconnected():
            if (
                time.ticks_diff(time.ticks_ms(), wait_start_time)
                > MAX_WAIT_PER_ATTEMPT * 1000
            ):
                log(
                    f"WiFi Thread: Connection attempt to '{ssid}' timed out after {MAX_WAIT_PER_ATTEMPT}s."
                )
                sta.disconnect()  # Ensure disconnect on timeout
                time.sleep(1)  # Give time for disconnect
                with get_wifi_lock():
                    wifi_state["connecting"] = False
                    wifi_state["error"] = f"Timeout connecting to {ssid}"
                    wifi_state["current_network_index"] = -1
                    wifi_state["led_state"] = "error"  # Signal error state
                return False, wifi_state["error"]

            # Blink LED while waiting (optional, ensure Pin is accessible)
            # try:
            #     Pin(8, Pin.OUT).value(not Pin(8, Pin.OUT).value())
            # except Exception: pass # Ignore if pin not setup or error
            time.sleep(1)  # Synchronous sleep

        # Connected successfully
        ip_address, subnet, gateway, dns = sta.ifconfig()
        log(
            f"""
WiFi Thread: Connected successfully to '{ssid}':
- IP Address: {ip_address}
- Subnet: {subnet}
- Gateway: {gateway}
- DNS: {dns}
            """
        )
        # Update state: Connected
        with get_wifi_lock():
            wifi_state["connected"] = True
            wifi_state["connecting"] = False
            wifi_state["ssid"] = ssid
            wifi_state["ip"] = ip_address
            wifi_state["subnet"] = subnet
            wifi_state["gateway"] = gateway
            wifi_state["dns"] = dns
            wifi_state["error"] = None
            wifi_state["led_state"] = "connected"  # Signal connected state
        return True, None

    except Exception as e:
        log(f"WiFi Thread: Error connecting to '{ssid}': {e}")
        error_msg = f"Error connecting to {ssid}: {e}"
        try:
            sta.disconnect()  # Attempt disconnect on error
            time.sleep(1)
        except Exception as disconnect_e:
            log(f"WiFi Thread: Error during disconnect after failure: {disconnect_e}")
        # Update state: Error
        with get_wifi_lock():
            wifi_state["connected"] = False
            wifi_state["connecting"] = False
            wifi_state["error"] = error_msg
            wifi_state["current_network_index"] = -1
            wifi_state["led_state"] = "error"  # Signal error state
        return False, error_msg


# --- Main WiFi Management Thread Function ---
def wifi_thread_manager():
    """Main thread function to manage WiFi connection, monitoring, and reconnection."""
    global wifi_state  # Access global state dict
    log("Starting WiFi Management Thread...")
    initial_connection_attempted = False

    while True:
        try:
            # --- Check Connection Status ---
            current_connected_status = sta.isconnected()

            with get_wifi_lock():
                # Update connection status if it changed unexpectedly
                if wifi_state["connected"] != current_connected_status:
                    log(
                        f"WiFi Thread: Status mismatch detected (state={wifi_state['connected']}, actual={current_connected_status}). Updating state."
                    )
                    wifi_state["connected"] = current_connected_status
                    if not current_connected_status:
                        wifi_state["ssid"] = None
                        wifi_state["ip"] = None
                        wifi_state["subnet"] = None
                        wifi_state["gateway"] = None
                        wifi_state["dns"] = None
                        wifi_state["current_network_index"] = -1
                        wifi_state["connecting"] = False
                        wifi_state["led_state"] = (
                            "disconnected"  # Signal disconnected state on mismatch
                        )

                is_currently_connected = wifi_state["connected"]
                is_currently_connecting = wifi_state["connecting"]

            # --- Handle Reconnection Logic ---
            if not is_currently_connected and not is_currently_connecting:
                if initial_connection_attempted:
                    log(
                        "WiFi Thread: Connection lost or failed previously. Attempting to reconnect..."
                    )
                else:
                    log(
                        "WiFi Thread: Not connected. Starting initial connection attempts..."
                    )

                # Reload config before attempting connection
                wifi_config = load_wifi_config()

                # Reset state before attempts
                with get_wifi_lock():
                    wifi_state["current_network_index"] = -1
                    wifi_state["error"] = None

                # Try primary network
                log("WiFi Thread: Trying primary network (index 0)...")
                connected, error = _try_connect_sync(0, wifi_config)

                # Try secondary network if primary failed
                if not connected:
                    log(
                        "WiFi Thread: Primary network failed. Trying secondary network (index 1)..."
                    )
                    time.sleep(1)  # Small delay
                    connected, error = _try_connect_sync(1, wifi_config)

                initial_connection_attempted = (
                    True  # Mark that we've tried at least once
                )

                if connected:
                    log("WiFi Thread: Connection established.")
                    # LED state already set to "connected" in _try_connect_sync
                    # Short success blink could be added here if desired, but requires led import
                    # led.blink_sequence(count=3, on_time=0.1, off_time=0.1) # Requires import led
                    time.sleep(CHECK_INTERVAL_CONNECTED)  # Wait longer after success
                else:
                    log(
                        f"WiFi Thread: All networks failed. Last error: {error}. Retrying in {RETRY_DELAY_AFTER_FAIL}s..."
                    )
                    # LED state already set to "error" in _try_connect_sync
                    # Error blink could be added here if desired, but requires led import
                    # led.blink_sequence(count=5, on_time=0.5, off_time=0.5) # Requires import led
                    time.sleep(RETRY_DELAY_AFTER_FAIL)  # Wait before next full cycle

            # --- Handle Connected State ---
            elif is_currently_connected:
                # Optional: Log active connection periodically
                # log("WiFi Thread: Connection active.") # Optional: uncomment for debugging
                time.sleep(CHECK_INTERVAL_CONNECTED)  # Check status periodically

            # --- Handle Connecting State ---
            elif is_currently_connecting:
                # This state should ideally be brief, handled within _try_connect_sync.
                # If stuck here, it might indicate an issue.
                log("WiFi Thread: Waiting for connection attempt to complete...")
                time.sleep(2)  # Wait a bit before checking again

        except Exception as e:
            log(f"WiFi Thread: Error in main loop: {e}")
            # Reset state potentially
            with get_wifi_lock():
                wifi_state["connected"] = False
                wifi_state["connecting"] = False
                wifi_state["error"] = f"Main loop error: {e}"
                wifi_state["led_state"] = (
                    "error"  # Signal error state on loop exception
                )
            time.sleep(10)  # Wait before retrying after a major loop error


# --- Helper Functions (Read from Shared State) ---
def get_ip():
    """Get the current IP address from the shared state"""
    with get_wifi_lock():
        if wifi_state["connected"]:
            return wifi_state["ip"]
        else:
            # Check if there was a recent error
            error = wifi_state.get("error")
            if error:
                return f"Error: {error}"  # Provide more context
            elif wifi_state.get("connecting"):
                return "Connecting..."
            else:
                return "Not connected"


def is_connected():
    """Check if WiFi is connected based on shared state"""
    with get_wifi_lock():
        # Also check the actual interface status for robustness, though state should be primary
        # return wifi_state["connected"] and sta.isconnected()
        # Simpler: rely on the state updated by the thread
        return wifi_state["connected"]


def get_current_network():
    """Get the currently connected network information from shared state"""
    with get_wifi_lock():
        if wifi_state["connected"] and wifi_state["current_network_index"] != -1:
            return {
                "index": wifi_state["current_network_index"],
                "ssid": wifi_state["ssid"],
                "is_primary": wifi_state["current_network_index"] == 0,
            }
        return None


async def manage_wifi_led_status():
    """Monitors wifi_state and updates LED accordingly."""
    log("Starting WiFi LED Status Monitor task...")
    last_led_state = None
    while True:
        try:
            with get_wifi_lock():
                current_led_state = wifi_state.get("led_state", "disconnected")

            if current_led_state != last_led_state:
                log(f"WiFi LED state changed: {last_led_state} -> {current_led_state}")
                if current_led_state == "connected":
                    # Slow blink for connected state
                    led.start_continuous_blink(interval=3.0, on_percentage=0.01)
                elif current_led_state == "connecting":
                    # Faster blink for connecting state
                    led.start_continuous_blink(interval=0.5, on_percentage=0.5)
                elif current_led_state == "error":
                    # Specific error blink sequence
                    led.blink_sequence(count=5, on_time=0.5, off_time=0.5)
                    # After sequence, maybe go back to disconnected state visually?
                    # Or keep error blink? For now, sequence runs once.
                    # Consider stopping continuous if it was running.
                    led.stop_continuous_blink()  # Stop any previous continuous blink
                elif current_led_state == "disconnected":
                    # Ensure LED is off (or default state)
                    led.stop_continuous_blink()
                else:
                    # Unknown state, default to off
                    led.stop_continuous_blink()

                last_led_state = current_led_state

        except Exception as e:
            log(f"Error in manage_wifi_led_status: {e}")
            # Avoid fast loop on error
            await asyncio.sleep(5)

        await asyncio.sleep_ms(200)
