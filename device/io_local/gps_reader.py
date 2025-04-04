from machine import UART, Pin
import uasyncio as asyncio
import time
from _thread import allocate_lock  # Import the thread-safe lock
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
_uart_lock = allocate_lock()  # Use a thread-safe lock for UART access
_last_valid_data_time = 0  # Timestamp of the last valid NMEA sentence
_gps_processing_time_us_sum = 0
_gps_processed_sentence_count = 0


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
        # Check fix quality (parts[6]): 0=No fix, 1=GPS fix, 2=DGPS fix, etc.
        fix_quality = int(parts[6]) if parts[6] else 0
        gps_fix = fix_quality > 0
        time_str = parts[1] if len(parts) > 1 else "N/A"
        sats_str = parts[7] if len(parts) > 7 and parts[7] else "0"
        alt = parts[9] if len(parts) > 9 and parts[9] else "N/A"
        # Format time for logging
        formatted_time = time_str
        if len(time_str) >= 6 and "." in time_str:  # Check basic format HHMMSS.sss
            try:
                formatted_time = f"{time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}"
            except IndexError:  # Handle potential malformed time_str
                pass  # Keep original time_str if formatting fails
        # log(
        #     f"GPS GPGGA Parsed: Fix={gps_fix} (Qual={fix_quality}), Sats={sats_str}, Alt={alt}m, Time={formatted_time}"
        # )

        # Satellites in view (parts[7]) - Parse regardless of fix status
        gps_satellites = int(sats_str) if sats_str else 0

        if gps_fix:
            # Time (parts[1]): HHMMSS.sss
            time_str = parts[1]
            if len(time_str) >= 6:
                gps_time_utc = (
                    int(time_str[0:2]),
                    int(time_str[2:4]),
                    int(float(time_str[4:])),
                )  # Hour, Min, Sec (float for ms)

            # Latitude (parts[2]) and N/S indicator (parts[3])
            lat = _parse_nmea_degrees(parts[2])
            if parts[3] == "S":
                lat = -lat
            gps_latitude = lat

            # Longitude (parts[4]) and E/W indicator (parts[5])
            lon = _parse_nmea_degrees(parts[4])
            if parts[5] == "W":
                lon = -lon
            gps_longitude = lon

            # Satellites already parsed above
            pass

            # Altitude (parts[9]) - meters above mean sea level
            gps_altitude = float(parts[9]) if parts[9] else 0.0
        else:
            # No fix, keep satellite count but reset other relevant data if desired
            # Resetting position/time seems safer if fix is lost for a while.
            # gps_latitude = 0.0
            # gps_longitude = 0.0
            # gps_altitude = 0.0
            # gps_time_utc = (0, 0, 0)
            pass  # Keep last known good values for position/time if fix is lost temporarily

    except (ValueError, IndexError) as e:
        log(f"Error parsing GPGGA: {e}, parts: {parts}")
        gps_fix = False  # Mark as no fix if parsing fails


