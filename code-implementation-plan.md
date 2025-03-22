# Chunked File Upload Implementation Plan

This document outlines the detailed implementation plan for adding chunked file upload capability to the ESP32 device.

## 1. Server-Side Changes

### 1.1. Add WiFi IP Endpoint to server.py

Add a new route in server.py to retrieve the current WiFi IP address:

```python
# Add a route to get the current WiFi IP address
@app.route("/wifi-ip")
def get_wifi_ip_route(request):
    """Return the current WiFi IP address"""
    from ap import get_ap_ip

    wifi_ip = get_ip()
    ap_ip = get_ap_ip()

    return json.dumps({
        "wifi_ip": wifi_ip,
        "ap_ip": ap_ip,
        "is_connected": is_connected()
    })
```

### 1.2. Modify upload.py

Update the `handle_upload` function in upload.py to handle chunked uploads:

```python
async def handle_upload(request, target_path=None):
    """Handle file uploads, including chunked uploads"""
    try:
        # Check if this is a chunked upload
        chunk_index = request.headers.get("X-Chunk-Index")
        total_chunks = request.headers.get("X-Total-Chunks")
        is_complete = request.headers.get("X-Is-Complete") == "true"

        if chunk_index is not None and total_chunks is not None:
            # Handle chunked upload
            chunk_index = int(chunk_index)
            total_chunks = int(total_chunks)

            # Create directory for temp files if needed
            temp_dir = os.path.dirname(target_path)
            if temp_dir and not os.path.exists(temp_dir):
                os.makedirs(temp_dir)

            # Save this chunk to a temporary file
            temp_path = f"{target_path}.part{chunk_index}"
            with open(temp_path, "wb") as f:
                f.write(request.body)

            log(f"Saved chunk {chunk_index+1}/{total_chunks} ({len(request.body)} bytes) to {temp_path}")

            # If this is the last chunk or we received a completion request, combine chunks
            if chunk_index == total_chunks - 1 or is_complete:
                try:
                    # Combine all chunks
                    with open(target_path, "wb") as final_file:
                        total_size = 0
                        for i in range(total_chunks):
                            part_path = f"{target_path}.part{i}"
                            # Skip if part file doesn't exist
                            if not os.path.exists(part_path):
                                log(f"Warning: Chunk {i+1}/{total_chunks} is missing")
                                continue

                            part_size = os.path.getsize(part_path)
                            total_size += part_size

                            # Read in small chunks to avoid memory issues
                            with open(part_path, "rb") as part_file:
                                bytes_processed = 0
                                while True:
                                    data = part_file.read(512)  # Read in 512-byte blocks
                                    if not data:
                                        break
                                    final_file.write(data)
                                    bytes_processed += len(data)

                                    # Log progress percentage for this chunk
                                    if bytes_processed % 1024 == 0 or bytes_processed == part_size:
                                        percent = (bytes_processed / part_size) * 100
                                        log(f"Combining chunk {i+1}/{total_chunks}: {percent:.1f}% ({bytes_processed}/{part_size} bytes)")

                            # Delete this part file
                            os.remove(part_path)

                    log(f"Successfully combined {total_chunks} chunks into {target_path} (Total: {total_size} bytes)")

                    # Get final file size
                    file_size = os.path.getsize(target_path)

                    return json.dumps({
                        "success": True,
                        "path": target_path,
                        "size": file_size,
                        "chunks": total_chunks
                    }), 200
                except Exception as e:
                    log(f"Error combining chunks: {str(e)}")
                    # Clean up any temporary files
                    for i in range(total_chunks):
                        try:
                            os.remove(f"{target_path}.part{i}")
                        except:
                            pass
                    return json.dumps({"success": False, "error": f"Error combining chunks: {str(e)}"}), 500
            else:
                # Return success for this chunk
                return json.dumps({
                    "success": True,
                    "chunk": chunk_index,
                    "total": total_chunks,
                    "path": temp_path
                }), 200

        # Original upload code for non-chunked uploads
        # Get content type and validate
        content_type = request.headers.get("Content-Type", "").lower()
        log(f"Content-Type: {content_type}")

        if "multipart/form-data" not in content_type:
            return (
                json.dumps({"success": False, "error": "Only form uploads supported"}),
                400,
            )

        # Get target filename from URL path
        if not target_path:
            return (
                json.dumps(
                    {"success": False, "error": "URL path must specify filename"}
                ),
                400,
            )

        log(f"Form upload request for {target_path}")

        # Extract boundary from content type
        boundary = "--" + content_type.split("boundary=")[-1].strip()
        log(f"Boundary: {boundary}")

        # Process multipart data
        content = request.body
        log(f"Request body size: {len(content)} bytes")

        # Debug: Log the first 100 bytes of the body
        log(f"Body start: {content[:100]}")

        # Split by boundary
        parts = content.split(boundary.encode())
        log(f"Found {len(parts)} parts")

        # Process each part
        for i, part in enumerate(parts):
            # Skip empty parts
            if len(part) < 10:
                continue

            # Find header/body separator
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue

            # Extract headers and content
            headers_part = part[:header_end]
            content_part = part[header_end + 4 :]  # Skip header separator

            # Check if this is a file part
            if b'name="file"' in headers_part or b"filename=" in headers_part:
                log(f"Found file part in part {i}")

                # Extract just the file content
                # Find the end of the content (before the next boundary or end of part)
                # The content ends with \r\n-- or just \r\n at the end of the request
                if b"\r\n--" in content_part:
                    clean_content = content_part.split(b"\r\n--")[0]
                else:
                    # If no boundary marker, find the last \r\n
                    last_crlf = content_part.rfind(b"\r\n")
                    if last_crlf > 0:
                        clean_content = content_part[:last_crlf]
                    else:
                        clean_content = content_part

                # Debug: Log the content
                log(f"Clean content size: {len(clean_content)} bytes")
                if len(clean_content) < 100:
                    log(f"Clean content: {clean_content}")

                # Write the file
                with open(target_path, "wb") as f:
                    f.write(clean_content)

                log(f"Saved file: {target_path} ({len(clean_content)} bytes)")
                return (
                    json.dumps(
                        {
                            "success": True,
                            "path": target_path,
                            "size": len(clean_content),
                        }
                    ),
                    200,
                )

        # If we get here, no file part was found
        log("No file part found in the form data")
        return json.dumps({"success": False, "error": "No file found in form"}), 400

    except Exception as e:
        log(f"Upload error: {str(e)}")
        return json.dumps({"success": False, "error": str(e)}), 500
```

