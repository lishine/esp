# device/io_local/adc.py
import machine
import uasyncio
import time
from log import log  # Assuming log module is in device/log.py

# --- Constants ---
ADC_PIN: int = 5
SAMPLES: int = 100
DELAY_MS: int = 10  # 100 samples * 10ms = 1000ms = 1s interval
ATTENUATION: int = machine.ADC.ATTN_11DB  # Corresponds to ~0-3.3V range
BIT_WIDTH: int = machine.ADC.WIDTH_12BIT  # Use 12-bit resolution

# Calibration Factors for read_uv() based voltage (2-point linear)
UV_SLOPE: float = 0.9905  # Recalculated 2025-04-06
UV_INTERCEPT: float = 0.0299  # Recalculated 2025-04-06
# Calibration Factor for read_u16() based voltage (linear assumption)
U16_CALIBRATION_FACTOR: float = (
    3.3 / 65535.0
)  # Linear factor for read_u16() based voltage

# --- Global Variables ---
# These store the latest readings from the background task
_latest_average_uv: int = 0
_latest_average_u16: int = 0
_latest_voltage_uv: float = 0.0  # Voltage calculated from read_uv() with 2-point factor
_latest_voltage_u16: float = (
    0.0  # Voltage calculated from read_u16() with linear factor
)

# --- ADC Initialization ---
# Initialize ADC object globally for the sampler task
_adc: machine.ADC | None = None
try:
    _pin: machine.Pin = machine.Pin(ADC_PIN, machine.Pin.IN)
    _adc = machine.ADC(_pin)
    _adc.atten(ATTENUATION)
    _adc.width(BIT_WIDTH)
    log("INFO", f"ADC initialized on Pin {ADC_PIN}")
except Exception as e:
    log("ERROR", f"Failed to initialize ADC on Pin {ADC_PIN}: {e}")
    # _adc remains None


# --- Background Sampler Task ---
async def run_adc_sampler() -> None:
    """
    Asynchronously samples the ADC continuously using both read_uv and read_u16,
    and updates global variables with calculated voltages using respective factors.
    """
    global _latest_average_uv, _latest_average_u16, _latest_voltage_uv, _latest_voltage_u16

    if _adc is None:  # Check if ADC initialization failed
        log("ERROR", "ADC not initialized. Sampler task cannot run.")
        return  # Exit task if ADC failed to init

    log("INFO", "Starting ADC sampler task...")
    while True:
        try:
            total_uv: int = 0
            total_u16: int = 0
            for _ in range(SAMPLES):
                # Read both values in the loop
                total_uv += _adc.read_uv()
                total_u16 += _adc.read_u16()
                # Yield control to scheduler
                await uasyncio.sleep_ms(DELAY_MS)

            # Update global averages
            _latest_average_uv = total_uv // SAMPLES
            _latest_average_u16 = total_u16 // SAMPLES

            # Update calculated voltages using respective factors
            # Apply the user-provided factor for read_uv based calculation
            _latest_voltage_uv = (
                _latest_average_uv / 1_000_000.0
            ) * UV_SLOPE + UV_INTERCEPT
            # Apply the linear factor for read_u16 based calculation
            _latest_voltage_u16 = (_latest_average_u16 * U16_CALIBRATION_FACTOR) + 0.05

            # Optional: Log the calculated voltages periodically
            # log("DEBUG", f"ADC Volt (uv_calib): {_latest_voltage_uv:.3f} V, ADC Volt (u16_lin): {_latest_voltage_u16:.3f} V")

        except Exception as e:
            log("ERROR", f"Error in ADC sampler task: {e}")
            # Avoid busy-looping on error, wait before retrying
            await uasyncio.sleep_ms(1000)


# --- Getter Functions ---
def get_latest_voltage_uv() -> float:
    """
    Synchronously returns the latest voltage calculated from read_uv()
    using the two-point linear calibration factor.
    Reads the value updated by the background async task.
    """
    return _latest_voltage_uv


def get_latest_voltage_u16() -> float:
    """
    Synchronously returns the latest voltage calculated from read_u16()
    using a linear 3.3V/65535 factor plus a fixed offset of 0.03V.
    Reads the value updated by the background async task.
    """
    return _latest_voltage_u16
