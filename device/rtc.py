import time
import machine
from log import log, _get_log_filepath, get_latest_log_index, _MONTH_ABBR

import uos


def set_rtc_from_gmtime_tuple(gmtime_tuple: tuple) -> bool:
    """Set the RTC from a standard time.gmtime() tuple (year, month, mday, hour, minute, second, weekday, yearday).
    Returns True if successful, False otherwise."""
    try:
        rtc = machine.RTC()
        # Convert gmtime tuple to RTC tuple format (year, month, day, weekday, hour, minute, second, subseconds)
        rtc_tuple = (
            gmtime_tuple[0],  # year
            gmtime_tuple[1],  # month
            gmtime_tuple[2],  # day
            gmtime_tuple[6],  # weekday (0-6 for Mon-Sun)
            gmtime_tuple[3],  # hour
            gmtime_tuple[4],  # minute
            gmtime_tuple[5],  # second
            0,  # subseconds
        )
        rtc.datetime(rtc_tuple)
        return True
    except Exception as e:
        log(f"RTC: Error setting from gmtime tuple: {e}")
        return False


def update_rtc_if_needed(gmtime_tuple_from_gps: tuple) -> bool:
    """Checks if RTC needs update from GPS time and performs it."""
    if not isinstance(gmtime_tuple_from_gps, tuple) or len(gmtime_tuple_from_gps) < 8:
        log("RTC: Invalid gmtime_tuple_from_gps format or length.")
        return False

    if gmtime_tuple_from_gps[0] < 2023:  # Year validation
        log("RTC: GPS year invalid.")
        return False

    try:
        # Convert GPS time to epoch seconds
        # mktime expects (year, month, day, hour, minute, second, weekday, yearday)
        gps_epoch_seconds = time.mktime(gmtime_tuple_from_gps)  # type: ignore
    except OverflowError:
        # Ensure gmtime_tuple_from_gps has enough elements for slicing before logging
        year, month, day = (
            gmtime_tuple_from_gps[0],
            gmtime_tuple_from_gps[1],
            gmtime_tuple_from_gps[2],
        )
        log(f"RTC: GPS date {year:04d}-{month:02d}-{day:02d} out of range for mktime.")
        return False
    except Exception as e:
        log(f"RTC: Error converting GPS time to epoch: {e}")
        return False

    # Get current RTC time
    current_rtc_epoch_seconds = time.time()

    if gps_epoch_seconds > current_rtc_epoch_seconds:
        if set_rtc_from_gmtime_tuple(gmtime_tuple_from_gps):
            # Ensure gmtime_tuple_from_gps has enough elements for string formatting
            year, month, day, hour, minute, second = (
                gmtime_tuple_from_gps[0],
                gmtime_tuple_from_gps[1],
                gmtime_tuple_from_gps[2],
                gmtime_tuple_from_gps[3],
                gmtime_tuple_from_gps[4],
                gmtime_tuple_from_gps[5],
            )
            log(
                f"RTC: Updated by GPS time: {year}-{month:02d}-{day:02d} "
                f"{hour:02d}:{minute:02d}:{second:02d} UTC"
            )
            return True
        else:
            log(
                "RTC: Update attempt with GPS time failed (set_rtc_from_gmtime_tuple returned False)."
            )
            return False
    else:
        log(
            f"RTC: GPS time {gps_epoch_seconds} not newer than current RTC {current_rtc_epoch_seconds}. No update."
        )
        return False


# def _read_last_line(filepath):
#     """Reads the last line of a file in binary mode."""
#     try:
#         with open(filepath, "rb") as f:
#             f.seek(0, 2)  # Go to end of file
#             file_size = f.tell()
#             if file_size == 0:
#                 return None  # Empty file

#             buffer = bytearray()
#             chunk_size = 128  # Read in chunks
#             offset = 0

#             while True:
#                 offset += chunk_size
#                 seek_pos = max(0, file_size - offset)
#                 f.seek(seek_pos)
#                 # Calculate bytes to read for this chunk
#                 bytes_to_read = min(
#                     chunk_size,
#                     file_size - seek_pos if offset <= file_size else chunk_size,
#                 )
#                 if (
#                     bytes_to_read <= 0 and seek_pos == 0
#                 ):  # Avoid reading 0 bytes unless at start
#                     break

#                 read_bytes = f.read(bytes_to_read)

#                 if not read_bytes:  # Safety check
#                     break

#                 # Prepend read bytes to buffer
#                 buffer = read_bytes + buffer

#                 # Check if newline is found
#                 newline_index = buffer.rfind(b"\n")
#                 if newline_index != -1:
#                     # Found the last newline (or start of file)
#                     # If newline is not the last char, return the part after it
#                     if newline_index < len(buffer) - 1:
#                         return buffer[newline_index + 1 :]
#                     # If newline is the last char, we need the line before it.
#                     # Search for the second to last newline.
#                     second_newline_index = buffer.rfind(b"\n", 0, newline_index)
#                     if second_newline_index != -1:
#                         return buffer[second_newline_index + 1 : newline_index]
#                     else:  # Only one line in the buffer (or file)
#                         return buffer[:newline_index]

#                 if seek_pos == 0:  # Reached start of file
#                     return buffer  # Return the whole buffer (single line file)
#     except OSError as e:
#         # Use log function which is already imported
#         log(f"RTC: Error reading file {filepath} in _read_last_line: {e}")
#         return None
#     except Exception as e:
#         log(f"RTC: Unexpected error in _read_last_line for {filepath}: {e}")
#         return None


# --- Main Function ---


