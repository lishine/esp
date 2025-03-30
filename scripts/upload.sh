#!/bin/bash
# Script to upload files to ESP32 device, handling compilation

# Source common functions and variables
# shellcheck source=./common.sh
source "$(dirname "$0")/common.sh" || { echo "Error: Unable to source common.sh" >&2; exit 1; } # Fixed >&2

# --- Argument Parsing ---
USE_AMPY=false
SKIP_COMPILE=false
ESP_IP="" # Must be provided via --ip
FILES=""
TARGET_PATH=""
declare -a REMAINING_ARGS=() # Store non-flag arguments

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --ip)
        ESP_IP="$2"
        shift # past argument
        shift # past value
        ;;
        --ampy)
        USE_AMPY=true
        shift # past argument
        ;;
        --py|--no-compile)
        SKIP_COMPILE=true
        shift # past argument
        ;;
        *)    # unknown option or positional argument
        REMAINING_ARGS+=("$1") # save it in an array for later
        shift # past argument
        ;;
    esac
done

# Assign positional arguments
if [ ${#REMAINING_ARGS[@]} -ge 1 ]; then
    FILES="${REMAINING_ARGS[0]}"
fi
if [ ${#REMAINING_ARGS[@]} -ge 2 ]; then
    TARGET_PATH="${REMAINING_ARGS[1]}"
fi

# Validate required arguments
if [ -z "$ESP_IP" ]; then
    echo "Error: --ip <address> is required." >&2 # Fixed >&2
    exit 1
fi
if [ -z "$FILES" ]; then
    echo "Error: Missing file path(s)." >&2 # Fixed >&2
    echo "Usage: ./upload.sh --ip <address> [--ampy] [--py] <file(s)> [target]" >&2 # Fixed >&2
    exit 1
fi
# Export ESP_IP so make_request (called by upload_chunked) can see it
export ESP_IP

# --- Upload Logic (Adapted from original run script) ---

# Track generated .mpy files for cleanup
declare -a GENERATED_MPY_FILES=()

# Function to clean up generated MPY files
cleanup_mpy() {
    if [ ${#GENERATED_MPY_FILES[@]} -gt 0 ]; then
        echo "Cleaning up ${#GENERATED_MPY_FILES[@]} locally generated .mpy file(s)..."
        rm -f "${GENERATED_MPY_FILES[@]}"
        echo "Cleanup complete."
    fi
}
# Ensure cleanup happens on exit
trap cleanup_mpy EXIT

if [ "$USE_AMPY" = true ]; then
    # Using ampy for upload
    # ampy doesn't support comma-separated files or compilation easily, handle first file only
    FILE_PATH=$(echo "$FILES" | cut -d',' -f1 | xargs)  # Get first file and trim whitespace

    if [ ! -f "$FILE_PATH" ]; then
        echo "Error: File '$FILE_PATH' not found" >&2 # Fixed >&2
        exit 1
    fi

    file_to_upload_ampy="$FILE_PATH"
    base_name=$(basename "$FILE_PATH")

    # Compile by default unless --py is used or it's main.py/boot.py
    if [[ "$FILE_PATH" == *.py ]] && [ "$SKIP_COMPILE" == false ] && [ "$base_name" != "main.py" ] && [ "$base_name" != "boot.py" ]; then # Fixed &&
        mpy_file="${FILE_PATH%.py}.mpy"
        echo "Compiling $FILE_PATH to $mpy_file for ESP32-C3..."
        # Use mpy-cross command (ensure it's in PATH)
        # Note: Adjust -march if needed for different ESP32 variants
        mpy_cross_cmd="mpy-cross -march=rv32imc -O2 -s \"$FILE_PATH\" -o \"$mpy_file\" \"$FILE_PATH\""
        echo "Running: $mpy_cross_cmd"
        compile_output=$(eval $mpy_cross_cmd 2>&1) # Fixed 2>&1
        compile_status=$?
        if [ $compile_status -ne 0 ]; then
            echo "Error: mpy-cross failed for $FILE_PATH. Output:" >&2 # Fixed >&2
            echo "$compile_output" >&2 # Fixed >&2
            exit 1
        fi
        echo "Compilation successful."
        file_to_upload_ampy="$mpy_file"
        GENERATED_MPY_FILES+=("$mpy_file") # Add to cleanup list
    fi

    target_ampy_path="$TARGET_PATH"
    # If target path is a directory, append the (potentially .mpy) filename
    if [[ -n "$target_ampy_path" ]] && [[ "$target_ampy_path" == */ ]]; then # Fixed &&
        target_ampy_path="$target_ampy_path$(basename "$file_to_upload_ampy")"
    elif [[ -z "$target_ampy_path" ]]; then
        target_ampy_path="$(basename "$file_to_upload_ampy")" # Default target is filename in root
    fi

    echo "Uploading $file_to_upload_ampy to ESP32 using ampy (Port: $AMPY_PORT) as $target_ampy_path..."
    ampy -p "$AMPY_PORT" put "$file_to_upload_ampy" "$target_ampy_path"
    ampy_status=$?
    if [ $ampy_status -ne 0 ]; then
        echo "Error: ampy upload failed for $file_to_upload_ampy." >&2 # Fixed >&2
        exit 1 # Exit with error status
    fi

else
    # Using HTTP API for upload (via upload_chunked.sh)
    # Convert comma-separated files into array
    IFS=',' read -r -a FILE_ARRAY <<< "$FILES"
    TOTAL_FILES=${#FILE_ARRAY[@]}

    for ((i=0; i<${#FILE_ARRAY[@]}; i++)); do
        FILE_PATH=$(echo "${FILE_ARRAY[$i]}" | xargs)  # Trim whitespace

        if [ ! -f "$FILE_PATH" ]; then
            echo "Error: File '$FILE_PATH' not found" >&2 # Fixed >&2
            exit 1 # Exit immediately if a file is missing
        fi

        # Print separator with current file number
        echo "------ Uploading $((i+1)) of $TOTAL_FILES --------- ($FILE_PATH)"

        file_to_upload_http="$FILE_PATH"
        base_name=$(basename "$FILE_PATH")
        target_http_path="$TARGET_PATH" # Base target path

        # Compile by default unless --py is used or it's main.py/boot.py
        if [[ "$FILE_PATH" == *.py ]] && [ "$SKIP_COMPILE" == false ] && [ "$base_name" != "main.py" ] && [ "$base_name" != "boot.py" ]; then # Fixed &&
            mpy_file="${FILE_PATH%.py}.mpy"
            echo "Compiling $FILE_PATH to $mpy_file for ESP32-C3..."
            # Note: Adjust -march if needed for different ESP32 variants
            mpy_cross_cmd="mpy-cross -march=rv32imc -O2 -s \"$FILE_PATH\" -o \"$mpy_file\" \"$FILE_PATH\""
            echo "Running: $mpy_cross_cmd"
            compile_output=$(eval $mpy_cross_cmd 2>&1) # Fixed 2>&1
            compile_status=$?
            if [ $compile_status -ne 0 ]; then
                echo "Error: mpy-cross failed for $FILE_PATH. Output:" >&2 # Fixed >&2
                echo "$compile_output" >&2 # Fixed >&2
                exit 1 # Exit on compilation failure
            fi
            echo "Compilation successful."
            file_to_upload_http="$mpy_file"
            GENERATED_MPY_FILES+=("$mpy_file") # Add to cleanup list
        fi

        # Determine the final target path on the device
        final_target_name=$(basename "$file_to_upload_http")
        if [ -n "$target_http_path" ]; then
            # If target path is specified, ensure it ends with / if it's meant to be a directory
            if [[ "$target_http_path" != */ ]]; then
                 target_http_path="${target_http_path}/"
            fi
            final_target_path_on_device="$target_http_path$final_target_name"
            echo "Uploading $file_to_upload_http to ESP32 at $ESP_IP as $final_target_path_on_device..."
        else
            # If no target path, upload to root with (potentially .mpy) filename
            final_target_path_on_device="/$final_target_name" # Prepend / for root
            echo "Uploading $file_to_upload_http to ESP32 at $ESP_IP as $final_target_path_on_device..."
        fi

        # Call the upload_chunked script (expects ESP_IP to be exported from common.sh or set here)
        "$UPLOAD_CHUNKED_SCRIPT_PATH" "$file_to_upload_http" "$final_target_path_on_device"
        upload_result=$?
        if [ "$upload_result" -ne 0 ]; then
            echo "Error: Upload of $file_to_upload_http failed (via $UPLOAD_CHUNKED_SCRIPT_PATH)." >&2 # Fixed >&2
            exit 1 # Exit on upload failure
        fi
        echo "Upload successful: $final_target_path_on_device"
    done
fi

# Cleanup is handled by the trap EXIT
echo "Upload command finished successfully."
exit 0 # Explicitly exit with success status