from machine import UART, Pin, RTC  # Added RTC
import uasyncio as asyncio
import time
import machine  # Added machine
from log import log
from rtc import set_rtc_from_gmtime_tuple
from . import data_log

_JERUSALEM_TZ_OFFSET_HOURS = 3  # Jerusalem Timezone Offset (UTC+3 for IDT)

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
gps_satellites = 0  # Active satellites used in fix (from GPGGA)
gps_speed_knots = 0.0  # Speed over ground in knots (from GPRMC)
gps_satellites_seen = 0  # Satellites in view (from GPGSV)
# gps_time_utc and gps_date are no longer primary state, managed internally for RTC sync
_reader_task = None
_logger_task = None  # Task handle for the logger coroutine
# _uart_lock = allocate_lock() # REMOVED
_reader_enabled_event = asyncio.Event()  # New: Controls reader activity
_reader_enabled_event.set()  # Start enabled
_last_valid_data_time = 0  # Timestamp of the last valid NMEA sentence
_gps_processing_time_us_sum = 0
_gps_processed_sentence_count = 0
_rtc_needs_initial_sync = True  # Flag to track if RTC needs first sync before fix
_rtc_synced_by_fix = False  # Flag to track if RTC has been synced by a fix
_seen_satellite_prns = set()  # Internal set to track unique PRNs seen in a GSV cycle

SENSOR_NAME = "gps"


# --- Getter Functions ---
def get_uart():
    """Returns the initialized UART object for the GPS."""
    return uart


# def get_uart_lock(): # REMOVED
#     return _uart_lock


def get_reader_enabled_event():
    """Returns the event controlling the reader task's active state."""
    return _reader_enabled_event


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
    # Parses GPGGA for Altitude and Active Satellite count.
    # Also resets the seen satellite set.
    global gps_fix, gps_altitude, gps_satellites, _seen_satellite_prns  # Removed lat/lon globals
    try:
        # Reset seen satellites at the start of a potential new cycle
        _seen_satellite_prns.clear()

        fix_quality = int(parts[6]) if parts[6] else 0
        current_fix_status = fix_quality > 0
        gps_satellites = (
            int(parts[7]) if len(parts) > 7 and parts[7] else 0
        )  # Active satellites

        # Update global fix status based on GGA as well
        gps_fix = current_fix_status

        if gps_fix:
            # Update altitude here
            gps_altitude = float(parts[9]) if len(parts) > 9 and parts[9] else 0.0
        # else: Keep last known good altitude

    except (ValueError, IndexError) as e:
        data_log.report_error(
            SENSOR_NAME,
            time.ticks_ms(),
            f"Error parsing GPGGA: {e}, parts: {parts}",
        )
        # Don't set global gps_fix to False here


