from machine import Pin
import time
import _thread

led = Pin(8, Pin.OUT)
led.on()

# Flag to control continuous blinking
_blink_active = False
_blink_thread_running = False


def led_turn_on():
    """Turn the LED on (LED is active low)"""
    led.off()


def led_turn_off():
    """Turn the LED off (LED is active low)"""
    led.on()


def blink(count=1, on_time=0.1, off_time=0.1):
    """Simple blink function

    Args:
        count: Number of blinks
        on_time: Time LED stays on in seconds
        off_time: Time LED stays off in seconds
    """
    for _ in range(count):
        led_turn_on()
        time.sleep(on_time)
        led_turn_off()
        time.sleep(off_time)


def blink_sequence(count=3, on_time=0.1, off_time=0.1):
    """Execute a sequence of LED blinks

    Args:
        count: Number of blinks
        on_time: Time LED stays on in seconds
        off_time: Time LED stays off in seconds
    """
    for _ in range(count):
        led.value(not led.value())
        time.sleep(on_time)
        led.value(not led.value())
        time.sleep(off_time)


def start_continuous_blink(interval=1.0):
    """Start continuous LED blinking in a separate thread

    Args:
        interval: Time in seconds for a complete on-off cycle
    """
    global _blink_active, _blink_thread_running

    # Set flag to enable blinking
    _blink_active = True

    # Only start a new thread if one isn't already running
    if not _blink_thread_running:
        _thread.start_new_thread(_continuous_blink_thread, (interval,))


def stop_continuous_blink():
    """Stop the continuous LED blinking"""
    global _blink_active
    _blink_active = False
    led_turn_off()  # Ensure LED is in the default state


def _continuous_blink_thread(interval):
    """Thread function for continuous blinking

    Args:
        interval: Time in seconds for a complete on-off cycle
    """
    global _blink_thread_running

    _blink_thread_running = True
    half_interval = interval / 2

    try:
        while _blink_active:
            led_turn_on()
            time.sleep(half_interval)
            led_turn_off()
            time.sleep(half_interval)
    finally:
        _blink_thread_running = False
