import utime
import uos
import _thread

from sd import SD_MOUNT_POINT

LOG_DIR = f"/{SD_MOUNT_POINT}/lb/logs"
LOG_FILE_PREFIX = "log_"
LOG_FILE_SUFFIX = ".txt"
MAX_LOG_FILE_SIZE = 4000  # Bytes

_current_log_index = -1  # Uninitialized by default, set by writer task
_log_dir_checked = False  # Flag to check dir only once

_queue_lock = _thread.allocate_lock()
_active_queue = []

_WRITE_THRESHOLD = 60  # Number of messages to trigger a write
_WRITE_TIMEOUT_MS = 60000
_POLL_INTERVAL_MS = 5000  # 1 second polling interval

_current_reset_count = None


def _get_next_reset_counter():
    """
    Determines the next reset counter value by reading the last line
    of the most recent log file.
    Returns 1 if no logs are found, or if errors occur during reading/parsing.
    """
    global _current_reset_count
    if _current_reset_count:
        return _current_reset_count
    latest_index = get_latest_log_index()
    if latest_index < 0:
        # get_latest_log_index handles printing errors if listing fails.
        # It returns 0 if the directory exists but is empty.
        # If it returns < 0, it means there was an error listing the directory.
        # In either case (error or empty dir), we start with 1.
        print(
            "Log: No previous log files found or error listing logs. Starting reset count at 1."
        )
        _current_reset_count = 1
        return 1

    latest_filepath = _get_log_filepath(latest_index)
    last_line_bytes = None
    file_size = 0

    try:
        # Check file size first to handle empty files efficiently
        try:
            stat_info = uos.stat(latest_filepath)
            file_size = stat_info[6]
        except OSError as e:
            if (
                e.args[0] == 2
            ):  # ENOENT - File not found (shouldn't happen if index >= 0, but check)
                print(
                    f"Log: Latest log file '{latest_filepath}' not found unexpectedly. Starting reset count at 1."
                )
                _current_reset_count = 1
                return 1
            else:
                print(
                    f"Log: Error stating latest log file '{latest_filepath}': {e}. Starting reset count at 1."
                )
                _current_reset_count = 1
                return 1

        if file_size == 0:
            print(
                f"Log: Latest log file '{latest_filepath}' is empty. Starting reset count at 1."
            )
            _current_reset_count = 1
            return 1

        # Read the last line (simple approach for MicroPython)
        # Read chunks from the end might be complex without tell/seek guarantees
        # Reading line by line is feasible given MAX_LOG_FILE_SIZE
        with open(latest_filepath, "rb") as f:
            # Read lines, keeping the last non-empty one
            current_line = f.readline()
            while current_line:
                stripped_line = current_line.strip()
                if stripped_line:  # Keep track of the last line with content
                    last_line_bytes = (
                        current_line  # Store the full line including newline if present
                    )
                current_line = f.readline()

        if last_line_bytes is None:
            print(
                f"Log: Latest log file '{latest_filepath}' contained no valid lines. Starting reset count at 1."
            )
            _current_reset_count = 1
            return 1

        # Decode and parse the last line
        try:
            last_line_str = last_line_bytes.decode(
                "utf-8"
            ).strip()  # Strip leading/trailing whitespace
            parts = last_line_str.split(" ", 1)  # Split only on the first space
            if not parts:
                raise ValueError(
                    "Line is empty after stripping"
                )  # Should not happen if last_line_bytes was not None

            previous_count_str = parts[0]
            previous_count = int(previous_count_str)
            print(
                f"Log: Found previous reset count {previous_count} in '{latest_filepath}'. Next count is {previous_count + 1}."
            )
            _current_reset_count = previous_count + 1
            return _current_reset_count

        except (ValueError, IndexError, UnicodeError) as e:
            print(
                f"Log: Error parsing reset count from last line of '{latest_filepath}': '{last_line_bytes}'. Error: {e}. Starting reset count at 1."
            )
            _current_reset_count = 1
            return _current_reset_count
        except Exception as e:
            print(
                f"Log: Unexpected error parsing last line of '{latest_filepath}': {e}. Starting reset count at 1."
            )
            _current_reset_count = 1
            return _current_reset_count

    except OSError as e:
        print(
            f"Log: Error reading latest log file '{latest_filepath}': {e}. Starting reset count at 1."
        )
        _current_reset_count = 1
        return _current_reset_count
    except Exception as e:
        print(
            f"Log: Unexpected error processing log file '{latest_filepath}': {e}. Starting reset count at 1."
        )
        _current_reset_count = 1
        return _current_reset_count


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


