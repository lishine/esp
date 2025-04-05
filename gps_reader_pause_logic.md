# GPS Reader Pause/Resume Implementation Plan

This plan details the modifications needed for `gps_reader.py` and `gps_config.py` to implement a pause/resume mechanism, preventing race conditions during GPS configuration commands.

## 1. Modify `gps_reader.py`

### 1.1 Add Imports and Event

```python
# gps_reader.py
# ... other imports ...
import uasyncio as asyncio # Ensure asyncio is imported

# --- State ---
# ... existing state variables ...
_reader_paused_event = asyncio.Event() # Event to signal pause
_reader_paused_event.set() # Initialize as NOT paused (set means running)

# ... rest of the state ...

# --- New Getter Function ---
def get_pause_event():
    """Returns the asyncio Event used to pause/resume the reader task."""
    return _reader_paused_event

# ... existing functions ...
```

### 1.2 Modify `_read_gps_task`

Add the check for the pause event at the beginning of the loop.

```python
# gps_reader.py

async def _read_gps_task():
    """Asynchronous task to continuously read and parse NMEA sentences from GPS."""
    if uart is None:
        log("GPS UART not initialized. Cannot start reader task.")
        return

    log("Starting GPS NMEA reader task...")
    reader = asyncio.StreamReader(uart)
    _reader_paused_event.set() # Ensure reader starts in running state

    while True:
        try:
            # --- Check Pause Event ---
            if not _reader_paused_event.is_set():
                log("GPS Reader: Paused.")
                await _reader_paused_event.wait() # Wait here until event is set (resumed)
                log("GPS Reader: Resumed.")
                # Optional: Flush buffer after resuming? Might be needed if config left data.
                if uart.any():
                     flushed = uart.read(uart.any())
                     log(f"GPS Reader: Flushed {len(flushed)} bytes after resume.")

            # --- Original Reading Logic ---
            line_bytes = await reader.readline()

            if not line_bytes:
                # If timeout/empty line, still yield but maybe sleep less if paused?
                # No, keep sleep, timeout indicates no data anyway.
                await asyncio.sleep_ms(1050) # Original sleep
                continue

            # ... rest of the parsing logic (GPGGA, GPRMC, checksum, etc.) ...
            # ... unchanged ...

        except Exception as e:
            log(f"Error in GPS reader task loop: {e}")
            # Ensure reader resumes if an error occurs while paused?
            # The finally block in config functions should handle this.
            await asyncio.sleep_ms(500)

        # Yield control briefly - No longer needed here, readline handles yielding.
        # await asyncio.sleep_ms(50) # REMOVE or comment out this line
```

**Key Changes in `gps_reader.py`:**

- Added `_reader_paused_event = asyncio.Event()`. Initialized to `set()` (running).
- Added `get_pause_event()` function.
- In `_read_gps_task`, added `if not _reader_paused_event.is_set(): await _reader_paused_event.wait()`.
- Added logging for pause/resume.
- Removed the final `await asyncio.sleep_ms(50)` as `readline` handles yielding.

## 2. Modify `gps_config.py`

### 2.1 Add Imports

```python
# gps_config.py
import uasyncio as asyncio # Add asyncio import
# ... other imports ...
from . import gps_reader # Ensure gps_reader is imported to get the event
```

### 2.2 Modify Functions Requiring Exclusive Access

Apply the following pattern to `set_nav_rate`, `get_nav_rate`, `_save_configuration`, and `factory_reset`.

**Example: Modifying `get_nav_rate`**

