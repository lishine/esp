from machine import UART, Pin, RTC  # Added RTC
import uasyncio as asyncio
import time
from io_local import control
import rtc
import log
from . import data_log

_JERUSALEM_TZ_OFFSET_HOURS = 3  # Jerusalem Timezone Offset (UTC+3 for IDT)

# --- Configuration ---
GPS_UART_ID = 1  # Using UART1
GPS_TX_PIN = 17  # ESP32 TX -> GPS RX
GPS_RX_PIN = 18  # ESP32 RX <- GPS TX
GPS_BAUDRATE = 9600  # Common default for NEO-xM modules
COMM_TIMEOUT_MS = 5000  # 5 seconds timeout for communication status
NO_FIX_LOG_INTERVAL_MS: int = 5000  # Interval for logging when no fix

# --- State ---
uart = None
gps_fix = False
gps_latitude = 0.0  # Decimal degrees
gps_longitude = 0.0  # Decimal degrees
gps_altitude = 0.0  # Meters
gps_satellites = 0  # Active satellites used in fix (from GPGGA)
gps_speed_knots = 0.0  # Speed over ground in knots (from GPRMC)
gps_satellites_seen = 0  # Satellites in view (from GPGSV)
gps_heading_degrees = 0.0
# gps_time_utc and gps_date are no longer primary state, managed internally for RTC sync
_reader_task = None
_logger_task = None  # Task handle for the logger coroutine
# _uart_lock = allocate_lock() # REMOVED
_reader_enabled_event = asyncio.Event()  # New: Controls reader activity
_reader_enabled_event.set()  # Start enabled
_last_valid_data_time = 0  # Timestamp of the last valid NMEA sentence
_gps_processing_time_us_sum = 0
_gps_processed_sentence_count = 0
_rtc_synced = False  # True after RTC is synced once on first GPS fix
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


