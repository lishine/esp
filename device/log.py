# --- Start of device/log.py ---
import utime
import uos

# --- Constants ---
LOG_FILE = "log"
MAX_LOG_LINES = 50  # Max lines per request
_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_MONTH_ABBR_MAP = {abbr: i + 1 for i, abbr in enumerate(_MONTH_ABBR)}


# --- Timestamp Parsing Helper ---
def _parse_log_timestamp_ms(line):
    """Parses 'DD-Mon-YYYY HH:MM:SS.ms' timestamp from log line start. Returns ms since epoch or None."""
    if len(line) < 24:
        return None
    try:
        timestamp_str = line[:24]
        ms_part = int(timestamp_str[21:])
        date_part = timestamp_str[:11]
        time_part = timestamp_str[12:20]

        day = int(date_part[:2])
        month_str = date_part[3:6]
        year = int(date_part[7:11])
        month = _MONTH_ABBR_MAP.get(month_str)
        if month is None:
            return None  # Invalid month

        hour = int(time_part[:2])
        minute = int(time_part[3:5])
        second = int(time_part[6:8])

        # utime.mktime handles tuple (year, month, day, hour, minute, second, weekday, yearday)
        # We provide 0 for weekday and yearday as they are not needed for epoch calculation
        time_tuple = (year, month, day, hour, minute, second, 0, 0)
        seconds_epoch = utime.mktime(time_tuple)
        # Make sure mktime didn't return an error (-1)
        if seconds_epoch == -1:
            return None
        return seconds_epoch * 1000 + ms_part
    except (
        ValueError,
        IndexError,
        TypeError,
    ):  # Catch potential errors during parsing/conversion
        return None  # Return None if parsing fails


# --- Logging Function ---
def log(*args, **kwargs):
    """Log function that writes messages to a file and prints to console with timestamp"""
    # Use ticks_ms for a more reliable millisecond source
    ticks_now_ms = utime.ticks_ms()
    # Calculate seconds since epoch (assuming epoch is 2000-01-01 for MicroPython)
    # 946684800 is seconds between Unix epoch (1970) and MP epoch (2000)
    # seconds_since_mp_epoch = utime.ticks_diff(ticks_now_ms // 1000, 0) # Ticks are relative, 0 might be boot time
    # A more robust way might involve getting RTC time if available and syncing ticks,
    # but for internal consistency utime.localtime() might be sufficient if RTC is set.
    # Let's stick to utime.localtime() for simplicity unless RTC is guaranteed.
    now = utime.localtime()  # Get current time tuple from RTC if set
    ms = ticks_now_ms % 1000  # Get ms part from ticks

    # Format timestamp using the time tuple from localtime()
    timestamp = "{:02d}-{}-{:04d} {:02d}:{:02d}:{:02d}.{:03d}".format(
        now[2], _MONTH_ABBR[now[1] - 1], now[0], now[3], now[4], now[5], ms
    )

    message = " ".join(str(arg) for arg in args)
    output = f"{timestamp} {message}\n"
    try:
        # Use 'a' mode to append. Create file if it doesn't exist.
        with open(LOG_FILE, "a") as f:
            f.write(output)
    except Exception as e:
        # Print error to console if log writing fails
        print(f"Error writing to log file '{LOG_FILE}': {e}")
    # Always print to console regardless of file write success
    print(output, end="", **kwargs)


# Unix epoch starts 1970-01-01, MicroPython epoch starts 2000-01-01
# Difference is 946684800 seconds = 946684800000 milliseconds
UNIX_TO_MP_EPOCH_OFFSET_MS = 946684800000


