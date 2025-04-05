import uasyncio as asyncio
from machine import Pin  # Keep Pin from machine
from neopixel import NeoPixel  # Import NeoPixel from its own module
from log import log

# Define the NeoPixel pin and number of pixels
NEOPIXEL_PIN = 48
NUM_PIXELS = 1
ON_COLOR = (0, 1, 2)  # Dim white, as per user example
OFF_COLOR = (0, 0, 0)  # Black

np_obj = None  # Will be initialized externally by init_io.py

_led_mode = "IDLE"  # Possible modes: 'IDLE', 'SEQUENCE', 'CONTINUOUS'
_sequence_params = None  # Tuple: (count, on_time_ms, off_time_ms)
_continuous_interval_ms = None  # Integer: interval in milliseconds
_continuous_on_percentage = 0.5  # Float: percentage of interval LED is ON (default 50%)


async def led_task():
    """Main asynchronous task to control the LED based on the current mode."""
    global _led_mode, _sequence_params, _continuous_interval_ms, _continuous_on_percentage
    while True:
        current_mode = _led_mode  # Cache mode for this iteration

        if current_mode == "SEQUENCE":
            if _sequence_params:
                count, on_time_ms, off_time_ms = _sequence_params
                for _ in range(count):
                    # Check if mode changed mid-sequence
                    if _led_mode != "SEQUENCE":
                        break
                    led_turn_on()
                    await asyncio.sleep_ms(on_time_ms)
                    # Check again after sleep
                    if _led_mode != "SEQUENCE":
                        break
                    led_turn_off()
                    await asyncio.sleep_ms(off_time_ms)
                # Sequence finished or interrupted, go back to IDLE if not changed again
                if _led_mode == "SEQUENCE":
                    _led_mode = "IDLE"
                    _sequence_params = None
                    led_turn_off()  # Ensure LED is off
            else:
                # Should not happen, but reset if params are missing
                _led_mode = "IDLE"
                led_turn_off()

        elif current_mode == "CONTINUOUS":
            if _continuous_interval_ms and _continuous_interval_ms > 0:
                # Calculate on and off times based on the on_percentage
                on_time_ms = int(_continuous_interval_ms * _continuous_on_percentage)
                off_time_ms = _continuous_interval_ms - on_time_ms
                led_turn_on()
                await asyncio.sleep_ms(on_time_ms)
                # Check if mode changed during on-time
                if _led_mode == "CONTINUOUS":
                    led_turn_off()
                    await asyncio.sleep_ms(off_time_ms)
            else:
                # Invalid interval or mode changed, go back to IDLE
                _led_mode = "IDLE"
                led_turn_off()

        elif current_mode == "IDLE":
            led_turn_off()  # Ensure LED is off in IDLE state
            await asyncio.sleep_ms(50)  # Yield control

        else:  # Unknown mode
            _led_mode = "IDLE"
            led_turn_off()
            await asyncio.sleep_ms(50)


def led_turn_on():
    """Turn the NeoPixel LED on."""
    if np_obj:
        try:
            np_obj.fill(ON_COLOR)
            np_obj.write()
        except Exception as e:
            log(f"Error setting NeoPixel ON: {e}")
    else:
        log("NeoPixel object not initialized")


def led_turn_off():
    """Turn the NeoPixel LED off."""
    if np_obj:
        try:
            np_obj.fill(OFF_COLOR)
            np_obj.write()
        except Exception as e:
            log(f"Error setting NeoPixel OFF: {e}")
    else:
        log("NeoPixel object not initialized")


def blink_sequence(count=3, on_time=0.1, off_time=0.1):
    """Initiate a sequence of LED blinks. Interrupts any current action.

    Args:
        count (int): Number of blinks.
        on_time (float): Time LED stays on in seconds.
        off_time (float): Time LED stays off in seconds.
    """
    global _led_mode, _sequence_params, _continuous_interval_ms
    _led_mode = "SEQUENCE"
    _sequence_params = (count, int(on_time * 1000), int(off_time * 1000))
    _continuous_interval_ms = None


def start_continuous_blink(interval=1.0, on_percentage=0.5):
    """Start continuous LED blinking. Interrupts any current action.

    Args:
        interval (float): Time in seconds for a complete on-off cycle.
        on_percentage (float): Percentage of the interval the LED is ON (0.0 to 1.0).
    """
    global _led_mode, _sequence_params, _continuous_interval_ms, _continuous_on_percentage
    _led_mode = "CONTINUOUS"
    _continuous_interval_ms = int(interval * 1000)
    _continuous_on_percentage = max(
        0.0, min(1.0, on_percentage)
    )  # Clamp between 0 and 1
    _sequence_params = None


def stop_continuous_blink():
    """Stop any LED blinking (sequence or continuous) and turn LED off."""
    global _led_mode, _sequence_params, _continuous_interval_ms
    _led_mode = "IDLE"
    _sequence_params = None
    _continuous_interval_ms = None
    led_turn_off()  # Ensure LED is off immediately
