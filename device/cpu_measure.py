import time
import uasyncio as asyncio
from log import log
from io_local.gps_reader import get_gps_processing_stats

idle_counter = 0
last_idle_check_time = time.ticks_ms()
last_idle_count = 0
cpu_load_percent = 0.0
prev_gps_time_sum_us = 0
prev_gps_count = 0

# --- IMPORTANT: CALIBRATE THIS VALUE ---
# Run idle_task alone on your ESP32 for 1 second
# to find the maximum increments possible when fully idle.
# Adjust this value based on your observation.
MAX_IDLE_INCREMENTS_PER_SEC = 4829  # Example value, needs calibration!


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