# def set_time_from_last_log():
#     """
#     Sets the RTC time based on the timestamp of the last entry
#     in the most recent log file, adding 1 second.
#     """
#     try:
#         # 1. Find the latest log file index
#         # Use log module directly as it's imported
#         latest_index = get_latest_log_index()

#         # get_latest_log_index returns 0 if no logs exist or dir error.
#         # We need to check if the corresponding file actually exists.
#         filepath = _get_log_filepath(latest_index)
#         try:
#             # Check existence by trying to get status
#             uos.stat(filepath)
#         except OSError as e:
#             if e.args[0] == 2:  # ENOENT (File not found)
#                 log(
#                     f"RTC: No log file found at index {latest_index} ({filepath}) to set time from."
#                 )
#                 return
#             else:  # Other stat error
#                 log(f"RTC: Error checking log file {filepath}: {e}")
#                 return

#         # 2. Read the last line of the latest log file
#         last_line_bytes = _read_last_line(filepath)
#         if not last_line_bytes:
#             log(f"RTC: Could not read last line or file empty: {filepath}")
#             return

#         try:
#             last_line_str = last_line_bytes.decode("utf-8").strip()
#         except UnicodeError:
#             log(f"RTC: Error decoding last line from {filepath}")
#             return

#         if not last_line_str:
#             log(f"RTC: Last line is empty in {filepath}")
#             return

#         # 3. Parse the timestamp from the last line
#         # Format: "reset_count DD-Mon-YYYY HH:MM:SS.fff message"
#         try:
#             # Find the first space to skip the reset counter
#             first_space_index = last_line_str.find(" ")
#             if first_space_index == -1:
#                 raise ValueError(
#                     "Log line format error: No space found after reset count"
#                 )

#             # Timestamp part starts after the first space and should be 24 chars long
#             # DD-Mon-YYYY HH:MM:SS.fff
#             timestamp_str = last_line_str[
#                 first_space_index + 1 : first_space_index + 1 + 24
#             ]

#             # Validate expected format briefly before splitting
#             if not (
#                 timestamp_str[2] == "-"
#                 and timestamp_str[6] == "-"
#                 and timestamp_str[11] == " "
#                 and timestamp_str[14] == ":"
#                 and timestamp_str[17] == ":"
#                 and timestamp_str[20] == "."
#             ):
#                 raise ValueError(f"Timestamp format error in '{timestamp_str}'")

#             # Manual parsing
#             day_str = timestamp_str[0:2]
#             mon_abbr = timestamp_str[3:6]
#             year_str = timestamp_str[7:11]
#             hour_str = timestamp_str[12:14]
#             min_str = timestamp_str[15:17]
#             sec_str = timestamp_str[18:20]
#             # ms_part = timestamp_str[21:24] # Ignored for RTC setting

#             day = int(day_str)
#             year = int(year_str)
#             hour = int(hour_str)
#             minute = int(min_str)
#             second = int(sec_str)

#             # Map month abbreviation to number using log._MONTH_ABBR
#             # Ensure log._MONTH_ABBR is accessible (it should be if log is imported)
#             MONTH_MAP = {abbr: i + 1 for i, abbr in enumerate(_MONTH_ABBR)}
#             if mon_abbr not in MONTH_MAP:
#                 raise ValueError(f"Invalid month abbreviation: {mon_abbr}")
#             month = MONTH_MAP[mon_abbr]

#         except (ValueError, IndexError, KeyError) as e:
#             log(f"RTC: Error parsing timestamp from line '{last_line_str}': {e}")
#             return

#         # 4. Calculate the new time (+1 second)
#         try:
#             # Create tuple for mktime (year, month, day, hour, minute, second, weekday, yearday)
#             # Weekday and yearday are ignored by mktime, set to 0
#             time_tuple = (year, month, day, hour, minute, second, 0, 0)

#             # Convert to epoch seconds
#             epoch_seconds = time.mktime(time_tuple)  # type: ignore

#             # Add 1 second
#             new_epoch_seconds = epoch_seconds + 1

#             # Convert back to a time tuple suitable for RTC
#             # localtime returns (year, month, mday, hour, minute, second, weekday, yearday)
#             # weekday is 0=Mon, 6=Sun
#             new_time_local = time.gmtime(new_epoch_seconds)

#             # RTC datetime format: (year, month, day, weekday, hours, minutes, seconds, subseconds)
#             # MicroPython RTC often uses weekday 0-6 for Mon-Sun, matching localtime.
#             rtc_tuple = (
#                 new_time_local[0],  # year
#                 new_time_local[1],  # month
#                 new_time_local[2],  # day
#                 new_time_local[6],  # weekday
#                 new_time_local[3],  # hour
#                 new_time_local[4],  # minute
#                 new_time_local[5],  # second
#                 0,  # subseconds
#             )
#         except Exception as e:
#             log(f"RTC: Error calculating new time: {e}")
#             return

#         # 5. Set the RTC
#         try:
#             rtc = machine.RTC()
#             rtc.datetime(rtc_tuple)
#             # Log success confirmation using the tuple components
#             # Ensure log._MONTH_ABBR is accessible
#             log(
#                 f"RTC: Set time from log {filepath} to {rtc_tuple[0]}-{_MONTH_ABBR[rtc_tuple[1]-1]}-{rtc_tuple[2]:02d} {rtc_tuple[4]:02d}:{rtc_tuple[5]:02d}:{rtc_tuple[6]:02d}"
#             )

#         except Exception as e:
#             log(f"RTC: Error setting RTC time: {e}")

#     except Exception as e:
#         # Catch-all for unexpected errors in the main function logic
#         log(f"RTC: Unexpected error in set_time_from_last_log: {e}")
