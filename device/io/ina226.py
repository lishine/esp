from machine import Pin, I2C
import time
from log import log

# --- Configuration ---
INA226_I2C_ID = 0
INA226_SCL_PIN = 10
INA226_SDA_PIN = 9
INA226_I2C_FREQ = 100000
INA226_ADDR = 0x40  # Default I2C address (can be changed by hardware jumpers)

# Shunt resistor value in Ohms
SHUNT_RESISTOR_OHMS = 0.0002  # 0.2 mOhm

# --- INA226 Register Addresses ---
CONFIG_REG = 0x00
SHUNT_VOLTAGE_REG = 0x01
BUS_VOLTAGE_REG = 0x02
POWER_REG = 0x03
CURRENT_REG = 0x04
CALIBRATION_REG = 0x05
MASK_ENABLE_REG = 0x06
ALERT_LIMIT_REG = 0x07
MANUFACTURER_ID_REG = 0xFE
DIE_ID_REG = 0xFF

# --- State ---
i2c = None
ina226_present = False
# Store latest readings
bus_voltage = 0.0
shunt_voltage = 0.0
current_amps = 0.0
power_watts = 0.0
# Calibration value calculated during init
current_lsb = 0.0
cal_value = 0

# --- Constants ---
BUS_VOLTAGE_LSB = 0.00125  # 1.25mV per LSB
SHUNT_VOLTAGE_LSB = 0.0000025  # 2.5uV per LSB


# --- Helper Functions ---
def _write_register(reg_addr, value):
    """Writes a 16-bit value to the specified register."""
    if i2c is None:
        return False
    try:
        # Value needs to be sent MSB first
        data = bytearray([reg_addr, (value >> 8) & 0xFF, value & 0xFF])
        i2c.writeto(INA226_ADDR, data)
        return True
    except OSError as e:
        log(f"INA226 I2C write error to reg {hex(reg_addr)}: {e}")
        return False


def _read_register(reg_addr):
    """Reads a 16-bit value from the specified register."""
    if i2c is None:
        return None
    try:
        # Write the register address we want to read from
        i2c.writeto(INA226_ADDR, bytes([reg_addr]))
        # Read 2 bytes (MSB first)
        data = i2c.readfrom(INA226_ADDR, 2)
        return (data[0] << 8) | data[1]
    except OSError as e:
        log(f"INA226 I2C read error from reg {hex(reg_addr)}: {e}")
        return None


def _read_signed_register(reg_addr):
    """Reads a 16-bit signed value from the specified register."""
    value = _read_register(reg_addr)
    if value is None:
        return None
    # Check if the sign bit (MSB) is set
    if value & 0x8000:
        # Convert to negative value using two's complement
        return value - 65536
    else:
        return value


# --- Initialization ---
def init_ina226():
    """Initializes the I2C bus and configures the INA226 sensor."""
    global i2c, ina226_present, current_lsb, cal_value
    try:
        i2c = I2C(
            INA226_I2C_ID,
            scl=Pin(INA226_SCL_PIN),
            sda=Pin(INA226_SDA_PIN),
            freq=INA226_I2C_FREQ,
        )
        log(
            f"I2C({INA226_I2C_ID}) initialized on SCL={INA226_SCL_PIN}, SDA={INA226_SDA_PIN}"
        )

        # Scan for the device
        devices = i2c.scan()
        log("I2C devices found:", [hex(device) for device in devices])
        if INA226_ADDR not in devices:
            log(f"Error: INA226 not found at address {hex(INA226_ADDR)}")
            ina226_present = False
            i2c = None  # Release I2C if device not found? Or keep for other devices?
            return False
        else:
            log(f"INA226 found at address {hex(INA226_ADDR)}")
            ina226_present = True

        # --- Configuration ---
        # Reset the device first
        # _write_register(CONFIG_REG, 0x8000) # Set reset bit
        # time.sleep_ms(5) # Wait for reset

        # Calculate Calibration Register value
        # Max Expected Current - Adjust if needed (e.g., 10A)
        # This influences the resolution (Current_LSB)
        max_expected_current = 10.0
        # Calculate Current_LSB (smallest current measurable) aiming for ~max_expected_current / 32767
        current_lsb = max_expected_current / 32768.0
        # Calculate Calibration value based on formula: Cal = 0.00512 / (Current_LSB * R_SHUNT)
        cal_value = int(0.00512 / (current_lsb * SHUNT_RESISTOR_OHMS))
        # Update the actual Current_LSB based on the calculated calibration value
        current_lsb = 0.00512 / (cal_value * SHUNT_RESISTOR_OHMS)

        log(
            f"INA226: Max Expected Current={max_expected_current:.2f}A, R_Shunt={SHUNT_RESISTOR_OHMS} Ohm"
        )
        log(
            f"INA226: Calculated CalValue={cal_value}, CurrentLSB={current_lsb * 1e6:.1f} uA/bit"
        )

        # Write Calibration Register
        if not _write_register(CALIBRATION_REG, cal_value):
            raise OSError("Failed to write INA226 Calibration Register")

        # Configure INA226 settings
        # Averaging: 16 samples (0b0100 << 9 = 0x0800)
        # Bus Voltage Conversion Time: 1.1ms (0b100 << 6 = 0x0100)
        # Shunt Voltage Conversion Time: 1.1ms (0b100 << 3 = 0x0020)
        # Mode: Shunt and Bus, Continuous (0b111 = 0x0007)
        config = (
            0x0800 | 0x0100 | 0x0020 | 0x0007
        )  # = 0x0927 (Example: 16 avg, 1.1ms, 1.1ms, continuous)
        # Original config from user: 0x4727 (128 avg, 1.1ms, 1.1ms, continuous) - Let's use the original one
        config = 0x4727
        log(f"INA226: Writing Config Register = {hex(config)}")
        if not _write_register(CONFIG_REG, config):
            raise OSError("Failed to write INA226 Config Register")

        time.sleep_ms(2)  # Wait for configuration to take effect and first conversion
        log("INA226 configured successfully.")
        return True

    except Exception as e:
        log(f"Error initializing INA226: {e}")
        i2c = None
        ina226_present = False
        return False


