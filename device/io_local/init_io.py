# Centralized initialization for IO components

from machine import Pin  # Needed for LED init
from log import log
import led

# Import specific IO modules from this directory
from . import motor_current
from . import esc_telemetry
from . import ds18b20

# from . import ina226 # Keep file but don't init
from . import neo7m
from . import buzzer


def init_io():
    """Initialize all IO components."""
    log("Initializing IO components...")  # Changed log.log to log

    # --- Initialize LED ---
    # Moved from led.py module level
    try:
        # Use the pin defined in led.py
        led.led_pin_obj = Pin(led.LED_PIN, Pin.OUT)
        led.led_pin_obj.value(
            1
        )  # Initialize LED to off (assuming active low based on led.py logic led.on())
        log(f"LED initialized on Pin {led.LED_PIN}")  # Changed log.log to log
    except Exception as e:
        log(
            f"Error initializing LED on Pin {led.LED_PIN}: {e}"
        )  # Changed log.log to log
        led.led_pin_obj = None  # Indicate failure

    # --- Initialize Sensors/Actuators ---
    # Initialize components sequentially. Check return values if needed.
    # motor_current.init_motor_current()
    # esc_telemetry.init_esc_telemetry()
    # ds18b20.init_ds18b20()
    # ina226.init_ina226() # Commented out as requested
    neo7m.init_neo7m()
    # buzzer.init_buzzer()

    log("IO initialization complete.")  # Changed log.log to log
