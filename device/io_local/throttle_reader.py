import uasyncio as asyncio
import machine
import utime
from log import log
import time
from . import data_log

# Configuration
THROTTLE_PIN_ID = 9
# Expected pulse range (microseconds) - adjust if needed
MIN_PULSE_US = 1000
MAX_PULSE_US = 2000
# Timeout for time_pulse_us (microseconds) - should be > max period (e.g., 20ms = 20000us)
PULSE_TIMEOUT_US = 50000
# Polling interval (milliseconds)
POLL_INTERVAL_MS = 500
# Log rate limit (seconds)
LOG_RATE_LIMIT_S = 1
# Low throttle logging interval (milliseconds)
LOW_THROTTLE_LOG_INTERVAL_MS: int = 5000

# Module state
_throttle_pin = None  # type: machine.Pin | None
_reader_task = None  # type: asyncio.Task | None
_last_value_us = None  # type: int | None # Store raw microseconds
_last_log_time = 0  # type: int

SENSOR_NAME = "th"


def init_throttle_reader() -> None:
    """Initialize the PWM reader for throttle on the specified pin."""
    global _throttle_pin
    try:
        _throttle_pin = machine.Pin(THROTTLE_PIN_ID, machine.Pin.IN)
        log(f"Throttle PWM reader initialized on pin {THROTTLE_PIN_ID}")
    except Exception as e:
        log(f"Throttle PWM: Failed to initialize pin {THROTTLE_PIN_ID}: {e}")
        _throttle_pin = None


async def _throttle_reader_task() -> None:
    """Async task to monitor throttle PWM value using time_pulse_us and log changes."""
    global _throttle_pin, _last_value_us, _last_log_time

    if _throttle_pin is None:
        log("Throttle PWM: Pin not initialized, task stopping.")
        return

    log("Throttle PWM reader task started using time_pulse_us")
    signal_lost_logged = False
    last_low_throttle_log_time_ms: int = 0

    while True:
        current_value_us = 0  # Default to 0 if error or no pulse
        try:
            # Measure the duration of the next high pulse (level=1)
            current_value_us = machine.time_pulse_us(_throttle_pin, 1, PULSE_TIMEOUT_US)
        except OSError:
            # Timeout likely means signal lost or pin issue
            # time_pulse_us returns 0 or negative on timeout, but OSError can also occur
            pass  # Keep current_value_us as 0

        if current_value_us > 0:  # Got a valid pulse reading
            signal_lost_logged = False  # Reset lost signal flag
            current_ticks: int = time.ticks_ms()
            if current_value_us < 1000:
                if (
                    time.ticks_diff(current_ticks, last_low_throttle_log_time_ms)
                    >= LOW_THROTTLE_LOG_INTERVAL_MS
                ):
                    data_log.report_data(SENSOR_NAME, current_ticks, current_value_us)
                    last_low_throttle_log_time_ms = current_ticks
            else:  # current_value_us >= 1000
                data_log.report_data(SENSOR_NAME, current_ticks, current_value_us)

            _last_value_us = current_value_us
            _last_log_time = (
                current_ticks  # Keep this updated, though its original use is removed
            )
        else:
            data_log.report_error(
                SENSOR_NAME,
                time.ticks_ms(),
                "no data",
            )
            # Handle case where pulse wasn't detected (timeout or 0 width)
            if (
                not signal_lost_logged and _last_value_us != 0
            ):  # Log only once when signal lost
                # log("Throttle PWM signal lost or invalid.")
                signal_lost_logged = True
            _last_value_us = 0  # Indicate signal lost/invalid

        await asyncio.sleep_ms(POLL_INTERVAL_MS)


def start_throttle_reader() -> None:
    """Start the async throttle PWM reader task if not already running."""
    global _reader_task
    if _throttle_pin is None:
        log("Throttle PWM: Cannot start reader task, pin not initialized.")
        return

    if _reader_task is None:
        try:
            _reader_task = asyncio.create_task(_throttle_reader_task())
            log("Throttle PWM reader task scheduled")
        except Exception as e:
            log(f"Throttle PWM: Failed to start reader task: {e}")
            _reader_task = None  # Ensure task is None if creation failed
    else:
        log("Throttle PWM: Reader task already running")


# Optional: Add a function to get the latest value if needed by other modules
def get_throttle_us() -> int | None:
    """Returns the last read throttle value in microseconds, or None if not read yet."""
    return _last_value_us


def get_throttle_scaled() -> float | None:
    """Returns the last read throttle value scaled to 0.0-1.0, or None."""
    if _last_value_us is None or _last_value_us == 0:
        return None
    scaled = (_last_value_us - MIN_PULSE_US) / (MAX_PULSE_US - MIN_PULSE_US)
    return max(0.0, min(1.0, scaled))  # Clamp to 0.0-1.0
