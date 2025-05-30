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

# Check for mpremote
check_mpremote() {
    if ! command -v mpremote > /dev/null; then
        echo "Error: mpremote is not installed or not in PATH." >&2
        echo "Please install mpremote:" >&2
        echo "  pip install mpremote" >&2
        exit 1
    fi
}
check_mpremote # Run the check immediately

# --- Script Setup ---

SCRIPT_DIR_COMMON="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT_DIR="$(dirname "$SCRIPT_DIR_COMMON")"

IP_JSON_FILE="$SCRIPT_DIR_COMMON/ip.json"
TIMESTAMP_FILE="$SCRIPT_DIR_COMMON/.last_sync"

UPLOAD_CHUNKED_SCRIPT_PATH="$SCRIPT_DIR_COMMON/upload_chunked.sh"
DEVICE_DIR="device" # Path to the device source files, relative to project root

# AMPY_PORT logic removed, mpremote handles port detection automatically.

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
    local timeout=1000
    # Use an array for curl options for better handling of spaces/special chars
    local curl_opts_array=("-s" "-m" "$timeout") # -s: silent, -m: max time

    # Add -k for HTTPS URLs to allow self-signed certificates
    if [[ "$url" == https://* ]]; then
        curl_opts_array+=("-k")
    fi

    if [ -z "$ESP_IP" ]; then
        echo "Error: ESP_IP variable is not set for make_request." >&2
        return 1
    fi

    shift 3 || true # Shift past url, method, output_file
    local headers=()
    local data_options=()

    # Parse remaining arguments for headers or data options
    while [ $# -gt 0 ]; do
        if [[ "$1" == "--data-binary" ]]; then
            if [ -z "$2" ]; then echo "Error: --data-binary requires an argument." >&2; return 1; fi
            data_options+=("$1" "$2")
            shift 2
        elif [[ "$1" == *":"* ]]; then
             headers+=("-H" "$1")
             shift
        else
            # Assume other args are data options
            data_options+=("$1")
            shift
        fi
    done

    # Add -o option if output file is specified
    if [ -n "$output_file" ]; then
        curl_opts_array+=("-o" "$output_file")
    fi

    # Add -X option if method is not GET
    if [ "$method" != "GET" ]; then
        curl_opts_array+=("-X" "$method")
    fi

    # Construct the full command array for robust execution
    local full_curl_cmd_array=("curl" "${curl_opts_array[@]}" "${headers[@]}" "${data_options[@]}" "$url")

    # Print the command for debugging (to stderr)
    # Use printf for safer expansion than echo
    printf "Running curl command: %s\n" "${full_curl_cmd_array[*]}" >&2

    # Execute the command.
    # If -o is present, output goes to file. Otherwise, it goes to stdout.
    "${full_curl_cmd_array[@]}"
    local status=$? # Capture exit status immediately

    # Check if curl command failed
    if [ $status -ne 0 ]; then
        # Curl might print its own errors to stderr depending on the error type.
        # Add a generic failure message to stderr as well.
        echo "Connection to $ESP_IP failed or curl command failed (status: $status)." >&2
        # Optionally remove partial output file if one was specified and curl failed
        # This prevents leaving incomplete files around.
        if [ -n "$output_file" ] && [ -f "$output_file" ]; then
            # Check if file exists before trying to remove, avoid error if -o failed early
             rm -f "$output_file"
        fi
    fi

    # Return the actual curl exit status (0 for success, non-zero for failure)
    return $status
}


export -f check_jq check_mpremote read_ip_from_json write_ip_to_json check_sync_needed make_request

# Export variables that might be needed by sub-scripts directly
export AP_IP IP_JSON_FILE TIMESTAMP_FILE UPLOAD_CHUNKED_SCRIPT_PATH DEVICE_DIR PROJECT_ROOT_DIR