# --- Data Reading Functions ---


def read_ina226_data():
    """Reads all relevant values from the INA226."""
    global bus_voltage, shunt_voltage, current_amps, power_watts
    if not ina226_present or i2c is None:
        # log("INA226 not present or I2C not initialized.")
        return None  # Return None if sensor not ready

    try:
        # Read Bus Voltage (Voltage from V+ to GND)
        raw_bus_voltage = _read_register(BUS_VOLTAGE_REG)
        if raw_bus_voltage is None:
            raise OSError("Failed to read Bus Voltage")
        # Check conversion ready flag? (Optional, depends on timing)
        # mask_enable = _read_register(MASK_ENABLE_REG)
        # if not (mask_enable & 0x0008): # Check CVRF bit
        #     log("INA226 conversion not ready")
        #     return None # Or return previous values?

        bus_voltage = raw_bus_voltage * BUS_VOLTAGE_LSB

        # Read Shunt Voltage (Voltage across the shunt resistor)
        raw_shunt_voltage = _read_signed_register(SHUNT_VOLTAGE_REG)
        if raw_shunt_voltage is None:
            raise OSError("Failed to read Shunt Voltage")
        shunt_voltage = raw_shunt_voltage * SHUNT_VOLTAGE_LSB

        # Read Current (Calculated by INA226 using calibration register)
        raw_current = _read_signed_register(CURRENT_REG)
        if raw_current is None:
            raise OSError("Failed to read Current")
        current_amps = raw_current * current_lsb

        # Read Power (Calculated by INA226)
        raw_power = _read_register(POWER_REG)
        if raw_power is None:
            raise OSError("Failed to read Power")
        # Power LSB = 25 * Current_LSB (Datasheet formula adjusted for INA226)
        power_lsb = 25.0 * current_lsb
        power_watts = raw_power * power_lsb

        return {
            "bus_voltage": bus_voltage,
            "shunt_voltage": shunt_voltage,
            "current_amps": current_amps,
            "power_watts": power_watts,
        }

    except Exception as e:
        log(f"Error reading INA226 data: {e}")
        # Reset values on error?
        bus_voltage = 0.0
        shunt_voltage = 0.0
        current_amps = 0.0
        power_watts = 0.0
        return None


# --- Data Access Functions ---
def get_bus_voltage():
    return bus_voltage


def get_shunt_voltage():
    return shunt_voltage


def get_current_amps():
    return current_amps


def get_power_watts():
    return power_watts


# Example async task (if needed for separate monitoring)
# async def monitor_ina226_task():
#     while True:
#         data = read_ina226_data()
#         if data:
#             log(f"INA226: V={data['bus_voltage']:.2f}V, I={data['current_amps']:.3f}A, P={data['power_watts']:.2f}W")
#         await asyncio.sleep_ms(1000) # Adjust interval
