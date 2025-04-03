import uasyncio as asyncio
import sys
import esp32  # Import esp32 module for heap info
import gc  # Import garbage collector module for mem_free


# Core project modules
from log import log, _log_writer_task
import server
import led
import wifi
import ap

# IO related modules
import io_local.init_io as init_io
import io_local.data_log as data_log
import io_local.gps_reader as gps_reader  # Only needed for gps_reader.start_gps_reader()

# --- Constants ---
# Removed DATA_LOG_INTERVAL_S (moved to data_log.py)

# --- Sensor Initialization ---
# Removed init_sensors() function (moved to init_io.py)

# --- Data Logging Task ---
# Removed data_log_task() function (moved to data_log.py)


async def main():
    log("main.py: Starting...")  # Changed log.log to log
    try:
        # --- Initialize Core Services ---
        # Start logger task first
        log("Creating Log Writer task...")  # Changed log.log to log
        # Note: _log_writer_task was imported directly
        asyncio.create_task(_log_writer_task())  # Use imported task directly
        log("Log Writer task created.")  # Changed log.log to log

        # Initialize IO components
        init_io.init_io()  # Call the centralized init function

        # Start AP mode
        log("Starting AP...")  # Changed log.log to log
        ap.start_ap(essid="DDDEV", password="")
        log(
            f"AP Started: http://{ap.get_ap_ip()} (SSID: DDDEV)"
        )  # Changed log.log to log

        # --- Start Background Async Tasks ---
        log("Starting asyncio tasks...")  # Changed log.log to log

        log("Creating LED task...")  # Changed log.log to log
        asyncio.create_task(led.led_task())
        log("LED task created.")  # Changed log.log to log

        log("Creating WiFi management task...")  # Changed log.log to log
        asyncio.create_task(wifi.manage_wifi_connection())
        log("WiFi management task created.")  # Changed log.log to log
        # Removed duplicate log message

        # Start sensor reader tasks (if they have one)
        log("Starting sensor reader tasks...")  # Changed log.log to log
        # esc_telemetry.start_esc_reader()  # Starts the async task internally
        # ds18b20.start_ds18b20_reader()  # Starts the async task internally
        gps_reader.start_gps_reader()  # Starts the async task internally
        log(
            "Sensor reader tasks started (if sensors initialized correctly)."
        )  # Changed log.log to log

        # Start the data logging task (from data_log module)
        log("Creating Data Logging task...")  # Changed log.log to log
        asyncio.create_task(
            data_log.data_log_task()
        )  # Call function from imported module
        log("Data Logging task created.")  # Changed log.log to log

        # Get the configured Microdot app from server.py
        app = server.get_app()
        log("Microdot app retrieved.")  # Changed log.log to log

        # Start the Microdot server as a background task
        log("Creating Microdot server task...")  # Changed log.log to log
        asyncio.create_task(app.start_server(port=80, debug=True))
        log("Microdot server task created.")  # Changed log.log to log

        # Keep the main task running indefinitely so background tasks continue
        # This is primarily needed to keep the logger_task alive
        log(
            "Entering main loop (logger task running, threads running)..."
        )  # Changed log.log to log
        loop_count = 0
        while True:
            # Remove blocking call from loop: blink_sequence(3, 2, 0.1)
            await asyncio.sleep(15)  # Use await asyncio.sleep to yield control
            loop_count += 1
            log(  # Changed log.log to log
                f"Async main loop alive - iteration {loop_count}"
            )  # Add periodic log

            # Log largest contiguous free block in data heaps
            try:
                # Get IDF Heap Info
                heap_info = esp32.idf_heap_info(
                    esp32.HEAP_DATA
                )  # List of (total, free, largest_free, min_free)
                max_free_block = 0
                total_free = 0
                num_regions = len(heap_info)
                for heap in heap_info:
                    total_free += heap[1]
                    if heap[2] > max_free_block:
                        max_free_block = heap[2]

                # Get MicroPython Heap Info
                upy_free = gc.mem_free()

                log(  # Changed log.log to log
                    f"Mem: IDF TotalFree={total_free}, MaxBlock={max_free_block}, Regions={num_regions}; UPy Free={upy_free}"
                )
            except Exception as heap_err:
                log(f"Error getting memory info: {heap_err}")  # Changed log.log to log

    except Exception as e:
        log("Error during async main execution:", e)  # Changed log.log to log
        sys.print_exception(e)
    finally:
        # Optional: Add cleanup logic here if needed
        log("Async main finished.")  # Changed log.log to log


log("Starting asyncio event loop for logger...")  # Changed log.log to log
try:
    asyncio.run(main())
except KeyboardInterrupt:
    log("Keyboard interrupt, stopping.")  # Changed log.log to log
except Exception as e:
    log("Error running asyncio main loop:", e)  # Changed log.log to log
    sys.print_exception(e)
finally:
    # Resetting the loop is often good practice if the script might be re-imported
    asyncio.new_event_loop()
    log("Event loop finished.")  # Changed log.log to log
