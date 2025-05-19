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
)

DATA_REPORT_INTERVAL_MS = 500
DATA_LOG_INTERVAL_S = 5
ERROR_LOG_INTERVAL_S = 30
QUEUE_SIZE = 500

SD_DATA_DIR = f"{SD_MOUNT_POINT}/data"
current_log_file_path = None
is_log_file_renamed_this_session = False

_raw_data_queue_instance = None
_log_data_queue_instance = None
_error_queue_instance = None


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
    config = settings_manager.get_setting("configuration")
    if config:
        try:
            with open(file_path, "w") as f:
                f.write(json.dumps(config) + "\n")
            log.log(f"DataLog: Wrote config header to {file_path}")
        except Exception as e:
            log.log(f"DataLog: Error writing config header: {e}")


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


# DOES NOT WORK CURRENTLY
def rename_file_if_rtc_updated() -> bool:
    """Renames the log file if RTC has been updated from GPS during this session.
    Only attempts rename once per session."""
    global current_log_file_path, is_log_file_renamed_this_session
    from rtc import get_rtc_set_with_time

    if (
        not get_rtc_set_with_time()
        or not current_log_file_path
        or is_log_file_renamed_this_session
    ):
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
        entry = {
            "t": timestamp_str,
            "r": f"{settings_manager.get_reset_counter():04d}",
            "n": sensor_name,
            "v": data,
        }
        with open(current_log_file_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return True
    except Exception as e:
        log.log(f"DataLog: Write error for {sensor_name}: {e}")
        return False


async def data_report_task():
    log.log("DataLog: Starting data report task")
    raw_q = _get_raw_data_queue()
    log_q = _get_log_data_queue()
    latest_data = {}

    while True:
        latest_data.clear()
        while True:
            try:
                rename_file_if_rtc_updated()
                sensor_name, data = raw_q.get_nowait()
                _write_jsonl_entry(sensor_name, data)
                latest_data[sensor_name] = data
            except QueueEmpty:
                break
            except Exception as e:
                log.log(f"DataLog: Processing error: {e}")
                break

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
            log_parts = [_format_value_for_log(k, v) for k, v in data_buffer.items()]
            log.log(f"DATA | {' | '.join(log_parts)}")

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
    global current_log_file_path, is_log_file_renamed_this_session

    if not _ensure_dir_exists(SD_DATA_DIR):
        return True

    success = clear_directory(SD_DATA_DIR, DATA_LOG_EXTENSION)
    if success:
        current_log_file_path = None
        is_log_file_renamed_this_session = False
        _setup_data_logging()

    return success
