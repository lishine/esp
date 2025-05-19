from machine import UART, Pin
import uasyncio as asyncio
import time  # Keep time for sleep in the reading loop for now
from log import log
from . import data_log

ZERO_RPM_LOG_INTERVAL_MS: int = 5000
REGULAR_LOG_INTERVAL_MS: int = 500

# --- Configuration ---
ESC_UART_ID = 2
ESC_TX_PIN = 3
ESC_RX_PIN = 14
ESC_BAUDRATE = 115200
MOTOR_POLE_PAIRS = 12 // 2  # Assuming 12 poles (6 pairs) for RPM calculation

# --- State ---
uart = None
esc_voltage = 0.0
esc_rpm = 0
esc_temp = 0
esc_current = 0.0
esc_consumption = 0
_reader_task = None


SENSOR_NAME = "esc"


# --- CRC Calculation ---
def _update_crc8(crc: int, crc_seed: int) -> int:
    crc_u = crc ^ crc_seed
    for _ in range(8):
        crc_u = (0x07 ^ (crc_u << 1)) if (crc_u & 0x80) else (crc_u << 1)
    return crc_u & 0xFF


def _get_crc8(buf: bytes, buflen: int) -> int:
    crc = 0
    for i in range(buflen):
        crc = _update_crc8(crc, buf[i])
    return crc


# --- Telemetry Parsing ---
def _parse_kiss_telemetry(data: bytes) -> dict | None:
    """Parses KISS telemetry data packet."""
    # KISS protocol frame structure (10 bytes):
    # 0: Temperature (°C)
    # 1: Voltage High Byte
    # 2: Voltage Low Byte (Voltage / 100.0)
    # 3: Current High Byte
    # 4: Current Low Byte (Current / 100.0)
    # 5: Consumption High Byte
    # 6: Consumption Low Byte (mAh)
    # 7: ERPM High Byte
    # 8: ERPM Low Byte (ERPM * 100)
    # 9: CRC8
    if data and len(data) >= 10:
        try:
            # Verify CRC
            received_crc = data[9]
            calculated_crc = _get_crc8(data[:9], 9)
            if received_crc != calculated_crc:
                log(
                    f"ESC CRC mismatch: received {received_crc}, calculated {calculated_crc}"
                )
                return None  # CRC error, discard packet

            temperature = data[0]
            voltage = (data[1] << 8 | data[2]) / 100.0
            current = (data[3] << 8 | data[4]) / 100.0
            consumption = data[5] << 8 | data[6]
            erpm = (data[7] << 8 | data[8]) * 100
            rpm = erpm // MOTOR_POLE_PAIRS  # Calculate actual RPM

            return {
                "voltage": voltage,
                "rpm": rpm,
                "temperature": temperature,
                "current": current,
                "consumption": consumption,
                "erpm": erpm,  # Include ERPM for potential debugging
            }
        except Exception as e:
            log(f"Error parsing ESC telemetry: {e}")
            return None
    return None


# --- Initialization ---
def init_esc_telemetry() -> bool:
    """Initializes the UART for ESC telemetry."""
    global uart
    try:
        # Ensure pins are correctly assigned if using specific constructor
        # uart = UART(ESC_UART_ID, baudrate=ESC_BAUDRATE, tx=Pin(ESC_TX_PIN), rx=Pin(ESC_RX_PIN), bits=8, parity=None, stop=1)
        # Simpler init if pins are fixed for the UART ID on the board:
        uart = UART(
            ESC_UART_ID,
            baudrate=ESC_BAUDRATE,
            tx=ESC_TX_PIN,
            rx=ESC_RX_PIN,
            timeout=1000,
        )
        log(
            f"ESC Telemetry UART({ESC_UART_ID}) initialized on TX={ESC_TX_PIN}, RX={ESC_RX_PIN}"
        )
        return True
    except Exception as e:
        log(f"Error initializing ESC Telemetry UART({ESC_UART_ID}): {e}")
        uart = None
        return False