def recursive_mkdir(path: str):
    """Creates a directory and all parent directories if they don't exist.
    Uses print for internal status messages during creation.
    Returns True on success, False on failure.
    """
    # Use print internally as log might not be initialized when this is first called
    print(f"FS: Attempting to recursively create directory: {path}")
    if not path:
        print("FS: recursive_mkdir called with empty path.")
        return False

    # Handle paths starting with / correctly
    parts = path.strip("/").split("/")
    current_path = "/" if path.startswith("/") else ""

    for part in parts:
        if not part:  # Handle potential double slashes //
            continue

        # Ensure trailing slash for concatenation if current_path is not empty or just "/"
        if current_path and not current_path.endswith("/"):
            current_path += "/"

        # Avoid double slash if root path is "/"
        if current_path != "/" or part:
            current_path += part

        try:
            uos.stat(current_path)
            # print(f"FS: Path component exists: {current_path}") # Optional debug
        except OSError as e:
            if e.args[0] == 2:  # ENOENT - Directory/file does not exist
                try:
                    uos.mkdir(current_path)
                    print(f"FS: Created directory component: {current_path}")
                except OSError as mkdir_e:
                    print(
                        f"FS: Error creating directory component '{current_path}': {mkdir_e}"
                    )
                    return False  # Signal failure
            else:
                # Other stat error (e.g., permission denied)
                print(f"FS: Error checking path component '{current_path}': {e}")
                return False  # Signal failure

    print(f"FS: Successfully ensured directory exists: {path}")
    return True  # Signal success


# Removed _recursive_mkdir helper function, will be moved to fs.py
def _ensure_log_dir():
    global _log_dir_checked
    if _log_dir_checked:
        return
    try:
        uos.stat(LOG_DIR)
        # Use print initially, log might not be ready.
        print(f"Log directory '{LOG_DIR}' already exists.")
    except OSError as e:
        if e.args[0] == 2:  # ENOENT - Directory doesn't exist
            # Attempt recursive creation using the function from fs.py
            # fs.recursive_mkdir uses print internally for its steps.
            print(
                f"Log directory '{LOG_DIR}' not found. Attempting recursive creation..."
            )
            try:
                success = recursive_mkdir(LOG_DIR)
                if success:
                    # Use print, log might not be ready.
                    print(f"Successfully created log directory structure: {LOG_DIR}")
                else:
                    # fs.recursive_mkdir already printed the specific error
                    print(f"Failed to create log directory structure: {LOG_DIR}")
                    # Logging to file will likely fail.
            except Exception as mkdir_e:
                # Catch any unexpected error from recursive_mkdir itself
                print(
                    f"Unexpected error during recursive directory creation for '{LOG_DIR}': {mkdir_e}"
                )

        else:
            # Other stat error (permissions, etc.)
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


def log(*args, **kwargs):
    ticks_now_ms = utime.ticks_ms()
    now = utime.gmtime()
    ms = ticks_now_ms % 1000
    timestamp = "{:02d}-{}-{:04d} {:02d}:{:02d}:{:02d}.{:03d}".format(
        now[2], _MONTH_ABBR[now[1] - 1], now[0], now[3], now[4], now[5], ms
    )
    message = " ".join(str(arg) for arg in args)
    output = f"{_get_next_reset_counter()} {timestamp} {message}\n"

    print(output, end="", **kwargs)
    output_bytes = output.encode("utf-8")
    _queue_lock.acquire()
    try:
        _active_queue.append(output_bytes)
    finally:
        _queue_lock.release()


