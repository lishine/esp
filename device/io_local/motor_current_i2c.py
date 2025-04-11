import uasyncio as asyncio
from machine import I2C, Pin
from log import log

I2C_ID = 0
I2C_SCL_PIN = 3
I2C_SDA_PIN = 8
I2C_FREQ = 400_000
I2C_ADDR = 0x08

_i2c = None
_reader_task = None


def init_rms_motor_current_i2c() -> None:
    """Initialize I2C for RMS motor current reading and check device presence."""
    global _i2c
    try:
        _i2c = I2C(
            I2C_ID,
            scl=Pin(I2C_SCL_PIN),
            sda=Pin(I2C_SDA_PIN),
            freq=I2C_FREQ,
        )
        devices = _i2c.scan()
        if I2C_ADDR not in devices:
            log(f"RMS I2C: Device not found at address 0x{I2C_ADDR:02X}")
        else:
            log(f"RMS I2C: Device found at address 0x{I2C_ADDR:02X}")
    except Exception as e:
        log(f"RMS I2C: Initialization error: {e}")
        _i2c = None


async def _rms_motor_current_i2c_task() -> None:
    """Async task to periodically read RMS motor current from I2C and log it."""
    global _i2c
    while True:
        try:
            if _i2c is None:
                log("RMS I2C: Not initialized, skipping read")
            else:
                data = _i2c.readfrom(I2C_ADDR, 2)
                if len(data) == 2:
                    rms_mv = data[0] | (data[1] << 8)
                    log(f"RMS Motor Current (I2C): {rms_mv} mV")
                else:
                    log(f"RMS I2C: Incomplete read, got {len(data)} bytes")
        except Exception as e:
            log(f"RMS I2C: Read error: {e}")
        await asyncio.sleep(1)


def start_rms_motor_current_i2c_reader() -> None:
    """Start the async RMS I2C reader task if not already running."""
    global _reader_task
    if _reader_task is None:
        try:
            import uasyncio as asyncio

            _reader_task = asyncio.create_task(_rms_motor_current_i2c_task())
            log("RMS I2C: Reader task started")
        except Exception as e:
            log(f"RMS I2C: Failed to start reader task: {e}")
    else:
        log("RMS I2C: Reader task already running")
