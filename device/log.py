import utime
import uos
import gc
import uasyncio as asyncio
from uasyncio import TimeoutError

# --- Configuration ---
LOG_DIR = "logs"
LOG_FILE_PREFIX = "log_"
LOG_FILE_SUFFIX = ".txt"
MAX_LOG_FILE_SIZE = 10000  # Bytes
MAX_LOG_FILES = 100  # Limit the number of log files

# --- Module State ---
_current_log_index = -1  # Uninitialized by default, set by writer task
_log_dir_checked = False  # Flag to check dir only once
_log_queue = []  # In-memory queue for log messages (bytes)
_MAX_QUEUE_SIZE = 200  # Max messages before dropping
_WRITE_THRESHOLD = 10  # Number of messages to trigger a write
_write_event = asyncio.Event()  # Event to signal the writer task

# --- Statistics (Rolling Window) ---
_ROLLING_WINDOW_SIZE = 5
_last_write_times_us = []  # Stores the last N write durations in microseconds

# --- Constants ---
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

# --- Helper Functions ---


def _ensure_log_dir():
    global _log_dir_checked
    if _log_dir_checked:
        return
    try:
        uos.stat(LOG_DIR)
        # print(f"Log directory '{LOG_DIR}' already exists.") # Debug
    except OSError as e:
        if e.args[0] == 2:
            try:
                uos.mkdir(LOG_DIR)
                print(f"Created log directory: {LOG_DIR}")
            except OSError as mkdir_e:
                print(f"Error creating log directory '{LOG_DIR}': {mkdir_e}")
                # If we can't create the dir, logging to file will fail
        else:
            # Other stat error
            print(f"Error checking log directory '{LOG_DIR}': {e}")
    _log_dir_checked = True


def get_latest_log_index():
    _ensure_log_dir()
    latest_index = -1
    try:
        files = uos.ilistdir(LOG_DIR)
        for entry in files:
            filename = entry[0]
            file_type = entry[1]
            # Check if it's a file and matches the pattern
            if (
                file_type == 0x8000
                and filename.startswith(LOG_FILE_PREFIX)
                and filename.endswith(LOG_FILE_SUFFIX)
            ):
                try:
                    # Extract index part: log_ (4 chars) until .txt (-4 chars)
                    index_str = filename[len(LOG_FILE_PREFIX) : -len(LOG_FILE_SUFFIX)]
                    index = int(index_str)
                    if index > latest_index:
                        latest_index = index
                except ValueError:
                    # Ignore files with non-integer index part
                    print(f"Warning: Found log file with non-integer index: {filename}")
                    pass
    except OSError as e:
        print(f"Error listing log directory '{LOG_DIR}': {e}")
        # If we can't list, assume no files exist
        return -1

    # If no files were found, return 0 to start with log_000.txt
    # Otherwise, return the highest index found.
    return latest_index if latest_index != -1 else 0


def _get_log_filepath(index):
    """Constructs the full path for a given log file index."""
    # Format index with 3 digits, zero-padded
    return f"{LOG_DIR}/{LOG_FILE_PREFIX}{index:03d}{LOG_FILE_SUFFIX}"


# --- Logging Function ---


def log(*args, **kwargs):

    # 1. Format the message with timestamp
    ticks_now_ms = utime.ticks_ms()
    now = utime.localtime()
    ms = ticks_now_ms % 1000
    timestamp = "{:02d}-{}-{:04d} {:02d}:{:02d}:{:02d}.{:03d}".format(
        now[2], _MONTH_ABBR[now[1] - 1], now[0], now[3], now[4], now[5], ms
    )
    message = " ".join(str(arg) for arg in args)
    output = f"{timestamp} {message}\n"

    # 2. Always print to console
    print(output, end="", **kwargs)
    # 3. Queue the message for the writer task
    output_bytes = output.encode("utf-8")

    if len(_log_queue) >= _MAX_QUEUE_SIZE:
        print(f"--- LOG QUEUE FULL (MAX {_MAX_QUEUE_SIZE}) - DROPPING MESSAGE ---")
        print(output, end="")  # Print the dropped message content as well
        print(f"--- END DROPPED MESSAGE ---")
        return  # Do not queue or signal

    _log_queue.append(output_bytes)

    # 4. Signal the writer task if the threshold is met
    if len(_log_queue) >= _WRITE_THRESHOLD:
        _write_event.set()


