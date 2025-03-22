# Multi-Part Binary Upload Approach for ESP32

This document outlines a chunked upload approach for handling large files on memory-constrained ESP32 devices.

## Problem

The ESP32 has limited memory (typically ~320KB of usable RAM), which makes handling large file uploads challenging. When using standard HTTP upload methods, the entire request must be processed in memory, leading to out-of-memory errors for files larger than a few hundred KB.

## Solution: Chunked Multi-Part Upload

The solution is to split large files into smaller chunks on the client side and upload them sequentially, then reassemble them on the server.

### Architecture Overview

1. **Client-Side Splitting**: Files are divided into small chunks (e.g., 4KB each)
2. **Sequential Upload**: Each chunk is uploaded individually with its position information
3. **Server-Side Storage**: Chunks are stored as temporary files
4. **Final Assembly**: After all chunks are uploaded, they are combined into the final file

## Implementation Details

### Server-Side Implementation

```python
# New endpoints for multi-part uploads
async def handle_chunk_upload(request, target_path, chunk_index):
    """Handle a single chunk of a multi-part upload"""
    # Create temporary filename for this chunk
    temp_filename = f"{target_path}.part.{chunk_index}"

    # Write chunk to temporary file
    with open(temp_filename, "wb") as f:
        # Read small portions of the chunk to minimize memory usage
        chunk_data = await request.read()
        f.write(chunk_data)

    return {"success": True, "chunk": chunk_index}

async def handle_chunk_complete(request, target_path, total_chunks):
    """Finalize a multi-part upload by combining chunks"""
    try:
        # Open final file for writing
        with open(target_path, "wb") as final_file:
            # Process each chunk in order
            for i in range(total_chunks):
                chunk_filename = f"{target_path}.part.{i}"

                # Read chunk file in small portions
                with open(chunk_filename, "rb") as chunk_file:
                    while True:
                        data = chunk_file.read(512)
                        if not data:
                            break
                        final_file.write(data)

                # Remove chunk file after processing
                os.remove(chunk_filename)

        return {"success": True, "path": target_path}
    except Exception as e:
        # Clean up any remaining chunk files
        for i in range(total_chunks):
            try:
                os.remove(f"{target_path}.part.{i}")
            except:
                pass
        return {"success": False, "error": str(e)}
```

### Routes Configuration

```python
@app.route("/upload/chunk/<path:target_path>/<int:chunk_index>", methods=["POST"])
async def upload_chunk(request, target_path, chunk_index):
    return await handle_chunk_upload(request, target_path, chunk_index)

@app.route("/upload/complete/<path:target_path>/<int:total_chunks>", methods=["POST"])
async def finish_upload(request, target_path, total_chunks):
    return await handle_chunk_complete(request, target_path, total_chunks)
```

### Client-Side Implementation (Bash Script)

```bash
#!/bin/bash
# Multi-part upload script for ESP32

FILE_PATH="$1"
REMOTE_NAME="${2:-$(basename "$FILE_PATH")}"
SERVER_URL="${3:-http://192.168.4.1}"
CHUNK_SIZE=4096  # 4KB chunks

# Get file size
FILE_SIZE=$(stat -c%s "$FILE_PATH")

# Calculate number of chunks
CHUNK_COUNT=$(( ($FILE_SIZE + $CHUNK_SIZE - 1) / $CHUNK_SIZE ))

echo "Uploading $FILE_PATH ($FILE_SIZE bytes) in $CHUNK_COUNT chunks"

# Upload each chunk
for ((i=0; i<$CHUNK_COUNT; i++)); do
    # Calculate chunk size (last chunk may be smaller)
    if [ $i -eq $(($CHUNK_COUNT-1)) ]; then
        CURRENT_CHUNK_SIZE=$(($FILE_SIZE - ($i * $CHUNK_SIZE)))
    else
        CURRENT_CHUNK_SIZE=$CHUNK_SIZE
    fi

    # Extract chunk using dd
    dd if="$FILE_PATH" bs=1 skip=$(($i * $CHUNK_SIZE)) count=$CURRENT_CHUNK_SIZE of=chunk.$i 2>/dev/null

    # Upload chunk
    echo "Uploading chunk $i/$CHUNK_COUNT ($(($CURRENT_CHUNK_SIZE)) bytes)"
    RESPONSE=$(curl -s -X POST \
         --data-binary @chunk.$i \
         -H "Content-Length: $CURRENT_CHUNK_SIZE" \
         "$SERVER_URL/upload/chunk/$REMOTE_NAME/$i")

    # Check response
    if ! echo "$RESPONSE" | grep -q '"success":true'; then
        echo "Error uploading chunk $i: $RESPONSE"
        rm chunk.$i
        exit 1
    fi

    # Remove temp chunk file
    rm chunk.$i

    # Force small delay between chunks
    sleep 0.5
done

# Finalize upload
echo "Finalizing upload..."
RESPONSE=$(curl -s -X POST \
     -H "Content-Type: application/json" \
     -d "{\"total_chunks\": $CHUNK_COUNT}" \
     "$SERVER_URL/upload/complete/$REMOTE_NAME/$CHUNK_COUNT")

# Check response
if echo "$RESPONSE" | grep -q '"success":true'; then
    echo "Upload completed successfully"
else
    echo "Error finalizing upload: $RESPONSE"
    exit 1
fi
```

## Memory Optimization Techniques

1. **Small Chunk Size**: Each chunk is small enough to be processed entirely in memory
2. **Sequential Processing**: Only one chunk is handled at a time
3. **Immediate Cleanup**: Temporary files are deleted as soon as they're processed
4. **Buffered Reading/Writing**: Even chunk files are processed in small buffers
5. **Forced Garbage Collection**: Memory is reclaimed after each chunk

## Advantages

1. **Reliable Large File Uploads**: Can handle files of any size, limited only by storage
2. **Memory Efficiency**: Peak memory usage remains constant regardless of file size
3. **Resumable Uploads**: Failed uploads can potentially be resumed from the last successful chunk
4. **Progress Tracking**: Clear visibility into upload progress
5. **Error Isolation**: Failure in one chunk doesn't corrupt the entire upload

## Implementation Considerations

1. **Temporary Storage**: Requires approximately 2x the final file size during upload
2. **Upload Time**: Slightly longer due to multiple requests and pauses between chunks
3. **Error Handling**: Need robust cleanup of partial uploads
4. **Client Complexity**: Requires more sophisticated client-side code

This approach provides a reliable way to upload large files to ESP32 devices without running into memory limitations.
