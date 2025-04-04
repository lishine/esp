from machine import UART, Pin
import uasyncio as asyncio
import time
from _thread import allocate_lock
from log import log


# --- Configuration ---
GPS_UART_ID = 1  # Using UART1
GPS_TX_PIN = 17  # ESP32 TX -> GPS RX
GPS_RX_PIN = 18  # ESP32 RX <- GPS TX
GPS_BAUDRATE = 9600  # Common default for NEO-xM modules
COMM_TIMEOUT_MS = 5000  # 5 seconds timeout for communication status

# --- State ---
uart = None
gps_fix = False
gps_latitude = 0.0  # Decimal degrees
gps_longitude = 0.0  # Decimal degrees
gps_altitude = 0.0  # Meters
gps_satellites = 0
gps_time_utc = (0, 0, 0)  # (hour, minute, second)
gps_date = (0, 0, 0)  # (day, month, year)
_reader_task = None
_uart_lock = allocate_lock()  # Keep thread lock
_config_request_event = asyncio.Event()  # New: Signal from config to reader
_config_done_event = asyncio.Event()  # New: Signal from config to reader
_last_valid_data_time = 0  # Timestamp of the last valid NMEA sentence
_gps_processing_time_us_sum = 0
_gps_processed_sentence_count = 0


# --- Getter Functions ---
def get_uart():
    """Returns the initialized UART object for the GPS."""
    return uart


def get_uart_lock():
    """Returns the thread-safe Lock used for UART access between config functions."""
    return _uart_lock


def get_config_request_event():
    """Returns the event used by config functions to signal the reader."""
    return _config_request_event


def get_config_done_event():
    """Returns the event used by config functions to signal completion."""
    return _config_done_event


# --- NMEA Parsing Helper ---
def _parse_nmea_degrees(term):
    """Parses NMEA latitude/longitude format (dddmm.mmmm) to decimal degrees."""
    if not term or term == ".":
        return 0.0
    try:
        val = float(term)
        deg = int(val / 100)
        minutes = val - (deg * 100)
        return deg + (minutes / 60.0)
    except ValueError:
        return 0.0


# --- NMEA Sentence Parsers ---
def _parse_gpgga(parts):
    """Parses the GPGGA sentence for fix, position, altitude, and satellite count."""
    global gps_fix, gps_latitude, gps_longitude, gps_altitude, gps_satellites, gps_time_utc
    try:
        fix_quality = int(parts[6]) if parts[6] else 0
        gps_fix = fix_quality > 0
        gps_satellites = int(parts[7]) if len(parts) > 7 and parts[7] else 0

        if gps_fix:
            time_str = parts[1]
            if len(time_str) >= 6:
                gps_time_utc = (
                    int(time_str[0:2]),
                    int(time_str[2:4]),
                    int(float(time_str[4:])),
                )
            lat = _parse_nmea_degrees(parts[2])
            if parts[3] == "S":
                lat = -lat
            gps_latitude = lat
            lon = _parse_nmea_degrees(parts[4])
            if parts[5] == "W":
                lon = -lon
            gps_longitude = lon
            gps_altitude = float(parts[9]) if len(parts) > 9 and parts[9] else 0.0
        # else: Keep last known good values if fix lost temporarily

    except (ValueError, IndexError) as e:
        log(f"Error parsing GPGGA: {e}, parts: {parts}")
        gps_fix = False


def _parse_gprmc(parts):
    """Parses the GPRMC sentence for fix status, time, date, lat, lon."""
    global gps_fix, gps_latitude, gps_longitude, gps_time_utc, gps_date
    try:
        status = parts[2] if len(parts) > 2 else "V"
        gps_fix = status == "A"

        if gps_fix:
            time_str = parts[1]
            if len(time_str) >= 6:
                gps_time_utc = (
                    int(time_str[0:2]),
                    int(time_str[2:4]),
                    int(float(time_str[4:])),
                )
            lat = _parse_nmea_degrees(parts[3])
            if parts[4] == "S":
                lat = -lat
            gps_latitude = lat
            lon = _parse_nmea_degrees(parts[5])
            if parts[6] == "W":
                lon = -lon
            gps_longitude = lon
            date_str = parts[9]
            if len(date_str) == 6:
                gps_date = (
                    int(date_str[0:2]),
                    int(date_str[2:4]),
                    int(date_str[4:6]) + 2000,
                )
        # else: Keep last known good values if fix lost temporarily

    except (ValueError, IndexError) as e:
        log(f"Error parsing GPRMC: {e}, parts: {parts}")
        gps_fix = False