# --- Async Log Writer Task ---


async def _log_writer_task():
    global _current_log_index
    global _last_write_times_us  # Use the list for rolling window

    # Initialize log directory and find starting index
    _ensure_log_dir()
    _current_log_index = get_latest_log_index()
    print(f"Log writer task started. Initial log index: {_current_log_index}")

    while True:
        try:
            # Wait for the event or timeout after 3 seconds
            try:
                await asyncio.wait_for_ms(_write_event.wait(), 3000)  # type: ignore
                _write_event.clear()
                # print("Log writer triggered by event.") # Debug
            except TimeoutError:
                pass  # Nothing specific to do on timeout itself

            # Process the queue if it has messages (either from event or timeout)
            if _log_queue:
                messages_to_write = _log_queue[:]  # Make a copy
                _log_queue.clear()  # Clear the original queue

                # print(f"Writing {len(messages_to_write)} log messages.") # Debug

                current_filepath = _get_log_filepath(_current_log_index)
                current_size = 0
                try:
                    # Get initial size of the current log file
                    stat = uos.stat(current_filepath)
                    current_size = stat[6]
                except OSError as e:
                    if e.args[0] != 2:  # Ignore ENOENT (file not found)
                        print(
                            f"Error stating log file '{current_filepath}' in writer: {e}"
                        )
                    # If file doesn't exist, current_size remains 0

                # Process each message in the batch
                for message_bytes in messages_to_write:
                    # Check rotation *before* writing this message
                    if (
                        current_size > 0
                        and (current_size + len(message_bytes)) > MAX_LOG_FILE_SIZE
                    ):
                        _current_log_index += 1

                        # --- START: Log File Limit Logic ---
                        # Check if we need to delete old log files to maintain the limit
                        if _current_log_index >= MAX_LOG_FILES:
                            # Calculate the oldest log file index that should be removed
                            # For example, if MAX_LOG_FILES=2 and _current_log_index=2,
                            # we should remove log_000.txt (index = 2 - 2 = 0)
                            oldest_index = (
                                _current_log_index - MAX_LOG_FILES
                            )  # CORRECTED LINE
                            oldest_filepath = _get_log_filepath(oldest_index)
                            try:
                                uos.remove(oldest_filepath)
                                print(f"Removed oldest log file: {oldest_filepath}")
                            except OSError as e:
                                # Use print directly to avoid recursion if logging fails
                                print(
                                    f"Error removing oldest log file '{oldest_filepath}': {e}"
                                )
                        # --- END: Log File Limit Logic ---

                        current_filepath = _get_log_filepath(_current_log_index)
                        current_size = 0  # Reset size for the new file
                        print(f"Rotating log to new file: {current_filepath}")
                        gc.collect()

                    # Write the message
                    try:
                        start_us = utime.ticks_us()
                        with open(current_filepath, "ab") as f:
                            bytes_written = f.write(message_bytes)
                        end_us = utime.ticks_us()
                        write_duration_us = utime.ticks_diff(end_us, start_us)

                        # Update rolling window stats
                        _last_write_times_us.append(write_duration_us)
                        # Keep only the last N entries
                        if len(_last_write_times_us) > _ROLLING_WINDOW_SIZE:
                            _last_write_times_us.pop(0)  # Remove the oldest entry

                        if bytes_written is not None:
                            # If write returns None, try to get size again
                            try:
                                stat = uos.stat(current_filepath)
                                current_size = stat[6]
                            except OSError:
                                # If stat fails after write, estimate based on what we tried to write
                                current_size += len(message_bytes)
                        else:
                            # If write returns None, assume bytes_written is the length of message_bytes
                            # This might happen on some MicroPython ports/versions
                            current_size += len(message_bytes)

                    except Exception as e:
                        print(
                            f"Error writing to log file '{current_filepath}' in writer: {e}"
                        )
                        # Avoid potential tight loops on persistent write errors for this file
                        await asyncio.sleep_ms(100)
            # else: # Debug
            # print("Log writer woke up, but queue is empty.")

        except Exception as e:
            print(f"Error in log writer task main loop: {e}")
            # Avoid tight loop on unexpected errors in the task logic itself
            await asyncio.sleep_ms(500)

        # Yield control briefly even if no event occurred or no messages processed
        # This prevents the task from potentially starving others if events fire rapidly
        await asyncio.sleep_ms(10)


