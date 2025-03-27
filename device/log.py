import utime
import uos

# Month abbreviations
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

# Map month abbreviations to numbers (1-12)
_MONTH_MAP = {abbr: i + 1 for i, abbr in enumerate(_MONTH_ABBR)}

LOG_FILE = "log"


def _parse_log_timestamp_ms(line):
    """Parse the timestamp from a log line into milliseconds since epoch."""
    try:
        # Timestamp format: DD-Mon-YYYY HH:MM:SS.ms
        ts_str = line[:24]  # Extract the timestamp part
        if (
            len(ts_str) != 24
            or ts_str[2] != "-"
            or ts_str[6] != "-"
            or ts_str[11] != " "
            or ts_str[14] != ":"
            or ts_str[17] != ":"
            or ts_str[20] != "."
        ):
            return None  # Basic format check

        day = int(ts_str[0:2])
        month_abbr = ts_str[3:6]
        year = int(ts_str[7:11])
        hour = int(ts_str[12:14])
        minute = int(ts_str[15:17])
        second = int(ts_str[18:20])
        ms = int(ts_str[21:24])

        month = _MONTH_MAP.get(month_abbr)
        if month is None:
            return None  # Invalid month abbreviation

        # utime.mktime expects (year, month, day, hour, minute, second, weekday, yearday)
        # weekday and yearday are ignored by mktime on ESP32, use 0
        time_tuple = (year, month, day, hour, minute, second, 0, 0)
        epoch_seconds = utime.mktime(time_tuple)
        return epoch_seconds * 1000 + ms
    except (ValueError, IndexError, TypeError):
        # Handle cases where the line doesn't start with a valid timestamp or parsing fails
        return None


def log(*args, **kwargs):
    """Log function that writes messages to a file and prints to console with timestamp"""
    # Get current time
    now = utime.localtime()
    # Calculate milliseconds ensuring it's always positive and within 0-999
    # utime.ticks_ms() can wrap around, utime.ticks_diff handles this
    ms_raw = utime.ticks_ms()
    ms = ms_raw % 1000

    # Format timestamp: DD-Mon-YYYY HH:MM:SS.ms
    timestamp = "{:02d}-{}-{:04d} {:02d}:{:02d}:{:02d}.{:03d}".format(
        now[2], _MONTH_ABBR[now[1] - 1], now[0], now[3], now[4], now[5], ms
    )

    # Original message
    message = " ".join(str(arg) for arg in args)

    # Prepend timestamp to message for file and print
    output = f"{timestamp} {message}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(output)
    except Exception as e:
        print(f"Error writing to log file: {e}")  # Print error if log writing fails
    print(output, end="", **kwargs)  # Print the combined output


def get_recent_logs(limit=100, offset=0, newer_than_timestamp_ms=None, chunk_size=4096):
    """
    Read log lines from the end of the file with options for limit, offset, and timestamp filtering.

    Args:
        limit (int): Maximum number of lines to return. Defaults to 100.
        offset (int): Number of lines to skip from the end before collecting. Defaults to 0.
                      Ignored if newer_than_timestamp_ms is provided.
        newer_than_timestamp_ms (int, optional): If provided, only return lines newer than this timestamp (ms since epoch).
        chunk_size (int): Size of chunks to read from the file. Defaults to 4096.

    Yields:
        str: Log lines (including newline), newest first within the filtered range.
             Yields nothing on error or if file not found.
    """
    collected_lines = []  # Store lines temporarily, oldest encountered first
    try:
        with open(LOG_FILE, "r") as f:
            f.seek(0, 2)
            file_size = f.tell()
            buffer = ""
            stop_reading = False

            while file_size > 0 and not stop_reading:
                read_size = min(chunk_size, file_size)
                # Seek relative to current position (which is end of last read chunk)
                f.seek(file_size - read_size)
                chunk = f.read(read_size)
                file_size -= read_size

                buffer = chunk + buffer
                found_lines = buffer.splitlines()

                if not found_lines and file_size > 0:
                    continue

                process_from_index = 1 if len(found_lines) > 1 else 0

                # Process lines from newest in chunk to oldest in chunk
                for i in range(len(found_lines) - 1, process_from_index - 1, -1):
                    line = found_lines[i]
                    if not line:
                        continue

                    if newer_than_timestamp_ms is not None:
                        line_ts = _parse_log_timestamp_ms(line)
                        if line_ts is None:
                            continue

                        if line_ts > newer_than_timestamp_ms:
                            collected_lines.append(
                                line
                            )  # Collect lines newer than threshold
                        else:
                            # Found the first line older than or equal to the threshold. Stop reading.
                            stop_reading = True
                            break  # Stop processing this chunk
                    else:
                        # Offset/Limit logic: Collect potential candidates
                        collected_lines.append(line)
                        # Stop reading if we have collected enough lines to satisfy offset + limit
                        if len(collected_lines) >= offset + limit:
                            stop_reading = True
                            break  # Stop processing this chunk

                if stop_reading:  # Break outer loop if needed
                    break

                # Keep the potentially partial first line for the next iteration's buffer
                buffer = found_lines[0] if len(found_lines) > 0 else ""

            # Process the very first line of the file if it remained in the buffer
            if buffer and not stop_reading:
                line = buffer
                if line:
                    if newer_than_timestamp_ms is not None:
                        line_ts = _parse_log_timestamp_ms(line)
                        if line_ts is not None and line_ts > newer_than_timestamp_ms:
                            collected_lines.append(line)
                    else:
                        if len(collected_lines) < offset + limit:
                            collected_lines.append(line)

            # collected_lines contains potential candidates, oldest encountered first.

            if newer_than_timestamp_ms is not None:
                # Yield in reverse order (newest first)
                for i in range(len(collected_lines) - 1, -1, -1):
                    yield collected_lines[i] + "\n"
            else:
                # Apply offset and limit to the collected lines
                total_collected = len(collected_lines)
                # Indices are relative to the start of collected_lines (oldest encountered)
                end_index = total_collected - offset
                start_index = max(0, end_index - limit)

                # Yield the slice in reverse order (newest first)
                for i in range(end_index - 1, start_index - 1, -1):
                    yield collected_lines[i] + "\n"

    except OSError:
        # File probably doesn't exist yet, yield nothing
        pass
    except Exception as e:
        try:
            print(f"Error in get_recent_logs generator: {type(e).__name__} {e}")
        except:
            pass  # Avoid errors during error handling
        # Yield nothing on error
        pass