def _parse_gprmc(parts):
    """Parses the GPRMC sentence for fix status, time, date, lat, lon."""
    global gps_fix, gps_latitude, gps_longitude, gps_time_utc, gps_date
    try:
        # Status (parts[2]): A=Active/Valid, V=Void/Invalid
        status = parts[2] if len(parts) > 2 else "N/A"
        gps_fix = status == "A"
        time_str = parts[1] if len(parts) > 1 else "N/A"
        date_str = parts[9] if len(parts) > 9 else "N/A"
        # Format time for logging
        formatted_time = time_str
        if len(time_str) >= 6 and "." in time_str:  # Check basic format HHMMSS.sss
            try:
                formatted_time = f"{time_str[0:2]}:{time_str[2:4]}:{time_str[4:6]}"
            except IndexError:  # Handle potential malformed time_str
                pass  # Keep original time_str if formatting fails
        # Format date for logging
        formatted_date = date_str
        if len(date_str) == 6:
            try:
                formatted_date = f"{date_str[0:2]}/{date_str[2:4]}/20{date_str[4:6]}"
            except IndexError:  # Handle potential malformed date_str
                pass  # Keep original date_str if formatting fails
        # log(
        #     f"GPS GPRMC Parsed: Fix={gps_fix} (Status={status}), Time={formatted_time}, Date={formatted_date}"
        # )

        if gps_fix:
            # Time (parts[1]): HHMMSS.sss
            time_str = parts[1]
            if len(time_str) >= 6:
                gps_time_utc = (
                    int(time_str[0:2]),
                    int(time_str[2:4]),
                    int(float(time_str[4:])),
                )

            # Latitude (parts[3]) and N/S indicator (parts[4])
            lat = _parse_nmea_degrees(parts[3])
            if parts[4] == "S":
                lat = -lat
            gps_latitude = lat

            # Longitude (parts[5]) and E/W indicator (parts[6])
            lon = _parse_nmea_degrees(parts[5])
            if parts[6] == "W":
                lon = -lon
            gps_longitude = lon

            # Date (parts[9]): DDMMYY
            date_str = parts[9]
            if len(date_str) == 6:
                day = int(date_str[0:2])
                month = int(date_str[2:4])
                year = int(date_str[4:6]) + 2000  # Assuming 21st century
                gps_date = (day, month, year)
        else:
            # No fix, reset relevant data (similar to GPGGA)
            pass  # Keep last known good values

    except (ValueError, IndexError) as e:
        log(f"Error parsing GPRMC: {e}, parts: {parts}")
        gps_fix = False

        # if uart.any():
        #     line_bytes = uart.readline()
        #     if not line_bytes:
        #         await asyncio.sleep_ms(10)
        #         continue
        # else:
        #     # No data available, yield control briefly
        #     await asyncio.sleep_ms(10)  # Shorter sleep interva


# --- Initialization ---
def init_gps_reader():
    """Initializes UART1 for the GPS module using the configured pins."""
    global uart
    log(
        f"Attempting to initialize NEO-7M GPS on UART({GPS_UART_ID}) TX={GPS_TX_PIN}, RX={GPS_RX_PIN}"
    )
    try:
        # Ensure pins are correctly assigned
        uart = UART(
            GPS_UART_ID,
            baudrate=GPS_BAUDRATE,
            tx=Pin(GPS_TX_PIN),
            rx=Pin(GPS_RX_PIN),
            rxbuf=10000,  # Reduced buffer size for 1Hz/9600baud
            timeout=10,
        )  # Short timeout
        log(f"GPS UART({GPS_UART_ID}) initialized.")
        return True
    except Exception as e:
        log(f"Error initializing GPS UART({GPS_UART_ID}): {e}")
        log("-> Check pin assignments and connections.")
        uart = None
        return False

    # log("Starting GPS NMEA reader task...")
    # while True:
    #     if uart.any():
    #         print(uart.readline())  # Print raw GPS data
    #     await asyncio.sleep_ms(200)