def read_log_file_content(file_index):
    """
    Reads the entire content of a specific log file.

    Args:
        file_index (int): The index of the log file to read (e.g., 0 for log_000.txt).

    Returns:
        bytes: The raw byte content of the file, or None if the file is not found
               or a read error occurs.
    """
    if not isinstance(file_index, int) or file_index < 0:
        print(f"Error: Invalid file index requested: {file_index}")
        return None

    filepath = _get_log_filepath(file_index)
    # print(f"Attempting to read log file: {filepath}") # Debug
    try:
        with open(filepath, "rb") as f:
            content = f.read()
            # print(f"Read {len(content)} bytes from {filepath}") # Debug
            return content
    except OSError as e:
        if e.args[0] == 2:  # ENOENT
            # print(f"Log file not found: {filepath}") # Debug
            pass
        else:
            # Log other errors
            print(f"Error reading log file '{filepath}': {e}")
        return None
    except Exception as e:
        print(f"Unexpected error reading log file '{filepath}': {e}")
        return None


def clear_logs():
    """Removes all log files from the log directory."""
    global _current_log_index, _last_write_times_us
    _ensure_log_dir()
    cleared_count = 0
    error_count = 0
    print(f"Attempting to clear logs in '{LOG_DIR}'...")
    try:
        entries = list(uos.ilistdir(LOG_DIR))  # Convert iterator to list
        # print(f"Found {len(entries)} entries in {LOG_DIR}") # Debug
        for entry in entries:
            filename = entry[0]
            file_type = entry[1]
            full_path = f"{LOG_DIR}/{filename}"

            # Check if it's a file and looks like one of our log files
            if (
                file_type == 0x8000
                and filename.startswith(LOG_FILE_PREFIX)
                and filename.endswith(LOG_FILE_SUFFIX)
            ):
                try:
                    uos.remove(full_path)
                    # print(f"Removed log file: {full_path}") # Debug
                    cleared_count += 1
                except OSError as e:
                    print(f"Error removing log file '{full_path}': {e}")
                    error_count += 1
            # else: # Debug
            #     print(f"Skipping non-log file or directory: {full_path}")

        # Reset the current index to start fresh from 0 next time
        _current_log_index = 0
        # Clear the stats window as well
        _last_write_times_us.clear()
        print(f"Log clearing finished. Removed: {cleared_count}, Errors: {error_count}")
        return True

    except OSError as e:
        print(f"Error listing or accessing log directory '{LOG_DIR}' during clear: {e}")
        return False


def get_log_write_stats():
    """
    Calculates and returns the log write time statistics based on a rolling window.

    Returns:
        dict: A dictionary containing 'log_write_time_max' (microseconds)
              and 'log_write_time_avg' (microseconds) for the last N writes.
              Returns 0 for both if no writes have occurred in the window.
    """
    if not _last_write_times_us:
        avg_time_us = 0
        max_time_us = 0
    else:
        total_time_us = sum(_last_write_times_us)
        count = len(_last_write_times_us)
        avg_time_us = float(total_time_us) / count
        max_time_us = max(_last_write_times_us)

    return {"log_write_time_max": max_time_us, "log_write_time_avg": avg_time_us}
