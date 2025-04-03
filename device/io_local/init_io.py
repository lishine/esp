# Centralized initialization for IO components

from machine import Pin  # Still needed for NeoPixel pin definition
from neopixel import NeoPixel  # Import NeoPixel
from log import log
import led

# Import specific IO modules from this directory
from . import motor_current
from . import esc_telemetry
from . import ds18b20

# from . import ina226 # Keep file but don't init
from . import gps_reader
from . import buzzer


def init_io():
    """Initialize all IO components."""
    log("Initializing IO components...")  # Changed log.log to log

    # --- Initialize NeoPixel LED ---
    # Moved from led.py module level, adapted for NeoPixel
    try:
        # Use the pin and pixel count defined in led.py
        pin_obj = Pin(led.NEOPIXEL_PIN, Pin.OUT)
        led.np_obj = NeoPixel(pin_obj, led.NUM_PIXELS)
        # Initialize LED to off
        led.np_obj.fill(led.OFF_COLOR)
        led.np_obj.write()
        log(f"NeoPixel LED initialized on Pin {led.NEOPIXEL_PIN}")
    except Exception as e:
        log(f"Error initializing NeoPixel LED on Pin {led.NEOPIXEL_PIN}: {e}")
        led.np_obj = None  # Indicate failure

    # --- Initialize Sensors/Actuators ---
    # Initialize components sequentially. Check return values if needed.
    # motor_current.init_motor_current()
    # esc_telemetry.init_esc_telemetry()
    # ds18b20.init_ds18b20()
    # ina226.init_ina226() # Commented out as requested
    gps_reader.init_gps_reader()
    # buzzer.init_buzzer()

    log("IO initialization complete.")  # Changed log.log to log
