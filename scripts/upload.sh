#!/usr/bin/env bash
# Script to upload files to ESP32 device, handling compilation
# Implements a two-phase approach: compile all first, then upload all.
# Expects a comma-separated list of files as the last argument.

# shellcheck source=./common.sh
source "$(dirname "$0")/common.sh" || { echo "Error: Unable to source common.sh" >&2; exit 1; }

# --- Argument Parsing ---
USE_MPREMOTE=false
SKIP_COMPILE=false
ESP_IP=""
FILES_STR="" # Comma-separated list of files

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --ip)
        ESP_IP="$2"
        shift 2
        ;;
        --mpremote)
        USE_MPREMOTE=true
        shift
        ;;
        --py|--no-compile)
        SKIP_COMPILE=true
        shift
        ;;
        *) # Assume the last argument is the file list
        if [[ -z "$FILES_STR" ]]; then # Only take the first non-flag argument as the file list
             FILES_STR="$1"
        else
             echo "Warning: Unexpected argument '$1' ignored." >&2
        fi
        shift
        ;;
    esac
done

# Validate required arguments
if [ -z "$ESP_IP" ]; then
    echo "Error: --ip <address> is required." >&2
    exit 1
fi
if [ -z "$FILES_STR" ]; then
    echo "Error: Missing comma-separated file path(s) argument." >&2
    echo "Usage: ./upload.sh --ip <address> [--mpremote] [--py|--no-compile] <file1,file2,...>" >&2
    exit 1
fi
if [ -z "$DEVICE_DIR" ]; then
    echo "Error: DEVICE_DIR variable not set (should be sourced from common.sh)." >&2
    exit 1
fi
export ESP_IP

# --- Initialization ---
declare -a FILE_ARRAY=()           # Array of original file paths
declare -a FILES_TO_COMPILE=()    # Array of original paths needing compilation
declare -a FILES_TO_UPLOAD_MAP=() # Array of maps {local="path", original="path", remote="path"}
declare -a GENERATED_MPY_FILES=() # Array of generated .mpy paths for cleanup
declare -a SUCCESSFUL_UPLOADS=()  # Array of remote paths successfully uploaded
compile_errors=0
upload_errors=0

