# GPS Synchronization Plan: Pause/Resume with Event + Lock

This plan details the final, robust strategy to prevent race conditions between the GPS NMEA reader task (running in the main `uasyncio` loop) and the GPS configuration functions (called from the synchronous web server thread). It uses both an `asyncio.Event` for pausing the reader and a `_thread.allocate_lock` for preventing concurrent configuration calls.

## 1. Modify `gps_reader.py`

### 1.1 Add Imports and Synchronization Primitives

```python
# gps_reader.py
from machine import UART, Pin
import uasyncio as asyncio # Ensure asyncio is imported
import time
from _thread import allocate_lock # Keep the thread lock
from log import log

# --- Configuration ---
# ... (unchanged) ...

# --- State ---
uart = None
# ... (other state variables unchanged) ...
_reader_task = None
_uart_lock = allocate_lock() # Keep thread lock for config functions
_reader_paused_event = asyncio.Event() # Event to signal pause/resume
_reader_paused_event.set() # Initialize as NOT paused (set means running)
# ... (rest of state variables unchanged) ...

# --- Getter Functions ---
def get_uart():
    """Returns the initialized UART object for the GPS."""
    return uart

def get_uart_lock():
    """Returns the thread-safe Lock used for UART access between config functions."""
    return _uart_lock

def get_pause_event():
    """Returns the asyncio Event used to pause/resume the reader task."""
    return _reader_paused_event

# ... (NMEA parsing functions unchanged) ...
# ... (init_gps_reader unchanged) ...
```

### 1.2 Modify `_read_gps_task`

Add the check for the pause event at the beginning of the loop.

```python
# gps_reader.py

async def _read_gps_task():
    """Asynchronous task to continuously read and parse NMEA sentences from GPS."""
    # ... (initial checks unchanged) ...
    log("Starting GPS NMEA reader task...")
    reader = asyncio.StreamReader(uart)
    _reader_paused_event.set() # Ensure reader starts in running state

    while True:
        try:
            # --- Check Pause Event ---
            # If event is cleared, wait here until it's set again
            if not _reader_paused_event.is_set():
                log("GPS Reader: Paused.")
                await _reader_paused_event.wait() # type: ignore # Non-blocking wait for event
                log("GPS Reader: Resumed.")
                # Optional: Flush buffer after resuming?
                if uart.any():
                     flushed = uart.read(uart.any())
                     log(f"GPS Reader: Flushed {len(flushed)} bytes after resume.")

            # --- Original Reading Logic ---
            line_bytes = await reader.readline()
            # ... (rest of reading and parsing logic unchanged) ...

        except asyncio.CancelledError:
             log("GPS Reader: Task cancelled.")
             _reader_paused_event.set() # Ensure event is set on exit
             raise # Re-raise CancelledError
        except Exception as e:
            log(f"Error in GPS reader task loop: {e}")
            _reader_paused_event.set() # Ensure event is set on error exit
            await asyncio.sleep_ms(500)

        # Removed final sleep_ms(50) as readline yields
```

### 1.3 Add/Modify `start_gps_reader` and `stop_gps_reader`

```python
# gps_reader.py

def start_gps_reader():
    """Starts the asynchronous GPS NMEA reader task if not already running."""
    global _reader_task
    if uart is None:
        log("Cannot start GPS reader: UART not initialized.")
        return False
    # Check if task exists and is still running (or finished cleanly)
    # A task object exists even after it finishes/is cancelled
    if _reader_task is None or _reader_task.done(): # Check if None or done
        _reader_task = asyncio.create_task(_read_gps_task())
        log("GPS NMEA reader task created/restarted.")
        return True
    else:
        log("GPS NMEA reader task already running.")
        return False

def stop_gps_reader():
    """Stops the asynchronous GPS NMEA reader task."""
    global _reader_task
    if _reader_task is not None and not _reader_task.done():
        try:
            log("GPS Reader: Attempting to cancel task...")
            _reader_task.cancel()
            # Note: We don't await the cancellation here as this is called
            # from a synchronous context. The config functions will handle waiting.
            log("GPS Reader: Cancellation requested.")
            # Setting task to None immediately might be premature,
            # let the config function await it if needed.
            # _reader_task = None
            return True
        except Exception as e:
            log(f"Error cancelling GPS reader task: {e}")
            return False
    elif _reader_task and _reader_task.done():
        log("GPS Reader: Task already finished.")
        _reader_task = None # Clean up reference
        return True
    else:
        log("GPS Reader: Task not running.")
        return True # Considered success if already stopped

def get_reader_task():
     """Returns the current reader task object (or None)."""
     return _reader_task

# ... (rest of data access functions unchanged) ...
```

