import uasyncio as asyncio
import uos
import json
import settings_manager
import log
from lib.queue import Queue, QueueEmpty, QueueFull
from globals import SD_MOUNT_POINT
from file_utils import (
    generate_filename,
    get_synced_timestamp,
    format_date,
    format_time,
)

DATA_REPORT_INTERVAL_MS = 500
DATA_LOG_INTERVAL_S = 4
ERROR_LOG_INTERVAL_S = 30
QUEUE_SIZE = 500

SD_DATA_DIR = f"{SD_MOUNT_POINT}/data"
current_log_file_path = None
is_log_file_renamed_this_session = False

_raw_data_queue_instance = None
_log_data_queue_instance = None
_error_queue_instance = None
_live_sensor_data_cache: dict = {}  # ADDED

# ADDED: Accumulator for sensor data arrays
_accumulated_sensor_arrays = []

from fs import recursive_mkdir, remove_file, clear_directory


def _ensure_dir_exists(path: str) -> bool:
    return recursive_mkdir(path)


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


DATA_LOG_EXTENSION = "jsonl"


def _write_config_header(file_path: str):
    header_data = settings_manager.get_setting("configuration")
    if not isinstance(header_data, dict):  # Ensure config is a dict, or start fresh
        header_data = {}

    try:
        # Add date and restart counter to the header_data dictionary
        _, time_tuple = get_synced_timestamp()
        date_str = format_date(time_tuple)
        header_data["date"] = date_str

        r_val = f"{settings_manager.get_reset_counter():04d}"
        header_data["restart"] = r_val

        with open(file_path, "w") as f:
            f.write(
                json.dumps(header_data) + "\n"
            )  # Write the single combined header object
        log.log(f"DataLog: Wrote combined header to {file_path}")
    except Exception as e:
        log.log(f"DataLog: Error writing combined header: {e}")


def _setup_data_logging():
    global current_log_file_path, is_log_file_renamed_this_session

    if not _ensure_dir_exists(SD_DATA_DIR):
        current_log_file_path = None
        return

    current_log_file_path = generate_filename(SD_DATA_DIR, DATA_LOG_EXTENSION)

    try:
        exists = True
        try:
            uos.stat(current_log_file_path)
        except OSError as e:
            if e.args[0] == 2:
                exists = False
                _write_config_header(current_log_file_path)

        log_status = "exists" if exists else "created"
        log.log(f"DataLog: File {current_log_file_path} {log_status}")
    except Exception as e:
        log.log(f"DataLog: Error during file setup: {e}")
        current_log_file_path = None


_setup_data_logging()  # Execute this setup when data_log.py is imported


def report_data(
    sensor_name: str,
    timestamp: int,
    data: dict | list | tuple | str | int | float | bool | None,
) -> None:
    q = _get_raw_data_queue()
    try:
        q.put_nowait((sensor_name, data))
    except QueueFull:
        log.log(f"DataLog: Raw data queue full. Dropping data from {sensor_name}")


def report_error(sensor_name: str, timestamp: int, error_msg: str) -> None:
    q = _get_error_queue()
    try:
        q.put_nowait((sensor_name, timestamp, error_msg))
    except QueueFull:
        log.log(f"DataLog: Error queue full. Dropping error from {sensor_name}")


def rename_file_if_rtc_updated() -> bool:
    """Renames the log file if RTC has been updated from GPS during this session.
    Only attempts rename once per session."""
    global current_log_file_path, is_log_file_renamed_this_session
    from rtc import get_rtc_set_with_time

    rtc_is_set = get_rtc_set_with_time()
    # Only perform detailed logging if RTC is considered set, to reduce log spam.

    if not rtc_is_set or not current_log_file_path or is_log_file_renamed_this_session:
        return False

    try:
        new_path = generate_filename(SD_DATA_DIR, DATA_LOG_EXTENSION)
        if current_log_file_path == new_path:
            is_log_file_renamed_this_session = True
            return False

        uos.rename(current_log_file_path, new_path)
        current_log_file_path = new_path
        is_log_file_renamed_this_session = True
        log.log(f"DataLog: Renamed to {new_path} after GPS time sync")
        return True
    except Exception as e:
        log.log(f"DataLog: Rename error: {e}")
        return False


