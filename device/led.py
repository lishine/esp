from machine import Pin
import time

led = Pin(8, Pin.OUT)
led.on()


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