def _parse_gprmc(parts: list[str]):
    """
    Parses GPRMC for Lat, Lon, Speed, Status, and performs a one-time RTC sync on first GPS fix.
    """
    global gps_fix, gps_latitude, gps_longitude, gps_speed_knots, gps_heading_degrees, _rtc_synced, _seen_satellite_prns

    try:
        # Reset seen satellites at the start of a potential new cycle
        _seen_satellite_prns.clear()

        # --- Basic Fix Status & Speed ---
        status = parts[2] if len(parts) > 2 else "V"
        prev_fix = gps_fix
        current_fix = status == "A"

        # If fix was just achieved, play the GPS fixed sequence
        if not prev_fix and current_fix:
            asyncio.create_task(control.gps_fixed())

        gps_fix = current_fix

        # Update Speed
        try:
            gps_speed_knots = float(parts[7]) if parts[7] else 0.0
        except (ValueError, IndexError):
            gps_speed_knots = 0.0  # Default to 0 on error

        if gps_fix:
            try:
                if len(parts) > 8 and parts[8]:
                    gps_heading_degrees = float(parts[8])
            except (ValueError, IndexError):
                pass  # Retain previous value on error

        # --- One-time RTC Sync on First Fix ---
        if gps_fix and not _rtc_synced:
            time_str = parts[1]
            date_str = parts[9]
            if len(time_str) >= 6 and len(date_str) == 6:
                try:
                    hh = int(time_str[0:2])
                    mm = int(time_str[2:4])
                    ss = int(float(time_str[4:]))
                    dd = int(date_str[0:2])
                    mo = int(date_str[2:4])
                    yy = int(date_str[4:6]) + 2000
                    if not (
                        0 <= hh <= 23
                        and 0 <= mm <= 59
                        and 0 <= ss <= 59
                        and 1 <= dd <= 31
                        and 1 <= mo <= 12
                        and yy >= 2023
                    ):
                        raise ValueError("Parsed date/time out of range")
                    utc_tuple = (
                        yy,
                        mo,
                        dd,
                        hh,
                        mm,
                        ss,
                        0,
                        0,
                    )  # weekday and yearday are 0
                    gps_epoch = time.mktime(utc_tuple)  # type: ignore
                    gmtime_tuple_current = time.gmtime(gps_epoch)
                    rtc.update_rtc_if_needed(gmtime_tuple_current)
                    _rtc_synced = True
                    log.log("GPS: RTC synced on first fix.")
                #
                except (ValueError, IndexError, TypeError) as e:
                    data_log.report_error(
                        SENSOR_NAME,
                        time.ticks_ms(),
                        f"Error parsing GPS date/time: {e}, Date: '{date_str}', Time: '{time_str}'",
                    )

        # --- Update Location (only if fix is current) ---
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
                    SENSOR_NAME, time.ticks_ms(), f"Error parsing Lat/Lon in GPRMC: {e}"
                )

    except (ValueError, IndexError) as e:
        data_log.report_error(
            SENSOR_NAME,
            time.ticks_ms(),
            f"Critical Error parsing GPRMC: {e}, parts: {parts}",
        )
        gps_fix = False


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
    log.log(
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
        log.log(f"GPS UART({GPS_UART_ID}) initialized.")
        return True
    except Exception as e:
        log.log(f"Error initializing GPS UART({GPS_UART_ID}): {e}")
        log.log("-> Check pin assignments and connections.")
        uart = None
        return False


# --- Data Reading Task ---
async def _read_gps_task():
    """Asynchronous task to continuously read and parse NMEA sentences from GPS."""
    if uart is None:
        log.log("GPS UART not initialized. Cannot start reader task.")
        return

    log.log("Starting GPS NMEA reader task...")
    reader = asyncio.StreamReader(uart)
    _reader_enabled_event.set()  # Ensure reader starts enabled

    while True:
        try:
            # --- Check if Enabled ---
            if not _reader_enabled_event.is_set():
                log.log("GPS Reader: Disabled by user. Waiting...")
                await _reader_enabled_event.wait()  # type: ignore # Wait until enabled
                log.log("GPS Reader: Re-enabled by user.")
                # Optional: Flush buffer after re-enabling?
                if uart.any():
                    flushed = uart.read(uart.any())
                    log.log(
                        f"GPS Reader: Flushed {len(flushed)} bytes after re-enable."
                    )

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

                        log.log(f"GPS Invalid checksum format: {parts_checksum[1]}")
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
                    global _last_valid_data_time
                    _last_valid_data_time = time.ticks_ms()

                if parsed_successfully:
                    # Update last valid time if any relevant sentence (GGA, RMC) parsed okay
                    _last_valid_data_time = time.ticks_ms()

                # Update Stats (GSV contributes to count but not necessarily 'successful parse')
                end_time_us = time.ticks_us()
                duration_us = time.ticks_diff(end_time_us, start_time_us)
                global _gps_processing_time_us_sum, _gps_processed_sentence_count
                _gps_processing_time_us_sum += duration_us
                _gps_processed_sentence_count += 1

        except asyncio.CancelledError:
            log.log("GPS Reader: Task cancelled.")
            _reader_enabled_event.set()
            raise
        except Exception as e:
            log.log(f"Error in GPS reader task loop: {e}")
            _reader_enabled_event.set()  # Ensure enabled on error exit
            await asyncio.sleep_ms(500)

        # Yield control
        await asyncio.sleep_ms(25)


async def _log_gps_status_task():
    """Asynchronous task to log GPS status periodically."""
    global gps_satellites_seen
    last_no_fix_log_time_ms: int = 0  # Initialize at the start of the task

    while True:
        try:
            await asyncio.sleep_ms(1000)  # Base check interval

            is_com_ok = False
            if _last_valid_data_time != 0:
                current_ticks = time.ticks_ms()
                time_since_last_data = time.ticks_diff(
                    current_ticks, _last_valid_data_time
                )
                is_com_ok = time_since_last_data < COMM_TIMEOUT_MS

            if not is_com_ok:
                data_log.report_error(SENSOR_NAME, time.ticks_ms(), "nocom")
                continue

            gps_satellites_seen = len(_seen_satellite_prns)

            # Conditional Logging based on fix status and interval
            if gps_fix:
                data_log.report_data(
                    SENSOR_NAME,
                    time.ticks_ms(),
                    dict(
                        fix=True,
                        lat=gps_latitude,
                        lon=gps_longitude,
                        alt=gps_altitude,
                        speed=gps_speed_knots,
                        hdg=gps_heading_degrees,
                        seen=gps_satellites_seen,
                        active=gps_satellites,
                    ),
                )
                # Reset no-fix log time when fix is acquired
                last_no_fix_log_time_ms = 0  # Or current_ticks, depending on desired behavior. 0 ensures next no-fix logs immediately.
            else:  # not gps_fix
                current_ticks = time.ticks_ms()
                if (
                    time.ticks_diff(current_ticks, last_no_fix_log_time_ms)
                    >= NO_FIX_LOG_INTERVAL_MS
                ):
                    data_log.report_data(
                        SENSOR_NAME,
                        current_ticks,
                        dict(
                            fix=False, seen=gps_satellites_seen, active=gps_satellites
                        ),
                    )
                    last_no_fix_log_time_ms = current_ticks  # Update log time

        except asyncio.CancelledError:
            log.log("GPS Logger: Task cancelled.")
            raise
        except Exception as e:
            log.log(f"Error in GPS logger task loop: {e}")
            await asyncio.sleep_ms(1000)


def start_gps_reader():
    """Starts the GPS reader and logger tasks if not already running."""
    global _reader_task, _logger_task
    if uart is None:
        log.log("Cannot start GPS reader: UART not initialized.")
        return False

    reader_started = False
    if _reader_task is None or _reader_task.done():  # type: ignore
        _reader_enabled_event.set()  # Ensure reader starts enabled
        _reader_task = asyncio.create_task(_read_gps_task())
        log.log("GPS NMEA reader task created/restarted.")
        reader_started = True
    else:
        # If already running, ensure it's enabled
        if not _reader_enabled_event.is_set():
            _reader_enabled_event.set()
            log.log("GPS NMEA reader task was paused, re-enabling.")
        else:
            log.log("GPS NMEA reader task already running.")
        reader_started = True  # Consider it success if already running

    logger_started = False
    if _logger_task is None or _logger_task.done():  # type: ignore
        _logger_task = asyncio.create_task(_log_gps_status_task())
        log.log("GPS Status logger task created/restarted.")
        logger_started = True
    else:
        log.log("GPS Status logger task already running.")
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


def get_gps_heading() -> float:
    return gps_heading_degrees


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
    """Returns True if the RTC has been synced by GPS fix."""
    global _rtc_synced
    return _rtc_synced