def _write_jsonl_entry(
    sensor_name: str, data: dict | list | tuple | str | int | float | bool | None
) -> bool:
    if not current_log_file_path:
        return False

    try:
        timestamp_str, current_time = get_synced_timestamp()
        # r_val = f"{settings_manager.get_reset_counter():04d}" # Moved to header
        # Manually construct the JSON string to ensure key order: t, n, v.
        # Each value is passed through json.dumps to ensure it's valid JSON (e.g., strings quoted, objects/arrays serialized).
        a = json.dumps(data, separators=(",", ":"))
        entry_json_string = (
            # f'{{"r":{json.dumps(r_val)},' # "r" key removed
            f'{{"t":{json.dumps(timestamp_str)},'
            f'"n":{json.dumps(sensor_name)},'
            f'"v":{a}}}'  # Corrected to two closing braces
        )
        with open(current_log_file_path, "a") as f:
            f.write(entry_json_string + "\n")
        return True
    except Exception as e:
        log.log(f"DataLog: Write error for {sensor_name}: {e}")
        return False


def _check_esc_rpm_zero_trigger(sensors_data: list) -> bool:
    """Check if any sensor in the batch is 'esc' with rpm value of 0"""
    for sensor_name, data in sensors_data:
        if sensor_name == "esc" and isinstance(data, dict) and data.get("rpm") == 0:
            return True
    return False


def _flush_accumulated_arrays() -> bool:
    """Write all accumulated sensor arrays to file and clear the accumulator"""
    global _accumulated_sensor_arrays

    if not current_log_file_path or not _accumulated_sensor_arrays:
        return True

    try:
        with open(current_log_file_path, "a") as f:
            for array_json_string in _accumulated_sensor_arrays:
                f.write(array_json_string + "\n")

        log.log(
            f"DataLog: Flushed {len(_accumulated_sensor_arrays)} accumulated arrays to file"
        )
        _accumulated_sensor_arrays.clear()
        return True
    except Exception as e:
        log.log(f"DataLog: Error flushing accumulated arrays: {e}")
        return False


def _write_sensors_array(sensors_data: list) -> bool:
    global _accumulated_sensor_arrays

    if not current_log_file_path or not sensors_data:
        return False

    try:
        full_timestamp_str, time_tuple = get_synced_timestamp()  # Get the time_tuple
        time_str = format_time(time_tuple)  # Format to time-only
        # r_val is no longer needed here as it's in the header
        # r_val = f"{settings_manager.get_reset_counter():04d}"

        # Create the common part first - now only contains time
        common_entry_json_string = f'{{"t":{json.dumps(time_str)}}}'

        sensor_specific_entries = []
        for sensor_name, data in sensors_data:
            # Create sensor-specific part: {"n": name, "v": value}
            # needed to override error
            s = json.dumps(data, separators=(",", ":"))
            sensor_part_json_string = f'{{"n":{json.dumps(sensor_name)},' f'"v":{s}}}'
            sensor_specific_entries.append(sensor_part_json_string)

        # Combine common entry with all sensor-specific entries
        all_entries_for_array = [common_entry_json_string] + sensor_specific_entries
        array_json_string = f"[{','.join(all_entries_for_array)}]"

        # Add to accumulator instead of writing immediately
        _accumulated_sensor_arrays.append(array_json_string)

        # Check if we should flush (write) all accumulated data
        if _check_esc_rpm_zero_trigger(sensors_data):
            return _flush_accumulated_arrays()

        return True
    except Exception as e:
        log.log(f"DataLog: Write error for sensors array: {e}")
        return False


