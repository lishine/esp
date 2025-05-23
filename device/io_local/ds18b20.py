from machine import Pin
import onewire
import ds18x20
import uasyncio as asyncio
import time
from log import log
from . import data_log
import settings_manager  # ADDED

DS18B20_PIN = 4
READ_INTERVAL_S = 2

ds_sensor = None
roms = []
ds18_temperatures = []
_reader_task = None

SENSOR = "ds"


def init_ds18b20():
    """Initializes the OneWire bus and scans for DS18B20 sensors."""
    global ds_sensor, roms, ds18_temperatures
    try:
        ds_pin = Pin(DS18B20_PIN, Pin.IN, Pin.PULL_UP)
        ow = onewire.OneWire(ds_pin)
        ds_sensor = ds18x20.DS18X20(ow)

        log("Scanning for DS18B20 sensors on Pin", DS18B20_PIN)
        roms = sorted(ds_sensor.scan())

        if not roms:
            log("Warning: No DS18B20 sensors found!")
            ds18_temperatures = []
        else:
            log(f"Found {len(roms)} DS18B20 sensors:")
            # Initialize temperature list with None values
            ds18_temperatures = [None] * len(roms)
            for i, rom in enumerate(roms):
                # Convert rom bytearray to hex string for logging
                rom_hex = "".join("{:02x}".format(x) for x in rom)
                log(f"  Sensor {i}: ROM={rom_hex}")
        return True
    except Exception as e:
        log(f"Error initializing DS18B20 on Pin {DS18B20_PIN}: {e}")
        ds_sensor = None
        roms = []
        ds18_temperatures = []
        return False


async def _read_ds18b20_task():
    """Asynchronous task to periodically read all detected DS18B20 sensors."""
    global ds18_temperatures
    if ds_sensor is None or not roms:
        log("DS18B20 not initialized or no sensors found. Cannot start reader task.")
        return

    while True:
        try:
            # Start temperature conversion for all sensors
            ds_sensor.convert_temp()
            # Wait for conversion (typically max 750ms for 12-bit resolution)
            await asyncio.sleep_ms(1000)

            # Read temperature from each sensor found
            temps = []
            for i, rom in enumerate(roms):
                try:
                    temp = ds_sensor.read_temp(rom)
                    temps.append(round(temp, 1))  # Round to 1 decimal place
                except Exception as read_e:
                    # Log error for specific sensor, append None
                    rom_hex = "".join("{:02x}".format(x) for x in rom)
                    err_msg = f"Sensor {i} (ROM {rom_hex}) read error: {read_e}"
                    temps.append(None)  # Indicate read failure for this sensor
                    # Report error to data_log
                    data_log.report_error(SENSOR, time.ticks_ms(), err_msg)

            ds18_temperatures = temps  # Update the global state atomically
            # Report successful data to data_log

            # Fetch DS associations to use custom names or ROM hex as keys
            ds_associations = settings_manager.get_ds_associations()
            rom_to_name_map = {
                assoc["address"]: assoc["name"]
                for assoc in ds_associations
                if assoc.get("address") and assoc.get("name")
            }

            reported_temps_data = {}
            for i, rom_bytearray in enumerate(roms):
                if i < len(ds18_temperatures):  # Ensure temp exists for this rom
                    temp_value = ds18_temperatures[i]
                    # Ensure temp_value is not None before trying to use it,
                    # or handle None appropriately if data_log expects numbers
                    if temp_value is not None:
                        rom_hex = "".join("{:02x}".format(x) for x in rom_bytearray)
                        sensor_key = rom_to_name_map.get(
                            rom_hex, rom_hex
                        )  # Custom name or ROM hex
                        reported_temps_data[sensor_key] = temp_value
                    # else: # Sensor read failed, temp_value is None, optionally report this
                    #     rom_hex = "".join("{:02x}".format(x) for x in rom_bytearray)
                    #     sensor_key = rom_to_name_map.get(rom_hex, rom_hex)
                    #     reported_temps_data[sensor_key] = None # Or skip
                else:
                    # This case should ideally not be reached if roms and ds18_temperatures are kept in sync
                    rom_hex = "".join("{:02x}".format(x) for x in rom_bytearray)
                    log(
                        f"DS18B20: Temperature data missing for ROM {rom_hex} during report_data prep."
                    )

            if reported_temps_data:  # Only report if there's valid data
                data_log.report_data(
                    SENSOR, time.ticks_ms(), reported_temps_data  # SENSOR is "ds"
                )
            # log("DS18B20 Temperatures reported:", reported_temps_data) # Optional: Log readings

        except Exception as e:
            # Error during convert_temp or general task issue
            err_msg = f"Error in DS18B20 reader task: {e}"
            # Report task error to data_log
            data_log.report_error(SENSOR, time.ticks_ms(), err_msg)
            # Reset temps to None if a major error occurred? Or keep last known?
            # For now, keep last known good values unless individual reads failed.

        # Wait for the specified interval before the next read cycle
        await asyncio.sleep(READ_INTERVAL_S)


def start_ds18b20_reader():
    """Starts the asynchronous DS18B20 reader task."""
    global _reader_task
    if ds_sensor is None or not roms:
        log("Cannot start DS18B20 reader: Not initialized or no sensors found.")
        return False
    if _reader_task is None:
        _reader_task = asyncio.create_task(_read_ds18b20_task())
        log("DS18B20 reader task created.")
        return True
    else:
        log("DS18B20 reader task already running.")
        return False


# --- Data Access Functions ---
def get_ds18b20_temperatures():
    """
    Returns the latest list of temperatures read from the DS18B20 sensors.
    The order corresponds to the order the sensors were found during scan.
    Returns an empty list if not initialized or no sensors found.
    Individual sensor read errors will result in None values in the list.
    """
    return ds18_temperatures


def get_ds18b20_roms():
    """Returns the list of ROM addresses (bytearrays) of detected sensors."""
    return roms
