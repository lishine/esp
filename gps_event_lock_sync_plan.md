# GPS Synchronization Plan: Event-Triggered Lock Release

This plan details the strategy to synchronize the async GPS reader task and synchronous configuration functions using a combination of `asyncio.Event`s and a `_thread.allocate_lock`.

**Goal:** Allow config functions (running in a separate thread) to signal the reader task (running in the main asyncio loop) to release the UART lock, wait for the config function to finish, and then resume normal operation.

**Primitives:**

- `_uart_lock` (`_thread.allocate_lock`): Ensures only one entity holds the lock for UART access at a time.
- `_config_request_event` (`asyncio.Event`): Set by config function to signal the reader to release the lock. Cleared by the reader once the signal is seen. Initial state: **Clear**.
- `_config_done_event` (`asyncio.Event`): Set by config function _before_ releasing the lock to signal the reader it can proceed. Cleared by the reader after waiting. Initial state: **Clear**.

## 1. Modify `gps_reader.py`

### 1.1 Add Imports and Synchronization Primitives

```python
# gps_reader.py
from machine import UART, Pin
import uasyncio as asyncio
import time
from _thread import allocate_lock
from log import log

# --- Configuration ---
# ... (unchanged) ...

# --- State ---
uart = None
# ... (other state variables unchanged) ...
_reader_task = None
_uart_lock = allocate_lock() # Keep thread lock
_config_request_event = asyncio.Event() # New: Signal from config to reader
_config_done_event = asyncio.Event() # New: Signal from config to reader
# Removed _reader_paused_event
# ... (rest of state variables unchanged) ...

# --- Getter Functions ---
def get_uart():
    return uart

def get_uart_lock():
    return _uart_lock

def get_config_request_event():
    return _config_request_event

def get_config_done_event():
    return _config_done_event

# ... (NMEA parsing functions unchanged) ...
# ... (init_gps_reader unchanged) ...
```

### 1.2 Modify `_read_gps_task`

The core loop needs restructuring.

```python
# gps_reader.py

async def _read_gps_task():
    """Asynchronous task to continuously read and parse NMEA sentences from GPS."""
    if uart is None:
        log("GPS UART not initialized. Cannot start reader task.")
        return

    log("Starting GPS NMEA reader task...")
    reader = asyncio.StreamReader(uart)
    lock_acquired_by_reader = False

    try:
        while True:
            # --- Try to Acquire Lock ---
            # Non-blocking attempt first
            lock_acquired_by_reader = _uart_lock.acquire(0)
            if not lock_acquired_by_reader:
                # If lock is held (likely by config func), yield briefly and retry loop
                await asyncio.sleep_ms(15) # Yield/short delay
                continue

            # --- Lock Acquired by Reader ---
            try:
                # --- Check if Config Function Wants Lock ---
                if _config_request_event.is_set():
                    log("GPS Reader: Config request detected.")
                    # Flush UART before releasing lock
                    if uart.any():
                        flushed = uart.read(uart.any())
                        log(f"GPS Reader: Flushed {len(flushed)} bytes before releasing lock.")
                    # Clear the request flag
                    _config_request_event.clear()
                    # Release the lock for the config function
                    _uart_lock.release()
                    lock_acquired_by_reader = False # Mark as released
                    log("GPS Reader: Lock released for config.")

                    # --- Wait for Config Function to Finish ---
                    log("GPS Reader: Waiting for config done signal...")
                    await _config_done_event.wait() # type: ignore # Wait until config sets this
                    _config_done_event.clear() # Clear ready for next time
                    log("GPS Reader: Config done signal received. Resuming loop.")
                    # Loop continues, will try to re-acquire lock immediately

                # --- Normal Read Operation (Lock Held) ---
                else:
                    line_bytes = await reader.readline() # type: ignore

                    if not line_bytes:
                        await asyncio.sleep_ms(1050) # Sleep if timeout/empty line
                        # No continue needed here, finally block will release lock

                    else:
                        # --- Parsing Logic (Lock Held) ---
                        # ... (Parsing, checksum, state updates - unchanged) ...
                        start_time_us = time.ticks_us()
                        try:
                            line = line_bytes.decode("ascii").strip()
                        except UnicodeError:
                            log("GPS RX: Invalid ASCII data received")
                            continue # Skip rest of loop iteration, finally releases lock

                        if not line.startswith("$") or "*" not in line:
                            continue # Skip rest of loop iteration, finally releases lock

                        # Checksum Verification
                        parts_checksum = line.split("*")
                        if len(parts_checksum) == 2:
                            sentence = parts_checksum[0]
                            try:
                                received_checksum = int(parts_checksum[1], 16)
                                calculated_checksum = 0
                                for char in sentence[1:]:
                                    calculated_checksum ^= ord(char)
                                if calculated_checksum != received_checksum:
                                    log(f"GPS Checksum error! Line: {line}, Calc: {hex(calculated_checksum)}, Recv: {hex(received_checksum)}")
                                    continue # Skip rest of loop iteration, finally releases lock
                            except ValueError:
                                log(f"GPS Invalid checksum format: {parts_checksum[1]}")
                                continue # Skip rest of loop iteration, finally releases lock
                        else:
                            log(f"GPS Malformed NMEA (no checksum?): {line}")
                            continue # Skip rest of loop iteration, finally releases lock

                        # Parse Specific Sentences
                        parts = sentence.split(",")
                        sentence_type = parts[0]
                        parsed_successfully = False
                        if sentence_type == "$GPGGA" and len(parts) >= 10:
                            _parse_gpgga(parts)
                            parsed_successfully = True
                        elif sentence_type == "$GPRMC" and len(parts) >= 10:
                            _parse_gprmc(parts)
                            parsed_successfully = True

                        if parsed_successfully:
                            global _last_valid_data_time
                            _last_valid_data_time = time.ticks_ms()

                        # Update Stats
                        end_time_us = time.ticks_us()
                        duration_us = time.ticks_diff(end_time_us, start_time_us)
                        global _gps_processing_time_us_sum, _gps_processed_sentence_count
                        _gps_processing_time_us_sum += duration_us
                        _gps_processed_sentence_count += 1

            finally:
                # --- Release Lock (if held by this iteration) ---
                if lock_acquired_by_reader:
                    _uart_lock.release()
                    lock_acquired_by_reader = False # Ensure state is correct for next loop

    except asyncio.CancelledError:
        log("GPS Reader: Task cancelled.")
        # Ensure lock is released if held during cancellation
        if lock_acquired_by_reader:
            _uart_lock.release()
        raise
    except Exception as e:
        log(f"Error in GPS reader task loop: {e}")
        # Ensure lock is released if held during exception
        if lock_acquired_by_reader:
            _uart_lock.release()
        await asyncio.sleep_ms(500)
```

