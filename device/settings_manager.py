import ujson
import uos
import log  # Changed to resolve circular import

# --- Constants ---
SETTINGS_FILE_PATH = "/sd/system_config.json"
SETTINGS_FILE_TMP_PATH = "/sd/system_config.json.tmp"

# --- Module State ---
_settings_data: dict = {}
_sd_card_ok: bool = (
    True  # Assume SD card is OK initially, can be updated by error handling
)


# --- Private Helper Functions ---
def _default_settings() -> dict:
    """Returns the default settings structure."""
    return {
        "settings": {
            "wifi": {
                "networks": [
                    {"ssid": "", "password": ""},  # Primary network
                    {"ssid": "", "password": ""},  # Secondary network
                ]
            }
        },
        "configuration": {"fan_enabled": False, "device_description": ""},
        "status": {
            "reset_counter": 0,
            "last_date": None,  # Stores 8-element datetime tuple or None
        },
    }


def _ensure_sd_path_exists():
    """
    Ensures the /sd directory exists.
    This is a basic check; full SD card mounting should be handled externally.
    """
    try:
        uos.statvfs("/sd")  # Check if /sd is mounted
    except OSError:
        log.log("Error: SD card path /sd not found or not mounted.")
        # In a real scenario, you might try to create /sd if it's just a dir missing
        # but if it's the mount point itself, this won't help.
        # For now, we'll just log and proceed, operations will likely fail.
        global _sd_card_ok
        _sd_card_ok = False


# --- Public API ---
def load_settings() -> None:
    """
    Loads settings from the JSON file on the SD card.
    If the file doesn't exist or is corrupt, it loads default settings
    and attempts to save them.
    """
    global _settings_data
    global _sd_card_ok
    _sd_card_ok = True  # Reset SD card status on load attempt
    _ensure_sd_path_exists()
    if not _sd_card_ok:
        log.log("SD card not available. Loading default settings into memory.")
        _settings_data = _default_settings()
        return

    try:
        with open(SETTINGS_FILE_PATH, "r") as f:
            _settings_data = ujson.load(f)
        log.log("Settings loaded successfully from SD card.")
    except OSError:
        log.log(
            f"Settings file '{SETTINGS_FILE_PATH}' not found. Loading defaults and creating file."
        )
        _settings_data = _default_settings()
        save_settings()  # Attempt to save defaults
    except ValueError:
        log.log(
            f"Error parsing settings file '{SETTINGS_FILE_PATH}'. Corrupted? Loading defaults and overwriting."
        )
        # Optionally, attempt to backup the corrupted file here
        try:
            uos.rename(SETTINGS_FILE_PATH, SETTINGS_FILE_PATH + ".corrupt")
            log.log(
                f"Backed up corrupted settings file to {SETTINGS_FILE_PATH + '.corrupt'}"
            )
        except OSError as e_backup:
            log.log(f"Could not backup corrupted settings file: {e_backup}")

        _settings_data = _default_settings()
        save_settings()  # Attempt to save defaults


def save_settings() -> bool:
    """
    Saves the current settings to the JSON file on the SD card atomically.
    Writes to a temporary file first, then renames.
    """
    global _sd_card_ok
    if not _sd_card_ok:  # If SD was marked as not OK during load or previous save
        _ensure_sd_path_exists()  # Re-check SD card
        if not _sd_card_ok:
            log.log("Cannot save settings: SD card not available.")
            return False

    try:
        with open(SETTINGS_FILE_TMP_PATH, "w") as f:
            ujson.dump(_settings_data, f)
        uos.rename(SETTINGS_FILE_TMP_PATH, SETTINGS_FILE_PATH)
        log.log("Settings saved successfully to SD card.")
        return True
    except OSError as e:
        log.log(f"Error saving settings to SD card: {e}")
        _sd_card_ok = False  # Mark SD as potentially problematic
        # Attempt to remove tmp file if it exists
        try:
            uos.remove(SETTINGS_FILE_TMP_PATH)
        except OSError:
            pass  # Ignore if tmp file doesn't exist or can't be removed
        return False
    except Exception as e:  # Catch any other unexpected errors during save
        log.log(f"Unexpected error saving settings: {e}")
        _sd_card_ok = False
        try:
            uos.remove(SETTINGS_FILE_TMP_PATH)
        except OSError:
            pass
        return False


# --- Getters and Setters ---


def get_setting(key_path: str, default_value=None):
    """
    Retrieves a setting value using a dot-separated key path.
    Example: get_setting("settings.wifi.networks")
    """
    keys = key_path.split(".")
    current_level = _settings_data
    try:
        for key in keys:
            if isinstance(current_level, dict):
                current_level = current_level.get(key)  # Use .get for safer access
                if current_level is None and key != keys[-1]:  # Path broken before end
                    return default_value
            elif isinstance(current_level, list) and key.isdigit():
                idx = int(key)
                if 0 <= idx < len(current_level):
                    current_level = current_level[idx]
                else:  # Index out of bounds
                    return default_value
            else:
                # log(f"Invalid path or type in get_setting for key '{key}' in path '{key_path}'")
                return default_value
        return current_level
    except (KeyError, IndexError, TypeError):
        # log(f"Setting not found for path '{key_path}'. Returning default.")
        return default_value


