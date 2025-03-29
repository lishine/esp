import sys
import time  # Keep for initial time adjustment
import machine

# import uasyncio as asyncio # Moved to main.py
from log import log  # Keep for initial logging

import wifi  # Needed here
import ap  # Needed here for AP start

# import server  # No longer needed here, started in main.py
import led  # Needed here for LED thread start


# def log(*args, **kwargs):
# print("")


# from log import logger_task # Moved to main.py

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

try:
    # Start background threads synchronously before main.py runs
    log("Starting AP thread from boot.py...")
    ap.start_ap(essid="DDDEV", password="")
    log(f"AP Started (thread): http://{ap.get_ap_ip()} (SSID: DDDEV)")

    log("Starting WiFi thread from boot.py...")
    wifi.start_wifi()  # Start WiFi connection/monitor threads
    log("WiFi thread started.")

    # log("Starting Server thread from boot.py...") # Moved to main.py
    # server.start_server() # Moved to main.py
    # log("Server thread started.") # Moved to main.py

except Exception as e:
    log("Error during synchronous boot initialization:", e)
    sys.print_exception(e)

log("boot.py finished.")  # Indicate boot sequence completion

# --- Async Main Function and Event Loop are now in main.py ---