# --- Initialization ---
def init_gps_reader():
    """Initializes UART1 for the GPS module using the configured pins."""
    global uart
    log(
        f"Attempting to initialize NEO-7M GPS on UART({GPS_UART_ID}) TX={GPS_TX_PIN}, RX={GPS_RX_PIN}"
    )
    try:
        uart = UART(
            GPS_UART_ID,
            baudrate=GPS_BAUDRATE,
            tx=Pin(GPS_TX_PIN),
            rx=Pin(GPS_RX_PIN),
            rxbuf=10000,
            timeout=10,
        )
        log(f"GPS UART({GPS_UART_ID}) initialized.")
        return True
    except Exception as e:
        log(f"Error initializing GPS UART({GPS_UART_ID}): {e}")
        log("-> Check pin assignments and connections.")
        uart = None
        return False


# --- Data Reading Task ---
async def _read_gps_task():
    """Asynchronous task to continuously read and parse NMEA sentences from GPS."""
    if uart is None:
        log("GPS UART not initialized. Cannot start reader task.")
        return

    log("Starting GPS NMEA reader task...")
    reader = asyncio.StreamReader(uart)
    lock_acquired_by_reader = False

    try:
        while True:
            # --- Try to Acquire Lock ---
            lock_acquired_by_reader = _uart_lock.acquire(0)
            if not lock_acquired_by_reader:
                await asyncio.sleep_ms(15)  # Yield/short delay if lock held
                continue

            # --- Lock Acquired by Reader ---
            try:
                # --- Check if Config Function Wants Lock ---
                if _config_request_event.is_set():
                    log("GPS Reader: Config request detected.")
                    if uart.any():
                        flushed = uart.read(uart.any())
                        log(
                            f"GPS Reader: Flushed {len(flushed)} bytes before releasing lock."
                        )
                    _config_request_event.clear()
                    _uart_lock.release()  # Release lock for config function
                    lock_acquired_by_reader = False
                    log("GPS Reader: Lock released for config.")

                    # --- Wait for Config Function to Finish ---
                    log("GPS Reader: Waiting for config done signal...")
                    await _config_done_event.wait()  # type: ignore # Wait until config sets this
                    _config_done_event.clear()  # Clear ready for next time
                    log("GPS Reader: Config done signal received. Resuming loop.")
                    continue  # Go back to start of loop to re-acquire lock

                # --- Normal Read Operation (Lock Held) ---
                else:
                    line_bytes = await reader.readline()  # type: ignore

                    if not line_bytes:
                        pass
                        # await asyncio.sleep_ms(1050)
                        # Continue to finally block to release lock before next iteration
                    else:
                        # --- Parsing Logic (Lock Held) ---
                        start_time_us = time.ticks_us()
                        try:
                            line = line_bytes.decode("ascii").strip()
                        except UnicodeError:
                            log("GPS RX: Invalid ASCII data received")
                            continue  # Skip rest, finally releases lock

                        if not line.startswith("$") or "*" not in line:
                            continue  # Skip rest, finally releases lock

                        # Checksum Verification
                        parts_checksum = line.split("*")
                        if len(parts_checksum) == 2:
                            sentence = parts_checksum[0]
                            try:
                                received_checksum = int(parts_checksum[1], 16)
                                calculated_checksum = 0
                                for char in sentence[1:]:
                                    calculated_checksum ^= ord(char)
                                if calculated_checksum != received_checksum:
                                    log(
                                        f"GPS Checksum error! Line: {line}, Calc: {hex(calculated_checksum)}, Recv: {hex(received_checksum)}"
                                    )
                                    continue  # Skip rest, finally releases lock
                            except ValueError:
                                log(f"GPS Invalid checksum format: {parts_checksum[1]}")
                                continue  # Skip rest, finally releases lock
                        else:
                            log(f"GPS Malformed NMEA (no checksum?): {line}")
                            continue  # Skip rest, finally releases lock

                        # Parse Specific Sentences
                        parts = sentence.split(",")
                        sentence_type = parts[0]
                        parsed_successfully = False
                        if sentence_type == "$GPGGA" and len(parts) >= 10:
                            _parse_gpgga(parts)
                            parsed_successfully = True
                        elif sentence_type == "$GPRMC" and len(parts) >= 10:
                            _parse_gprmc(parts)
                            parsed_successfully = True

                        if parsed_successfully:
                            global _last_valid_data_time
                            _last_valid_data_time = time.ticks_ms()

                        # Update Stats
                        end_time_us = time.ticks_us()
                        duration_us = time.ticks_diff(end_time_us, start_time_us)
                        global _gps_processing_time_us_sum, _gps_processed_sentence_count
                        _gps_processing_time_us_sum += duration_us
                        _gps_processed_sentence_count += 1

            finally:
                # --- Release Lock (if held by this iteration) ---
                if lock_acquired_by_reader:
                    _uart_lock.release()
                    lock_acquired_by_reader = False

            # This is essential in order not to get high CPU in a async reader
            await asyncio.sleep_ms(5)  # Yield/short delay if lock held

    except asyncio.CancelledError:
        log("GPS Reader: Task cancelled.")
        if lock_acquired_by_reader:
            _uart_lock.release()  # Ensure release on cancel
        raise
    except Exception as e:
        log(f"Error in GPS reader task loop: {e}")
        if lock_acquired_by_reader:
            _uart_lock.release()  # Ensure release on error
        await asyncio.sleep_ms(500)


