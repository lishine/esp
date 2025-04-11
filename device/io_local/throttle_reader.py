import uasyncio as asyncio
from log import log
from lib.ppm_reader import PpmReader

_ppm_reader = None  # type: PpmReader | None
_reader_task = None  # type: asyncio.Task | None
_last_value = None  # type: float | None
_last_log_time = 0  # type: int


def init_throttle_reader() -> None:
    """Initialize the PPM reader for throttle on pin 9, single channel."""
    global _ppm_reader
    _ppm_reader = PpmReader(9, 1)


async def _throttle_reader_task() -> None:
    """Async task to monitor throttle PPM value and log changes (rate-limited)."""
    global _ppm_reader, _last_value, _last_log_time
    first_packet_printed = False
    import utime

    while True:
        await asyncio.sleep_ms(100)
        if _ppm_reader is None:
            continue
        if _ppm_reader.get_valid_packets() == 0:
            continue
        value = _ppm_reader.get_value(0)
        if not first_packet_printed:
            print("PPM throttle available")
            first_packet_printed = True
        if _last_value is None or value != _last_value:
            now = utime.ticks_ms() // 1000
            if now - _last_log_time >= 1:
                log(f"PPM throttle changed: {value:.3f}")
                _last_log_time = now
            _last_value = value


def start_throttle_reader() -> None:
    """Start the async throttle reader task if not already running."""
    global _reader_task
    if _reader_task is None:
        try:
            import uasyncio as asyncio

            _reader_task = asyncio.create_task(_throttle_reader_task())
            log("Throttle PPM reader task started")
        except Exception as e:
            log(f"Throttle PPM: Failed to start reader task: {e}")
    else:
        log("Throttle PPM: Reader task already running")