def update_setting(key_path: str, value) -> bool:
    """
    Updates a setting value using a dot-separated key path and saves all settings.
    Example: update_setting("configuration.fan_enabled", True)
    Returns True if successful, False otherwise.
    """
    keys = key_path.split(".")
    current_level = _settings_data
    try:
        for i, key in enumerate(keys[:-1]):  # Navigate to the parent dictionary/list
            if isinstance(current_level, dict):
                if (
                    key not in current_level
                ):  # Create intermediate dicts if they don't exist
                    current_level[key] = {}
                current_level = current_level[key]
            elif isinstance(current_level, list) and key.isdigit():
                idx = int(key)
                if 0 <= idx < len(current_level):
                    current_level = current_level[idx]
                else:  # Index out of bounds, cannot create path
                    log.log(
                        f"Index out of bounds for key '{key}' in path '{key_path}' during update."
                    )
                    return False
            else:  # Path is invalid
                log.log(
                    f"Invalid path or type for key '{key}' in path '{key_path}' during update."
                )
                return False

        # Set the final key's value
        parent_for_final_key = current_level
        final_key = keys[-1]

        if isinstance(parent_for_final_key, dict):
            parent_for_final_key[final_key] = value
        elif isinstance(parent_for_final_key, list):
            if final_key.isdigit():
                idx = int(final_key)
                if 0 <= idx < len(parent_for_final_key):
                    parent_for_final_key[idx] = value
                elif idx == len(parent_for_final_key):  # Allow appending
                    parent_for_final_key.append(value)
                else:
                    log.log(
                        f"Index out of bounds for final key '{final_key}' (index {idx}) in list for path '{key_path}' during update."
                    )
                    return False
            else:
                log.log(
                    f"Final key '{final_key}' is not a valid integer index for list parent in path '{key_path}'."
                )
                return False
        else:
            log.log(
                f"Cannot set value. Parent for final key '{final_key}' in path '{key_path}' is not a dict or list (type: {type(parent_for_final_key)})."
            )
            return False

    except (KeyError, IndexError, TypeError) as e:
        log.log(f"Error navigating path '{key_path}' for update: {e}")
        return False

    return save_settings()


# Specific Getters
def get_wifi_networks() -> list:
    networks = get_setting("settings.wifi.networks", default_value=[])
    if isinstance(networks, list):
        return networks
    log.log(
        f"WiFi networks setting is not a list (type: {type(networks)}). Returning empty list."
    )
    return []


def is_fan_enabled() -> bool:
    # Ensure boolean return, as get_setting can return default_value (False) or actual value
    val = get_setting("configuration.fan_enabled", default_value=False)
    return bool(val)


def get_reset_counter() -> int:
    val = get_setting("status.reset_counter", default_value=0)

    if isinstance(val, int):
        return val

    if isinstance(val, str):  # Check if it's a string
        try:
            return int(val)
        except ValueError:
            log.log(
                f"Reset counter string value '{val}' is not a valid integer. Returning 0."
            )
            return 0  # Fallback for string conversion failure
    elif isinstance(val, float):  # Check if it's a float
        try:
            return int(val)  # float to int conversion
        except ValueError:
            log.log(
                f"Reset counter float value '{val}' could not be converted to int. Returning 0."
            )
            return 0  # Fallback for float conversion failure

    # If val was not int, str, or float, but was returned by get_setting
    # and wasn't the default_value=0 (which would be an int and caught above).
    if val != 0:
        log.log(
            f"Unexpected type for reset counter: {type(val)}, value: '{val}'. Returning 0."
        )

    return 0  # Default fallback for all other cases


def get_last_date():  # Original hint was -> tuple | None. Assuming 8-element tuple of ints, or None
    # JSON stores lists, convert back to tuple if it's a list, else None
    date_list = get_setting("status.last_date", default_value=None)
    if isinstance(date_list, list):
        # Ensure all elements are integers for the tuple
        try:
            return tuple(int(item) for item in date_list)
        except (ValueError, TypeError):
            log.log("Invalid items in last_date list, cannot convert to tuple of ints.")
            return None
    return None


def get_device_description() -> str:
    val = get_setting("configuration.device_description", default_value="")
    return str(val) if val is not None else ""


# Specific Setters
def set_wifi_networks(networks: list) -> bool:
    if not isinstance(networks, list):
        log.log("set_wifi_networks: networks argument must be a list.")
        return False
    for net in networks:
        if not isinstance(net, dict) or "ssid" not in net or "password" not in net:
            log.log(
                "set_wifi_networks: Each network in the list must be a dict with 'ssid' and 'password'."
            )
            return False
    return update_setting("settings.wifi.networks", networks)


def set_fan_enabled(state: bool) -> bool:
    if not isinstance(state, bool):
        log.log("set_fan_enabled: state argument must be a boolean.")
        return False
    return update_setting("configuration.fan_enabled", state)


def increment_reset_counter() -> bool:
    current_counter = get_reset_counter()
    return update_setting("status.reset_counter", current_counter + 1)


def set_last_date(date_tuple: tuple) -> bool:  # Can be None
    if date_tuple is not None:
        if not isinstance(date_tuple, tuple) or len(date_tuple) != 8:
            log.log(
                "set_last_date: date_tuple argument must be an 8-element tuple or None."
            )
            return False
        # Ensure all elements are integers before converting to list for JSON
        try:
            processed_date_list: list | None = [  # type: ignore
                int(item) for item in date_tuple
            ]
        except (ValueError, TypeError):
            log.log("set_last_date: date_tuple contains non-integer elements.")
            return False
    else:
        processed_date_list = None

    return update_setting("status.last_date", processed_date_list)


def set_device_description(description: str) -> bool:
    if not isinstance(description, str):
        log.log("set_device_description: description argument must be a string.")
        return False
    return update_setting("configuration.device_description", description)


# Initialize by loading settings when the module is imported.
# This ensures _settings_data is populated.
# However, SD card initialization must happen before this module is imported or used.
# load_settings() # Deferred to be called explicitly after SD init in boot.py