def _parse_gprmc(parts):
    """Parses GPRMC for Lat, Lon, Speed, Status, and performs RTC sync logic."""
    global gps_fix, gps_latitude, gps_longitude, gps_speed_knots, _rtc_needs_initial_sync, _rtc_synced_by_fix, _seen_satellite_prns
    gps_epoch = None  # Initialize for this scope

    try:
        # Reset seen satellites at the start of a potential new cycle
        _seen_satellite_prns.clear()

        # --- Basic Fix Status & Speed ---
        status = parts[2] if len(parts) > 2 else "V"
        current_fix_status = status == "A"
        gps_fix = current_fix_status  # Update global fix status

        # Update Speed
        try:
            gps_speed_knots = float(parts[7]) if parts[7] else 0.0
        except (ValueError, IndexError):
            gps_speed_knots = 0.0  # Default to 0 on error

        # --- Early Exit if RTC is already synced by a fix ---
        if _rtc_synced_by_fix:
            # Only update location if we have a fix, then return
            if gps_fix:
                try:
                    lat = _parse_nmea_degrees(parts[3])
                    if parts[4] == "S":
                        lat = -lat
                    gps_latitude = lat
                    lon = _parse_nmea_degrees(parts[5])
                    if parts[6] == "W":
                        lon = -lon
                    gps_longitude = lon
                except (ValueError, IndexError) as e:
                    data_log.report_error(
                        SENSOR_NAME,
                        time.ticks_ms(),
                        f"Error parsing Lat/Lon in GPRMC (post-sync): {e}",
                    )
            return  # Skip all time processing

        # --- Time Processing (Only if RTC not yet synced by fix) ---
        time_str = parts[1]
        date_str = parts[9]
        parsed_epoch_this_run = False

        # Only parse time if date/time strings are valid AND we still need an initial sync OR if we have a fix
        if (
            len(time_str) >= 6
            and len(date_str) == 6
            and (_rtc_needs_initial_sync or gps_fix)
        ):
            try:
                # Parse to Epoch
                hh = int(time_str[0:2])
                mm = int(time_str[2:4])
                ss = int(float(time_str[4:]))
                dd = int(date_str[0:2])
                mo = int(date_str[2:4])
                yy = int(date_str[4:6]) + 2000
                utc_tuple = (yy, mo, dd, hh, mm, ss, 0, 0)
                gps_epoch = time.mktime(utc_tuple)  # type: ignore
                parsed_epoch_this_run = True

                # (c) Attempt Initial Sync (if needed and epoch is valid)
                if _rtc_needs_initial_sync and gps_epoch > time.time():
                    try:
                        rtc = machine.RTC()
                        rtc_tuple = time.gmtime(gps_epoch)
                        rtc.datetime(rtc_tuple)
                        _rtc_needs_initial_sync = False
                        log_time_str = f"{rtc_tuple[0]}-{rtc_tuple[1]:02d}-{rtc_tuple[2]:02d} {rtc_tuple[4]:02d}:{rtc_tuple[5]:02d}:{rtc_tuple[6]:02d}"
                        log(f"RTC updated (initial sync): {log_time_str} UTC")
                    except Exception as e:
                        log(f"Error setting RTC during initial sync: {e}")

            except (ValueError, IndexError, TypeError) as e:
                data_log.report_error(
                    SENSOR_NAME,
                    time.ticks_ms(),
                    f"Error parsing GPS date/time: {e}, Date: '{date_str}', Time: '{time_str}'",
                )
                gps_epoch = None  # Ensure gps_epoch is None if parsing failed

        # --- Update RTC on Fix (The definitive sync) ---
        if gps_fix and parsed_epoch_this_run and gps_epoch is not None:
            try:
                gmtime_tuple = time.gmtime(gps_epoch)
                if not _rtc_synced_by_fix:  # Log only the first time
                    if set_rtc_from_gmtime_tuple(gmtime_tuple):
                        log_time_str = f"{gmtime_tuple[0]}-{gmtime_tuple[1]:02d}-{gmtime_tuple[2]:02d} {gmtime_tuple[3]:02d}:{gmtime_tuple[4]:02d}:{gmtime_tuple[5]:02d}"
                        log(f"RTC updated via GPS using helper: {log_time_str} UTC")
                    _rtc_needs_initial_sync = False
                _rtc_needs_initial_sync = False
                _rtc_synced_by_fix = True
            except Exception as e:
                log(f"Error setting RTC on fix: {e}")

        # --- Update Location (only if fix is current) ---
        # This happens regardless of RTC sync status, as long as fix is valid
        if gps_fix:
            try:
                lat = _parse_nmea_degrees(parts[3])
                if parts[4] == "S":
                    lat = -lat
                gps_latitude = lat
                lon = _parse_nmea_degrees(parts[5])
                if parts[6] == "W":
                    lon = -lon
                gps_longitude = lon
            except (ValueError, IndexError) as e:
                data_log.report_error(
                    SENSOR_NAME,
                    time.ticks_ms(),
                    f"Error parsing Lat/Lon in GPRMC: {e}",
                )

    except (ValueError, IndexError) as e:
        data_log.report_error(
            SENSOR_NAME,
            time.ticks_ms(),
            f"Critical Error parsing GPRMC: {e}, parts: {parts}",
        )
        gps_fix = False  # Ensure fix is false on major parsing error


