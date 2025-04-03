#!/usr/bin/env bash
# Script to upload files to ESP32 device, handling compilation

# shellcheck source=./common.sh
source "$(dirname "$0")/common.sh" || { echo "Error: Unable to source common.sh" >&2; exit 1; }

USE_MPREMOTE=false # Renamed from USE_AMPY
SKIP_COMPILE=false
ESP_IP=""
FILES=""
TARGET_PATH=""
declare -a REMAINING_ARGS=()

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --ip)
        ESP_IP="$2"
        shift
        shift
        ;;
        --mpremote) # Renamed from --ampy
        USE_MPREMOTE=true # Renamed from USE_AMPY
        shift
        ;;
        --py|--no-compile)
        SKIP_COMPILE=true
        shift
        ;;
        *)
        REMAINING_ARGS+=("$1")
        shift
        ;;
    esac
done

if [ ${#REMAINING_ARGS[@]} -ge 1 ]; then
    FILES="${REMAINING_ARGS[0]}"
fi
if [ ${#REMAINING_ARGS[@]} -ge 2 ]; then
    TARGET_PATH="${REMAINING_ARGS[1]}"
fi

if [ -z "$ESP_IP" ]; then
    echo "Error: --ip <address> is required." >&2
    exit 1
fi
if [ -z "$FILES" ]; then
    echo "Error: Missing file path(s)." >&2
    echo "Usage: ./upload.sh --ip <address> [--mpremote] [--py] <file(s)> [target]" >&2
    exit 1
fi
export ESP_IP

declare -a GENERATED_MPY_FILES=()

# Function to clean up generated MPY files
cleanup_mpy() {
    if [ ${#GENERATED_MPY_FILES[@]} -gt 0 ]; then
        echo "Cleaning up ${#GENERATED_MPY_FILES[@]} locally generated .mpy file(s)..."
        rm -f "${GENERATED_MPY_FILES[@]}"
        echo "Cleanup complete."
    fi
}
trap cleanup_mpy EXIT

if [ "$USE_MPREMOTE" = true ]; then
    # Use mpremote for upload (handles multiple files and directory creation)
    IFS=',' read -r -a FILE_ARRAY <<< "$FILES"
    TOTAL_FILES=${#FILE_ARRAY[@]}

    for ((i=0; i<${#FILE_ARRAY[@]}; i++)); do
        FILE_PATH=$(echo "${FILE_ARRAY[$i]}" | xargs) # Trim whitespace

        if [ ! -f "$FILE_PATH" ]; then
            echo "Error: File '$FILE_PATH' not found" >&2
            exit 1
        fi

        echo "------ Uploading $((i+1)) of $TOTAL_FILES via mpremote --------- ($FILE_PATH)"

        file_to_upload="$FILE_PATH"
        base_name=$(basename "$FILE_PATH")

        # Compile if necessary
        if [[ "$FILE_PATH" == *.py ]] && [ "$SKIP_COMPILE" == false ] && [ "$base_name" != "main.py" ] && [ "$base_name" != "boot.py" ]; then
            mpy_file="${FILE_PATH%.py}.mpy"
            echo "Compiling $FILE_PATH to $mpy_file..."
            # Assuming mpy-cross is in PATH and using default options for simplicity
            # Adjust march/Olevel if needed: mpy-cross -march=... -O...
            mpy_cross_cmd="mpy-cross -s \"$FILE_PATH\" -o \"$mpy_file\" \"$FILE_PATH\""
            echo "Running: $mpy_cross_cmd"
            compile_output=$(eval $mpy_cross_cmd 2>&1)
            compile_status=$?
            if [ $compile_status -ne 0 ]; then
                echo "Error: mpy-cross failed for $FILE_PATH. Output:" >&2
                echo "$compile_output" >&2
                exit 1
            fi
            echo "Compilation successful."
            file_to_upload="$mpy_file"
            GENERATED_MPY_FILES+=("$mpy_file")
        fi

        # Construct the remote path, ensuring it starts with ':'
        final_target_name=$(basename "$file_to_upload")
        if [ -n "$TARGET_PATH" ]; then
            # Ensure target path starts with / and ends with /
            remote_dir=":$TARGET_PATH"
            remote_dir="${remote_dir//:\//:}" # Remove double slash after colon if TARGET_PATH starts with /
            if [[ "$remote_dir" != */ ]]; then
                 remote_dir="${remote_dir}/"
            fi
            remote_file_path="${remote_dir}$final_target_name"
        else
            # Upload to root directory
            remote_file_path=":/$final_target_name"
        fi
        # Clean up potential double slashes or colon-slash issues
        remote_file_path="${remote_file_path//:\/\//:/}"
        remote_file_path="${remote_file_path//\/\//\/}"


        # Ensure the target directory exists using 'mpremote mkdir' (handles nested paths)
        remote_dir_path=$(dirname "$remote_file_path")
        if [[ "$remote_dir_path" != ":" && "$remote_dir_path" != ":/" ]]; then
             echo "Ensuring remote directory exists: $remote_dir_path"
             mpremote_mkdir_cmd="mpremote mkdir \"$remote_dir_path\""
             echo "Running mpremote command: $mpremote_mkdir_cmd"
             eval $mpremote_mkdir_cmd
             mkdir_status=$?
             # Exit if mkdir failed for a real reason (not just 'already exists')
             # We rely on mkdir exiting non-zero for critical errors.
             # A more robust check might involve 'ls' first, but let's try this.
             if [ $mkdir_status -ne 0 ]; then
                 # Attempt ls to see if the failure was because it exists
                 mpremote_ls_cmd="mpremote ls \"$remote_dir_path\" > /dev/null 2>&1"
                 eval $mpremote_ls_cmd
                 ls_status=$?
                 if [ $ls_status -ne 0 ]; then
                    # If ls also fails, then the mkdir failure was likely real
                    echo "Error: mpremote mkdir failed for $remote_dir_path (Status: $mkdir_status) and directory does not seem to exist." >&2
                    exit 1
                 else
                    echo "Warning: mpremote mkdir failed for $remote_dir_path (Status: $mkdir_status), but directory seems to exist. Continuing..." >&2
                 fi
             fi
        fi

        # Copy the file using standard 'mpremote cp'
        echo "Uploading $file_to_upload to ESP32 using mpremote as $remote_file_path..."
        mpremote_cp_cmd="mpremote cp \"$file_to_upload\" \"$remote_file_path\""
        echo "Running mpremote command: $mpremote_cp_cmd"
        eval $mpremote_cp_cmd
        cp_status=$?
        if [ $cp_status -ne 0 ]; then
            echo "Error: mpremote cp failed for $file_to_upload (Status: $cp_status)." >&2
            exit 1
        fi
        echo "Upload successful: $remote_file_path"
    done

else
    IFS=',' read -r -a FILE_ARRAY <<< "$FILES"
    TOTAL_FILES=${#FILE_ARRAY[@]}

    for ((i=0; i<${#FILE_ARRAY[@]}; i++)); do
        FILE_PATH=$(echo "${FILE_ARRAY[$i]}" | xargs)

        if [ ! -f "$FILE_PATH" ]; then
            echo "Error: File '$FILE_PATH' not found" >&2
            exit 1
        fi

        echo "------ Uploading $((i+1)) of $TOTAL_FILES --------- ($FILE_PATH)"

        file_to_upload_http="$FILE_PATH"
        base_name=$(basename "$FILE_PATH")
        target_http_path="$TARGET_PATH"

        if [[ "$FILE_PATH" == *.py ]] && [ "$SKIP_COMPILE" == false ] && [ "$base_name" != "main.py" ] && [ "$base_name" != "boot.py" ]; then
            mpy_file="${FILE_PATH%.py}.mpy"
            echo "Compiling $FILE_PATH to $mpy_file for ESP32-C3..."
            mpy_cross_cmd="mpy-cross -march=rv32imc -O2 -s \"$FILE_PATH\" -o \"$mpy_file\" \"$FILE_PATH\""
            echo "Running: $mpy_cross_cmd"
            compile_output=$(eval $mpy_cross_cmd 2>&1)
            compile_status=$?
            if [ $compile_status -ne 0 ]; then
                echo "Error: mpy-cross failed for $FILE_PATH. Output:" >&2
                echo "$compile_output" >&2
                exit 1
            fi
            echo "Compilation successful."
            file_to_upload_http="$mpy_file"
            GENERATED_MPY_FILES+=("$mpy_file")
        fi

        final_target_name=$(basename "$file_to_upload_http")
        if [ -n "$target_http_path" ]; then
            if [[ "$target_http_path" != */ ]]; then
                 target_http_path="${target_http_path}/"
            fi
            final_target_path_on_device="$target_http_path$final_target_name"
            echo "Uploading $file_to_upload_http to ESP32 at $ESP_IP as $final_target_path_on_device..."
        else
            final_target_path_on_device="/$final_target_name"
            echo "Uploading $file_to_upload_http to ESP32 at $ESP_IP as $final_target_path_on_device..."
        fi

        "$UPLOAD_CHUNKED_SCRIPT_PATH" "$file_to_upload_http" "$final_target_path_on_device"
        upload_result=$?
        if [ "$upload_result" -ne 0 ]; then
            echo "Error: Upload of $file_to_upload_http failed (via $UPLOAD_CHUNKED_SCRIPT_PATH)." >&2
            exit 1
        fi
        echo "Upload successful: $final_target_path_on_device"
    done
fi

echo "Upload command finished successfully."
exit 0