# --- Cleanup Function ---
cleanup_mpy() {
    if [ ${#GENERATED_MPY_FILES[@]} -gt 0 ]; then
        echo "Cleaning up ${#GENERATED_MPY_FILES[@]} locally generated .mpy file(s)..."
        rm -f "${GENERATED_MPY_FILES[@]}"
        # echo "Cleanup complete." # Reduce verbosity
    fi
}
trap cleanup_mpy EXIT

# --- Phase 0: Preparation and File Validation ---
echo "--- Preparing file list ---"
IFS=',' read -r -a FILE_ARRAY <<< "$FILES_STR"
TOTAL_FILES_TO_PROCESS=${#FILE_ARRAY[@]}
valid_files_count=0

for original_path in "${FILE_ARRAY[@]}"; do
    original_path=$(echo "$original_path" | xargs) # Trim whitespace

    if [ ! -f "$original_path" ]; then
        echo "Error: File not found: '$original_path'. Skipping." >&2
        continue # Skip this file
    fi

    # Calculate relative path from DEVICE_DIR
    relative_path="${original_path#$DEVICE_DIR/}"
    if [[ "$original_path" == "$relative_path" ]]; then # Check if path was outside DEVICE_DIR
         echo "Warning: File '$original_path' seems outside DEVICE_DIR ('$DEVICE_DIR'). Uploading to root '/$relative_path'." >&2
         remote_path="/$(basename "$original_path")" # Default to root if outside
    else
         remote_path="/$relative_path"
    fi

    # Determine if compilation is needed
    base_name=$(basename "$original_path")
    local_path="$original_path" # Default local path is the original
    file_type="other"

    if [[ "$original_path" == *.py ]] && [ "$SKIP_COMPILE" == false ] && [ "$base_name" != "main.py" ] && [ "$base_name" != "boot.py" ]; then
        FILES_TO_COMPILE+=("$original_path")
        file_type="py_compile" # Mark for compilation check
    elif [[ "$original_path" == *.py ]]; then
         file_type="py_skip" # Python file, but skipping compile
    fi

    # Store map for later processing (using bash associative array simulation with delimited string)
    # Format: "local_path|original_path|remote_path|file_type"
    FILES_TO_UPLOAD_MAP+=("$local_path|$original_path|$remote_path|$file_type")
    valid_files_count=$((valid_files_count + 1))
done

if [ $valid_files_count -eq 0 ]; then
    echo "No valid files found to process."
    exit 0
fi
echo "Found $valid_files_count valid files to process."


# --- Phase 1: Compilation ---
if [ ${#FILES_TO_COMPILE[@]} -gt 0 ]; then
    echo "--- Starting Compilation Phase (${#FILES_TO_COMPILE[@]} files) ---"
    # echo "Files identified for compilation:" # Verbose listing
    # printf "  - %s\n" "${FILES_TO_COMPILE[@]}"

    for original_path_to_compile in "${FILES_TO_COMPILE[@]}"; do
        mpy_file="${original_path_to_compile%.py}.mpy"
        echo -n "Compiling: $original_path_to_compile -> $mpy_file ... "

        if [ "$USE_MPREMOTE" = true ]; then
            mpy_cross_cmd="mpy-cross -s \"$original_path_to_compile\" -o \"$mpy_file\" \"$original_path_to_compile\""
        else
            mpy_cross_cmd="mpy-cross -march=rv32imc -O2 -s \"$original_path_to_compile\" -o \"$mpy_file\" \"$original_path_to_compile\""
        fi

        # Run quietly, capture output only on error
        compile_output=$(eval $mpy_cross_cmd 2>&1)
        compile_status=$?

        if [ $compile_status -ne 0 ]; then
            echo "FAILED"
            echo "Error details:" >&2
            echo "$compile_output" >&2
            compile_errors=$((compile_errors + 1))
            # Mark the file as failed in the map
            for i in "${!FILES_TO_UPLOAD_MAP[@]}"; do
                IFS='|' read -r _ orig _ ftype <<< "${FILES_TO_UPLOAD_MAP[$i]}"
                if [[ "$orig" == "$original_path_to_compile" ]]; then
                    FILES_TO_UPLOAD_MAP[$i]="${FILES_TO_UPLOAD_MAP[$i]%|*|*|*|*}|failed_compile" # Append status
                    break
                fi
            done
        else
            echo "OK"
            GENERATED_MPY_FILES+=("$mpy_file")
            # Update the map: change local path to .mpy and type to 'mpy'
             for i in "${!FILES_TO_UPLOAD_MAP[@]}"; do
                IFS='|' read -r _ orig remote ftype <<< "${FILES_TO_UPLOAD_MAP[$i]}"
                if [[ "$orig" == "$original_path_to_compile" ]]; then
                    # Calculate the remote path with .mpy extension
                    remote_mpy_path="${remote%.py}.mpy"
                    # Reconstruct with updated local path, original path, updated remote path, and type
                    FILES_TO_UPLOAD_MAP[$i]="$mpy_file|$orig|$remote_mpy_path|mpy"
                    break
                fi
            done
        fi
    done

    if [ $compile_errors -gt 0 ]; then
        echo "--- Compilation Phase Failed: $compile_errors error(s). Aborting upload. ---" >&2
        exit 1
    else
        echo "--- Compilation Phase Successful ---"
    fi
else
    echo "--- Skipping Compilation Phase (no .py files eligible) ---"
fi


# --- Phase 2: Upload ---
# Prepare final list of files to upload (excluding those that failed compilation)
declare -a FINAL_UPLOAD_LIST=()
for map_entry in "${FILES_TO_UPLOAD_MAP[@]}"; do
     IFS='|' read -r local_path original_path remote_path file_type status <<< "$map_entry"
     # Include if type is mpy (compiled ok), py_skip, other, or py_compile (if compile was skipped globally)
     if [[ "$file_type" == "mpy" || "$file_type" == "py_skip" || "$file_type" == "other" || ("$file_type" == "py_compile" && "$SKIP_COMPILE" == true) ]]; then
        FINAL_UPLOAD_LIST+=("$local_path|$remote_path") # Store as "local|remote"
     fi
done

if [ ${#FINAL_UPLOAD_LIST[@]} -eq 0 ]; then
    echo "No files remaining to upload."
    exit 0
fi

TOTAL_FILES_TO_UPLOAD=${#FINAL_UPLOAD_LIST[@]}
echo "--- Starting Upload Phase (${TOTAL_FILES_TO_UPLOAD} files) ---"
# echo "Files to be uploaded:" # Verbose listing
# for entry in "${FINAL_UPLOAD_LIST[@]}"; do IFS='|' read -r l r <<< "$entry"; printf "  - %s -> %s\n" "$l" "$r"; done


for ((i=0; i<${#FINAL_UPLOAD_LIST[@]}; i++)); do
    IFS='|' read -r local_path remote_path <<< "${FINAL_UPLOAD_LIST[$i]}"
    final_target_name=$(basename "$remote_path") # Get the target filename

    echo -n "Uploading [$((i+1))/$TOTAL_FILES_TO_UPLOAD]: $local_path -> $remote_path ... "

    if [ "$USE_MPREMOTE" = true ]; then
        # --- mpremote Upload Logic ---
        remote_dir_path=$(dirname "$remote_path")
        # Ensure remote path starts with ':' for mpremote
        mpremote_target_path=":$remote_path"
        mpremote_target_path="${mpremote_target_path//:\/\//:/}" # Clean double slashes after colon

        # Ensure directory exists (quietly if possible)
        if [[ "$remote_dir_path" != "/" && "$remote_dir_path" != "." ]]; then
             mpremote_dir=":$remote_dir_path"
             mpremote_dir="${mpremote_dir//:\/\//:/}"
             # Try mkdir, ignore errors for existing dirs, check critical errors after cp
             mpremote mkdir "$mpremote_dir" > /dev/null 2>&1
        fi

        # Copy the file (use -q for quiet if available, otherwise default)
        mpremote_cp_cmd="mpremote cp \"$local_path\" \"$mpremote_target_path\""
        cp_output=$(eval $mpremote_cp_cmd 2>&1)
        cp_status=$?

        if [ $cp_status -ne 0 ]; then
            echo "FAILED"
            echo "Error: mpremote cp failed (Status: $cp_status)." >&2
            echo "Command: $mpremote_cp_cmd" >&2
            echo "Output: $cp_output" >&2
            upload_errors=$((upload_errors + 1))
        else
            echo "OK"
            SUCCESSFUL_UPLOADS+=("$remote_path")
        fi

    else
        # --- HTTP Upload Logic ---
        # Ensure target path starts with /
        if [[ "$remote_path" != /* ]]; then
            remote_path="/$remote_path"
        fi
        # Clean up double slashes
        remote_path="${remote_path//\/\//\/}"

        # Check if UPLOAD_CHUNKED_SCRIPT_PATH is defined
        if [ -z "$UPLOAD_CHUNKED_SCRIPT_PATH" ] || [ ! -x "$UPLOAD_CHUNKED_SCRIPT_PATH" ]; then
             echo "FAILED"
             echo "Error: UPLOAD_CHUNKED_SCRIPT_PATH ('$UPLOAD_CHUNKED_SCRIPT_PATH') is not defined or not executable." >&2
             upload_errors=$((upload_errors + 1))
             continue # Skip to next file
        fi

        # Run upload script, capture output only on error? Or always show summary?
        # Let's keep the chunked script's output minimal by default if possible
        upload_chunked_output=$("$UPLOAD_CHUNKED_SCRIPT_PATH" "$local_path" "$remote_path" 2>&1)
        upload_result=$?

        if [ "$upload_result" -ne 0 ]; then
            echo "FAILED"
            echo "Error: Upload failed (via $UPLOAD_CHUNKED_SCRIPT_PATH)." >&2
            echo "Output: $upload_chunked_output" >&2
            upload_errors=$((upload_errors + 1))
        else
            # Extract confirmation from chunked script output if needed, or just assume OK
            echo "OK" # Assume OK if exit code is 0
            SUCCESSFUL_UPLOADS+=("$remote_path")
        fi
    fi
done

# --- Final Status ---
if [ $upload_errors -gt 0 ]; then
    echo "--- Upload Phase Completed with $upload_errors error(s). ---" >&2
    if [ ${#SUCCESSFUL_UPLOADS[@]} -gt 0 ]; then
         echo "Successfully uploaded files:"
         printf "  - %s\n" "${SUCCESSFUL_UPLOADS[@]}"
    fi
    exit 1
else
    echo "--- Upload Phase Successful ---"
    # echo "Successfully uploaded files:" # Can be uncommented for more verbosity
    # printf "  - %s\n" "${SUCCESSFUL_UPLOADS[@]}"
    exit 0
fi