def _log_writer_thread_func():
    global _current_log_index
    global _last_write_times_us
    global _active_queue
    global _queue_lock

    _ensure_log_dir()
    _current_log_index = get_latest_log_index()
    print("Log writer thread started. Initial log index:", _current_log_index)

    last_write_time_ms = utime.ticks_ms()
    current_size = 0
    current_filepath = _get_log_filepath(_current_log_index)
    try:
        stat = uos.stat(current_filepath)
        current_size = stat[6]
        print(
            f"Log writer: Initial size for {current_filepath} is {current_size} bytes."
        )
    except OSError as e:
        if e.args[0] == 2:  # ENOENT (File not found)
            print(
                f"Log writer: Initial log file {current_filepath} not found. Starting size 0."
            )
            # current_size remains 0
        else:
            print(
                f"Log writer: Error stating initial log file {current_filepath}: {e}. Assuming size 0."
            )
            # current_size remains 0

    while True:
        utime.sleep_ms(_POLL_INTERVAL_MS)
        now_ms = utime.ticks_ms()
        should_write = False
        queue_size = 0

        _queue_lock.acquire()
        try:
            queue_size = len(_active_queue)
        finally:
            _queue_lock.release()

        if queue_size >= _WRITE_THRESHOLD:
            should_write = True
        elif (
            queue_size > 0
            and utime.ticks_diff(now_ms, last_write_time_ms) >= _WRITE_TIMEOUT_MS
        ):
            last_write_time_ms = utime.ticks_ms()
            should_write = True

        if should_write:
            messages_to_write = None
            # Swap queue under lock
            _queue_lock.acquire()
            try:
                if _active_queue:
                    messages_to_write = _active_queue
                    _active_queue = []
            finally:
                _queue_lock.release()

            if messages_to_write:
                # Get the current filepath (might have changed due to rotation)
                current_filepath = _get_log_filepath(_current_log_index)
                batch_bytes = b"".join(messages_to_write)
                batch_size = len(batch_bytes)
                bytes_written = None

                if current_size > 0 and (current_size + batch_size) > MAX_LOG_FILE_SIZE:
                    _current_log_index += 1

                    current_filepath = _get_log_filepath(_current_log_index)
                    current_size = 0  # Reset size for the new file
                    print(f"Rotating log to new file: {current_filepath}")

                try:
                    t_write_start_ms = utime.ticks_ms()
                    with open(current_filepath, "ab") as f:
                        bytes_written = f.write(batch_bytes)
                    t_write_end_ms = utime.ticks_ms()
                    write_duration_ms = utime.ticks_diff(
                        t_write_end_ms, t_write_start_ms
                    )

                    log(
                        f"LogT: Wrote batch ({len(messages_to_write)} msgs, {len(batch_bytes)} bytes) took {write_duration_ms} ms to {current_filepath}"
                    )

                    if bytes_written is not None and bytes_written == len(batch_bytes):
                        current_size += bytes_written
                    elif bytes_written is not None:
                        # Partial write - less likely in binary mode but handle defensively
                        print(
                            f"Warning: Partial write to log file '{current_filepath}'. Expected {len(batch_bytes)}, wrote {bytes_written}."
                        )
                        current_size += (
                            bytes_written  # Still update with actual written
                        )
                    else:
                        print(
                            f"Warning: f.write returned None for log file '{current_filepath}'. Estimating size increase."
                        )
                        # Estimate size increase, though the file might be inconsistent
                        current_size += len(batch_bytes)

                except Exception as e:
                    print(f"Error writing batch to log file '{current_filepath}': {e}")
                    # Consider if a sleep is still needed here after a batch failure
                    utime.sleep_ms(100)
                # --- END: Bulk Write Logic ---


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
