import utime
import uos
import _thread

from globals import SD_MOUNT_POINT
import settings_manager
from file_utils import generate_filename
import fs


LOG_DIR = f"{SD_MOUNT_POINT}/ld/logs"
LOG_FILE_EXTENSION = "txt"
MAX_LOG_FILE_SIZE = 4000000  # Bytes

current_log_filename = None  # Will be set by _log_writer_thread_func
_log_dir_checked = False

_queue_lock = _thread.allocate_lock()
_active_queue = []

_WRITE_THRESHOLD = 60  # Number of messages to trigger a write
_WRITE_TIMEOUT_MS = 60000
_POLL_INTERVAL_MS = 5000  # 1 second polling interval

_last_write_times_us = []  # Stores the last N write durations in microseconds

# Month abbreviations for log message formatting
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
                success = fs.recursive_mkdir(LOG_DIR)
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


def get_current_log_filename() -> str | None:
    """Returns the full path of the current log file."""
    global current_log_filename
    return current_log_filename


def log(*args, **kwargs):
    """Log a message with timestamp and reset counter."""
    now = utime.gmtime()
    # Use custom format for log messages (DD-Mon-YYYY HH:MM:SS)
    timestamp_str = "{:02d}-{}-{:04d} {:02d}:{:02d}:{:02d}".format(
        now[2], _MONTH_ABBR[now[1] - 1], now[0], now[3], now[4], now[5]
    )
    message = " ".join(str(arg) for arg in args)
    output = f"{settings_manager.get_reset_counter()} {timestamp_str} {message}\n"

    print(output, end="", **kwargs)
    output_bytes = output.encode("utf-8")
    _queue_lock.acquire()
    try:
        _active_queue.append(output_bytes)
    finally:
        _queue_lock.release()


def _log_writer_thread_func():
    global current_log_filename, _last_write_times_us, _active_queue, _queue_lock

    _ensure_log_dir()
    current_log_filename = generate_filename(LOG_DIR, LOG_FILE_EXTENSION)
    print(f"Log writer thread started. Initial log file: {current_log_filename}")

    last_write_time_ms = utime.ticks_ms()
    current_size = 0
    try:
        if current_log_filename:  # Ensure filename is not None
            stat = uos.stat(current_log_filename)
            current_size = stat[6]
            print(
                f"Log writer: Initial size for {current_log_filename} is {current_size} bytes."
            )
    except OSError as e:
        if e.args[0] == 2:  # ENOENT
            print(
                f"Log writer: Initial log file {current_log_filename} not found. Starting size 0."
            )
        else:
            print(
                f"Log writer: Error stating initial log file {current_log_filename}: {e}. Assuming size 0."
            )

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

            if messages_to_write and current_log_filename:
                batch_bytes = b"".join(messages_to_write)
                batch_size = len(batch_bytes)
                bytes_written = None

                if current_size > 0 and (current_size + batch_size) > MAX_LOG_FILE_SIZE:
                    current_log_filename = generate_filename(
                        LOG_DIR, LOG_FILE_EXTENSION
                    )
                    current_size = 0
                    print(f"Rotating log to new file: {current_log_filename}")

                try:
                    t_write_start_ms = utime.ticks_ms()
                    with open(current_log_filename, "ab") as f:
                        bytes_written = f.write(batch_bytes)
                    t_write_end_ms = utime.ticks_ms()
                    write_duration_ms = utime.ticks_diff(
                        t_write_end_ms, t_write_start_ms
                    )

                    # Temporarily disable self-logging during write to avoid recursion if log itself is called here
                    # This is a simplified approach. A more robust solution might involve a flag.
                    # For now, we rely on the fact that print is used for critical writer messages.
                    # log(f"LogT: Wrote batch ({len(messages_to_write)} msgs, {batch_size} bytes) took {write_duration_ms} ms to {current_log_filename}")
                    print(
                        f"LogT: Wrote batch ({len(messages_to_write)} msgs, {batch_size} bytes) took {write_duration_ms} ms to {current_log_filename}"
                    )

                    if bytes_written is not None and bytes_written == batch_size:
                        current_size += bytes_written
                    elif bytes_written is not None:
                        print(
                            f"Warning: Partial write to log file '{current_log_filename}'. Expected {batch_size}, wrote {bytes_written}."
                        )
                        current_size += bytes_written
                    else:
                        print(
                            f"Warning: f.write returned None for log file '{current_log_filename}'. Estimating size increase."
                        )
                        current_size += batch_size
                except Exception as e:
                    print(
                        f"Error writing batch to log file '{current_log_filename}': {e}"
                    )
                    utime.sleep_ms(100)


def clear_logs() -> bool:
    """Removes all log files from the log directory."""
    global current_log_filename, _last_write_times_us
    _ensure_log_dir()

    success = fs.clear_directory(LOG_DIR, LOG_FILE_EXTENSION)
    if success:
        current_log_filename = generate_filename(
            LOG_DIR, LOG_FILE_EXTENSION
        )  # Set up for a new log file
        _last_write_times_us.clear()
        print(f"Log clearing finished. New log: {current_log_filename}")

    return success
