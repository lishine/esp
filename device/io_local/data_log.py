import uasyncio as asyncio
import uos
import time
import json

from log import log, _get_next_reset_counter  # Use log directly
from lib.queue import Queue, QueueEmpty, QueueFull  # Use the custom queue
import sd  # For SD_MOUNT_POINT

# import io_local.gps_reader as gps_reader # Defer this import

# Keep original sensor imports - adjust if other sensors are added/removed
# from . import esc_telemetry # Example, ensure these are available if used by _format_sensor_data_values
# from . import ds18b20 # Example

# --- Configuration ---
DATA_REPORT_INTERVAL_MS: int = (
    300  # How often data_report_task runs (also for JSONL writes)
)
DATA_LOG_INTERVAL_S: int = 5  # For the reinstated summary log task
ERROR_LOG_INTERVAL_S: int = 30
QUEUE_SIZE: int = 500

# --- Module-Level Globals and One-Time Setup ---
SD_DATA_DIR: str = f"{sd.SD_MOUNT_POINT}/data"
current_log_file_path: str | None = None  # For JSONL file
is_log_file_renamed_this_session: bool = False

# --- Queues ---
# Using lazy initialization pattern for queues as well
_raw_data_queue_instance: Queue | None = None
_log_data_queue_instance: Queue | None = None  # Reinstated for summary logging
_error_queue_instance: Queue | None = None


def _get_raw_data_queue() -> Queue:
    global _raw_data_queue_instance
    if _raw_data_queue_instance is None:
        _raw_data_queue_instance = Queue(QUEUE_SIZE)
    return _raw_data_queue_instance


def _get_log_data_queue() -> Queue:  # Reinstated
    global _log_data_queue_instance
    if _log_data_queue_instance is None:
        _log_data_queue_instance = Queue(QUEUE_SIZE)
    return _log_data_queue_instance


def _get_error_queue() -> Queue:
    global _error_queue_instance
    if _error_queue_instance is None:
        _error_queue_instance = Queue(QUEUE_SIZE)
    return _error_queue_instance


def _setup_data_logging():
    global current_log_file_path, is_log_file_renamed_this_session, SD_DATA_DIR

    # Removed initial log line as per feedback

    # 1. Ensure SD_DATA_DIR exists
    try:
        uos.stat(SD_DATA_DIR)
        log(
            f"DataLog: Data directory '{SD_DATA_DIR}' already exists."
        )  # Use log directly
    except OSError as e:
        if e.args[0] == 2:  # ENOENT - Directory doesn't exist
            try:
                uos.mkdir(SD_DATA_DIR)
                log(
                    f"DataLog: Created data directory: {SD_DATA_DIR}"
                )  # Use log directly
            except OSError as mkdir_e:
                log(  # Use log directly
                    f"DataLog: CRITICAL - Failed to create data directory {SD_DATA_DIR}: {mkdir_e}. SD logging will fail."
                )
                current_log_file_path = None  # Ensure it's None if dir creation fails
                return  # Stop further setup
        else:  # Other error checking directory
            log(  # Use log directly
                f"DataLog: CRITICAL - Error checking data directory {SD_DATA_DIR}: {e}. SD logging will fail."
            )
            current_log_file_path = None
            return

    # 2. Set initial filename and flags
    is_log_file_renamed_this_session = False
    reset_count = _get_next_reset_counter()  # Fetch current reset count
    initial_filename_only = (
        f"{reset_count:04d}.jsonl"  # e.g., 0001.jsonl (removed temp_)
    )
    current_log_file_path = f"{SD_DATA_DIR}/{initial_filename_only}"
    log(
        f"DataLog: Initial data log file set to: {current_log_file_path}"
    )  # Use log directly


_setup_data_logging()  # Execute this setup when data_log.py is imported


# --- Reporting API for Sensors ---
def report_data(sensor_name: str, timestamp: int, data: any):  # type: ignore # Original timestamp is now unused for JSONL 't' field
    """Called by sensor modules to report new data. Original timestamp is ignored for JSONL 't' field."""
    q = _get_raw_data_queue()
    try:
        # Store sensor_name and data. Timestamp will be generated at write time.
        q.put_nowait((sensor_name, data))
    except QueueFull:
        log(
            f"DataLog: Raw data queue full. Dropping data from {sensor_name}"
        )  # Use log directly


