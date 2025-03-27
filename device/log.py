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


def get_recent_logs(limit=50, offset=0, newer_than_timestamp_ms=None, chunk_size=512):
    """
    Generator function that yields log lines from the file, newest first.

    Key improvements:
    1. True streaming - yields lines as they're processed with minimal buffering.
    2. Handles newest-first ordering using a limited buffer for offset/limit.
    3. Processes file in small chunks to avoid memory issues.

    Args:
        limit (int): Maximum number of lines to return (0 means no limit, capped internally).
        offset (int): Number of lines to skip from the end.
        newer_than_timestamp_ms (int, optional): Only yield lines newer than this timestamp.
        chunk_size (int): Size of chunks to process at a time (smaller is better for memory).

    Yields:
        str: Log lines with newline character, newest first.
    """
    # Cap limit to prevent excessive memory use with the buffer
    effective_limit = min(limit, 200) if limit > 0 else 200  # Max buffer size

    try:
        # Check if file exists and is not empty
        try:
            stat = uos.stat(LOG_FILE)
            if stat[6] == 0:  # Size is 0
                return
        except OSError:
            return  # File doesn't exist

        # --- Timestamp Filtering (Read Forward) ---
        if newer_than_timestamp_ms is not None:
            # Read forward, collect matching lines, then yield newest first
            matching_lines = []
            with open(LOG_FILE, "r") as f:
                buffer = ""
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    buffer += chunk
                    lines = buffer.split("\n")
                    # Process all complete lines except the last (potentially incomplete)
                    for i in range(len(lines) - 1):
                        line = lines[i]
                        if not line:
                            continue
                        line_ts = _parse_log_timestamp_ms(line)
                        if line_ts is not None and line_ts > newer_than_timestamp_ms:
                            matching_lines.append(line + "\n")
                            # Optional: Limit memory usage if too many lines match
                            # if len(matching_lines) > some_large_number:
                            #     matching_lines.pop(0) # Keep only the latest
                    buffer = lines[-1]  # Keep last part for next chunk

                # Process the very last part if it forms a complete line
                if buffer:
                    line_ts = _parse_log_timestamp_ms(buffer)
                    if line_ts is not None and line_ts > newer_than_timestamp_ms:
                        matching_lines.append(buffer + "\n")

            # Yield collected lines newest first
            yielded_count = 0
            for i in range(len(matching_lines) - 1, -1, -1):
                yield matching_lines[i]
                yielded_count += 1
                if effective_limit > 0 and yielded_count >= effective_limit:
                    break
            return  # End timestamp filtering

        # --- Offset/Limit Filtering (Read Forward with Buffer) ---
        else:
            # Use a circular buffer to keep track of the last N lines
            # N = offset + effective_limit
            buffer_size = offset + effective_limit
            line_buffer = [None] * buffer_size
            line_count = 0

            with open(LOG_FILE, "r") as f:
                for line in f:
                    line_buffer[line_count % buffer_size] = line
                    line_count += 1

            # Determine which lines to yield from the buffer
            # Start index in the conceptual full list of lines
            start_index = max(0, line_count - offset - effective_limit)
            # Number of lines to yield
            num_to_yield = min(effective_limit, line_count - offset - start_index)

            # Yield lines from the buffer in correct (newest first) order
            for i in range(num_to_yield):
                # Index in the conceptual full list (newest is line_count - 1)
                conceptual_index = line_count - 1 - offset - i
                if conceptual_index < 0:
                    break  # Should not happen with checks above, but safety first

                # Index in the actual circular buffer
                buffer_index = conceptual_index % buffer_size
                line_to_yield = line_buffer[buffer_index]
                if line_to_yield is not None:  # Check if buffer slot was filled
                    yield line_to_yield

    except Exception as e:
        try:
            # Use print for basic error logging on device if log() fails
            print(f"Error in get_recent_logs: {type(e).__name__} {e}")
        except:
            pass  # Avoid errors during error handling itself
