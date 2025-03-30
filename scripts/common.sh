#!/bin/bash
# Common functions and variables for ESP32 management scripts

# Get the directory where this common script resides
SCRIPT_DIR_COMMON="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Get the root project directory (one level up from scripts)
PROJECT_ROOT_DIR="$(dirname "$SCRIPT_DIR_COMMON")"

# Configuration Files (relative to this script's directory)
IP_JSON_FILE="$SCRIPT_DIR_COMMON/ip.json"
TIMESTAMP_FILE="$SCRIPT_DIR_COMMON/.last_sync"

# Paths (relative to this script's directory or project root)
UPLOAD_CHUNKED_SCRIPT_PATH="$SCRIPT_DIR_COMMON/upload_chunked.sh"
DEVICE_DIR="$PROJECT_ROOT_DIR/device" # Path to the device source files

# Default AMPY port for serial communication
AMPY_PORT="/dev/tty.usbmodem101"

# Default AP IP
AP_IP="192.168.4.1"

# Function to check if jq is available
check_jq() {
    if ! command -v jq > /dev/null; then
        echo "Error: jq is not installed but required." >&2
        echo "Please install jq (e.g., 'brew install jq' or 'sudo apt-get install jq')." >&2
        exit 1
    fi
}

# Function to read IP from JSON file
# Usage: read_ip_from_json
# Returns: IP address on stdout, exit code 0 on success, 1 on failure
read_ip_from_json() {
    if [ -f "$IP_JSON_FILE" ]; then
        check_jq
        local ip
        ip=$(jq -r '.ip' "$IP_JSON_FILE" 2>/dev/null)
        if [ -n "$ip" ] && [ "$ip" != "null" ]; then
            echo "$ip"
            return 0
        fi
    fi
    return 1
}

# Function to write IP to JSON file
# Usage: write_ip_to_json <new_ip>
write_ip_to_json() {
    local new_ip="$1"
    local json_content

    if [ -z "$new_ip" ]; then
        echo "Error: No IP address provided to write_ip_to_json." >&2
        return 1
    fi

    check_jq
    if [ -f "$IP_JSON_FILE" ]; then
        # Read existing JSON and update only the IP field while preserving other values
        json_content=$(jq --arg ip "$new_ip" '. + {ip: $ip}' "$IP_JSON_FILE")
    else
        # Create new JSON
        json_content="{\"ip\": \"$new_ip\"}"
    fi
    # Use printf for better portability and error handling
    printf "%s\n" "$json_content" > "$IP_JSON_FILE"
    return $? # Return the status of the printf command
}

# Function to check if sync is needed
# Usage: check_sync_needed
# Returns: Exit code 0 if sync is needed, 1 otherwise. Prints message to stdout.
check_sync_needed() {
    # If timestamp file doesn't exist, sync is needed
    if [ ! -f "$TIMESTAMP_FILE" ]; then
        echo "*** Sync required (no timestamp file) ***"
        return 0
    fi

    # Check if any files in device/ directory are newer than timestamp file
    # Use -print -quit for efficiency
    if find "$DEVICE_DIR" -type f -newer "$TIMESTAMP_FILE" -print -quit | grep -q .; then
        echo "*** Sync required (files modified) ***"
        return 0
    fi

    return 1
}

# Helper function to make a curl request with timeout (Identical to original run script)
# Usage: make_request <url> [method] [output_file] [curl_options...]
# Expects ESP_IP to be set in the calling script's environment
# Returns: Response body on stdout, exit code 0 on success, 1 on failure.
make_request() {
    local url="$1"
    local method="${2:-GET}"
    local output_file="${3:-}"
    local timeout=10
    local curl_opts="-s -m $timeout" # Original: String concatenation

    # Check if ESP_IP is set
    if [ -z "$ESP_IP" ]; then
        echo "Error: ESP_IP variable is not set for make_request." >&2
        return 1
    fi

    # Process additional headers and options passed as arguments
    shift 3 || true # Shift past url, method, output_file
    local headers=() # Original: Array
    local data_options=() # Original: Array

    # Original loop logic
    while [ $# -gt 0 ]; do
        if [[ "$1" == "--data-binary" ]]; then
            if [ -z "$2" ]; then echo "Error: --data-binary requires an argument." >&2; return 1; fi
            data_options+=("$1" "$2") # Added to array
            shift 2
        elif [[ "$1" == *":"* ]]; then
             headers+=("-H" "$1") # Added to array
             shift
        else
            # Handle other options (assumed to be data options in original)
            data_options+=("$1") # Added to array
            shift
        fi
    done

    # Original string concatenation for -o and -X
    if [ -n "$output_file" ]; then
        curl_opts="$curl_opts -o \"$output_file\"" # Add quotes for safety, though original didn't have them explicitly here
    fi

    if [ "$method" != "GET" ]; then
        curl_opts="$curl_opts -X $method"
    fi

    # Try with the current ESP_IP
    local response
    # Original curl execution: mixed string and arrays, stderr discarded
    # Need to use eval if curl_opts contains quoted arguments like -o "filename"
    # However, the original didn't use eval. Let's stick to that for strict identity.
    # If filenames have spaces, the original might have failed.
    # Using the exact original call structure:
    response=$(curl $curl_opts "${headers[@]}" "${data_options[@]}" "$url" 2>/dev/null)
    local status=$?

    if [ $status -eq 0 ]; then
        echo "$response"
        return 0
    else
        # If curl failed (e.g., timeout, connection refused)
        echo "Connection to $ESP_IP failed (curl status: $status)." >&2
        return 1
    fi
}


# Export functions so they can be used by scripts sourcing this file
# and potentially by subshells (like in the original sync command)
export -f check_jq read_ip_from_json write_ip_to_json check_sync_needed make_request

# Export variables that might be needed by sub-scripts directly
export AMPY_PORT AP_IP IP_JSON_FILE TIMESTAMP_FILE UPLOAD_CHUNKED_SCRIPT_PATH DEVICE_DIR PROJECT_ROOT_DIR