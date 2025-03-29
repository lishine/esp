import sys
import machine  # Keep machine import if needed elsewhere, otherwise remove
from log import log  # Keep for initial logging
import rtc  # Import the new rtc module

# Adjust time using the dedicated function
rtc.adjust_time_forward_one_day()

log("\n" + "=" * 40)
log("ESP32 Boot Sequence Starting...")
log("=" * 40)

# Synchronous initializations (like AP, WiFi, Server) moved to main.py

log("boot.py finished.")  # Indicate boot sequence completion

# --- Async Main Function and Event Loop are now in main.py ---
