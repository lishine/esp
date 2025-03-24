# ESP32 MicroPython Recovery Strategies

This document outlines potential recovery strategies that could be implemented to further enhance the robustness of the ESP32 MicroPython system against code errors.

## 1. Safe Boot System

Implement a boot counter mechanism that tracks failed boot attempts and enters a recovery mode after multiple failures:

```python
# Modified boot.py
import sys
import machine
import time
from log import log

# Flag file to indicate boot attempts
BOOT_COUNTER_FILE = 'boot_attempts.txt'
MAX_BOOT_ATTEMPTS = 3

def increment_boot_counter():
    try:
        try:
            with open(BOOT_COUNTER_FILE, 'r') as f:
                count = int(f.read().strip() or '0')
        except:
            count = 0

        count += 1

        with open(BOOT_COUNTER_FILE, 'w') as f:
            f.write(str(count))

        return count
    except:
        return 999  # Assume high count if can't read/write

def reset_boot_counter():
    try:
        with open(BOOT_COUNTER_FILE, 'w') as f:
            f.write('0')
    except:
        pass

# Check boot counter
boot_count = increment_boot_counter()

log("\n" + "=" * 40)
log(f"ESP32 Device Starting... (Boot attempt: {boot_count}/{MAX_BOOT_ATTEMPTS})")
log("=" * 40)

# If too many boot attempts, enter recovery mode
if boot_count >= MAX_BOOT_ATTEMPTS:
    log("Too many failed boot attempts, entering recovery mode")
    # Reset counter for next boot
    reset_boot_counter()

    # Start minimal recovery system
    try:
        import ap
        ap.start_ap(essid="DDDEV_RECOVERY", password="")

        # Import a minimal recovery server that only allows file operations
        try:
            import recovery
            recovery.start()
        except Exception as e:
            log("Error starting recovery server:", e)
            sys.print_exception(e)
    except Exception as e:
        log("Critical error in recovery mode:", e)
        sys.print_exception(e)
else:
    # Normal boot
    try:
        import ap
        import wifi
        import server

        ap.start_ap(essid="DDDEV", password="")
        wifi.start_wifi()
        server.start_server()

        log(
            f"""
Device is ready:
- AP mode: http://{ap.get_ap_ip()} (SSID: DDDEV)
- Station mode: http://{wifi.get_ip()} (if connected)
            """
        )

        # Boot successful, reset counter
        reset_boot_counter()

    except Exception as e:
        log("Error during initialization:", e)
        sys.print_exception(e)
        # Counter will remain incremented for next boot
```

## 2. Recovery Server Module

Create a minimal server that only allows file operations, to be used in recovery mode:

```python
# recovery.py
from microdot import Microdot, Response
import json
import _thread
import machine
import os
from log import log

# Create minimal recovery app
app = Microdot()

@app.route('/')
def index(request):
    return """
    <html>
    <head><title>ESP32 Recovery Mode</title></head>
    <body>
        <h1>ESP32 Recovery Mode</h1>
        <p>The device is in recovery mode due to boot failures.</p>
        <p>You can upload fixed files or reset the device.</p>
        <p><a href="/reset">Reset Device</a></p>
    </body>
    </html>
    """

@app.route('/reset', methods=['GET'])
def reset(request):
    import _thread
    import time

    def delayed_reset():
        time.sleep(0.1)
        machine.reset()

    _thread.start_new_thread(delayed_reset, ())
    return "Device resetting..."

@app.route('/upload/<path:target_path>', methods=['POST'])
async def upload_file(request, target_path):
    try:
        # Simple direct file write
        f = open(target_path, 'wb')
        f.write(request.body)
        f.close()

        return json.dumps({
            'success': True,
            'path': target_path,
            'size': len(request.body)
        }), 200
    except Exception as e:
        return json.dumps({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/log')
def show_log(request):
    from log import log_buffer
    return '\n'.join(log_buffer.get_all())

def start():
    _thread.start_new_thread(lambda: app.run(port=80), ())
    log("Recovery server started")
```

## 3. Watchdog Timer

Add a watchdog timer to automatically reset if the system hangs:

```python
# Add to beginning of boot.py
import machine

# Set up watchdog with 30 second timeout
wdt = machine.WDT(timeout=30000)

# Add periodic wdt.feed() calls in your main loop
# or disable it once boot is complete
```

## 4. Safe Module Import System

Create a wrapper for importing modules that catches and logs errors:

```python
# safe_import.py
import sys
from log import log

def safe_import(module_name):
    """
    Safely import a module, catching and logging any errors
    Returns the module if successful, None if failed
    """
    try:
        module = __import__(module_name)
        return module
    except Exception as e:
        log(f"Error importing module {module_name}: {e}")
        sys.print_exception(e)
        return None

# Usage in boot.py:
# ap = safe_import('ap')
# if ap:
#     ap.start_ap(essid="DDDEV", password="")
# else:
#     log("Failed to start AP mode")
```

## 5. Versioned Backups

Implement a system that keeps multiple versions of critical files:

```python
# In fs.py
def backup_with_version(file_path, max_backups=3):
    """Create a versioned backup of a file"""
    import os

    # Check if file exists
    if not os.path.exists(file_path):
        return False

    # Get list of existing backups
    backups = []
    for i in range(max_backups):
        backup_path = f"{file_path}.bak{i}"
        if os.path.exists(backup_path):
            backups.append((i, backup_path))

    # Sort by version number
    backups.sort()

    # If we have max backups, remove the oldest
    if len(backups) >= max_backups:
        os.remove(backups[0][1])
        backups.pop(0)

    # Shift all backups up one version
    for version, path in reversed(backups):
        new_path = f"{file_path}.bak{version+1}"
        os.rename(path, new_path)

    # Create new backup as version 0
    with open(file_path, 'rb') as src:
        with open(f"{file_path}.bak0", 'wb') as dst:
            while True:
                chunk = src.read(512)
                if not chunk:
                    break
                dst.write(chunk)

    return True
```

## Implementation Priority

1. Safe Boot System - Provides a way to recover from boot failures
2. Recovery Server Module - Needed for the Safe Boot System
3. Watchdog Timer - Simple to implement and provides a last resort
4. Safe Module Import System - Helps diagnose import errors
5. Versioned Backups - More advanced feature for critical files
