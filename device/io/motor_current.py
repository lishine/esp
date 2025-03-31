from machine import Pin, ADC
import uasyncio as asyncio
from log import log

# --- Configuration ---
MOTOR_CURRENT_PIN = 4
# Assuming FSR pin is the same? The original code used 'fsr_pin' which wasn't defined.
# Using MOTOR_CURRENT_PIN directly for ADC. Verify if this is correct for your hardware.
# If you have a separate pin for Full Scale Range setting, define it here.
# Example: FSR_PIN = Pin(X, Pin.OUT)
# FSR_PIN.on() # Or FSR_PIN.off() depending on required logic

# --- State ---
motor_current_adc = None
current_motor_amps = 0.0  # Initialize with a default value

# --- Constants ---
# ADC Calibration / Conversion Factors (Placeholder - Adjust based on your hardware)
# These values depend on the ADC resolution, voltage reference, and sensor characteristics.
# Example: If ADC reads 0-4095 for 0-3.3V, and the sensor outputs 0V for 0A and 3.3V for 50A:
ADC_MAX_VALUE = 4095
VOLTAGE_REF = 3.3
MAX_AMPS = 50.0  # Example max current
AMPS_PER_VOLT = MAX_AMPS / VOLTAGE_REF
VOLTS_PER_ADC_UNIT = VOLTAGE_REF / ADC_MAX_VALUE


def init_motor_current():
    """Initializes the ADC for motor current sensing."""
    global motor_current_adc
    try:
        # Ensure the pin is configured as input
        pin = Pin(MOTOR_CURRENT_PIN, Pin.IN)
        motor_current_adc = ADC(pin)
        # Configure ADC attenuation and width if necessary (ESP32 specific)
        # Example: 11dB attenuation allows reading up to 3.3V (approx)
        motor_current_adc.atten(ADC.ATTN_11DB)
        # Example: 12-bit width
        # motor_current_adc.width(ADC.WIDTH_12BIT) # Default is usually 12-bit
        log(
            "Motor Current ADC initialized on Pin", MOTOR_CURRENT_PIN
        )  # Changed log.log to log
        return True
    except Exception as e:
        log("Error initializing Motor Current ADC:", e)  # Changed log.log to log
        motor_current_adc = None
        return False


def read_motor_current():
    """Reads the raw ADC value for motor current."""
    if motor_current_adc is None:
        log("Motor Current ADC not initialized.")  # Changed log.log to log
        return None
    try:
        return motor_current_adc.read()
    except Exception as e:
        log("Error reading Motor Current ADC:", e)  # Changed log.log to log
        return None


def get_motor_current_amps():
    """Reads the ADC and converts the value to Amps."""
    global current_motor_amps
    raw_value = read_motor_current()
    if raw_value is None:
        current_motor_amps = 0.0  # Or keep previous value? Resetting might be safer.
        return current_motor_amps

    # --- Conversion Logic (Needs Calibration) ---
    # This is a placeholder. You MUST calibrate this based on your sensor and ADC setup.
    voltage = raw_value * VOLTS_PER_ADC_UNIT
    current_motor_amps = voltage * AMPS_PER_VOLT
    # Apply any offset correction if needed
    # current_motor_amps = current_motor_amps - OFFSET_AMPS

    # Optional: Add clamping or filtering
    current_motor_amps = max(0, current_motor_amps)  # Ensure non-negative

    return current_motor_amps


# Example of an async task if continuous monitoring is needed separately
# async def monitor_motor_current_task():
#     while True:
#         amps = get_motor_current_amps()
#         log(f"Motor Current: {amps:.2f} A") # Log periodically if needed
#         await asyncio.sleep_ms(500) # Adjust interval as needed
