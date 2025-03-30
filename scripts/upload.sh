#!/usr/bin/env bash
# Script to upload files to ESP32 device, handling compilation

# shellcheck source=./common.sh
source "$(dirname "$0")/common.sh" || { echo "Error: Unable to source common.sh" >&2; exit 1; }

USE_AMPY=false
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
        --ampy)
        USE_AMPY=true
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
    echo "Usage: ./upload.sh --ip <address> [--ampy] [--py] <file(s)> [target]" >&2
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

if [ "$USE_AMPY" = true ]; then
    FILE_PATH=$(echo "$FILES" | cut -d',' -f1 | xargs)

    if [ ! -f "$FILE_PATH" ]; then
        echo "Error: File '$FILE_PATH' not found" >&2
        exit 1
    fi

    file_to_upload_ampy="$FILE_PATH"
    base_name=$(basename "$FILE_PATH")

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
        file_to_upload_ampy="$mpy_file"
        GENERATED_MPY_FILES+=("$mpy_file")
    fi

    # Construct the target path for ampy
    target_ampy_base_name=$(basename "$file_to_upload_ampy")
    if [ -n "$TARGET_PATH" ]; then
        # If target path is provided, ensure it ends with / and append filename
        if [[ "$TARGET_PATH" != */ ]]; then
            target_ampy_path="${TARGET_PATH}/$target_ampy_base_name"
        else
            target_ampy_path="${TARGET_PATH}$target_ampy_base_name"
        fi
    else
        # If no target path provided, upload to root with original/compiled filename
        target_ampy_path="/$target_ampy_base_name" # Add leading slash for root
    fi

    echo "Uploading $file_to_upload_ampy to ESP32 using ampy (Port: $AMPY_PORT) as $target_ampy_path..."
    ampy_cmd="ampy -p \"$AMPY_PORT\" put \"$file_to_upload_ampy\" \"$target_ampy_path\""
    echo "Running ampy command: $ampy_cmd"
    eval $ampy_cmd # Use eval to handle potential spaces in paths correctly
    ampy_status=$?
    if [ $ampy_status -ne 0 ]; then
        echo "Error: ampy upload failed for $file_to_upload_ampy." >&2
        exit 1
    fi

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