### 1.3 Modify `start_gps_reader`

Ensure events are cleared when starting.

```python
# gps_reader.py

def start_gps_reader():
    """Starts the asynchronous GPS NMEA reader task if not already running."""
    global _reader_task
    if uart is None:
        log("Cannot start GPS reader: UART not initialized.")
        return False
    if _reader_task is None or _reader_task.done(): # type: ignore
        # Clear events before starting
        _config_request_event.clear()
        _config_done_event.clear()
        _reader_task = asyncio.create_task(_read_gps_task())
        log("GPS NMEA reader task created/restarted.")
        return True
    else:
        log("GPS NMEA reader task already running.")
        return False

# Remove stop_gps_reader function - cancellation is no longer used
```

**Key Changes in `gps_reader.py`:**

- Added `_config_request_event` and `_config_done_event`.
- Added getters for the new events.
- Removed pause event logic.
- Restructured `_read_gps_task` loop: acquire lock -> check request event -> if request: flush, clear request, release lock, await done event -> else: read/process -> finally: release lock.
- `start_gps_reader` now clears the new events.
- Removed `stop_gps_reader`.

## 2. Modify `gps_config.py`

### 2.1 Add Imports

```python
# gps_config.py
import uasyncio as asyncio # Keep asyncio import
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

Apply the following pattern to `get_nav_rate`, `set_nav_rate`, and `factory_reset`.

**Example: Modifying `get_nav_rate`**

```python
# gps_config.py

def get_nav_rate(uart: UART, lock): # Keep lock parameter
    """Polls and parses the current navigation measurement and solution rate (CFG-RATE)."""
    if not uart or not lock:
        log("GPS CFG Error: UART or Lock not available for get_nav_rate")
        return None

    lock_acquired_by_config = False
    result_data = None
    config_request_event = gps_reader.get_config_request_event()
    config_done_event = gps_reader.get_config_done_event()

    if not config_request_event or not config_done_event:
         log("GPS CFG Error: Could not get sync events.")
         return None

    try:
        # --- Signal Reader ---
        log("GPS CFG: Signaling reader task for get_nav_rate...")
        config_request_event.set()

        # --- Acquire Lock (Wait for reader to see event and release lock) ---
        log("GPS CFG: Acquiring UART lock for get_nav_rate (waiting for reader release)...")
        lock_acquired_by_config = lock.acquire(True, 1.5) # Wait up to 1.5 sec
        if not lock_acquired_by_config:
            log("GPS CFG Error: Could not acquire UART lock for get_nav_rate (timeout waiting for reader release).")
            config_request_event.clear() # Clear request if we timed out
            return None
        log("GPS CFG: UART lock acquired.")

        # --- Perform UART Operations (Lock Held) ---
        log("GPS CFG: Polling current nav rate (CFG-RATE)")
        send_ok = _send_ubx_command(uart, UBX_CLASS_CFG, UBX_CFG_RATE)
        if not send_ok:
             log("GPS CFG Error: Failed to send poll request for CFG-RATE")
             # result_data remains None
        else:
            # Reader is waiting, now read response
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
        # --- Signal Reader Done (BEFORE releasing lock) ---
        log("GPS CFG: Signaling reader task done.")
        config_done_event.set()

        # --- Release Lock ---
        if lock_acquired_by_config:
            log("GPS CFG: Releasing UART lock.")
            lock.release()
        # --- Ensure request event is clear (in case of errors before reader saw it) ---
        if config_request_event.is_set():
             config_request_event.clear()

    return result_data
```

**Apply Similar Pattern:**

Wrap the core logic (after checking `uart` and `lock` availability) of `set_nav_rate` and `factory_reset` within the `try...finally` block that includes:

1. Getting the `config_request_event` and `config_done_event`.
2. `config_request_event.set()`.
3. `lock_acquired = lock.acquire(True, 1.5)`. Handle failure.
4. Performing UART operations (`_send_ubx_command`, `_read_ubx_response`, call to `_save_configuration` inside `set_nav_rate`).
5. Setting `config_done_event.set()` in `finally`.
6. Releasing the lock in `finally` (if acquired).
7. Clearing `config_request_event` in `finally` just in case.

**Important:** The call `save_success = _save_configuration(uart, lock)` inside `set_nav_rate` remains correct. `_save_configuration` doesn't need the event/lock logic itself as the caller (`set_nav_rate`) manages the synchronization.

## Summary

This approach uses events to coordinate the state transition (reader pausing/resuming) and the lock to ensure exclusive access during the critical section. It avoids task cancellation and keeps the config functions synchronous.
