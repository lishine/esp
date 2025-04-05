# GPS Synchronization Plan: Manual User Control via Web UI

This plan details reverting complex synchronization logic and implementing a user-controlled enable/disable switch for the GPS reader task via the web interface.

**Goal:** Allow the user to manually stop the GPS reader task before performing configuration actions and restart it afterwards, avoiding automatic synchronization complexity but placing responsibility on the user.

**Primitives:**

- `_reader_enabled_event` (`asyncio.Event`): Controls whether the reader task actively reads data. Set = Enabled, Clear = Disabled/Paused. Initial state: **Set** (Enabled).

## 1. Revert Previous Synchronization Logic (Conceptual)

Before applying the new changes, ensure `gps_reader.py` and `gps_config.py` are reverted to the state _after_ the `bytearray.clear()` fixes and the `get_nav_rate` implementation, but _before_ any "Pause/Resume+Event+Lock" or "Cancel+Lock" logic was added. This means:

- `gps_reader.py` should not contain `_config_request_event`, `_config_done_event`, or `stop_gps_reader`. The `_read_gps_task` should not acquire/release the `_uart_lock`.
- `gps_config.py` functions (`get_nav_rate`, `set_nav_rate`, `factory_reset`) should not contain any event signaling or lock acquisition/release logic related to pausing/stopping the reader. The `lock` parameter should be removed if present from previous attempts.

## 2. Modify `gps_reader.py`

### 2.1 Add Event and Getter

```python
# gps_reader.py
from machine import UART, Pin
import uasyncio as asyncio
import time
# from _thread import allocate_lock # No longer needed
from log import log

# --- Configuration ---
# ... (unchanged) ...

# --- State ---
uart = None
# ... (other state variables unchanged) ...
_reader_task = None
# _uart_lock = allocate_lock() # REMOVED
_reader_enabled_event = asyncio.Event() # New: Controls reader activity
_reader_enabled_event.set() # Start enabled
# ... (rest of state variables unchanged) ...

# --- Getter Functions ---
def get_uart():
    return uart

# def get_uart_lock(): # REMOVED
#     return _uart_lock

def get_reader_enabled_event():
    """Returns the event controlling the reader task's active state."""
    return _reader_enabled_event

# ... (NMEA parsing functions unchanged) ...
# ... (init_gps_reader unchanged) ...
```

### 2.2 Modify `_read_gps_task`

Add a check for the `_reader_enabled_event` at the start of the loop.

```python
# gps_reader.py

async def _read_gps_task():
    """Asynchronous task to continuously read and parse NMEA sentences from GPS."""
    if uart is None:
        log("GPS UART not initialized. Cannot start reader task.")
        return

    log("Starting GPS NMEA reader task...")
    reader = asyncio.StreamReader(uart)
    _reader_enabled_event.set() # Ensure reader starts enabled

    while True:
        try:
            # --- Check if Enabled ---
            if not _reader_enabled_event.is_set():
                log("GPS Reader: Disabled by user. Waiting...")
                await _reader_enabled_event.wait() # type: ignore # Wait until enabled
                log("GPS Reader: Re-enabled by user.")
                # Optional: Flush buffer after re-enabling?
                if uart.any():
                     flushed = uart.read(uart.any())
                     log(f"GPS Reader: Flushed {len(flushed)} bytes after re-enable.")

            # --- Normal Read Operation (No Lock Needed Here) ---
            line_bytes = await reader.readline() # type: ignore

            if not line_bytes:
                await asyncio.sleep_ms(1050)
                continue
            else:
                # --- Parsing Logic ---
                # ... (Parsing, checksum, state updates - unchanged) ...
                start_time_us = time.ticks_us()
                try:
                    line = line_bytes.decode("ascii").strip()
                except UnicodeError:
                    log("GPS RX: Invalid ASCII data received")
                    continue

                if not line.startswith("$") or "*" not in line:
                    continue

                # Checksum Verification ...
                # Parse Specific Sentences ...
                # Update Stats ...

        except asyncio.CancelledError:
             log("GPS Reader: Task cancelled.")
             _reader_enabled_event.set() # Ensure enabled on exit? Or leave as is? Let's set it.
             raise
        except Exception as e:
            log(f"Error in GPS reader task loop: {e}")
            _reader_enabled_event.set() # Ensure enabled on error exit
            await asyncio.sleep_ms(500)
```

### 2.3 Modify `start_gps_reader`

Ensure the event is set when starting.

```python
# gps_reader.py

def start_gps_reader():
    """Starts the asynchronous GPS NMEA reader task if not already running."""
    global _reader_task
    if uart is None:
        log("Cannot start GPS reader: UART not initialized.")
        return False
    if _reader_task is None or _reader_task.done(): # type: ignore
        _reader_enabled_event.set() # Ensure reader starts enabled
        _reader_task = asyncio.create_task(_read_gps_task())
        log("GPS NMEA reader task created/restarted.")
        return True
    else:
        # If already running, ensure it's enabled
        if not _reader_enabled_event.is_set():
             _reader_enabled_event.set()
             log("GPS NMEA reader task was paused, re-enabling.")
        else:
             log("GPS NMEA reader task already running.")
        return True # Consider it success if already running
```

## 3. Modify `gps_config.py`

### 3.1 Remove Lock Parameter and Logic

Remove the `lock` parameter from the definitions and calls of `get_nav_rate`, `set_nav_rate`, `factory_reset`, and `_save_configuration`. Remove all `lock.acquire()` and `lock.release()` calls and associated `try...finally` blocks _related to the lock_.

### 3.2 Add New Actions to `handle_gps_settings_data`

