from machine import UART, Pin
import uasyncio as asyncio
import time  # Keep time for sleep in the reading loop for now
from log import log

# --- Configuration ---
ESC_UART_ID = 1  # Using UART1 as specified
ESC_TX_PIN = 2  # GPIO2 (Pinout Table)
ESC_RX_PIN = 7  # GPIO7 (Pinout Table)
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


# --- CRC Calculation ---
def _update_crc8(crc, crc_seed):
    crc_u = crc ^ crc_seed
    for _ in range(8):
        crc_u = (0x07 ^ (crc_u << 1)) if (crc_u & 0x80) else (crc_u << 1)
    return crc_u & 0xFF


def _get_crc8(buf, buflen):
    crc = 0
    for i in range(buflen):
        crc = _update_crc8(buf[i], crc)
    return crc


# --- Telemetry Parsing ---
def _parse_kiss_telemetry(data):
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
                # log(f"ESC CRC mismatch: received {received_crc}, calculated {calculated_crc}")
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
            log(f"Error parsing ESC telemetry: {e}")  # Changed log.log to log
            return None
    # log(f"Short ESC packet received: len={len(data) if data else 0}") # Debug short packets # Changed log.log to log
    return None


# --- Initialization ---
def init_esc_telemetry():
    """Initializes the UART for ESC telemetry."""
    global uart
    try:
        # Ensure pins are correctly assigned if using specific constructor
        # uart = UART(ESC_UART_ID, baudrate=ESC_BAUDRATE, tx=Pin(ESC_TX_PIN), rx=Pin(ESC_RX_PIN), bits=8, parity=None, stop=1)
        # Simpler init if pins are fixed for the UART ID on the board:
        uart = UART(ESC_UART_ID, baudrate=ESC_BAUDRATE, tx=ESC_TX_PIN, rx=ESC_RX_PIN)
        log(  # Changed log.log to log
            f"ESC Telemetry UART({ESC_UART_ID}) initialized on TX={ESC_TX_PIN}, RX={ESC_RX_PIN}"
        )
        return True
    except Exception as e:
        log(
            f"Error initializing ESC Telemetry UART({ESC_UART_ID}): {e}"
        )  # Changed log.log to log
        uart = None
        return False


# --- Data Reading Task ---
async def _read_esc_telemetry_task():
    """Asynchronous task to continuously read and parse ESC telemetry."""
    global esc_voltage, esc_rpm, esc_temp, esc_current, esc_consumption
    if uart is None:
        log(
            "ESC UART not initialized. Cannot start reader task."
        )  # Changed log.log to log
        return

    log("Starting ESC telemetry reader task...")  # Changed log.log to log
    read_buffer = bytearray()
    last_data_time = time.ticks_ms()

    while True:
        try:
            if uart.any():
                # Read available data and append to buffer
                new_data = uart.read()
                if new_data:
                    read_buffer.extend(new_data)
                    last_data_time = time.ticks_ms()
                    # log(f"ESC Read {len(new_data)} bytes, buffer size: {len(read_buffer)}") # Debug reads # Changed log.log to log

                # Process buffer: Look for potential packets (at least 10 bytes)
                while len(read_buffer) >= 10:
                    # Attempt to parse from the beginning of the buffer
                    telemetry = _parse_kiss_telemetry(read_buffer)

                    if telemetry:
                        # log("ESC Telemetry Parsed:", telemetry) # Debug successful parse # Changed log.log to log
                        esc_voltage = telemetry["voltage"]
                        esc_rpm = telemetry["rpm"]
                        esc_temp = telemetry["temperature"]
                        esc_current = telemetry["current"]
                        esc_consumption = telemetry["consumption"]
                        # Consume the parsed packet (10 bytes) from the buffer
                        read_buffer = read_buffer[10:]
                    else:
                        # Parsing failed (bad CRC or format).
                        # Try to find the next potential start by discarding one byte.
                        # This is a simple sync mechanism; more robust methods exist.
                        # log(f"ESC Parse failed or CRC error. Discarding byte: {hex(read_buffer[0])}") # Debug sync # Changed log.log to log
                        read_buffer = read_buffer[1:]

            # Timeout check: If no data received for a while, clear buffer to prevent stale data buildup
            if time.ticks_diff(time.ticks_ms(), last_data_time) > 500:  # 500ms timeout
                if len(read_buffer) > 0:
                    # log(f"ESC Timeout: Clearing stale buffer ({len(read_buffer)} bytes)") # Debug timeout # Changed log.log to log
                    read_buffer = bytearray()  # Clear buffer

            # Yield control to allow other tasks to run
            await asyncio.sleep_ms(20)  # Check UART frequently

        except Exception as e:
            log(f"Error in ESC telemetry reader task: {e}")  # Changed log.log to log
            # Avoid tight loop on error
            await asyncio.sleep_ms(500)


def start_esc_reader():
    """Starts the asynchronous ESC telemetry reader task."""
    global _reader_task
    if uart is None:
        log("Cannot start ESC reader: UART not initialized.")  # Changed log.log to log
        return False
    if _reader_task is None:
        _reader_task = asyncio.create_task(_read_esc_telemetry_task())
        log("ESC telemetry reader task created.")  # Changed log.log to log
        return True
    else:
        log("ESC telemetry reader task already running.")  # Changed log.log to log
        return False


# --- Data Access Functions ---
def get_esc_data():
    """Returns the latest ESC telemetry data."""
    return {
        "voltage": esc_voltage,
        "rpm": esc_rpm,
        "temperature": esc_temp,
        "current": esc_current,
        "consumption": esc_consumption,
    }


def get_esc_voltage():
    return esc_voltage


def get_esc_rpm():
    return esc_rpm


def get_esc_temp():
    return esc_temp


def get_esc_current():
    return esc_current


def get_esc_consumption():
    return esc_consumption
