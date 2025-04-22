import time  # Import the new rtc module

time.sleep(3)
print("loading modules at boot")
import machine
from log import log
import rtc  # Import the new rtc module
from init_sd import init_sd

print("end loading modules at main")

time.sleep(4)
print("boot")

init_sd()

rtc.set_time_from_last_log()  # Set time based on last log entry

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
