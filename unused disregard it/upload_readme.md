# ESP32 Binary Upload API

This document describes the binary upload API implemented for the ESP32 device.

## Overview

The binary upload API provides a more efficient way to upload files to the ESP32 by using direct binary uploads instead of multipart form data. This approach:

1. Uses less memory on the ESP32
2. Is more reliable for large files
3. Provides better error handling and recovery
4. Includes space checking to prevent failed uploads
5. Implements memory management for large file handling
6. Supports verification of uploaded files

## API Endpoints

### Upload a File

Two endpoints are available for uploading:

```
POST /upload/<target_path>
POST /upload
```

**Headers:**

- `Content-Length`: (Required) Size of the file in bytes
- `X-Filename`: (Optional) Alternative filename to use instead of the path parameter
  - Required when using the `/upload` endpoint without a path parameter

**Request Body:**

- Raw binary data of the file

**Response:**

```json
{
  "success": true,
  "path": "path/to/file.txt",
  "size": 1234
}
```

**Error Response:**

```json
{
  "success": false,
  "error": "Error message"
}
```

### Check Free Space

```
GET /free
```

**Response:**

```json
{
  "free_kb": 1024.5,
  "total_kb": 2048.0,
  "used_kb": 1023.5,
  "usage_percent": 50.0
}
```

### Verify Upload

```
GET /verify/<filename>
```

**Response:**

```json
{
  "success": true,
  "filename": "path/to/file.txt",
  "size": 1234
}
```

**Error Response:**

```json
{
  "success": false,
  "error": "File not found"
}
```

## Example Usage

### Using curl

```bash
# Upload a file (Linux)
curl -X POST \
  --data-binary @local_file.txt \
  -H "Content-Length: $(stat -c%s 'local_file.txt')" \
  -H "X-Filename: remote_file.txt" \
  http://192.168.4.1/upload

# Upload a file (macOS)
curl -X POST \
  --data-binary @local_file.txt \
  -H "Content-Length: $(stat -f%z 'local_file.txt')" \
  -H "X-Filename: remote_file.txt" \
  http://192.168.4.1/upload

# Check free space
curl http://192.168.4.1/free

# Verify an upload
curl http://192.168.4.1/verify/remote_file.txt
```

### Using Python

See the `upload_example.py` script for a complete Python example.

```python
import requests

# Upload a file
with open('local_file.txt', 'rb') as f:
    file_data = f.read()

response = requests.post(
    'http://192.168.4.1/upload',
    data=file_data,
    headers={
        'Content-Length': str(len(file_data)),
        'X-Filename': 'remote_file.txt'
    },
    timeout=30  # Timeout for large files
)

print(response.json())

# Verify the upload
verify_response = requests.get('http://192.168.4.1/verify/remote_file.txt')
print(verify_response.json())
```

### Using the Shell Script

A cross-platform shell script `upload_curl.sh` is provided for convenience:

```bash
# On macOS or Linux
./upload_curl.sh local_file.txt remote_file.txt http://192.168.4.1
```

The script:

- Works on both macOS and Linux
- Automatically detects file size using the appropriate command
- Checks for available space before uploading
- Provides detailed error messages
- Implements retry logic for reliability
- Verifies uploads after completion

## Auto-Opening Settings Popup

When a device connects to the ESP32's access point, the settings page will automatically open with a welcome popup. This helps users quickly configure the device without having to manually navigate to the settings page.

The popup provides:

- A welcome message
- Instructions for configuring Wi-Fi settings
- A button to dismiss the popup

This feature works across different devices and browsers through the captive portal detection mechanism.

## Implementation Details

### Memory Management

The upload handler implements several memory optimization techniques:

- Reduced chunk size (256 bytes) for better memory efficiency
- Explicit garbage collection during uploads
- Memory usage monitoring
- Proper cleanup of resources

### Error Handling

The system includes robust error handling:

- Timeout detection and recovery
- Retry logic for failed uploads
- Proper cleanup of partial files
- Detailed error reporting

### Cross-Platform Support

All tools are designed to work across different platforms:

- Shell scripts work on both macOS and Linux
- Python examples work on any system with Python and requests
- Browser-based uploads work on all modern browsers