```python
# gps_config.py

def get_nav_rate(uart: UART, lock):
    """Polls and parses the current navigation measurement and solution rate (CFG-RATE)."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for get_nav_rate")
        return None

    lock_acquired = False
    result_data = None
    pause_event = gps_reader.get_pause_event() # Get the event

    try:
        # --- Pause Reader ---
        if pause_event.is_set():
            log("GPS CFG: Pausing reader task for get_nav_rate...")
            pause_event.clear() # Signal pause
            # MUST yield briefly to allow reader task to process the event change
            # This sleep duration might need tuning, but should be short.
            time.sleep_ms(20) # Allow reader task to hit await pause_event.wait()

        # --- Acquire Lock ---
        lock_acquired = lock.acquire(True, 0.5) # Shorter timeout for lock needed? Maybe 0.5s
        if not lock_acquired:
            log("GPS CFG Error: Could not acquire UART lock for get_nav_rate (reader paused)")
            # Resume reader before returning
            if not pause_event.is_set():
                 pause_event.set()
            return None

        # --- Perform UART Operations ---
        log("GPS CFG: Polling current nav rate (CFG-RATE)")
        if not _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE):
             log("GPS CFG Error: Failed to send poll request for CFG-RATE")
             # result_data remains None
        else:
            response_payload = _read_ubx_response(
                uart,
                expected_class_id=UBX_CLASS_CFG,
                expected_msg_id=UBX_CFG_RATE,
                timeout_ms=1500,
                expect_payload=True
            )
            # ... (parsing logic as implemented previously) ...
            if response_payload is None:
                 log("GPS CFG Error: Timeout or error reading CFG-RATE response")
            elif isinstance(response_payload, bytes) and len(response_payload) == 6:
                 meas_rate_ms, nav_rate_cycles, time_ref = struct.unpack('<HHH', response_payload)
                 rate_hz = 1000.0 / meas_rate_ms if meas_rate_ms > 0 else 0
                 log(f"GPS CFG RX: Parsed CFG-RATE - measRate={meas_rate_ms}ms ({rate_hz:.2f} Hz), navRate={nav_rate_cycles}, timeRef={time_ref}")
                 result_data = { # Populate result
                     "rate_hz": round(rate_hz, 2),
                     "meas_rate_ms": meas_rate_ms,
                     "nav_rate_cycles": nav_rate_cycles,
                     "time_ref": time_ref,
                 }
            else:
                 log(f"GPS CFG Error: Received unexpected response type or length for CFG-RATE poll. Type: {type(response_payload)}")

    finally:
        # --- Release Lock ---
        if lock_acquired:
            lock.release()
        # --- Resume Reader ---
        if not pause_event.is_set():
            log("GPS CFG: Resuming reader task after get_nav_rate.")
            pause_event.set() # Signal resume

    return result_data
```

**Apply Similar Pattern:**

Wrap the core logic (after checking `uart` and `lock` availability) of `set_nav_rate`, `_save_configuration`, and `factory_reset` within the `try...finally` block that includes:

1. Getting the `pause_event`.
2. `pause_event.clear()` before acquiring the lock.
3. `time.sleep_ms(20)` after clearing the event.
4. Acquiring the lock.
5. Performing UART operations.
6. Releasing the lock in `finally`.
7. `pause_event.set()` in `finally` (after releasing lock).

**Important Considerations:**

- **Sleep Duration:** The `time.sleep_ms(20)` after `pause_event.clear()` is crucial. It gives the `asyncio` scheduler time to switch to the `_read_gps_task`, let it see the cleared event, and start awaiting `pause_event.wait()`. Without this, the config task might acquire the lock _before_ the reader task has actually paused, potentially leading to the same race condition or deadlock if the reader holds the lock implicitly via `StreamReader`. This duration might need tuning based on system load.
- **Error Handling:** The `finally` block ensures the reader is always resumed and the lock released, even if errors occur during the UART communication.
- **Lock Timeout:** Consider if the lock acquisition timeout needs adjustment. If the reader task somehow delays pausing, the config task might time out acquiring the lock.

## Next Steps

1.  Switch to Code mode.
2.  Apply these changes to `gps_reader.py` and `gps_config.py`.
3.  Upload the modified code.
4.  Re-enable the GPS reader task in your `main.py` or wherever it was disabled.
5.  Test setting and getting the navigation rate again. Monitor logs for pause/resume messages and successful operations.
