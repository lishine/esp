import sys
import machine  # Keep machine import if needed elsewhere, otherwise remove
from log import log  # Keep for initial logging
import rtc  # Import the new rtc module

# Adjust time using the dedicated function
rtc.adjust_time_forward_one_day()

log("\n" + "=" * 40)
log("ESP32 Boot Sequence Starting...")
log("=" * 40)

# Log Reset Cause
reset_cause_val = machine.reset_cause()
reset_causes = {
    machine.PWRON_RESET: "Power On Reset",
    machine.HARD_RESET: "Hard Reset",
    machine.WDT_RESET: "Watchdog Reset",
    machine.DEEPSLEEP_RESET: "Deepsleep Reset",
    machine.SOFT_RESET: "Soft Reset",
}
cause_str = reset_causes.get(
    reset_cause_val, f"Unknown Reset Cause ({reset_cause_val})"
)
log(f"**** Reset Cause: {cause_str} ****")


# Synchronous initializations (like AP, WiFi, Server) moved to main.py

log("boot.py finished.")  # Indicate boot sequence completion

# --- Async Main Function and Event Loop are now in main.py ---
