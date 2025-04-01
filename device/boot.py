import machine
import uos  # Import uos for dupterm
from log import log
import rtc  # Import the new rtc module

# --- Disable REPL on UART0 ---
# This ensures UART0 is free for other uses (like GPS), especially if
# the default console is the USB Serial/JTAG. Index 1 refers to UART0.
# try:
#     uos.dupterm(None, 0) # Disable REPL on UART0 - No longer needed as GPS uses SoftUART
#     log("REPL disabled on UART0.")
# except Exception as e:
#     log(f"Could not disable REPL on UART0: {e}")

# Adjust time using the dedicated function
rtc.adjust_time_forward_one_day()

log("\n" + "=" * 40)
log("ESP32 Boot Sequence Starting...")
log("=" * 40)
# Filesystem is automatically mounted by MicroPython (defaults to LittleFS v2 on recent builds)

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


log("boot.py finished.")