```python
# gps_config.py

# ... imports ...

def handle_gps_settings_data(request: Request):
    """Handles getting and setting GPS configuration via UBX commands."""
    config = json.loads(request.body)
    action = config.get("action")
    uart = gps_reader.get_uart()
    # lock = gps_reader.get_uart_lock() # REMOVED

    # if not uart or not lock: # REMOVED lock check
    if not uart:
        log("GPS Settings API Error: UART not available")
        return Response(...) # Error response

    reader_enabled_event = gps_reader.get_reader_enabled_event()
    if not reader_enabled_event:
         log("GPS Settings API Error: Could not get reader enabled event.")
         return Response(...) # Error response

    try:
        if action == "get_rate":
            log("GPS Settings API: Received get_rate request")
            # WARNING: User must manually disable reader first!
            if reader_enabled_event.is_set():
                 log("GPS Settings API Warning: get_rate called while reader may be active!")
            rate_data = get_nav_rate(uart) # REMOVED lock
            # ... (response handling) ...

        elif action == "set_rate":
            log("GPS Settings API: Received set_rate request")
            # WARNING: User must manually disable reader first!
            if reader_enabled_event.is_set():
                 log("GPS Settings API Warning: set_rate called while reader may be active!")
            rate_hz = config.get("rate")
            # ... (validation) ...
            success = set_nav_rate(uart, rate_hz) # REMOVED lock
            # ... (response handling) ...

        elif action == "factory_reset":
            log("GPS Settings API: Received factory_reset request")
            # WARNING: User must manually disable reader first!
            if reader_enabled_event.is_set():
                 log("GPS Settings API Warning: factory_reset called while reader may be active!")
            success = factory_reset(uart) # REMOVED lock
            # ... (response handling) ...

        # --- Add Reader Control Actions ---
        elif action == "start_reader":
             log("GPS Settings API: Received start_reader request")
             reader_enabled_event.set()
             # Optionally call start_gps_reader ensure task is running if stopped previously
             gps_reader.start_gps_reader()
             log("GPS Settings API: Reader enabled.")
             return Response(body=json.dumps({"success": True, "message": "GPS Reader enabled."}), headers={"Content-Type": "application/json"})

        elif action == "stop_reader":
             log("GPS Settings API: Received stop_reader request")
             reader_enabled_event.clear()
             log("GPS Settings API: Reader disabled.")
             # We don't stop the task itself, just signal it to pause in its loop
             return Response(body=json.dumps({"success": True, "message": "GPS Reader disabled."}), headers={"Content-Type": "application/json"})
        # --- End Reader Control Actions ---

        else:
            # ... (unknown action handling) ...

    except Exception as e:
        # ... (exception handling) ...
        # Ensure reader is re-enabled on error? Maybe not, user controls it.
        # reader_enabled_event.set() # Consider if this is desired
        return Response(...)

# ... (get_nav_rate, set_nav_rate, factory_reset definitions updated to remove lock parameter) ...
# Example:
# def get_nav_rate(uart: UART): # No lock parameter
#    # ... direct UART operations ...
```

## 4. Modify `device/io_local/gps_settings.html`

Add controls (e.g., a toggle switch or two buttons) to send the `start_reader` and `stop_reader` actions. Update the status display accordingly.

**HTML Addition (Example using buttons):**

```html
    <!-- ... existing sections ... -->

    <div class="setting">
        <label>GPS Reader Task:</label>
        <button id="startReaderBtn" style="background-color: #ddffdd;">Enable Reader</button>
        <button id="stopReaderBtn" style="background-color: #ffdddd;">Disable Reader</button>
        <span id="readerStatus" style="margin-left: 10px;">(Unknown)</span>
        <p style="font-size: 0.8em; color: #666;">Disable the reader before using Set Rate or Factory Reset.</p>
    </div>

    <!-- ... status div ... -->

    <script>
        // ... existing const declarations ...
        const startReaderBtn = document.getElementById('startReaderBtn');
        const stopReaderBtn = document.getElementById('stopReaderBtn');
        const readerStatusSpan = document.getElementById('readerStatus');

        // ... existing showStatus function ...

        // --- Reader Control Button Event Listeners ---
        async function controlReader(action) {
             const actionText = action === 'start_reader' ? 'Enabling' : 'Disabling';
             statusDiv.textContent = `${actionText} reader...`;
             statusDiv.style.color = 'black';
             readerStatusSpan.textContent = '(Processing...)';
             try {
                 const response = await fetch('/api/gps-settings/data', {
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify({ action: action })
                 });
                 const data = await response.json();
                 if (response.ok && data.success) {
                     showStatus(data.message || `${actionText} successful.`);
                     readerStatusSpan.textContent = action === 'start_reader' ? '(Enabled)' : '(Disabled)';
                 } else {
                     throw new Error(data.message || `Failed to ${actionText.toLowerCase()} reader.`);
                 }
             } catch (error) {
                 console.error(`Error ${actionText.toLowerCase()} reader:`, error);
                 showStatus(`Error: ${error.message}`, true);
                 readerStatusSpan.textContent = '(Error)';
             }
        }

        startReaderBtn.addEventListener('click', () => controlReader('start_reader'));
        stopReaderBtn.addEventListener('click', () => controlReader('stop_reader'));

        // TODO: Optionally add a way to query initial reader status on page load

        // ... existing getRateBtn, setRateBtn, factoryResetBtn listeners ...
        // Add warnings to other listeners if readerStatusSpan doesn't indicate '(Disabled)'?
    </script>
</body>
</html>
```

## Summary

This approach simplifies the code by removing automatic synchronization but requires the user to manually disable the reader via the UI before performing configuration actions to prevent errors.
