# Asynchronous Logging Plan

**Goal:** Modify the logging system to use a simple in-memory list as a queue (max size 10) and a separate asynchronous task that writes logs to the file system in batches when the queue size reaches 5.

**Architecture:**

```mermaid
sequenceDiagram
    participant AppCode as Application Code
    participant LogFunc as log() in log.py
    participant LogQueue as _log_queue (List)
    participant WriteEvent as _write_event (asyncio.Event)
    participant WriterTask as _log_writer_task() in log.py
    participant FileSystem as File System

    AppCode->>+LogFunc: log("message")
    LogFunc->>LogFunc: Format message with timestamp
    LogFunc->>LogFunc: Print message to console
    alt Queue Full (>=10)
        LogFunc->>LogFunc: Print error "Queue full, dropping"
        LogFunc-->>AppCode: Return
    else Queue Not Full
        LogFunc->>+LogQueue: Append formatted_message
        LogQueue-->>-LogFunc: OK
        alt Queue Threshold Reached (>=5)
            LogFunc->>+WriteEvent: set()
            WriteEvent-->>-LogFunc: OK
        end
        LogFunc-->>-AppCode: Return
    end

    loop Async Writer Loop
        WriterTask->>+WriteEvent: await wait()
        WriteEvent-->>-WriterTask: Event triggered
        WriterTask->>WriteEvent: clear()
        WriterTask->>+LogQueue: Get all messages (copy)
        LogQueue-->>-WriterTask: list_of_messages
        WriterTask->>LogQueue: Clear original queue
        LogQueue-->>WriterTask: OK
        WriterTask->>WriterTask: Process batch (check rotation, write to file)
        WriterTask->>+FileSystem: Write messages
        FileSystem-->>-WriterTask: OK
    end
```

**Detailed Plan:**

1.  **Modify `device/log.py`:**

    - **Import `uasyncio`**.
    - **Create Globals:**
      - `_log_queue = []` (Standard list for the queue)
      - `_MAX_QUEUE_SIZE = 10`
      - `_WRITE_THRESHOLD = 5`
      - `_write_event = asyncio.Event()` (Signal for the writer task)
    - **Modify `log(\*args, **kwargs)` function:\*\*
      - Keep timestamp formatting and console print.
      - Check queue size: `if len(_log_queue) >= _MAX_QUEUE_SIZE:`.
        - If full, print an error message (e.g., `f"Log queue full (size {_MAX_QUEUE_SIZE}). Dropping message: {message}"`) and `return`.
      - If not full, append the formatted `output_bytes` to `_log_queue`.
      - Check threshold: `if len(_log_queue) >= _WRITE_THRESHOLD:`.
        - If threshold met, set the event: `_write_event.set()`.
    - **Create `_log_writer_task()` async function:**
      - Call `_ensure_log_dir()` and initialize `_current_log_index = get_latest_log_index()`.
      - Start `while True:` loop.
      - `await _write_event.wait()`: Wait for the signal.
      - `_write_event.clear()`: Clear the signal immediately.
      - **Process Batch:**
        - `messages_to_write = _log_queue[:]` (Copy all messages currently in the queue).
        - `_log_queue.clear()` (Clear the original queue).
        - If `not messages_to_write: continue` (Safety check).
        - Iterate through `message_bytes` in `messages_to_write`:
          - Get `current_filepath = _get_log_filepath(_current_log_index)`.
          - Check current file size using `uos.stat(current_filepath)` (handle `OSError` for non-existent file, setting `current_size = 0`).
          - Check rotation: `if current_size > 0 and (current_size + len(message_bytes)) > MAX_LOG_FILE_SIZE:`.
            - If rotation needed: increment `_current_log_index`, get new `current_filepath`, print rotation message, `gc.collect()`.
          - Write the `message_bytes` to the (potentially new) `current_filepath` using `with open(..., "ab") as f: f.write(...)`.
          - Include `try...except` around file operations and print errors if they occur.

2.  **Modify `device/main.py`:**
    - Ensure `_log_writer_task` is imported from `device.log`.
    - Start the task using `asyncio.create_task(log._log_writer_task())` within `async def main()`.
