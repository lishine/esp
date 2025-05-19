# SD Card-Based Settings Management Plan

**1. Objective:**
Create a robust system to store and retrieve device settings, configuration, and status counters on an SD card. This system will ensure data persistence across reboots and even full firmware reflashes (as the SD card data remains independent).

**2. Data Structure:**
The settings will be stored in a JSON file on the SD card.
*   **Filename:** `/sd/system_config.json`
*   **Content Structure:**

```json
{
  "settings": {
    "wifi": {
      "networks": [
        {"ssid": "", "password": ""}, // Primary network
        {"ssid": "", "password": ""}  // Secondary network
      ]
    }
    // Other general device settings can be added here in the future
  },
  "configuration": {
    "fan_enabled": false,        // Current state of the fan
    "device_description": ""   // A user-configurable description for the device
  },
  "status": {
    "reset_counter": 0,        // Increments on each boot
    "last_date": null          // Last valid 8-element datetime tuple from RTC (e.g., [2025, 5, 19, 8, 47, 0, 0, 139]), or null
  }
}
```
*Default values for SSIDs and passwords will be empty strings.*

**3. Core Module: `device/settings_manager.py`**

*   **Key Responsibilities:**
    *   Ensure SD card is initialized (potentially by calling a utility function from `device/sd_utils.py` or `device/sd.py`).
    *   Load settings from `/sd/system_config.json` at startup.
    *   If the settings file doesn't exist or is found to be corrupt, it will be created (or overwritten) with the default structure and values.
    *   Provide getter and setter functions for accessing and modifying settings.
    *   Atomically save the entire settings object back to `/sd/system_config.json` whenever a setting is modified. This will be achieved by writing to a temporary file first, then using `uos.rename()` to replace the original file, ensuring data integrity even if a reset occurs during the save operation.
    *   Hold the loaded configuration in an internal variable for quick access.

*   **Proposed Functions (Illustrative - actual implementation might vary slightly):**
    *   `_settings_data = {}` (internal variable to hold loaded settings)
    *   `_default_settings() -> dict`: Returns the complete default settings structure.
    *   `load_settings()`:
        *   Attempts to read and parse `/sd/system_config.json`.
        *   On success, stores in `_settings_data`.
        *   On failure (file not found, parse error), logs the error, loads `_default_settings()` into `_settings_data`, and calls `save_settings()` to create a valid default file on the SD card.
    *   `save_settings()`:
        *   Writes the content of `_settings_data` to a temporary file (e.g., `/sd/system_config.json.tmp`).
        *   If successful, renames the temporary file to `/sd/system_config.json`.
        *   Handles potential errors during file operations.
    *   `get_setting(key_path: str, default=None)`: A generic getter, e.g., `get_setting("settings.wifi.networks")`.
    *   `update_setting(key_path: str, value)`: A generic setter, automatically calls `save_settings()`.
    *   Specific getters/setters for convenience:
        *   `get_wifi_networks() -> list`: Returns `_settings_data["settings"]["wifi"]["networks"]`.
        *   `set_wifi_networks(networks: list)`: Updates the WiFi networks list in `_settings_data` and calls `save_settings()`.
        *   `is_fan_enabled() -> bool`.
        *   `set_fan_enabled(state: bool)`.
        *   `get_reset_counter() -> int`.
        *   `increment_reset_counter()`: Increments the counter in `_settings_data` and calls `save_settings()`.
        *   `get_last_date() -> tuple | None`.
        *   `set_last_date(date_tuple: tuple)`.
        *   `get_device_description() -> str`.
        *   `set_device_description(description: str)`.

**4. Integration Points:**

*   **`device/boot.py` (or very early in `device/main.py`):**
    1.  Ensure SD card is mounted/initialized (e.g., using a function from `device/sd_utils.py` or `device/sd.py`).
    2.  Import `settings_manager` from `device.settings_manager`.
    3.  Call `settings_manager.load_settings()`.
    4.  Call `settings_manager.increment_reset_counter()`.
*   **`device/wifi.py`:**
    *   **Remove** its internal `load_wifi_config()` and `save_wifi_config()` functions that operate on the local `wifi.json`.
    *   Modify the `wifi_thread_manager()` function:
        *   Where it currently calls `load_wifi_config()`, it should instead fetch the configuration using `settings_manager.get_wifi_networks()`. The result will be a list of network dictionaries, which then needs to be wrapped into a dictionary like `{"networks": the_list_from_settings_manager}` to match the existing expectation of `_try_connect_sync`.
    *   If WiFi settings are to be updated (e.g., via `device/settings.html` or another interface), those mechanisms will call `settings_manager.set_wifi_networks(new_networks_list)`.
*   **`device/io_local/fan.py`:**
    *   On initialization, get the fan's default state using `settings_manager.is_fan_enabled()`.
    *   When the fan's state is changed programmatically, call `settings_manager.set_fan_enabled(new_state)`.
*   **`device/rtc.py`:**
    *   After a successful RTC time synchronization and validation, call `settings_manager.set_last_date(time_tuple_from_rtc)`.
*   **Web Interface (e.g., via `device/http_server.py` and `device/settings.html`):**
    *   API endpoints for fetching settings will call the relevant `get_...` functions from `settings_manager`.
    *   API endpoints for updating settings will call the relevant `set_...` functions from `settings_manager`.

**5. Error Handling and Resilience:**

*   **SD Card Issues:** If the SD card is not present, fails to initialize, or file operations fail:
    *   The `settings_manager` will log an error (using `device/log.py`).
    *   It will operate with in-memory default settings for the current session.
    *   It should not persistently try to write to a non-functional SD card unless explicitly retried.
*   **JSON File Corruption:** If `/sd/system_config.json` is found but cannot be parsed during `load_settings()`:
    *   Log an error.
    *   Attempt to rename the corrupted file (e.g., to `/sd/system_config.json.backup_corrupt`).
    *   Proceed to load default settings and save them to create a new, valid `/sd/system_config.json`.
*   **Atomic Saves:** As stated, all saves to `/sd/system_config.json` will use the temporary file and rename strategy.