# --- Data Reading Task ---
async def _read_gps_task():
    """Asynchronous task to continuously read and parse NMEA sentences from GPS."""
    if uart is None:
        log("GPS UART not initialized. Cannot start reader task.")
        return

    log("Starting GPS NMEA reader task...")
    reader = asyncio.StreamReader(uart)

    while True:
        try:
            # Read a line (NMEA sentence ends with \r\n)
            # Using readline() on StreamReader handles buffering and line endings
            line_bytes = await reader.readline()  # type: ignore # Pylance false positive

            # if line_bytes:  # DEBUG: Log raw bytes received
            # log(f"GPS RAW RX ({len(line_bytes)} bytes): {line_bytes}")
            if not line_bytes:
                # log("GPS Read timeout or empty line") # Debug
                # Wait slightly longer than 1Hz update cycle when buffer is empty
                print(1)
                await asyncio.sleep_ms(1050)
                print(2)
                continue
            # If we reach here, line_bytes is not empty
            start_time_us = time.ticks_us()  # Start timing processing

            try:
                line = line_bytes.decode("ascii").strip()
                # log(f"GPS RX: {line}") # Debug: Print raw NMEA sentences
            except UnicodeError:
                log("GPS RX: Invalid ASCII data received")
                continue

            if not line.startswith("$") or "*" not in line:
                # log(f"GPS RX: Skipping invalid NMEA line: {line}") # Debug
                continue

            # --- NMEA Checksum Verification (Optional but Recommended) ---
            parts_checksum = line.split("*")
            if len(parts_checksum) == 2:
                sentence = parts_checksum[0]
                try:
                    received_checksum = int(parts_checksum[1], 16)
                    calculated_checksum = 0
                    for char in sentence[1:]:  # Skip the '$'
                        calculated_checksum ^= ord(char)
                    if calculated_checksum != received_checksum:
                        log(
                            f"GPS Checksum error! Line: {line}, Calc: {hex(calculated_checksum)}, Recv: {hex(received_checksum)}"
                        )
                        continue  # Skip lines with bad checksum
                except ValueError:
                    log(f"GPS Invalid checksum format: {parts_checksum[1]}")
                    continue  # Skip lines with bad checksum format
            else:
                log(f"GPS Malformed NMEA (no checksum?): {line}")
                continue  # Skip malformed lines

            # --- Parse Specific Sentences ---
            parts = sentence.split(",")
            sentence_type = parts[0]
            parsed_successfully = False

            if sentence_type == "$GPGGA" and len(parts) >= 10:
                _parse_gpgga(parts)
                parsed_successfully = True  # Assume parsing means valid data received
            elif sentence_type == "$GPRMC" and len(parts) >= 10:
                _parse_gprmc(parts)
                parsed_successfully = True  # Assume parsing means valid data received
            # Add parsers for other sentences (GSA, GSV, etc.) if needed

            # Update last valid data time if parsing was successful
            if parsed_successfully:
                global _last_valid_data_time
                _last_valid_data_time = time.ticks_ms()  # Mark time of valid data

            # --- End Timing and Update Stats ---
            end_time_us = time.ticks_us()
            duration_us = time.ticks_diff(end_time_us, start_time_us)
            global _gps_processing_time_us_sum, _gps_processed_sentence_count
            _gps_processing_time_us_sum += duration_us
            _gps_processed_sentence_count += 1

        except Exception as e:
            log(f"Error in GPS reader task loop: {e}")
            await asyncio.sleep_ms(500)  # Avoid tight loop on error

        # Yield control briefly
        # Minimal sleep after processing a line to yield control
        await asyncio.sleep_ms(50)


def start_gps_reader():
    """Starts the asynchronous GPS NMEA reader task."""
    global _reader_task
    if uart is None:
        log("Cannot start GPS reader: UART not initialized.")
        return False
    if _reader_task is None:
        _reader_task = asyncio.create_task(_read_gps_task())
        log("GPS NMEA reader task created.")
        return True
    else:
        log("GPS NMEA reader task already running.")
        return False


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
    # Check communication status
    com_ok = False
    if _last_valid_data_time != 0:  # Ensure we've received at least one message
        time_since_last_data = time.ticks_diff(time.ticks_ms(), _last_valid_data_time)
        com_ok = time_since_last_data < COMM_TIMEOUT_MS

    com_status = "COM" if com_ok else "NOCOM"

    # Format date and time
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
        "time_utc": gps_time_utc,  # Keep raw tuple
        "date": gps_date,  # Keep raw tuple
        "formatted_time": formatted_time,
        "formatted_date": formatted_date,
        "com_status": com_status,
    }


def get_uart():
    """Returns the initialized UART object for the GPS."""
    return uart


def get_uart_lock():
    """Returns the thread-safe Lock used for UART access."""
    return _uart_lock


def get_gps_processing_stats():
    """Returns the accumulated GPS sentence processing time (us) and count."""
    # Return copies to avoid race conditions if accessed elsewhere, though unlikely here
    return _gps_processing_time_us_sum, _gps_processed_sentence_count