## 2. Client-Side Shell Script (upload_chunked.sh)

Create a new shell script `upload_chunked.sh` for uploading files in chunks:

```bash
#!/bin/bash
# Chunked upload script for ESP32
# This script splits files into 4000-byte chunks and uploads them to the ESP32

# Usage: ./upload_chunked.sh <file_path>
# Example: ./upload_chunked.sh large_file.bin

# Function to display progress bar
show_progress() {
    local percent=$1
    local width=40
    local num_chars=$(($width * $percent / 100))
    local progress="["
    for ((i=0; i<$width; i++)); do
        if [ $i -lt $num_chars ]; then
            progress+="#"
        else
            progress+=" "
        fi
    done
    progress+="] $percent%"
    echo -ne "$progress\r"
}

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <file_path>"
    exit 1
fi

FILE_PATH="$1"
TARGET_PATH=$(basename "$FILE_PATH")
CHUNK_SIZE=4000  # 4000 bytes as specified

# Check if file exists
if [ ! -f "$FILE_PATH" ]; then
    echo "Error: File $FILE_PATH not found"
    exit 1
fi

# Get file size (cross-platform)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    FILE_SIZE=$(stat -f%z "$FILE_PATH")
else
    # Linux and others
    FILE_SIZE=$(stat -c%s "$FILE_PATH")
fi

# Calculate number of chunks
CHUNK_COUNT=$(( ($FILE_SIZE + $CHUNK_SIZE - 1) / $CHUNK_SIZE ))

echo "Retrieving ESP32 IP address..."

# Get the ESP32 IP address
ESP_IP=$(curl -s http://192.168.4.1/wifi-ip | grep -o '"ap_ip":"[^"]*' | cut -d'"' -f4)
if [ -z "$ESP_IP" ]; then
    ESP_IP="192.168.4.1"  # Default fallback
    echo "Could not retrieve IP address, using default: $ESP_IP"
else
    echo "Using ESP32 IP address: $ESP_IP"
fi

UPLOAD_URL="http://$ESP_IP/upload/$TARGET_PATH"

echo "Uploading $FILE_PATH ($FILE_SIZE bytes) to $TARGET_PATH in $CHUNK_COUNT chunks"

# Create temp directory for chunks
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Split file into chunks
echo "Splitting file into chunks..."
CHUNK_INDEX=0
while [ $CHUNK_INDEX -lt $CHUNK_COUNT ]; do
    # Calculate offset and bytes to read
    OFFSET=$(($CHUNK_INDEX * $CHUNK_SIZE))
    if [ $(($OFFSET + $CHUNK_SIZE)) -gt $FILE_SIZE ]; then
        BYTES=$(($FILE_SIZE - $OFFSET))
    else
        BYTES=$CHUNK_SIZE
    fi

    # Extract chunk using dd
    CHUNK_FILE="$TEMP_DIR/chunk_$CHUNK_INDEX"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        dd if="$FILE_PATH" bs=$CHUNK_SIZE skip=$CHUNK_INDEX count=1 of="$CHUNK_FILE" 2>/dev/null
    else
        # Linux
        dd if="$FILE_PATH" bs=1 skip=$OFFSET count=$BYTES of="$CHUNK_FILE" 2>/dev/null
    fi

    # Calculate progress percentage
    CHUNK_SIZE_ACTUAL=$(stat -f%z "$CHUNK_FILE" 2>/dev/null || stat -c%s "$CHUNK_FILE")
    TOTAL_UPLOADED=$(( $OFFSET + $CHUNK_SIZE_ACTUAL ))
    PERCENT=$(( ($TOTAL_UPLOADED * 100) / $FILE_SIZE ))

    # Upload this chunk
    echo -n "Uploading chunk $(($CHUNK_INDEX+1))/$CHUNK_COUNT (${CHUNK_SIZE_ACTUAL} bytes): "
    show_progress $PERCENT

    CURL_RESULT=$(curl -s -X POST \
        --data-binary @"$CHUNK_FILE" \
        -H "Content-Type: application/octet-stream" \
        -H "X-Chunk-Index: $CHUNK_INDEX" \
        -H "X-Total-Chunks: $CHUNK_COUNT" \
        "$UPLOAD_URL")

    # Check result
    if echo "$CURL_RESULT" | grep -q '"success":true'; then
        echo -e "\nChunk $(($CHUNK_INDEX+1))/$CHUNK_COUNT uploaded successfully"
    else
        echo -e "\nError uploading chunk $(($CHUNK_INDEX+1)): $CURL_RESULT"
        rm -rf "$TEMP_DIR"
        exit 1
    fi

    # Remove chunk file
    rm "$CHUNK_FILE"

    # Increment counter
    CHUNK_INDEX=$(($CHUNK_INDEX + 1))
done

# Complete the upload
echo "All chunks uploaded. Finalizing..."
CURL_RESULT=$(curl -s -X POST \
    -H "Content-Length: 0" \
    -H "X-Is-Complete: true" \
    -H "X-Total-Chunks: $CHUNK_COUNT" \
    "$UPLOAD_URL")

# Check result
if echo "$CURL_RESULT" | grep -q '"success":true'; then
    echo "Upload completed successfully"
    echo "$CURL_RESULT"
else
    echo "Error finalizing upload: $CURL_RESULT"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Clean up
rm -rf "$TEMP_DIR"
echo "Temporary files cleaned up"
echo "Upload of $FILE_PATH to $TARGET_PATH completed successfully"
```

## Next Steps

1. Switch to Code mode to implement these changes
2. Add the WiFi IP endpoint to server.py
3. Modify upload.py to handle chunked uploads
4. Create and test the upload_chunked.sh script

## Testing Procedure

1. Create a test file larger than 7000 bytes
2. Use the upload_chunked.sh script to upload the file
3. Verify the file was successfully transferred
4. Check the logs on the ESP32 to ensure proper operation
