import uasyncio as asyncio
from machine import I2C, Pin
from log import log
from . import data_log

I2C_ID = 0
I2C_SCL_PIN = 39
I2C_SDA_PIN = 38
I2C_FREQ = 400_000
I2C_ADDR = 0x08

_i2c = None
_reader_task = None

SENSOR_NAME = "motor current"
FACTOR = 0.2


def init_rms_motor_current_i2c() -> None:
    """Initialize I2C for RMS motor current reading and check device presence."""
    global _i2c
    try:
        _i2c = I2C(
            I2C_ID,
            scl=Pin(I2C_SCL_PIN),
            sda=Pin(I2C_SDA_PIN),
            freq=I2C_FREQ,
            timeout=50,
        )
        log(f"RMS I2C: I2C object created: {_i2c}")  # Add log here
        devices = _i2c.scan()
        if I2C_ADDR not in devices:
            log(f"RMS I2C: Device not found at address 0x{I2C_ADDR:02X}")
        else:
            log(f"RMS I2C: Device found at address 0x{I2C_ADDR:02X}")
    except Exception as e:
        log(f"RMS I2C: Initialization error: {e}")
        _i2c = None


async def _rms_motor_current_i2c_task() -> None:
    """Async task to poll RMS motor current from I2C 10 times/sec, log once/sec."""
    global _i2c
    import time

    while True:
        try:
            if _i2c is None:
                data_log.report_error(
                    SENSOR_NAME,
                    time.ticks_ms(),
                    "RMS I2C: Not initialized, skipping read",
                )
            else:
                data = _i2c.readfrom(I2C_ADDR, 2)
                if len(data) == 2:
                    rms_mv = data[0] | (data[1] << 8)
                    data_log.report_data(SENSOR_NAME, time.ticks_ms(), rms_mv * FACTOR)
                else:
                    data_log.report_error(
                        SENSOR_NAME,
                        time.ticks_ms(),
                        f"RMS I2C: Incomplete read, got {len(data)} bytes",
                    )
        except Exception as e:
            pass
            data_log.report_error(
                SENSOR_NAME,
                time.ticks_ms(),
                "no data",
            )
        await asyncio.sleep(0.35)


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
