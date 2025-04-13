# Data Logging Architecture Plan (Queue-Based, Multi-Stage)

This plan outlines an architecture where sensor modules push data and errors to a central logging module (`data_log.py`) using function calls. The logging module then uses multiple asynchronous tasks and queues to process and log this information at different rates.

**Note on Type Hints:** Standard Python type hints (using the `typing` module) were initially added to `lib/queue.py` to aid linters like Pylance. However, the `typing` module is not available in standard MicroPython builds, causing `ImportError`. All type hints have been removed from `lib/queue.py` to ensure runtime compatibility. Linter errors related to `uasyncio` or the custom queue might still appear but should be ignored if the code runs correctly on the device.

## 1. `data_log.py` - Central Hub & Processing Stages

### Queues:

- Uses the custom `Queue` implementation from `lib/queue.py`.
- `RAW_DATA_QUEUE = Queue(50)`: Stores raw data tuples `(sensor_name, timestamp, data)` pushed by sensors.
- `LOG_DATA_QUEUE = Queue(50)`: Stores aggregated data dictionaries `{sensor_name: latest_data}` pushed by the fast processing task.
- `ERROR_QUEUE = Queue(50)`: Stores error tuples `(sensor_name, timestamp, error_msg)` pushed by sensors.

### Reporting Functions (API for Sensors):

- `report_data(sensor_name, timestamp, data)`: Puts data onto `RAW_DATA_QUEUE` (non-blocking). Handles `QueueFull`.
- `report_error(sensor_name, timestamp, error_msg)`: Puts error onto `ERROR_QUEUE` (non-blocking). Handles `QueueFull`.

### Processing Tasks:

- **`data_report_task` (Fast Task):**
  - Interval: `0.3s`.
  - Drains `RAW_DATA_QUEUE`.
  - Performs external data reporting action (e.g., WebSocket push - Placeholder).
  - Aggregates the latest reading for each sensor within the 0.3s window.
  - Puts the aggregated dictionary `{sensor_name: latest_data}` onto `LOG_DATA_QUEUE`.
- **`data_log_task` (Logging Task):**
  - Interval: `5s`.
  - Drains `LOG_DATA_QUEUE`.
  - Merges data dictionaries received over the 5s interval, keeping the absolute latest data per sensor.
  - Formats the final aggregated data into the `DATA | SENSOR1:[...] | SENSOR2:[...]` log string.
  - Logs the string if any data was received.
- **`error_log_task` (Error Logging Task):**
  - Interval: `10s`.
  - Drains `ERROR_QUEUE`.
  - Logs _each_ error message received: `log(f"ERROR | {sensor_name}: {error_msg}")`.

## 2. Sensor Module Example (`device/io_local/ds18b20.py`)

- Imports `data_log`.
- Removes direct queue interaction.
- On successful read: Calls `data_log.report_data('DS18B20', time.ticks_ms(), temperature_list)`.
- On error: Calls `data_log.report_error('DS18B20', time.ticks_ms(), formatted_error_string)` (and also logs the error directly via `log()`).

## 3. Task Orchestration (`device/main.py` or similar)

- Must create and run the three tasks from `data_log.py` (`data_report_task`, `data_log_task`, `error_log_task`) using `asyncio.create_task()`.
- Must also initialize and run the sensor task(s) (e.g., `ds18b20._read_ds18b20_task`).

## Mermaid Diagram

```mermaid
graph TD
    subgraph ds18b20.py
        A[_read_ds18b20_task] --> B{Read OK?};
        B -- Yes --> C[Call data_log.report_data(...)];
        B -- No --> D[Log Error Directly];
        D --> D2[Call data_log.report_error(...)];
    end

    subgraph data_log.py (API & Queues)
        E[report_data()] --> F[RAW_DATA_QUEUE];
        G[report_error()] --> H[ERROR_QUEUE];
        I[LOG_DATA_QUEUE];
    end

    subgraph data_log.py (Tasks)
        J[data_report_task (0.3s)] --> K{Loop};
        K --> L[Drain RAW_DATA_QUEUE];
        L --> M[Perform 'Data Reporting' (Placeholder)];
        M --> N[Aggregate latest data per sensor];
        N --> O[Put aggregated dict onto LOG_DATA_QUEUE];
        O --> P[Sleep 0.3s];
        P --> K;

        Q[data_log_task (5s)] --> R{Loop};
        R --> S[Drain LOG_DATA_QUEUE];
        S --> T[Merge data batches];
        T --> U[Format log parts];
        U --> V[Log "DATA | ..."];
        V --> W[Sleep 5s];
        W --> R;

        X[error_log_task (10s)] --> Y{Loop};
        Y --> Z[Drain ERROR_QUEUE];
        Z --> AA{For each error};
        AA --> BB[Log "ERROR | ..."];
        BB --> Z;
        Z -- Done --> CC[Sleep 10s];
        CC --> Y;
    end

    C --> E;
    D2 --> G;
    L --> F;
    O --> I;
    S --> I;
    Z --> H;

    subgraph main.py
        DD[Start App] --> EE[Create/Run data_report_task];
        DD --> FF[Create/Run data_log_task];
        DD --> GG[Create/Run error_log_task];
        DD --> HH[Init/Run ds18b20 task];
        HH --> A;
    end
```