async def data_report_task():
    log.log("DataLog: Starting data report task")
    raw_q = _get_raw_data_queue()
    log_q = _get_log_data_queue()
    latest_data = {}

    while True:
        latest_data.clear()
        sensors_batch = []

        while True:
            try:
                rename_file_if_rtc_updated()
                sensor_name, data = raw_q.get_nowait()

                # Get timestamp for this specific data point for the live cache
                _timestamp_str_for_jsonl, current_sensor_time_for_cache = (
                    get_synced_timestamp()
                )

                # Collect sensor data for batch writing
                sensors_batch.append((sensor_name, data))

                # Update latest_data with value and its specific timestamp
                latest_data[sensor_name] = {
                    "value": data,
                    "timestamp": current_sensor_time_for_cache,
                }
            except QueueEmpty:
                break
            except Exception as e:
                log.log(f"DataLog: Processing error: {e}")
                break

        # Write all sensors in current batch as a single array line (now accumulates)
        if sensors_batch:
            _write_sensors_array(sensors_batch)

        if latest_data:
            try:
                log_q.put_nowait(latest_data.copy())
            except QueueFull:
                log.log("DataLog: Summary queue full")

        await asyncio.sleep_ms(DATA_REPORT_INTERVAL_MS)


def _format_value_for_log(
    key: str, value: dict | list | tuple | str | int | float | bool | None
) -> str:
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            if isinstance(v, float):
                parts.append(f"{k}={v:.2f}")
            else:
                parts.append(f"{k}={v}")
        return f"{key}: {' '.join(parts)}"
    if isinstance(value, (list, tuple)):
        return f"{key}:[{','.join(map(str, value))}]"
    return f"{key}:{value}"


async def data_log_task() -> None:
    log.log("DataLog: Starting summary logging")
    log_q = _get_log_data_queue()
    data_buffer = {}

    while True:
        data_buffer.clear()
        while True:
            try:
                data_buffer.update(log_q.get_nowait())
            except QueueEmpty:
                break
            except Exception as e:
                log.log(f"DataLog: Queue processing error: {e}")
                break

        if data_buffer:
            # Adjust formatting as v is now a dict {"value": ..., "timestamp": ...}
            log_parts = [
                _format_value_for_log(k, v.get("value"))
                for k, v in data_buffer.items()
                if isinstance(v, dict)  # Ensure v is a dictionary as expected
            ]
            log.log(f"DATA | {' | '.join(log_parts)}")

            global _live_sensor_data_cache  # ADDED
            _live_sensor_data_cache = (
                data_buffer.copy()
            )  # ADDED - Update the live cache

        await asyncio.sleep(DATA_LOG_INTERVAL_S)


def _log_unique_error(
    sensor_name: str, timestamp: int, error_msg: str, unique_errors: set
) -> None:
    error_key = (sensor_name, error_msg)
    if error_key not in unique_errors:
        unique_errors.add(error_key)
        log.log(
            f"DataLog ERROR | Sensor: {sensor_name}, TS: {timestamp}, Msg: {error_msg}"
        )


async def error_log_task() -> None:
    log.log("DataLog: Starting error log task")
    error_q = _get_error_queue()
    unique_errors = set()

    while True:
        unique_errors.clear()
        while True:
            try:
                sensor_name, timestamp, error_msg = error_q.get_nowait()
                _log_unique_error(sensor_name, timestamp, error_msg, unique_errors)
            except QueueEmpty:
                break
            except Exception as e:
                log.log(f"DataLog: Error processing queue: {e}")
                break

        await asyncio.sleep(ERROR_LOG_INTERVAL_S)


def get_current_data_log_file_path() -> str | None:
    """Returns the full path of the current JSONL data log file."""
    global current_log_file_path
    return current_log_file_path


def clear_data_logs() -> bool:
    global current_log_file_path, is_log_file_renamed_this_session, _accumulated_sensor_arrays

    if not _ensure_dir_exists(SD_DATA_DIR):
        return True

    success = clear_directory(SD_DATA_DIR, DATA_LOG_EXTENSION)
    if success:
        current_log_file_path = None
        is_log_file_renamed_this_session = False
        _accumulated_sensor_arrays.clear()  # Clear accumulator
        _setup_data_logging()

    return success


def get_latest_live_data() -> dict:
    """Returns a copy of the most recent live sensor data cache."""
    global _live_sensor_data_cache
    return _live_sensor_data_cache.copy()


def force_flush_accumulated_data() -> bool:
    """Manually flush any accumulated sensor data to file"""
    return _flush_accumulated_arrays()
