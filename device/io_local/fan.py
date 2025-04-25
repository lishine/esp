from machine import Pin

FAN_PIN_NUM = 8
_fan_pin: Pin | None = None


def init_fan() -> None:
    """Initialize the fan control pin as output (Pin 10)."""
    global _fan_pin
    try:
        _fan_pin = Pin(FAN_PIN_NUM, Pin.OUT)
    except Exception as e:
        from log import log

        log(f"Error initializing fan pin {FAN_PIN_NUM}: {e}")
        _fan_pin = None


def set_fan(on: bool) -> None:
    """Set the fan ON (True) or OFF (False) by outputting 1 or 0 on the pin."""
    global _fan_pin
    if _fan_pin is None:
        init_fan()
    if _fan_pin is not None:
        _fan_pin.value(1 if on else 0)