async def _read_esc_telemetry_task():
    """Asynchronous task implementing user-specified timing logic for ESC telemetry."""
    last_zero_rpm_log_time_ms: int = 0
    last_regular_log_time_ms: int = 0
    global esc_voltage, esc_rpm, esc_temp, esc_current, esc_consumption, uart

    if uart is None:
        log("ESC Telemetry UART not initialized. Cannot start reader task.")
        return

    log("Starting ESC telemetry reader task (user timing logic)...")
    reader = asyncio.StreamReader(uart)

    data_count = 0
    parsed_count = 0
    log_interval_ms = 5000
    last_log_time = time.ticks_ms()

    while True:
        data = None  # Reset data
        parsed_data = None  # Reset parsed_data

        try:
            # 1. Clear Buffer
            if uart.any():
                _ = uart.read(uart.any())

            # 2. Short Delay
            await asyncio.sleep_ms(18)

            # 3. Check Buffer Again
            if not uart.any():
                # 4. Attempt Read (if buffer empty)
                try:
                    # Note: Consider adding timeout to UART init or StreamReader if readexactly blocks indefinitely
                    data = await reader.readexactly(10)  # type: ignore
                except asyncio.TimeoutError:
                    data_log.report_error(
                        SENSOR_NAME,
                        time.ticks_ms(),
                        "uart no data",
                    )
                    # Expected if no data arrived, don't log unless debugging
                    # log("ESC Telemetry: readexactly timed out after 10ms wait.")
                    pass  # Proceed to short sleep at the end
                except EOFError:
                    data_log.report_error(
                        SENSOR_NAME,
                        time.ticks_ms(),
                        "ESC Telemetry: UART connection closed during read.",
                    )
                    await asyncio.sleep_ms(1000)  # Longer sleep on EOF
                    continue  # Go to start of loop

                if data:
                    data_count += 1  # Increment successful read count
                    # 5. Parse Data
                    parsed_data = _parse_kiss_telemetry(data)
                    if parsed_data:
                        # 6. Process Valid Data
                        esc_voltage = parsed_data["voltage"]
                        esc_rpm = parsed_data["rpm"]
                        esc_temp = parsed_data["temperature"]
                        esc_current = parsed_data["current"]
                        esc_consumption = parsed_data["consumption"]

                        # THIS IS THE SECTION TO MODIFY FOR CONDITIONAL LOGGING
                        current_ticks: int = time.ticks_ms()
                        if esc_rpm != 0:
                            if (
                                time.ticks_diff(current_ticks, last_regular_log_time_ms)
                                >= REGULAR_LOG_INTERVAL_MS
                            ):
                                data_log.report_data(
                                    SENSOR_NAME,
                                    current_ticks,
                                    dict(
                                        v=esc_voltage,
                                        c=esc_current,
                                        rpm=esc_rpm,
                                        t=esc_temp,
                                        mah=esc_consumption,
                                    ),
                                )
                                parsed_count += 1  # Increment successful parse count
                                last_regular_log_time_ms = current_ticks
                            # Else: Do not log if RPM is non-zero and interval hasn't passed
                            # Update last_zero_rpm_log_time_ms even when RPM is not zero
                            # to ensure the interval starts from the last log time.
                            last_zero_rpm_log_time_ms = current_ticks  # This ensures the 5s timer resets when RPM becomes non-zero
                        else:  # esc_rpm is zero
                            if (
                                time.ticks_diff(
                                    current_ticks, last_zero_rpm_log_time_ms
                                )
                                >= ZERO_RPM_LOG_INTERVAL_MS
                            ):
                                data_log.report_data(
                                    SENSOR_NAME,
                                    current_ticks,
                                    dict(
                                        v=esc_voltage,
                                        c=esc_current,
                                        rpm=esc_rpm,
                                        t=esc_temp,
                                        mah=esc_consumption,
                                    ),
                                )
                                parsed_count += 1  # Increment successful parse count
                                last_zero_rpm_log_time_ms = current_ticks
                            # Else: Do not log if RPM is zero and interval hasn't passed
                            # Update last_regular_log_time_ms even when RPM is zero
                            # to ensure the interval starts from the last log time.
                            last_regular_log_time_ms = current_ticks  # This ensures the 0.5s timer resets when RPM becomes zero
                        await asyncio.sleep_ms(150)
                    else:
                        data_log.report_error(
                            SENSOR_NAME,
                            time.ticks_ms(),
                            "ESC Telemetry: UART parsing error",
                        )
                        # CRC Error (already logged inside _parse_kiss_telemetry if enabled)

            # If buffer was not empty after 10ms, or read failed/timed out, or CRC failed...
            # Proceed to the short sleep at the end of the main try block

        except asyncio.CancelledError:
            log("ESC Telemetry: Reader task cancelled.")
            raise
        except Exception as e:
            # Catch other unexpected errors during the logic (not read/parse)
            log(f"Error in ESC telemetry task logic: {e}")
            await asyncio.sleep_ms(500)  # Wait after unexpected error

        # Check if it's time to log counts
        current_time = time.ticks_ms()
        if time.ticks_diff(current_time, last_log_time) >= log_interval_ms:
            log(
                f"ESC Telemetry Stats (1s): Reads={data_count*(1000/log_interval_ms):.0f}, Parsed={parsed_count*(1000/log_interval_ms):.0f}"
            )
            data_count = 0
            parsed_count = 0
            last_log_time = current_time


def start_esc_reader() -> bool:
    """Starts the asynchronous ESC telemetry reader task."""
    global _reader_task
    if uart is None:
        log("Cannot start ESC reader: UART not initialized.")
        return False
    if _reader_task is None:
        _reader_task = asyncio.create_task(_read_esc_telemetry_task())
        log("ESC telemetry reader task created.")
        return True
    else:
        log("ESC telemetry reader task already running.")
        return False


# --- Data Access Functions ---
def get_esc_data() -> dict:
    """Returns the latest ESC telemetry data."""
    return {
        "voltage": esc_voltage,
        "rpm": esc_rpm,
        "temperature": esc_temp,
        "current": esc_current,
        "consumption": esc_consumption,
    }


def get_esc_voltage() -> float:
    return esc_voltage


def get_esc_rpm() -> int:
    return esc_rpm


def get_esc_temp() -> int:
    return esc_temp


def get_esc_current() -> float:
    return esc_current


def get_esc_consumption() -> int:
    return esc_consumption
