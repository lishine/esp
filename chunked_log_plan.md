# Plan for Chunked Logging Implementation

This plan outlines the steps to modify the logging system to use multiple smaller files (chunks) instead of a single large file.

**1. Configuration (log.py):**
_ `LOG_DIR = "logs"`: Directory to store log files.
_ `LOG_FILE_PREFIX = "log_"`: Prefix for log file names.
_ `LOG_FILE_SUFFIX = ".txt"`: Extension for log files.
_ `MAX_LOG_FILE_SIZE = 3000`: Maximum size (bytes) per log file.
_ `MAX_LOG_FILES = None`: No limit on the number of log files (they will accumulate).
_ State variable(s) needed to track the current log file index (e.g., `_current_log_index`).

**2. `log()` Function (log.py):**
_ **Initialization:** On first call or if state is lost, determine the latest log index using `get_latest_log_index()`.
_ **Ensure Directory:** Use a helper `_ensure_log_dir()` to create `LOG_DIR` if it doesn't exist.
_ **Determine Current Path:** Construct the path to the current log file based on `_current_log_index`.
_ **Check Size:** Get the size of the current log file using `uos.stat()`. Handle `OSError` if the file doesn't exist yet (size is 0).
_ **Rotate if Needed:** If `current_size + len(new_message) > MAX_LOG_FILE_SIZE`:
_ Increment `_current_log_index`.
_ Determine the new file path.
_ _(No deletion logic as MAX_LOG_FILES is None)_
_ Update the current log file path/index state.
_ **Write:** Open the current log file in append mode (`'a'`). Write the timestamped message (ensure `\n`). Close the file. \* **Console Output:** Print the message to the console.

**3. Reading Function (log.py):**
_ `read_log_file_content(file_index)`:
_ Constructs the filename: `f"{LOG_DIR}/{LOG_FILE_PREFIX}{file_index:03d}{LOG_FILE_SUFFIX}"` (using 3 digits for index).
_ Tries to open the file (`'rb'`).
_ Reads and returns the entire content as bytes. \* If `OSError` (e.g., file not found), return `None`.

**4. Helper Functions (log.py):**
_ `get_latest_log_index()`:
_ Ensure `LOG_DIR` exists.
_ List files in `LOG_DIR` using `uos.ilistdir()`.
_ Filter for files matching the pattern (`log_###.txt`).
_ Extract indices, find the maximum.
_ Return the highest index found, or `0` if no log files exist (to start with `log_000.txt`).
_ `_ensure_log_dir()`:
_ Checks if `LOG_DIR` exists using `uos.stat()`. \* If not, creates it using `uos.mkdir()`. Handles potential errors.

**5. API Endpoint `/api/log/chunk` (server.py):**
_ Import `read_log_file_content`, `get_latest_log_index` from `log`.
_ Get optional `file_index` from `request.args`. Convert to `int`.
_ If `file_index` is `None`:
_ `target_index = get_latest_log_index()`
_ If `target_index < 0` (should return 0 if dir exists but no files), handle appropriately (maybe return empty or 404 if truly no logs).
_ Else:
_ `target_index = file_index`
_ Call `content = read_log_file_content(target_index)`.
_ If `content is None`: Return 404 Not Found.
_ Else: Return `Response(body=content, headers={'Content-Type': 'text/plain; charset=utf-8', 'X-Log-File-Index': str(target_index)})`.

**6. API Endpoint `/log/clear` (server.py):**
_ Import `LOG_DIR` from `log`.
_ Check if `LOG_DIR` exists using `uos.stat()`.
_ If it exists:
_ Iterate through `uos.ilistdir(LOG_DIR)`.
_ For each entry, construct the full path (`f"{LOG_DIR}/{entry[0]}"`).
_ Check if it's a file (using `entry[1] == 0x8000`).
_ Attempt `uos.remove(full_path)`. Log errors.
_ _Do not remove the directory itself_, just its contents. Reset internal log index state if possible (e.g., set `_current_log_index` back to 0 in `log.py`, though this might require a global state or class). \* Return success/error message.

**7. API Endpoint `/log/add-test-entries` (server.py):** \* Change the loop range to `200`.

**8. Log Viewer (`log_viewer.html` - JavaScript):**
_ Remove `nextOffsetToRequest`. Add `latestFileIndex = -1`, `currentOldestFileIndex = -1`, `noMoreOlderLogs = false`.
_ `initialLoad`: Fetch `/api/log/chunk`. Store `X-Log-File-Index` in `latestFileIndex` and `currentOldestFileIndex`. Process text, reverse lines, render (prepend).
_ `loadOlderLogs`: If loading or `noMoreOlderLogs` or `currentOldestFileIndex <= 0`, return. Calculate `previousIndex = currentOldestFileIndex - 1`. Fetch `/api/log/chunk?file_index=${previousIndex}`. On 200 OK, get content, process lines, prepend (no reverse). Update `currentOldestFileIndex` from header. On 404, set `noMoreOlderLogs = true`.
_ `loadNewerLogs`: Fetch `/api/log/chunk`. Get `newLatestIndex` from header. If `newLatestIndex > latestFileIndex`: Process text, compare with displayed lines, find _new_ lines, reverse _new_ lines, prepend. Update `latestFileIndex`. \* Update scroll trigger logic.

**Storage Note:** With `MAX_LOG_FILES = None`, logs will accumulate and eventually fill the filesystem. Manual cleanup will be required.
