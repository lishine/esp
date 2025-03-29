import sys
import time  # Keep for initial time adjustment
import machine
from log import log  # Keep for initial logging

# Keep the time adjustment logic as is, it runs before asyncio starts
try:
    # Ensure time is synced (e.g., via NTP if configured, though not shown here)
    # before incrementing to avoid setting incorrect time based on default RTC state.
    # For now, we proceed assuming RTC holds a somewhat valid time or default.

    current_secs = time.time()
    # Add one day in seconds
    new_secs = current_secs + 86400
    # Convert seconds since epoch back to localtime tuple
    # localtime returns (year, month, mday, hour, minute, second, weekday, yearday)
    new_time_tuple = time.localtime(new_secs)

    # Set RTC time using the new tuple
    # rtc.datetime expects (year, month, day, weekday, hours, minutes, seconds, subseconds)
    # Note: time.localtime weekday is 0-6 Mon-Sun. rtc.datetime weekday might differ,
    # but often setting it is optional or handled internally. We'll use the weekday from localtime.
    # MicroPython's RTC typically ignores the subseconds value when setting.
    rtc = machine.RTC()
    rtc.datetime(
        (
            new_time_tuple[0],
            new_time_tuple[1],
            new_time_tuple[2],
            new_time_tuple[6],
            new_time_tuple[3],
            new_time_tuple[4],
            new_time_tuple[5],
            0,
        )
    )
    log(
        f"Incremented system time by one day. New time set."
    )  # Avoid logging rtc.datetime() here as it might be slightly different due to internal handling
except Exception as e:
    log("Error adjusting time:", e)


log("\n" + "=" * 40)
log("ESP32 Boot Sequence Starting...")
log("=" * 40)

# Synchronous initializations (like AP, WiFi, Server) moved to main.py

log("boot.py finished.")  # Indicate boot sequence completion

# --- Async Main Function and Event Loop are now in main.py ---
