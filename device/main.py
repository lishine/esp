import uasyncio as asyncio
import sys
import esp32  # Import esp32 module for heap info
import gc  # Import garbage collector module for mem_free
import time  # For ticks_ms, ticks_diff, sleep

# import _thread # No longer using threads for server


# Core project modules
from log import log, _log_writer_task

# import server # Using server1 now
# from server_minimal import app as minimal_app # No longer using minimal server
import led
import wifi
import ap

# IO related modules
import io_local.init_io as init_io
import io_local.data_log as data_log
import io_local.gps_reader as gps_reader  # Import the whole module
from io_local.gps_reader import get_gps_processing_stats  # Import specific function

from http_server import start_server

# --- Constants ---
# Removed DATA_LOG_INTERVAL_S (moved to data_log.py)

# --- Sensor Initialization ---
# Removed init_sensors() function (moved to init_io.py)

# --- Data Logging Task ---
# Removed data_log_task() function (moved to data_log.py)

# --- CPU Load Measurement ---
idle_counter = 0
last_idle_check_time = time.ticks_ms()
last_idle_count = 0
cpu_load_percent = 0.0
# Variables for tracking GPS processing stats between intervals
prev_gps_time_sum_us = 0
prev_gps_count = 0

# --- IMPORTANT: CALIBRATE THIS VALUE ---
# Run idle_task alone on your ESP32 for 1 second
# to find the maximum increments possible when fully idle.
# Adjust this value based on your observation.
MAX_IDLE_INCREMENTS_PER_SEC = 4829  # Example value, needs calibration!

# time.sleep(3)
# print(1)
# time.sleep(3)
# print(1)
# time.sleep(3)
# print(1)
# time.sleep(3)
# print(1)


async def idle_task():
    """Increments counter when CPU is idle. Runs at lowest priority."""
    global idle_counter
    log("Starting idle_task for CPU load measurement...")
    while True:
        idle_counter += 1
        # Yield control immediately, allowing other tasks to run.
        # This task effectively runs only when nothing else needs the CPU.
        await asyncio.sleep_ms(0)


async def measure_cpu():  # Note: This task now depends on gps_reader being initialized
    """Periodically estimates CPU load based on idle task increments."""
    global idle_counter, last_idle_check_time, last_idle_count, cpu_load_percent, MAX_IDLE_INCREMENTS_PER_SEC
    global prev_gps_time_sum_us, prev_gps_count  # Add globals for GPS stats tracking
    log("Starting measure_cpu task...")
    while True:
        # Wait for the measurement interval
        await asyncio.sleep(5)  # Measure every 5 seconds (adjust as needed)

        current_time = time.ticks_ms()
        current_count = idle_counter

        # Calculate differences since last measurement
        time_diff_ms = time.ticks_diff(current_time, last_idle_check_time)
        count_diff = current_count - last_idle_count

        # Get current GPS processing stats
        current_gps_time_sum_us, current_gps_count = get_gps_processing_stats()

        # Calculate differences since last measurement
        gps_time_diff_us = current_gps_time_sum_us - prev_gps_time_sum_us
        gps_count_diff = current_gps_count - prev_gps_count

        # Calculate average GPS processing time for this interval
        avg_gps_proc_time_us = 0
        if gps_count_diff > 0:
            avg_gps_proc_time_us = gps_time_diff_us / gps_count_diff

        # Prevent division by zero and ensure meaningful time difference
        if time_diff_ms > 100:  # Check if at least 100ms passed
            # Calculate idle increments per second during the interval
            increments_per_sec = (count_diff * 1000) / time_diff_ms

            # Calculate idle percentage relative to the calibrated maximum
            # Clamp the value between 0 and 100
            idle_percent = max(
                0.0,
                min(100.0, (increments_per_sec / MAX_IDLE_INCREMENTS_PER_SEC) * 100.0),
            )

            # CPU load is the inverse of idle time
            cpu_load_percent = 100.0 - idle_percent

            log(
                f"CPU Load: {cpu_load_percent:.1f}% (Idle/sec: {increments_per_sec:.0f}, GPS Sentences: {gps_count_diff} in {time_diff_ms/1000.0:.1f}s, Avg Proc: {avg_gps_proc_time_us:.0f} us/sentence)"
            )
        else:
            log("measure_cpu: Interval too short, skipping calculation.")

        # Update state for the next interval
        # Update state for the next interval
        last_idle_check_time = current_time
        last_idle_count = current_count
        prev_gps_time_sum_us = current_gps_time_sum_us
        prev_gps_count = current_gps_count


# --- Removed thread logic ---


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
        log("Data Logging task created.")

        # --- Start the HTTP server in its thread ---
        log("Starting HTTP server thread (server_http_server)...")
        start_server()  # Use the new module and function name
        log("HTTP server thread started.")  # Updated log message
        # app = server3.get_app()
        # asyncio.create_task(app.start_server(port=80, debug=True))
        # Start CPU load measurement tasks
        # Start CPU load measurement tasks
        log("Creating CPU load measurement tasks...")
        asyncio.create_task(idle_task())
        asyncio.create_task(measure_cpu())
        log("CPU load measurement tasks created.")

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
