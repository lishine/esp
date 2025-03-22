"""
Example script demonstrating how to use the binary upload API.

This script shows how to upload a file to the ESP32 using the binary upload API.
It uses the requests library to make the HTTP request.

Usage:
    python upload_example.py <file_path> <target_path> [server_url]

Example:
    python upload_example.py local_file.txt remote_file.txt
    python upload_example.py local_file.txt remote_file.txt http://192.168.33.7
"""

import sys
import os
import requests
from requests.exceptions import RequestException, Timeout
import json
from json.decoder import JSONDecodeError
import time


def check_server_status(server_url):
    """Check if the server is reachable"""
    try:
        response = requests.get(f"{server_url}/", timeout=2)
        return response.status_code < 400  # Any non-error response is good
    except RequestException:
        return False


def check_free_space(server_url):
    """Check free space on the server"""
    try:
        response = requests.get(f"{server_url}/free", timeout=5)
        if response.status_code == 200:
            try:
                return response.json()
            except JSONDecodeError:
                print(f"Warning: Invalid JSON response from server: {response.text}")
                return None
        else:
            print(
                f"Warning: Server returned status {response.status_code} when checking free space"
            )
            return None
    except RequestException as e:
        print(f"Warning: Could not check free space: {e}")
        return None


def verify_upload(server_url, target_path):
    """Verify an uploaded file exists and check its size."""
    print(f"Verifying upload of {target_path}...")
    try:
        response = requests.get(f"{server_url}/verify/{target_path}", timeout=5)
        if response.status_code == 200:
            try:
                result = response.json()
                if result.get("success", False):
                    print(
                        f"Verification successful: {result['filename']} ({result['size']} bytes)"
                    )
                    return True
                else:
                    print(
                        f"Verification failed: {result.get('error', 'Unknown error')}"
                    )
                    return False
            except JSONDecodeError:
                print(f"Invalid verification response: {response.text}")
                return False
        else:
            print(f"Verification failed: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except RequestException as e:
        print(f"Error during verification: {e}")
        return False


def upload_file(file_path, target_path, server_url="http://192.168.4.1", max_retries=3):
    """Upload a file to the ESP32 using the binary upload API."""
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} not found")
        return False

    # Get file size
    file_size = os.path.getsize(file_path)
    print(f"Uploading {file_path} ({file_size} bytes) to {target_path}")

    # Check if server is reachable
    print(f"Checking if server at {server_url} is reachable...")
    if not check_server_status(server_url):
        print(f"Error: Server at {server_url} is not reachable")
        return False

    # Check free space first
    print("Checking free space...")
    free_space = check_free_space(server_url)
    if free_space:
        print(f"Free space: {free_space['free_kb']} KB")
        if file_size > free_space["free_kb"] * 1024:
            print(
                f"Error: Not enough space. Need {file_size/1024:.2f} KB, have {free_space['free_kb']} KB"
            )
            return False
    else:
        print("Warning: Could not check free space, continuing anyway")

    # Open file in binary mode
    try:
        with open(file_path, "rb") as f:
            file_data = f.read()
    except IOError as e:
        print(f"Error reading file: {e}")
        return False

    # Set headers
    headers = {
        "Content-Length": str(file_size),
        "X-Filename": target_path,  # Specify the target filename
    }

    # Upload file with retry logic
    retry_count = 0
    success = False

    while retry_count < max_retries and not success:
        if retry_count > 0:
            print(f"Retry attempt {retry_count} of {max_retries}...")
            time.sleep(1)  # Wait before retrying

        # Upload file
        print(f"Uploading to {server_url}/upload...")
        start_time = time.time()
        try:
            # Use the simpler /upload endpoint with X-Filename header
            upload_url = f"{server_url}/upload"
            response = requests.post(
                upload_url,
                data=file_data,
                headers=headers,
                timeout=60,  # Longer timeout for large files
            )

            # Check response
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get("success", False):
                        elapsed = time.time() - start_time
                        speed = file_size / elapsed / 1024 if elapsed > 0 else 0  # KB/s
                        print(
                            f"Upload successful: {result['path']} ({result['size']} bytes)"
                        )
                        print(
                            f"Transfer time: {elapsed:.2f} seconds ({speed:.2f} KB/s)"
                        )
                        success = True
                    else:
                        print(f"Upload failed: {result.get('error', 'Unknown error')}")
                        retry_count += 1
                except JSONDecodeError:
                    print(
                        f"Upload status unclear - server returned non-JSON response: {response.text}"
                    )
                    retry_count += 1
            elif response.status_code == 507:  # Insufficient Storage
                print(f"Upload failed: Not enough space on the device")
                try:
                    error_info = response.json()
                    print(
                        f"Required: {error_info.get('required_kb', 'unknown')} KB, Available: {error_info.get('available_kb', 'unknown')} KB"
                    )
                except:
                    pass
                return False  # Don't retry space issues
            else:
                print(f"Upload failed: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                retry_count += 1
        except Timeout:
            print(
                "Upload timed out - the file may be too large or the connection too slow"
            )
            retry_count += 1
        except RequestException as e:
            print(f"Error during upload: {e}")
            retry_count += 1

    # Verify the upload if successful
    if success:
        verify_upload(server_url, target_path)

    return success


if __name__ == "__main__":
    # Check arguments
    if len(sys.argv) < 3:
        print(
            f"Usage: {sys.argv[0]} <file_path> <target_path> [server_url] [max_retries]"
        )
        sys.exit(1)

    file_path = sys.argv[1]
    target_path = sys.argv[2]
    server_url = sys.argv[3] if len(sys.argv) > 3 else "http://192.168.4.1"
    max_retries = int(sys.argv[4]) if len(sys.argv) > 4 else 3

    # Upload file
    if upload_file(file_path, target_path, server_url, max_retries):
        print("Upload completed successfully")
    else:
        print("Upload failed")
        sys.exit(1)
