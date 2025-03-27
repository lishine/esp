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

LOG_FILE = "log"


def log(*args, **kwargs):
    """Log function that writes messages to a file and prints to console with timestamp"""
    # Get current time
    now = utime.localtime()
    ms = utime.ticks_ms() % 1000

    # Format timestamp: DD-Mon-YYYY HH:MM:SS.ms
    timestamp = "{:02d}-{}-{:04d} {:02d}:{:02d}:{:02d}.{:03d}".format(
        now[2], _MONTH_ABBR[now[1] - 1], now[0], now[3], now[4], now[5], ms
    )

    # Original message
    message = " ".join(str(arg) for arg in args)

    # Prepend timestamp to message for file and print
    output = f"{timestamp} {message}\n"
    with open(LOG_FILE, "a") as f:
        f.write(output)
    print(output, end="", **kwargs)  # Print the combined output


def get_recent_logs(count=100, chunk_size=4096):
    """Read last 'count' lines from log file (newest first) using efficient chunked reading"""
    try:
        with open(LOG_FILE, "r") as f:
            # Go to end of file
            f.seek(0, 2)
            file_size = f.tell()

            lines = []
            remaining_lines = count
            buffer = ""

            # Read chunks backwards from end of file
            while remaining_lines > 0 and file_size > 0:
                # Calculate next chunk position
                read_size = min(chunk_size, file_size)
                f.seek(-read_size, 2)
                chunk = f.read(read_size)
                file_size -= read_size

                # Add chunk to buffer and split lines
                buffer = chunk + buffer
                found_lines = buffer.splitlines()

                # If we found complete lines, add them (except maybe first partial line)
                if len(found_lines) > 1:
                    lines.extend(found_lines[1:][::-1])
                    remaining_lines -= len(found_lines) - 1
                    buffer = found_lines[0]

            # Add any remaining lines in buffer
            if buffer:
                lines.append(buffer)
                remaining_lines -= 1

            # Return requested number of lines (newest first)
            return lines[-count:][::-1] if len(lines) > count else lines[::-1]
    except OSError:
        return []
