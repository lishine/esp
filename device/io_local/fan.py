from machine import Pin
import settings_manager
from log import log  # Ensure log is available for all functions

FAN_PIN_NUM = 8  # Assuming this is correct, was Pin 10 in a comment
_fan_pin: Pin | None = None
_current_fan_state = False  # Internal state to avoid redundant saves


def init_fan() -> None:
    """Initialize the fan control pin and set initial state from settings."""
    global _fan_pin
    global _current_fan_state
    try:
        _fan_pin = Pin(FAN_PIN_NUM, Pin.OUT)
        # Get initial state from settings
        initial_state_from_settings = settings_manager.is_fan_enabled()
        _fan_pin.value(1 if initial_state_from_settings else 0)
        _current_fan_state = initial_state_from_settings
        log(
            f"Fan initialized. Pin: {FAN_PIN_NUM}, Initial state from settings: {'ON' if initial_state_from_settings else 'OFF'}"
        )
    except Exception as e:
        log(f"Error initializing fan pin {FAN_PIN_NUM}: {e}")
        _fan_pin = None


def set_fan(on: bool) -> None:
    """Set the fan ON (True) or OFF (False), and save state to settings."""
    global _fan_pin
    global _current_fan_state

    if _fan_pin is None:
        log("Fan pin not initialized. Attempting to initialize now.")
        init_fan()  # Attempt to initialize if not already
        if _fan_pin is None:  # Still not initialized
            log("Cannot set fan state: Fan pin failed to initialize.")
            return

    _fan_pin.value(1 if on else 0)
    log(f"Fan set to {'ON' if on else 'OFF'}")

    # Save to settings only if state actually changed
    if on != _current_fan_state:
        if settings_manager.set_fan_enabled(on):
            _current_fan_state = on
            log(f"Fan state ({'ON' if on else 'OFF'}) saved to settings.")
        else:
            log(f"Failed to save fan state ({'ON' if on else 'OFF'}) to settings.")
    else:
        log(f"Fan state already {'ON' if on else 'OFF'}, no settings update needed.")
