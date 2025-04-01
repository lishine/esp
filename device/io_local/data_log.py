# Centralized data logging task for IO components

import uasyncio as asyncio
from log import log

# Import specific IO modules from this directory
from . import motor_current
from . import esc_telemetry
from . import ds18b20

# from . import ina226 # Keep file but don't log
from . import neo7m

# Buzzer doesn't typically have data to log continuously

# --- Constants ---
DATA_LOG_INTERVAL_S = 10

# --- Data Gathering Functions (Optional Abstraction) ---
# These could be simple wrappers or add formatting


def _log_motor_current():
    mc_amps = motor_current.get_motor_current_amps()
    return f"MC:{mc_amps:.2f}A" if mc_amps is not None else "MC:N/A"


def _log_esc_telemetry():
    esc_data = esc_telemetry.get_esc_data()
    return f"ESC:{esc_data['voltage']:.1f}V,{esc_data['rpm']}rpm,{esc_data['temperature']}C,{esc_data['current']:.1f}A,{esc_data['consumption']}mAh"


def _log_ds18b20():
    ds_temps = ds18b20.get_ds18b20_temperatures()
    return (
        "DS:" + ",".join([f"{t:.1f}C" if t is not None else "N/A" for t in ds_temps])
        if ds_temps
        else "DS:N/A"
    )


# def _log_ina226():
#     ina_data = ina226.read_ina226_data() # Reads all INA values at once
#     if ina_data:
#         return f"INA:{ina_data['bus_voltage']:.2f}V,{ina_data['current_amps']:.3f}A,{ina_data['power_watts']:.2f}W"
#     else:
#         return "INA:N/A"


def _log_gps():
    gps_data = neo7m.get_gps_data()
    if gps_data["fix"]:
        return f"GPS:Fix({gps_data['satellites']}),{gps_data['latitude']:.5f},{gps_data['longitude']:.5f},{gps_data['altitude']:.1f}m"
    else:
        return "GPS:NoFix"


# --- Data Logging Task ---
async def data_log_task():
    """Periodically reads sensor data and logs it."""
    log("Starting data logging task...")  # Changed log.log to log
    while True:
        try:
            # Gather data using helper functions
            # mc_str = _log_motor_current() # Commented out
            # esc_str = _log_esc_telemetry() # Commented out
            # ds_str = _log_ds18b20() # Commented out
            # ina_str = _log_ina226() # Commented out
            gps_str = _log_gps()  # Only log GPS for now

            # Format log message (concise)
            # log(f"DATA | {mc_str} | {esc_str} | {ds_str} | {ina_str} | {gps_str}") # Changed log.log to log
            log(f"DATA | {gps_str}")  # Log only GPS # Changed log.log to log

        except Exception as e:
            log(f"Error in data_log_task: {e}")  # Changed log.log to log

        # Wait for the next interval
        await asyncio.sleep(DATA_LOG_INTERVAL_S)
