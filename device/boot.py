import time
import globals  # Import globals first

time.sleep(3)
print("loading modules at boot")
import machine
from sd_utils import init_sd
from log import log
import settings_manager

print("end loading modules at main")

time.sleep(4)
print("boot")

init_sd()

# Initialize settings manager and increment reset counter
settings_manager.load_settings()
settings_manager.increment_reset_counter()
log(f"Settings loaded. Reset counter: {settings_manager.get_reset_counter()}")


# rtc.set_time_from_last_log()  # Set time based on last log entry

log("\n" + "=" * 40)
log("ESP32 Boot Sequence Starting...")
log("=" * 40)


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