# --- Log Reading Function ---
def get_recent_logs(offset=0, newer_than_timestamp_ms=None, chunk_size=4096):
    """
    Read log lines from LOG_FILE (newest first) with filtering.

    Args:
        offset (int): Number of newest lines to skip. Used only if newer_than_timestamp_ms is None.
        newer_than_timestamp_ms (int): If provided, return only lines newer than this timestamp (ms since epoch).
                                       Offset is ignored if this is provided. Max MAX_LOG_LINES returned.
        chunk_size (int): Size of chunks to read from the file.

    Returns:
        list: A list of log line strings (newest first), max MAX_LOG_LINES items. Returns empty list on error.
    """
    collected_lines = []
    try:
        # Convert incoming Unix epoch timestamp to MicroPython epoch timestamp if provided
        newer_than_timestamp_mp_ms = None
        if newer_than_timestamp_ms is not None:
            newer_than_timestamp_mp_ms = (
                newer_than_timestamp_ms - UNIX_TO_MP_EPOCH_OFFSET_MS
            )

        with open(LOG_FILE, "r") as f:
            f.seek(0, 2)
            file_size = f.tell()
            buffer = ""
            processed_bytes = 0

            # Read file backwards in chunks
            while processed_bytes < file_size:
                read_size = min(chunk_size, file_size - processed_bytes)
                # Seek backwards relative to the end of the file
                f.seek(file_size - processed_bytes - read_size)
                chunk = f.read(read_size)
                processed_bytes += read_size

                # Prepend chunk to buffer
                buffer = chunk + buffer
                # Split buffer into lines based on newline
                found_lines_in_chunk = buffer.splitlines()

                # Process complete lines found in this chunk
                if len(found_lines_in_chunk) > 1:
                    # New complete lines are all but the first potentially partial line
                    # Reverse them to process newest first within the chunk
                    new_lines_this_chunk = found_lines_in_chunk[1:][::-1]

                    # Prepend these new lines to our overall collected list
                    collected_lines = new_lines_this_chunk + collected_lines

                    # Keep the first (potentially partial) line for the next iteration
                    buffer = found_lines_in_chunk[0]

                    # --- Optimizations ---
                    # If in offset mode, check if we have collected enough lines
                    if (
                        newer_than_timestamp_ms is None
                        and len(collected_lines) >= offset + MAX_LOG_LINES
                    ):
                        break  # Stop reading more chunks

                    # If in timestamp mode, check if the oldest line found *in this chunk*
                    # is already older than our target. If so, we can likely stop.
                    if (
                        newer_than_timestamp_mp_ms is not None and new_lines_this_chunk
                    ):  # Use mp_ms
                        oldest_ts_in_chunk = _parse_log_timestamp_ms(
                            new_lines_this_chunk[-1]
                        )
                        if (
                            oldest_ts_in_chunk is not None
                            and oldest_ts_in_chunk
                            <= newer_than_timestamp_mp_ms  # Use mp_ms
                        ):
                            # If we already found *some* lines newer than the target, we can stop.
                            # Check if any line collected so far is newer than the target.
                            if any(
                                _parse_log_timestamp_ms(l)
                                > newer_than_timestamp_mp_ms  # Use mp_ms
                                for l in collected_lines
                                if _parse_log_timestamp_ms(l) is not None
                            ):
                                break  # Stop reading more chunks

            # After the loop, process the remaining buffer (contains the first line of the file if reached)
            if buffer and processed_bytes == file_size:
                collected_lines.insert(0, buffer)  # Prepend the very first line

            # --- Post-processing and Filtering ---
            if newer_than_timestamp_mp_ms is not None:  # Use mp_ms
                # Filter collected lines by timestamp
                filtered_lines = []
                for line in collected_lines:  # Iterating newest first
                    ts = _parse_log_timestamp_ms(line)
                    # Check if timestamp is valid and newer than requested (using MP epoch)
                    if ts is not None and ts > newer_than_timestamp_mp_ms:  # Use mp_ms
                        filtered_lines.append(line)
                        # Stop once we have MAX_LOG_LINES
                        if len(filtered_lines) >= MAX_LOG_LINES:
                            break
                return filtered_lines  # Return filtered list (newest first)
            else:
                # Apply offset and limit
                start_index = offset
                end_index = offset + MAX_LOG_LINES
                # Ensure indices are within the bounds of the collected lines
                start_index = min(start_index, len(collected_lines))
                end_index = min(end_index, len(collected_lines))
                # Return the requested slice (newest first)
                return collected_lines[start_index:end_index]

    except OSError:
        # File probably doesn't exist yet
        return []
    except Exception as e:
        # Log error to console if something else goes wrong
        print(f"Error reading log file '{LOG_FILE}': {e}")
        return []


# --- End of device/log.py ---
