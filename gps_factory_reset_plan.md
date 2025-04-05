# GPS Factory Reset Feature - Implementation Plan

This plan details the steps to add a Factory Reset button to the GPS settings web interface.

## 1. Modify `device/io_local/gps_settings.html`

Add a new section for the reset button and the corresponding JavaScript logic.

**HTML Addition (e.g., after the Set Rate section):**

```html
    <!-- ... existing sections ... -->

    <div class="setting" style="border-color: #ffcccc;">
        <label>Factory Reset:</label>
        <button id="factoryResetBtn" style="background-color: #ffdddd; color: #a00;">Reset GPS to Defaults</button>
        <p style="font-size: 0.8em; color: #666;">Warning: This will erase all custom configurations on the GPS module.</p>
    </div>

    <div id="status"></div>

    <script>
        // ... existing const declarations (getRateBtn, setRateBtn, etc.) ...
        const factoryResetBtn = document.getElementById('factoryResetBtn');
        // ... existing statusDiv declaration ...

        // ... existing showStatus function ...

        // ... existing getRateBtn event listener ...

        // ... existing setRateBtn event listener ...

        // --- Factory Reset Button Event Listener ---
        factoryResetBtn.addEventListener('click', async () => {
            // Confirmation Dialog
            if (!confirm('Are you sure you want to reset the GPS module to factory defaults? All custom settings will be lost.')) {
                showStatus('Factory reset cancelled.', false);
                return;
            }

            statusDiv.textContent = 'Sending factory reset command...';
            statusDiv.style.color = 'orange';
            try {
                const response = await fetch('/api/gps-settings/data', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'factory_reset' })
                });
                const data = await response.json();
                if (response.ok && data.success) {
                    showStatus('Factory reset command sent successfully. Module may restart.', false);
                    // Clear current rate display as it's likely reset
                    currentRateSpan.textContent = '--';
                } else {
                    throw new Error(data.message || 'Failed to send factory reset command.');
                }
            } catch (error) {
                console.error('Error sending factory reset:', error);
                showStatus(`Error: ${error.message}`, true);
            }
        });
    </script>
</body>
</html>
```

## 2. Modify `device/io_local/gps_config.py`

Add handling for the `factory_reset` action within `handle_gps_settings_data`.

```python
# gps_config.py

# ... imports and other functions ...

def handle_gps_settings_data(request: Request):
    """Handles getting and setting GPS configuration via UBX commands."""
    config = json.loads(request.body)

    action = config.get("action")
    uart = gps_reader.get_uart()
    lock = gps_reader.get_uart_lock()

    if not uart or not lock:
        # ... (error handling unchanged) ...
        return Response(...)

    try:
        if action == "get_rate":
            # ... (unchanged) ...
            rate_data = get_nav_rate(uart, lock)
            # ... (response handling unchanged) ...

        elif action == "set_rate":
            # ... (unchanged) ...
            rate_hz = config.get("rate")
            # ... (validation unchanged) ...
            success = set_nav_rate(uart, lock, rate_hz)
            # ... (response handling unchanged) ...

        # --- Add Factory Reset Handling ---
        elif action == "factory_reset":
            log("GPS Settings API: Received factory_reset request")
            success = factory_reset(uart, lock) # Call existing function
            if success:
                log("GPS Settings API: factory_reset successful")
                return Response(
                    body=json.dumps(
                        {
                            "success": True,
                            "message": "Factory reset command sent successfully.",
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
            else:
                log("GPS Settings API Error: factory_reset failed")
                return Response(
                    body=json.dumps(
                        {
                            "success": False,
                            "message": "Failed to send factory reset command to GPS.",
                        }
                    ),
                    status=500,
                    headers={"Content-Type": "application/json"},
                )
        # --- End Factory Reset Handling ---

        else:
            # ... (unknown action handling unchanged) ...
            return Response(...)

    except Exception as e:
        # ... (exception handling unchanged) ...
        return Response(...)

# ... rest of the file (get_nav_rate, set_nav_rate, factory_reset, etc.) ...
```

## Next Steps

1.  Switch to Code mode.
2.  Apply the HTML changes to `device/io_local/gps_settings.html`.
3.  Apply the Python changes to `device/io_local/gps_config.py`.
4.  Upload both modified files.
5.  Test the new "Factory Reset" button on the web interface.
6.  Once confirmed working, create the sub-task for UBX/NMEA switching.
