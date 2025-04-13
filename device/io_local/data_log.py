import uasyncio as asyncio
from log import log
from lib.queue import Queue, QueueEmpty, QueueFull  # Use the custom queue

# Keep original sensor imports - adjust if other sensors are added/removed
from . import esc_telemetry
from . import ds18b20

# from . import gps_reader # Assuming GPS might push data later
# from . import ina226 # Assuming INA might push data later

# --- Configuration ---
DATA_REPORT_INTERVAL_MS: int = 300
DATA_LOG_INTERVAL_S: int = 5
ERROR_LOG_INTERVAL_S: int = 10
QUEUE_SIZE: int = 50

# --- Queues ---
# Using lazy initialization pattern for queues as well
_raw_data_queue_instance: Queue | None = None
_log_data_queue_instance: Queue | None = None
_error_queue_instance: Queue | None = None


def _get_raw_data_queue() -> Queue:
    global _raw_data_queue_instance
    if _raw_data_queue_instance is None:
        _raw_data_queue_instance = Queue(QUEUE_SIZE)
    return _raw_data_queue_instance


def _get_log_data_queue() -> Queue:
    global _log_data_queue_instance
    if _log_data_queue_instance is None:
        _log_data_queue_instance = Queue(QUEUE_SIZE)
    return _log_data_queue_instance


def _get_error_queue() -> Queue:
    global _error_queue_instance
    if _error_queue_instance is None:
        _error_queue_instance = Queue(QUEUE_SIZE)
    return _error_queue_instance


# --- Reporting API for Sensors ---
def report_data(sensor_name: str, timestamp: int, data: any):  # type: ignore
    """Called by sensor modules to report new data."""
    q = _get_raw_data_queue()
    try:
        q.put_nowait((sensor_name, timestamp, data))
    except QueueFull:
        log(f"DataLog: Raw data queue full. Dropping data from {sensor_name}")


def report_error(sensor_name: str, timestamp: int, error_msg: str):
    """Called by sensor modules to report errors."""
    q = _get_error_queue()
    try:
        q.put_nowait((sensor_name, timestamp, error_msg))
    except QueueFull:
        log(f"DataLog: Error queue full. Dropping error from {sensor_name}")


# --- Processing Tasks ---


async def data_report_task():
    """
    Fast task (0.3s): Reads raw data, performs external reporting (placeholder),
    aggregates latest data per sensor, and passes to the logging queue.
    """
    log("Starting data report task...")
    raw_q = _get_raw_data_queue()
    log_q = _get_log_data_queue()
    latest_data_this_cycle: dict[str, any] = {}  # type: ignore

    while True:
        latest_data_this_cycle.clear()  # Reset for this interval
        # Drain the raw queue
        while True:
            try:
                sensor_name, timestamp, data = raw_q.get_nowait()
                # --- Placeholder for external data reporting ---
                # Example: await send_to_websocket(sensor_name, timestamp, data)
                # --- End Placeholder ---
                latest_data_this_cycle[sensor_name] = data  # Keep latest
            except QueueEmpty:
                break  # Raw queue drained for this cycle
            except Exception as e:
                log(f"DataReportTask: Error processing raw queue: {e}")
                break  # Avoid tight loop on unexpected error

        # If any data was processed, push the aggregated dict to the log queue
        if latest_data_this_cycle:
            try:
                # Pass a copy to avoid modification issues if processing takes time
                log_q.put_nowait(latest_data_this_cycle.copy())
            except QueueFull:
                log("DataLog: Log data queue full. Dropping aggregated data.")

        await asyncio.sleep_ms(DATA_REPORT_INTERVAL_MS)


async def data_log_task():
    """
    Slower task (5s): Reads aggregated data batches from the report task,
    merges them, formats, and logs the latest state for the interval.
    """
    log("Starting data logging task...")
    log_q = _get_log_data_queue()
    final_data_this_log_interval: dict[str, any] = {}  # type: ignore

    while True:
        final_data_this_log_interval.clear()  # Reset for this interval
        # Drain the log data queue, merging results
        while True:
            try:
                aggregated_batch = log_q.get_nowait()
                # Merge, keeping the latest data (from potentially multiple 0.3s cycles)
                final_data_this_log_interval.update(aggregated_batch)
            except QueueEmpty:
                break  # Log queue drained for this cycle
            except Exception as e:
                log(f"DataLogTask: Error processing log queue: {e}")
                break

        # Format the final log message if data exists
        if final_data_this_log_interval:
            log_parts = []
            # --- Format DS18B20 ---
            if "DS18B20" in final_data_this_log_interval:
                temps = final_data_this_log_interval["DS18B20"]
                # Ensure temps is a list or tuple before joining
                if isinstance(temps, (list, tuple)):
                    ds_str = (
                        "DS:"
                        + "["
                        + ",".join(
                            [f"{t:.1f}C" if t is not None else "N/A" for t in temps]
                        )
                        + "]"
                    )
                    log_parts.append(ds_str)
                else:
                    log(f"DataLogTask: Invalid DS18B20 data format: {temps}")

            # --- Format ESC Telemetry (Example) ---
            # if 'ESC' in final_data_this_log_interval:
            #     esc_data = final_data_this_log_interval['ESC']
            #     # Assuming esc_data is a dict as returned by original _log_esc_telemetry
            #     esc_str = f"ESC:{esc_data.get('voltage', 0):.1f}V,{esc_data.get('rpm', 0)}rpm,{esc_data.get('temperature', 0)}C,{esc_data.get('current', 0):.1f}A,{esc_data.get('consumption', 0)}mAh"
            #     log_parts.append(esc_str)

            # --- Add formatting for other sensors here ---

            if log_parts:
                log(f"DATA | {' | '.join(log_parts)}")

        await asyncio.sleep(DATA_LOG_INTERVAL_S)


async def error_log_task():
    """
    Error logging task (10s): Reads all errors from the error queue and logs them.
    """
    log("Starting error logging task...")
    error_q = _get_error_queue()
    while True:
        # Drain the error queue
        errors_found = False
        while True:
            try:
                sensor_name, timestamp, error_msg = error_q.get_nowait()
                log(f"ERROR | {sensor_name}: {error_msg}")
                errors_found = True
            except QueueEmpty:
                # if errors_found: log("ErrorLogTask: Error queue drained.") # Optional
                break  # Error queue drained
            except Exception as e:
                log(f"ErrorLogTask: Error processing error queue: {e}")
                break

        await asyncio.sleep(ERROR_LOG_INTERVAL_S)
