from machine import Pin
import uasyncio as asyncio

# --- Configuration ---
LED_PIN = 8

# --- Initialization ---
led = Pin(LED_PIN, Pin.OUT)
led.on()  # Initialize LED to off (active low)

# --- State Variables ---
_led_mode = "IDLE"  # Possible modes: 'IDLE', 'SEQUENCE', 'CONTINUOUS'
_sequence_params = None  # Tuple: (count, on_time_ms, off_time_ms)
_continuous_interval_ms = None  # Integer: interval in milliseconds


# --- Core Task ---
async def led_task():
    """Main asynchronous task to control the LED based on the current mode."""
    global _led_mode, _sequence_params, _continuous_interval_ms

    while True:
        current_mode = _led_mode  # Cache mode for this iteration

        if current_mode == "SEQUENCE":
            if _sequence_params:
                count, on_time_ms, off_time_ms = _sequence_params
                # print(f"LED Sequence: count={count}, on={on_time_ms}, off={off_time_ms}")
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
                half_interval_ms = _continuous_interval_ms // 2
                # print(f"LED Continuous: interval={_continuous_interval_ms}")
                led_turn_on()
                await asyncio.sleep_ms(half_interval_ms)
                # Check if mode changed during on-time
                if _led_mode == "CONTINUOUS":
                    led_turn_off()
                    await asyncio.sleep_ms(half_interval_ms)
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


# --- Control Functions ---
def led_turn_on():
    """Turn the LED on (LED is active low)."""
    led.off()


def led_turn_off():
    """Turn the LED off (LED is active low)."""
    led.on()


def blink_sequence(count=3, on_time=0.1, off_time=0.1):
    """Initiate a sequence of LED blinks. Interrupts any current action.

    Args:
        count (int): Number of blinks.
        on_time (float): Time LED stays on in seconds.
        off_time (float): Time LED stays off in seconds.
    """
    global _led_mode, _sequence_params, _continuous_interval_ms
    # print(f"Setting LED Sequence: count={count}, on={on_time}, off={off_time}")
    _led_mode = "SEQUENCE"
    _sequence_params = (count, int(on_time * 1000), int(off_time * 1000))
    _continuous_interval_ms = None


def start_continuous_blink(interval=1.0):
    """Start continuous LED blinking. Interrupts any current action.

    Args:
        interval (float): Time in seconds for a complete on-off cycle.
    """
    global _led_mode, _sequence_params, _continuous_interval_ms
    # print(f"Setting LED Continuous: interval={interval}")
    _led_mode = "CONTINUOUS"
    _continuous_interval_ms = int(interval * 1000)
    _sequence_params = None


def stop_continuous_blink():
    """Stop any LED blinking (sequence or continuous) and turn LED off."""
    global _led_mode, _sequence_params, _continuous_interval_ms
    # print("Setting LED IDLE")
    _led_mode = "IDLE"
    _sequence_params = None
    _continuous_interval_ms = None
    led_turn_off()  # Ensure LED is off immediately
