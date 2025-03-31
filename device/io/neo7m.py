from machine import UART, Pin
import uasyncio as asyncio
from log import log

# --- Configuration ---
GPS_UART_ID = 0  # Using UART0 as requested
# IMPORTANT: Default pins for UART0 on many ESP32s (including C3) are often
# used for USB/Serial communication (REPL). Using UART0 might conflict
# if the REPL is active (though less likely on C3 with native USB).
# Disabling REPL on UART0 via uos.dupterm(None, 1) in boot.py is recommended.
# Using default UART0 pins according to pinout table.
GPS_TX_PIN = 21  # GPIO21 (Pinout Table - UART0 Default TX)
GPS_RX_PIN = 20  # GPIO20 (Pinout Table - UART0 Default RX)
GPS_BAUDRATE = 9600  # Common default for NEO-xM modules

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

            # Satellites in view (parts[7])
            gps_satellites = int(parts[7]) if parts[7] else 0

            # Altitude (parts[9]) - meters above mean sea level
            gps_altitude = float(parts[9]) if parts[9] else 0.0
        else:
            # No fix, reset relevant data
            gps_satellites = 0
            # Keep last known time/position? Or reset? Resetting seems safer.
            # gps_latitude = 0.0
            # gps_longitude = 0.0
            # gps_altitude = 0.0
            # gps_time_utc = (0, 0, 0)
            pass  # Keep last known good values if fix is lost temporarily

    except (ValueError, IndexError) as e:
        log(f"Error parsing GPGGA: {e}, parts: {parts}")
        gps_fix = False  # Mark as no fix if parsing fails


def _parse_gprmc(parts):
    """Parses the GPRMC sentence for fix status, time, date, lat, lon."""
    global gps_fix, gps_latitude, gps_longitude, gps_time_utc, gps_date
    try:
        # Status (parts[2]): A=Active/Valid, V=Void/Invalid
        status = parts[2]
        gps_fix = status == "A"

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


# --- Initialization ---
def init_neo7m():
    """
    Initializes UART0 for the NEO-7M GPS module.

    WARNING: UART0 is often used for the REPL (console) and flashing/debugging
    on ESP32 boards, especially the C3 variant. Using it for GPS might lead to
    conflicts or prevent the REPL from working.

    Potential Issues & Solutions:
    1. REPL Conflict: If the REPL is running on UART0, the GPS module won't work reliably.
       - Solution A: Disable the REPL on UART0 (e.g., `uos.dupterm(None, 1)` in boot.py)
                    and potentially redirect it to UART1 if needed and pins are available.
       - Solution B: Use a different UART (UART1 or UART2 if available on your board)
                    with appropriate, free GPIO pins. Check your board's pinout.
    2. Pin Conflict: Ensure the chosen TX/RX pins (currently {GPS_TX_PIN}/{GPS_RX_PIN})
                     are not used by other peripherals or essential functions.
       - Solution: Modify GPS_TX_PIN and GPS_RX_PIN in this file to match available pins.
    3. Hardware UART Limitation: Some boards might have limitations on which pins
                                can be used for hardware UARTs.
       - Solution: Consider using `machine.SoftUART` if hardware UARTs are unavailable,
                   but be aware of potential performance impacts.

    This function attempts initialization but success depends on resolving these conflicts.
    """
    global uart
    log(
        f"Attempting to initialize NEO-7M GPS on UART({GPS_UART_ID}) TX={GPS_TX_PIN}, RX={GPS_RX_PIN}"
    )
    log("WARNING: UART0 conflict possible with REPL/USB. Check init_neo7m() comments.")
    try:
        # Ensure pins are correctly assigned
        uart = UART(
            GPS_UART_ID,
            baudrate=GPS_BAUDRATE,
            tx=Pin(GPS_TX_PIN),
            rx=Pin(GPS_RX_PIN),
            timeout=10,
        )  # Short timeout
        log(f"GPS UART({GPS_UART_ID}) initialized.")
        return True
    except Exception as e:
        log(f"Error initializing GPS UART({GPS_UART_ID}): {e}")
        log("-> Check for REPL/pin conflicts or try different UART/pins.")
        uart = None
        return False


# --- Data Reading Task ---
async def _read_neo7m_task():
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

            if not line_bytes:
                # log("GPS Read timeout or empty line") # Debug
                await asyncio.sleep_ms(100)  # Avoid busy-looping on empty reads
                continue

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

            if sentence_type == "$GPGGA" and len(parts) >= 10:
                _parse_gpgga(parts)
            elif sentence_type == "$GPRMC" and len(parts) >= 10:
                _parse_gprmc(parts)
            # Add parsers for other sentences (GSA, GSV, etc.) if needed

        except Exception as e:
            log(f"Error in GPS reader task loop: {e}")
            await asyncio.sleep_ms(500)  # Avoid tight loop on error

        # Yield control briefly
        await asyncio.sleep_ms(10)


def start_neo7m_reader():
    """Starts the asynchronous GPS NMEA reader task."""
    global _reader_task
    if uart is None:
        log("Cannot start GPS reader: UART not initialized.")
        return False
    if _reader_task is None:
        _reader_task = asyncio.create_task(_read_neo7m_task())
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
    """Returns a dictionary containing all current GPS data."""
    return {
        "fix": gps_fix,
        "latitude": gps_latitude,
        "longitude": gps_longitude,
        "altitude": gps_altitude,
        "satellites": gps_satellites,
        "time_utc": gps_time_utc,
        "date": gps_date,
    }
