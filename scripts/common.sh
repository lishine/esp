#!/usr/bin/env bash
# Common functions and variables for ESP32 management scripts

# --- Dependency Checks ---

# Check Bash version (need >= 4 for mapfile used in sync.sh)
if (( BASH_VERSINFO[0] < 4 )); then
    echo "Error: Bash version 4 or higher is required (you have $BASH_VERSION)." >&2
    echo "On macOS, run: brew install bash" >&2
    echo "Then ensure the new bash is used (e.g., by starting a new terminal or using '/usr/local/bin/bash script.sh')." >&2
    exit 1
fi

# Check for jq early
check_jq() {
    if ! command -v jq > /dev/null; then
        echo "Error: jq is not installed but required for IP address management and status parsing." >&2
        echo "Please install jq:" >&2
        echo "  macOS: brew install jq" >&2
        echo "  Debian/Ubuntu: sudo apt-get update && sudo apt-get install jq" >&2
        echo "  Other systems: Check your package manager." >&2
        exit 1
    fi
}
check_jq # Run the check immediately

# --- Script Setup ---

SCRIPT_DIR_COMMON="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT_DIR="$(dirname "$SCRIPT_DIR_COMMON")"

IP_JSON_FILE="$SCRIPT_DIR_COMMON/ip.json"
TIMESTAMP_FILE="$SCRIPT_DIR_COMMON/.last_sync"

UPLOAD_CHUNKED_SCRIPT_PATH="$SCRIPT_DIR_COMMON/upload_chunked.sh"
DEVICE_DIR="$PROJECT_ROOT_DIR/device" # Path to the device source files

# Detect AMPY port dynamically (macOS specific)
DETECTED_PORT=$(ls /dev/tty.usbmodem* 2>/dev/null | head -n 1)

if [ -n "$DETECTED_PORT" ]; then
    AMPY_PORT="$DETECTED_PORT"
    echo "Detected AMPY port: $AMPY_PORT" >&2 # Log to stderr
else
    echo "Warning: Could not automatically detect ESP32 serial port (/dev/tty.usbmodem*)." >&2
    echo "         Please ensure the device is connected and drivers are installed." >&2
    echo "         Falling back to default: /dev/tty.usbmodem101" >&2
    AMPY_PORT="/dev/tty.usbmodem101" # Fallback to default if detection fails
fi

# Default AP IP
AP_IP="192.168.4.1"

check_jq() {
    if ! command -v jq > /dev/null; then
        echo "Error: jq is not installed but required." >&2
        echo "Please install jq (e.g., 'brew install jq' or 'sudo apt-get install jq')." >&2
        exit 1
    fi
}

read_ip_from_json() {
    if [ -f "$IP_JSON_FILE" ]; then
        # check_jq is already called at the start
        local ip
        ip=$(jq -r '.ip' "$IP_JSON_FILE" 2>/dev/null)
        if [ -n "$ip" ] && [ "$ip" != "null" ]; then
            echo "$ip"
            return 0
        fi
    fi
    return 1
}

write_ip_to_json() {
    local new_ip="$1"
    local json_content

    if [ -z "$new_ip" ]; then
        echo "Error: No IP address provided to write_ip_to_json." >&2
        return 1
    fi

    # check_jq is already called at the start
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

make_request() {
    local url="$1"
    local method="${2:-GET}"
    local output_file="${3:-}"
    local timeout=10
    local curl_opts="-s -m $timeout" # Original: String concatenation

    if [ -z "$ESP_IP" ]; then
        echo "Error: ESP_IP variable is not set for make_request." >&2
        return 1
    fi

    shift 3 || true # Shift past url, method, output_file
    local headers=()
    local data_options=()

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

    if [ -n "$output_file" ]; then
        curl_opts="$curl_opts -o \"$output_file\"" # Add quotes for safety, though original didn't have them explicitly here
    fi

    if [ "$method" != "GET" ]; then
        curl_opts="$curl_opts -X $method"
    fi

    # Try with the current ESP_IP
    local response
    local full_curl_cmd="curl $curl_opts ${headers[@]} ${data_options[@]} \"$url\""
    echo "Running curl command: $full_curl_cmd" >&2 # Print to stderr to avoid interfering with stdout capture
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


export -f check_jq read_ip_from_json write_ip_to_json check_sync_needed make_request

# Export variables that might be needed by sub-scripts directly
export AMPY_PORT AP_IP IP_JSON_FILE TIMESTAMP_FILE UPLOAD_CHUNKED_SCRIPT_PATH DEVICE_DIR PROJECT_ROOT_DIR