def report_error(sensor_name: str, timestamp: int, error_msg: str):
    """Called by sensor modules to report errors."""
    q = _get_error_queue()
    try:
        q.put_nowait((sensor_name, timestamp, error_msg))
    except QueueFull:
        log(
            f"DataLog: Error queue full. Dropping error from {sensor_name}"
        )  # Use log directly


# _format_sensor_data_values function removed as per feedback.
# Sensor modules are now responsible for providing the 'data' argument
# to report_data() as a dictionary ready for the "values" field in JSONL.


# --- Processing Tasks ---
async def data_report_task():
    """
    Reads raw data from queue, writes it as JSONL to SD card, handles filename rename,
    and also passes aggregated data to the _log_data_queue for summary logging.
    """
    global current_log_file_path, is_log_file_renamed_this_session, SD_DATA_DIR

    # Import gps_reader locally to avoid circular import at module level
    import io_local.gps_reader as gps_reader_local

    log("DataLog: Starting data_report_task for JSONL and summary logging...")
    raw_q = _get_raw_data_queue()
    log_q = _get_log_data_queue()  # Reinstated: get the queue for summary log
    latest_data_this_cycle: dict[str, any] = {}  # type: ignore

    while True:
        latest_data_this_cycle.clear()  # Reset for this interval for summary log

        # Drain the raw queue for this cycle
        items_processed_for_jsonl_this_cycle = 0
        while True:  # Inner loop to process all available items in raw_q
            try:
                sensor_name, data = raw_q.get_nowait()
                items_processed_for_jsonl_this_cycle += 1

                # --- JSONL Logging Logic (as before) ---
                if current_log_file_path is not None:
                    # --- Check and Perform Rename (if needed) ---
                    if not is_log_file_renamed_this_session:
                        try:
                            if (
                                gps_reader_local.is_rtc_synced()
                            ):  # Use locally imported gps_reader
                                current_utc_tuple = time.gmtime(time.time())
                                if current_utc_tuple[0] >= 2023:
                                    timestamp_str = (
                                        f"{current_utc_tuple[0]:04d}-{current_utc_tuple[1]:02d}-{current_utc_tuple[2]:02d}_"
                                        f"{current_utc_tuple[3]:02d}-{current_utc_tuple[4]:02d}-{current_utc_tuple[5]:02d}"
                                    )
                                    new_filename_only = f"{timestamp_str}.jsonl"
                                    new_full_path = f"{SD_DATA_DIR}/{new_filename_only}"
                                    old_full_path = current_log_file_path

                                    if old_full_path != new_full_path:
                                        log(
                                            f"DataLog: RTC synced. Attempting to rename data log from {old_full_path} to {new_full_path}"
                                        )
                                        try:
                                            uos.rename(old_full_path, new_full_path)
                                            current_log_file_path = new_full_path
                                            is_log_file_renamed_this_session = True
                                            log(
                                                f"DataLog: Data log renamed to: {current_log_file_path}"
                                            )
                                        except Exception as e_rename:
                                            log(
                                                f"DataLog: Error renaming data log: {e_rename}. Continuing with old name: {current_log_file_path}"
                                            )
                                    else:
                                        is_log_file_renamed_this_session = True
                                else:
                                    log(
                                        f"DataLog: RTC synced according to GPS, but year ({current_utc_tuple[0]}) seems invalid. Postponing rename."
                                    )
                        except Exception as e_check_rename:
                            log(
                                f"DataLog: Error during RTC sync check or pre-rename: {e_check_rename}"
                            )

                    # --- Proceed with Writing JSONL Data ---
                    sensor_values = data

                    # Generate timestamp with milliseconds for the 't' field
                    current_ticks_ms_for_t = time.ticks_ms()
                    current_epoch_s_for_t = current_ticks_ms_for_t // 1000
                    milliseconds_for_t = current_ticks_ms_for_t % 1000
                    current_utc_tuple_for_t = time.gmtime(current_epoch_s_for_t)

                    formatted_t_stamp = (
                        f"{current_utc_tuple_for_t[0]:04d}-{current_utc_tuple_for_t[1]:02d}-{current_utc_tuple_for_t[2]:02d}_"
                        f"{current_utc_tuple_for_t[3]:02d}-{current_utc_tuple_for_t[4]:02d}-{current_utc_tuple_for_t[5]:02d}_{milliseconds_for_t:03d}"
                    )

                    entry_dict = {
                        "t": formatted_t_stamp,  # Use the new formatted timestamp with correct milliseconds
                        "n": sensor_name,
                        "v": sensor_values,
                    }
                    json_string = json.dumps(entry_dict)
                    try:
                        with open(current_log_file_path, "a") as f:
                            f.write(json_string + "\n")
                    except OSError as e_write:
                        log(
                            f"DataLog: OSError writing to {current_log_file_path}: {e_write}. Data for {sensor_name} lost."
                        )
                    except Exception as e_generic_write:
                        log(
                            f"DataLog: Generic error writing to {current_log_file_path}: {e_generic_write}. Data for {sensor_name} lost."
                        )
                else:  # current_log_file_path is None
                    log(
                        f"DataLog: Skipping JSONL write for {sensor_name} as current_log_file_path is None (setup failed)."
                    )

                # --- Aggregation for Summary Log (original behavior) ---
                latest_data_this_cycle[sensor_name] = (
                    data  # Keep latest for summary log
                )

            except QueueEmpty:
                break  # Raw queue drained for this processing burst
            except Exception as e_inner_loop:
                log(
                    f"DataLog: Error in data_report_task inner processing loop: {e_inner_loop}"
                )
                break  # Exit inner loop on error to avoid tight spin

        # --- Push to Summary Log Queue (original behavior) ---
        if latest_data_this_cycle:
            try:
                log_q.put_nowait(latest_data_this_cycle.copy())
            except QueueFull:
                log(
                    "DataLog: Summary log data queue full. Dropping aggregated data for summary."
                )

        # Sleep at the end of the outer loop, after processing all available raw data
        # and attempting to push to summary log queue.
        await asyncio.sleep_ms(DATA_REPORT_INTERVAL_MS)  # Revert to asyncio alias