def _parse_gpgsv(parts):
    """
    Parses GPGSV sentences to collect the PRNs of satellites in view.
    Expected format: $GPGSV,num_msgs,msg_num,sats_in_view,prn1,elev1,azim1,snr1,prn2,...*cs
    """
    global _seen_satellite_prns
    try:
        # num_msgs = int(parts[1])
        # msg_num = int(parts[2])
        # sats_in_view = int(parts[3]) # Total sats in view (can be used for validation)

        # If this is the first message of a potential sequence, clear the set?
        # RMC/GGA already clear it, so maybe not needed here unless GSV arrives first.
        # Let's rely on RMC/GGA clearing for now.

        # Sat info starts at index 4, in groups of 4 (prn, elev, azim, snr)
        sat_info_start_index = 4
        num_sats_in_this_msg = (
            len(parts) - sat_info_start_index - 1
        ) // 4  # -1 for checksum part split later

        for i in range(num_sats_in_this_msg):
            prn_index = sat_info_start_index + (i * 4)
            if parts[prn_index]:  # Check if PRN field is not empty
                prn = int(parts[prn_index])
                _seen_satellite_prns.add(prn)
            # We don't currently need elevation, azimuth, or SNR

    except (ValueError, IndexError) as e:
        data_log.report_error(
            SENSOR_NAME,
            time.ticks_ms(),
            f"Error parsing GPGSV: {e}, parts: {parts}",
        )


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
    _reader_enabled_event.set()  # Ensure reader starts enabled

    while True:
        try:
            # --- Check if Enabled ---
            if not _reader_enabled_event.is_set():
                log("GPS Reader: Disabled by user. Waiting...")
                await _reader_enabled_event.wait()  # type: ignore # Wait until enabled
                log("GPS Reader: Re-enabled by user.")
                # Optional: Flush buffer after re-enabling?
                if uart.any():
                    flushed = uart.read(uart.any())
                    log(f"GPS Reader: Flushed {len(flushed)} bytes after re-enable.")

            # --- Normal Read Operation (No Lock Needed) ---
            line_bytes = await reader.readline()  # type: ignore

            if not line_bytes:
                pass
            else:
                # --- Parsing Logic ---
                start_time_us = time.ticks_us()
                try:
                    line = line_bytes.decode("ascii").strip()
                except UnicodeError:
                    data_log.report_error(
                        SENSOR_NAME,
                        time.ticks_ms(),
                        "GPS RX: Invalid ASCII data received",
                    )
                    continue

                if not line.startswith("$") or "*" not in line:
                    continue

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
                            data_log.report_error(
                                SENSOR_NAME,
                                time.ticks_ms(),
                                f"GPS Checksum error! Line: {line}, Calc: {hex(calculated_checksum)}, Recv: {hex(received_checksum)}",
                            )
                            continue
                    except ValueError:
                        data_log.report_error(
                            SENSOR_NAME,
                            time.ticks_ms(),
                            f"GPS Malformed NMEA (no checksum?): {line}",
                        )

                        log(f"GPS Invalid checksum format: {parts_checksum[1]}")
                        continue
                else:
                    data_log.report_error(
                        SENSOR_NAME,
                        time.ticks_ms(),
                        f"GPS Malformed NMEA (no checksum?): {line}",
                    )

                    continue

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
                elif sentence_type == "$GPGSV":  # Handle GPGSV
                    _parse_gpgsv(parts)
                    # Don't mark parsed_successfully=True for GSV alone,
                    # as it doesn't guarantee core fix/time data.
                    # But DO update last valid data time if checksum was okay.
                    global _last_valid_data_time  # Make sure global is declared if needed here
                    _last_valid_data_time = time.ticks_ms()

                if parsed_successfully:
                    # Update last valid time only if GGA or RMC parsed okay
                    _last_valid_data_time = time.ticks_ms()

                # Update Stats (GSV contributes to count but not necessarily 'successful parse')
                end_time_us = time.ticks_us()
                duration_us = time.ticks_diff(end_time_us, start_time_us)
                global _gps_processing_time_us_sum, _gps_processed_sentence_count  # Make sure global is declared
                _gps_processing_time_us_sum += duration_us
                _gps_processed_sentence_count += 1

        except asyncio.CancelledError:
            log("GPS Reader: Task cancelled.")
            _reader_enabled_event.set()
            raise
        except Exception as e:
            log(f"Error in GPS reader task loop: {e}")
            _reader_enabled_event.set()  # Ensure enabled on error exit
            await asyncio.sleep_ms(500)

        # Yield control
        await asyncio.sleep_ms(25)