def start_gps_reader():
    """Starts the asynchronous GPS NMEA reader task if not already running."""
    global _reader_task
    if uart is None:
        log("Cannot start GPS reader: UART not initialized.")
        return False
    if _reader_task is None or _reader_task.done():  # type: ignore
        # Clear events before starting
        _config_request_event.clear()
        _config_done_event.clear()
        _reader_task = asyncio.create_task(_read_gps_task())
        log("GPS NMEA reader task created/restarted.")
        return True
    else:
        log("GPS NMEA reader task already running.")
        return False


# Remove stop_gps_reader function


# --- Data Access Functions ---
def get_gps_fix():
    """Returns True if the GPS has a valid fix, False otherwise."""
    return gps_fix


def get_gps_location():
    """Returns the latest GPS location (latitude, longitude) in decimal degrees."""
    return gps_latitude, gps_longitude


def get_gps_altitude():
    """Returns the latest GPS altitude in meters."""
    return gps_altitude


def get_gps_satellites():
    """Returns the number of satellites used in the current fix."""
    return gps_satellites


def get_gps_time_utc():
    """Returns the latest UTC time from GPS as (hour, minute, second)."""
    return gps_time_utc


def get_gps_date():
    """Returns the latest date from GPS as (day, month, year)."""
    return gps_date


def get_gps_data():
    """Returns a dictionary containing all current GPS data, including communication status and formatted date/time."""
    com_ok = False
    if _last_valid_data_time != 0:
        time_since_last_data = time.ticks_diff(time.ticks_ms(), _last_valid_data_time)
        com_ok = time_since_last_data < COMM_TIMEOUT_MS
    com_status = "COM" if com_ok else "NOCOM"

    d, m, y = gps_date
    h, mn, s = gps_time_utc
    formatted_date = f"{d:02d}/{m:02d}/{y}" if y > 0 else "00/00/0000"
    formatted_time = (
        f"{h:02d}:{mn:02d}:{s:02d}" if h > 0 or mn > 0 or s > 0 else "00:00:00"
    )

    return {
        "fix": gps_fix,
        "latitude": gps_latitude,
        "longitude": gps_longitude,
        "altitude": gps_altitude,
        "satellites": gps_satellites,
        "time_utc": gps_time_utc,
        "date": gps_date,
        "formatted_time": formatted_time,
        "formatted_date": formatted_date,
        "com_status": com_status,
    }


def get_gps_processing_stats():
    """Returns the accumulated GPS sentence processing time (us) and count."""
    return _gps_processing_time_us_sum, _gps_processed_sentence_count