async def data_log_task():  # Reinstated
    """
    Slower task (default 5s): Reads aggregated data batches from the _log_data_queue,
    merges them, formats, and logs the latest state for the interval via main log.
    """
    log("DataLog: Starting data_log_task for summary logging...")
    log_q = _get_log_data_queue()
    final_data_this_log_interval: dict[str, any] = {}  # type: ignore

    while True:
        final_data_this_log_interval.clear()
        while True:
            try:
                aggregated_batch = log_q.get_nowait()
                final_data_this_log_interval.update(aggregated_batch)
            except QueueEmpty:
                break
            except Exception as e:
                log(f"DataLog: Error processing summary log queue: {e}")
                break

        if final_data_this_log_interval:
            log_parts = []
            for key, value in final_data_this_log_interval.items():
                if isinstance(value, dict):
                    dict_parts = []
                    for sub_key, sub_value in value.items():
                        if isinstance(sub_value, float):
                            dict_parts.append(f"{sub_key}={sub_value:.2f}")
                        else:
                            dict_parts.append(f"{sub_key}={sub_value}")
                    dict_string = " ".join(dict_parts)
                    log_parts.append(f"{key}: {dict_string}")
                elif isinstance(value, (list, tuple)):
                    items_str = ",".join(map(str, value))
                    log_parts.append(f"{key}:[{items_str}]")
                else:
                    log_parts.append(f"{key}:{value}")

            if log_parts:
                log(f"DATA | {' | '.join(log_parts)}")

        await asyncio.sleep(DATA_LOG_INTERVAL_S)  # Revert to asyncio alias


async def error_log_task():
    """
    Error logging task (default 30s): Reads all errors from the error queue and logs
    only unique errors (by sensor_name and error_msg) per cycle using the main system log.
    """
    log("DataLog: Starting error_log_task...")  # Use log directly
    error_q = _get_error_queue()
    while True:
        unique_errors_this_cycle = set()  # Track unique errors for this cycle
        # Drain the error queue
        while True:
            try:
                sensor_name, timestamp, error_msg = (
                    error_q.get_nowait()
                )  # Original timestamp is kept for error context
                error_key = (
                    sensor_name,
                    error_msg,
                )  # Uniqueness based on sensor and message

                if error_key not in unique_errors_this_cycle:
                    unique_errors_this_cycle.add(error_key)
                    log(  # Use log directly
                        f"DataLog ERROR | Sensor: {sensor_name}, TS: {timestamp}, Msg: {error_msg}"
                    )
            except QueueEmpty:
                break  # Error queue drained for this cycle
            except Exception as e:
                log(
                    f"DataLog: Error in error_log_task processing queue: {e}"
                )  # Use log directly
                break  # Avoid tight loop on error

        await asyncio.sleep(ERROR_LOG_INTERVAL_S)  # Revert to asyncio alias


def get_current_data_log_file_path() -> str | None:
    """Returns the full path of the current JSONL data log file."""
    global current_log_file_path
    return current_log_file_path
