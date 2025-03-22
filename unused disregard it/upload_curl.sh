#!/bin/bash
# Simple upload script for ESP32

# Usage: ./upload_curl.sh <file_path> [remote_name] [server_url]
# Example: ./upload_curl.sh local_file.txt remote_file.txt http://192.168.33.7

# Check arguments
if [ $# -lt 1 ]; then
    echo "Usage: $0 <file_path> [remote_name] [server_url]"
    exit 1
fi

FILE_PATH="$1"
REMOTE_NAME="${2:-$(basename "$FILE_PATH")}"
SERVER_URL="${3:-http://192.168.4.1}"
UPLOAD_URL="$SERVER_URL/upload/$REMOTE_NAME"

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

echo "Uploading $FILE_PATH ($FILE_SIZE bytes) to $REMOTE_NAME"

# Upload file using form data
echo "Uploading file..."
curl -v -X POST \
     -F "file=@$FILE_PATH" \
     "$UPLOAD_URL"

CURL_STATUS=$?
echo -e "\nUpload completed with status $CURL_STATUS"

# Verify the upload if successful
if [ $CURL_STATUS -eq 0 ]; then
    echo "Verifying upload..."
    VERIFY_RESPONSE=$(curl -s "$SERVER_URL/verify/$REMOTE_NAME")
    if echo "$VERIFY_RESPONSE" | grep -q '"success":true'; then
        echo "Verification successful!"
        echo "$VERIFY_RESPONSE"
    else
        echo "Warning: Verification failed or not supported"
        echo "$VERIFY_RESPONSE"
    fi
fi

exit $CURL_STATUS
