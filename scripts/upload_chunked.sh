#!/usr/bin/env bash
# Chunked upload script for ESP32
# Usage: ESP_IP=<device_ip> ./upload_chunked.sh <file_path> [target_path]
# Example: ESP_IP=192.168.4.1 ./upload_chunked.sh large_file.bin /data/large_file.bin

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

if [ $# -lt 1 ]; then
    echo "Usage: $0 <file_path>"
    exit 1
fi

FILE_PATH="$1"
TARGET_PATH="${2:-$(basename "$FILE_PATH")}" # Use $2 if provided, else default to basename of $1
CHUNK_SIZE=10000  # 4000 bytes as specified

if [ ! -f "$FILE_PATH" ]; then
    echo "Error: File $FILE_PATH not found"
    exit 1
fi

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    FILE_SIZE=$(stat -f%z "$FILE_PATH")
else
    # Linux and others
    FILE_SIZE=$(stat -c%s "$FILE_PATH")
fi

CHUNK_COUNT=$(( ($FILE_SIZE + $CHUNK_SIZE - 1) / $CHUNK_SIZE ))

if [ -z "$ESP_IP" ]; then
    echo "Error: ESP_IP environment variable is required"
    echo "Please set ESP_IP environment variable before running this script"
    echo "Example: ESP_IP=192.168.4.1 $0 <file_path>"
    exit 1
fi

UPLOAD_URL="http://$ESP_IP/upload/$TARGET_PATH"

# If file is smaller than CHUNK_SIZE, use regular upload instead of chunked
if [ $FILE_SIZE -le $CHUNK_SIZE ]; then
    echo "File size ($FILE_SIZE bytes) is smaller than chunk size ($CHUNK_SIZE bytes). Using regular upload."
    
    echo "Uploading $FILE_PATH ($FILE_SIZE bytes) to $TARGET_PATH"
    
    # Use the original file directly - no need for temp files
    echo "Using simplified upload for small file"
    RESPONSE=$(make_request "$UPLOAD_URL" "POST" "" "X-Chunk-Index: 0" "X-Total-Chunks: 1" "Content-Type: application/octet-stream" "--data-binary" "@${FILE_PATH}")
    echo "$FILE_PATH"
    echo "$UPLOAD_URL"
    echo "Server response: $RESPONSE"
    
    if [ -z "$RESPONSE" ]; then
        echo "Error uploading file - No response from server"
        exit 1
    elif echo "$RESPONSE" | grep -q "success.*true"; then
        echo "Upload completed successfully"
        exit 0
    else
        echo "Error uploading file"
        exit 1
    fi
fi

echo "Uploading $FILE_PATH ($FILE_SIZE bytes) to $TARGET_PATH in $CHUNK_COUNT chunks"

TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

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
    
    CHUNK_SIZE_ACTUAL=$(stat -f%z "$CHUNK_FILE" 2>/dev/null || stat -c%s "$CHUNK_FILE")
    TOTAL_UPLOADED=$(( $OFFSET + $CHUNK_SIZE_ACTUAL ))
    PERCENT=$(( ($TOTAL_UPLOADED * 100) / $FILE_SIZE ))
    
    echo -n "Uploading chunk $(($CHUNK_INDEX+1))/$CHUNK_COUNT (${CHUNK_SIZE_ACTUAL} bytes): "
    show_progress $PERCENT
    
    RESPONSE=$(make_request "$UPLOAD_URL" "POST" "" "X-Chunk-Index: $CHUNK_INDEX" "X-Total-Chunks: $CHUNK_COUNT" "Content-Type: application/octet-stream" "--data-binary" "@$CHUNK_FILE")
    
    echo -e "\nServer response: $RESPONSE"
    
    if [ -z "$RESPONSE" ]; then
        echo "Error uploading chunk $(($CHUNK_INDEX+1)) - No response from server"
        rm -rf "$TEMP_DIR"
        exit 1
    elif echo "$RESPONSE" | grep -q "success.*true"; then
        echo "Chunk $(($CHUNK_INDEX+1))/$CHUNK_COUNT uploaded successfully"
    else
        echo "Error uploading chunk $(($CHUNK_INDEX+1))"
        rm -rf "$TEMP_DIR"
        exit 1
    fi
    
    # Remove chunk file
    rm "$CHUNK_FILE"
    
    # Increment counter
    CHUNK_INDEX=$(($CHUNK_INDEX + 1))
done

if ! echo "$RESPONSE" | grep -q "chunks"; then
    # If not, and we have multiple chunks, send a completion request
    if [ $CHUNK_COUNT -gt 1 ]; then
        echo "All chunks uploaded. Finalizing..."
        RESPONSE=$(make_request "$UPLOAD_URL" "POST" "" "Content-Length: 0" "Content-Type: application/octet-stream" "X-Is-Complete: true" "X-Total-Chunks: $CHUNK_COUNT")
        
        echo "Server response: $RESPONSE"
        
        if [ -z "$RESPONSE" ]; then
            echo "Error finalizing upload - No response from server"
            rm -rf "$TEMP_DIR"
            exit 1
        elif echo "$RESPONSE" | grep -q "success.*true"; then
            echo "Upload completed successfully"
        else
            echo "Error finalizing upload"
            rm -rf "$TEMP_DIR"
            exit 1
        fi
    fi
else
    echo "Server already combined chunks on last chunk upload"
fi

rm -rf "$TEMP_DIR"
echo "Temporary files cleaned up"
echo "Upload of $FILE_PATH to $TARGET_PATH completed successfully"