async def _log_gps_status_task():
    """Asynchronous task to log GPS status periodically."""
    global gps_satellites_seen  # We need to update this global based on the set
    while True:
        try:
            await asyncio.sleep_ms(1000)

            # Check communication status
            is_com_ok = False
            if _last_valid_data_time != 0:
                time_since_last_data = time.ticks_diff(
                    time.ticks_ms(), _last_valid_data_time
                )
                is_com_ok = time_since_last_data < COMM_TIMEOUT_MS

            if not is_com_ok:
                data_log.report_error(SENSOR_NAME, time.ticks_ms(), "nocom")
                continue

            # Update seen satellite count from the collected set
            gps_satellites_seen = len(_seen_satellite_prns)

            # Log based on fix status
            if gps_fix:
                data_log.report_data(
                    SENSOR_NAME,
                    time.ticks_ms(),
                    dict(
                        Fix=True,
                        Lat=gps_latitude,
                        Lon=gps_longitude,
                        Alt=gps_altitude,
                        Spd=gps_speed_knots,
                        Seen=gps_satellites_seen,
                        Active=gps_satellites,
                    ),
                )

            else:
                data_log.report_data(
                    SENSOR_NAME,
                    time.ticks_ms(),
                    dict(Fix=False, Seen=gps_satellites_seen, Active=gps_satellites),
                )

        except asyncio.CancelledError:
            log("GPS Logger: Task cancelled.")
            raise
        except Exception as e:
            log(f"Error in GPS logger task loop: {e}")
            await asyncio.sleep_ms(1000)  # Wait a bit before retrying on error


def start_gps_reader():
    """Starts the GPS reader and logger tasks if not already running."""
    global _reader_task, _logger_task
    if uart is None:
        log("Cannot start GPS reader: UART not initialized.")
        return False

    reader_started = False
    if _reader_task is None or _reader_task.done():  # type: ignore
        _reader_enabled_event.set()  # Ensure reader starts enabled
        _reader_task = asyncio.create_task(_read_gps_task())
        log("GPS NMEA reader task created/restarted.")
        reader_started = True
    else:
        # If already running, ensure it's enabled
        if not _reader_enabled_event.is_set():
            _reader_enabled_event.set()
            log("GPS NMEA reader task was paused, re-enabling.")
        else:
            log("GPS NMEA reader task already running.")
        reader_started = True  # Consider it success if already running

    logger_started = False
    if _logger_task is None or _logger_task.done():  # type: ignore
        _logger_task = asyncio.create_task(_log_gps_status_task())
        log("GPS Status logger task created/restarted.")
        logger_started = True
    else:
        log("GPS Status logger task already running.")
        logger_started = True

    return reader_started and logger_started


# Removed stop_gps_reader function


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


# Removed get_gps_time_utc()
# Removed get_gps_date()
# Removed get_gps_data() - Logging is now handled by _log_gps_status_task


def get_gps_processing_stats():
    """Returns the accumulated GPS sentence processing time (us) and count."""
    return _gps_processing_time_us_sum, _gps_processed_sentence_count


# --- Public Data Access ---
# Provide getters for the data used in the new log format
def get_gps_speed_knots():
    """Returns the latest speed over ground in knots."""
    return gps_speed_knots


def get_gps_satellites_seen():
    """Returns the count of unique satellites seen in the last cycle."""
    # Note: This value is updated periodically by the logger task based on _seen_satellite_prns
    return gps_satellites_seen


def is_rtc_synced() -> bool:
    """Returns True if the RTC has been synced by a GPS fix."""
    global _rtc_synced_by_fix
    return _rtc_synced_by_fix