**Key Changes in `gps_reader.py`:**

- Added `_reader_paused_event = asyncio.Event()`, initialized `set()`.
- Added `get_pause_event()`.
- Kept `_uart_lock` and `get_uart_lock()`.
- Modified `_read_gps_task` to check and `await _reader_paused_event.wait()`. Added `CancelledError` handling.
- Added `stop_gps_reader()` function to request cancellation.
- Modified `start_gps_reader()` to handle restarting after cancellation/completion.
- Added `get_reader_task()` to allow config functions to potentially `await` the cancelled task.

## 2. Modify `gps_config.py`

### 2.1 Add Imports

```python
# gps_config.py
import uasyncio as asyncio # Add asyncio import
import struct
import time
import json
from log import log
from machine import UART
from . import gps_reader # Ensure gps_reader is imported
from server_framework import Response, Request
# ... (rest of imports/constants unchanged) ...
```

### 2.2 Modify Functions Requiring Exclusive Access

Apply the following pattern to `get_nav_rate`, `set_nav_rate`, and `factory_reset`. The internal `_save_configuration` doesn't need the pattern directly as it will be called by `set_nav_rate` which already holds the lock and manages the pause event.

**Example: Modifying `get_nav_rate`**

```python
# gps_config.py

def get_nav_rate(uart: UART, lock): # Keep lock parameter for inter-thread safety
    """Polls and parses the current navigation measurement and solution rate (CFG-RATE)."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for get_nav_rate")
        return None

    lock_acquired = False
    result_data = None
    pause_event = gps_reader.get_pause_event() # Get the event

    try:
        # --- Pause Reader ---
        if pause_event and pause_event.is_set():
            log("GPS CFG: Signaling reader task pause for get_nav_rate...")
            pause_event.clear() # Signal pause
            # Give event loop a chance to schedule the reader task to see the event
            # This is still a small delay, but necessary for the event mechanism.
            time.sleep_ms(20)

        # --- Acquire Lock (Blocks this thread, allows asyncio loop to run) ---
        log("GPS CFG: Acquiring UART lock for get_nav_rate...")
        lock_acquired = lock.acquire(True, 1.0) # Wait up to 1 sec
        if not lock_acquired:
            log("GPS CFG Error: Could not acquire UART lock for get_nav_rate")
            # Resume reader before returning (handled in finally)
            return None
        log("GPS CFG: UART lock acquired.")

        # --- Perform UART Operations ---
        log("GPS CFG: Polling current nav rate (CFG-RATE)")
        send_ok = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE)
        if not send_ok:
             log("GPS CFG Error: Failed to send poll request for CFG-RATE")
             # result_data remains None
        else:
            # Reader is paused, now read response
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
            log("GPS CFG: Releasing UART lock.")
            lock.release()
        # --- Resume Reader ---
        if pause_event and not pause_event.is_set():
            log("GPS CFG: Resuming reader task after get_nav_rate.")
            pause_event.set() # Signal resume

    return result_data
```

**Apply Similar Pattern:**

Wrap the core logic (after checking `uart` and `lock` availability) of `set_nav_rate` and `factory_reset` within the `try...finally` block that includes:

1. Getting the `pause_event`.
2. `pause_event.clear()`.
3. `time.sleep_ms(20)` (or similar small delay).
4. `lock_acquired = lock.acquire(True, 1.0)`. Handle failure.
5. Performing UART operations (`_send_ubx_command`, `_read_ubx_response`, call to `_save_configuration` inside `set_nav_rate`).
6. Releasing the lock in `finally` (if acquired).
7. `pause_event.set()` in `finally` (if event exists and was cleared).

**Important:** The call `save_success = _save_configuration(uart, lock)` inside `set_nav_rate` is correct. `_save_configuration` itself does _not_ need the pause/resume/lock logic internally, because its caller (`set_nav_rate`) already handles pausing the reader and holds the lock.

## 3. Re-enable Reader Task

Ensure that `gps_reader.start_gps_reader()` is called in your main application startup sequence (e.g., in `main.py` or `init_io.py`) after `gps_reader.init_gps_reader()`.

## Summary

This approach uses the `asyncio.Event` to correctly signal the async reader task to pause/resume, yielding control appropriately within the `uasyncio` loop. It uses the `_thread.allocate_lock` to prevent multiple web server threads from interfering with each other during the pause-config-resume sequence. This should provide robust synchronization.
