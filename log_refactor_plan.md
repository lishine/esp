# Plan: Refactor Log Retrieval to Use Raw Byte Chunks

**Goal:** Simplify backend log retrieval logic by reading fixed-size raw byte chunks based on a backward offset, pushing parsing and pagination state management to the client.

**Backend Changes (`log.py`):**

1.  **Define Constant:** Add `LOG_READ_LEN = 1000` (or similar) at the module level.
2.  **Replace `get_recent_logs`:** Remove the existing `get_recent_logs` function.
3.  **Create `read_log_chunk_bytes(offset=0)`:**
    - **Signature:** Takes an integer `offset` (default 0), representing how many bytes back from the end the desired chunk should _end_.
    - **Get File Size:** Use `uos.stat(LOG_FILE)[6]`. Handle `OSError` if the file doesn't exist (return `b'', -1`).
    - **Calculate Positions:**
      - `end_pos = max(0, file_size - offset)`
      - `start_pos = max(0, end_pos - LOG_READ_LEN)`
    - **Handle Edge Case:** If `start_pos >= end_pos` (offset is beyond file start), return `b'', start_pos`.
    - **Calculate Read Length:** `bytes_to_read = end_pos - start_pos`.
    - **Read Bytes:** Open `LOG_FILE` in binary read mode (`"rb"`), `seek(start_pos)`, `read(bytes_to_read)`.
    - **Return:** `tuple(bytes, int)` containing the raw `chunk_bytes` read and the actual `start_pos` used. Return `(b'', -1)` on file read errors.

**Backend Changes (`server.py`):**

1.  **Import:** Update imports from `log` to use `read_log_chunk_bytes`.
2.  **Update `/log` Route:**
    - Call `chunk_bytes, _ = read_log_chunk_bytes(offset=0)`.
    - Return raw bytes: `Response(body=chunk_bytes, headers={"Content-Type": "text/plain; charset=utf-8"})`.
3.  **Update `/api/log/chunk` Route:**
    - Remove `newer_than_timestamp` logic.
    - Get `offset` query parameter (default 0). This `offset` represents how far back from the end the _previous_ chunk ended (or 0 for the initial request).
    - Call `chunk_bytes, start_pos = read_log_chunk_bytes(offset=offset)`.
    - Handle `start_pos == -1` (error).
    - Return raw bytes with the starting position of the _current_ chunk in a header:
      ```python
      headers = {
          "Content-Type": "application/octet-stream",
          "X-Chunk-Start-Offset": str(start_pos)
      }
      return Response(body=chunk_bytes, headers=headers)
      ```

**Frontend Changes (`log_viewer.html` - High Level):**

- **Fetch Logic:**
  - Modify `fetchLogs` to request `/api/log/chunk` using a byte `offset` parameter (initially 0 for newest, subsequent values from header for older).
  - Expect raw bytes in the response (`response.arrayBuffer()`).
  - Read the `X-Chunk-Start-Offset` header from the response. This value indicates the byte position where the received chunk started in the file.
- **Parsing:**
  - Use `TextDecoder('utf-8').decode(arrayBuffer)` to convert received bytes to a string.
  - Split the string into lines (`.split('\n')`).
  - Handle potential partial lines at the beginning/end of the decoded string chunk if necessary.
- **State Management:**
  - Use `nextOffsetToRequest` (byte offset) to track the starting position of the _oldest_ chunk currently displayed. Initialize appropriately after the initial load (likely with the `X-Chunk-Start-Offset` from the first fetch).
  - Remove `newestTimestampMs`.
- **Rendering:**
  - New logs (from interval fetch with `offset=0`) are **prepended**.
  - Older logs (from scroll-down fetch) are **appended**.
- **Loading Older Logs (Scroll Down):**
  - Trigger when scrolling near the **bottom** of the page.
  - Call `fetchLogs` using the current `nextOffsetToRequest` as the `offset` parameter.
  - **Append** the decoded/parsed lines to the `logContainer`.
  - Update `nextOffsetToRequest` with the `X-Chunk-Start-Offset` value received in the response header for this older chunk.
- **Loading Newer Logs (Interval):**
  - Periodically call `fetchLogs` with `offset=0`.
  - Decode bytes, parse lines.
  - Compare fetched lines with the current top lines in `logContainer`.
  - **Prepend** only the lines that are actually new to avoid duplicates.
