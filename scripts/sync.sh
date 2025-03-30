#!/bin/bash
# Script to synchronize modified files from ./device directory to ESP32

# Source common functions and variables
# shellcheck source=./common.sh
source "$(dirname "$0")/common.sh" || { echo "Error: Unable to source common.sh" >&amp;2; exit 1; }

# --- Argument Parsing ---
USE_AMPY=false
DRY_RUN=false
FORCE_UPLOAD=false
SKIP_COMPILE_SYNC=false
ESP_IP="" # Must be provided via --ip
declare -a SYNC_ARGS=() # Store non-flag arguments (should be none for sync)

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --ip)
        ESP_IP="$2"
        shift 2
        ;;
        --ampy)
        USE_AMPY=true
        shift
        ;;
        --dry-run)
        DRY_RUN=true
        shift
        ;;
        --force)
        FORCE_UPLOAD=true
        shift
        ;;
        --py|--no-compile)
        SKIP_COMPILE_SYNC=true
        shift
        ;;
        *)    # unknown option or positional argument
        SYNC_ARGS+=("$1") # save it, though sync shouldn't have positional args
        shift
        ;;
    esac
done

# Validate required arguments
if [ -z "$ESP_IP" ]; then
    echo "Error: --ip <address> is required." >&amp;2
    exit 1
fi
if [ ${#SYNC_ARGS[@]} -gt 0 ]; then
    echo "Warning: Unexpected arguments passed to sync: ${SYNC_ARGS[*]}" >&amp;2
fi
# Export ESP_IP for potential use in subshells if needed, though upload.sh takes it as arg
export ESP_IP

# --- Sync Logic (Adapted from original run script) ---

# Ensure the timestamp directory exists (it's SCRIPT_DIR_COMMON now)
if [ ! -d "$SCRIPT_DIR_COMMON" ]; then
  echo "Creating directory: $SCRIPT_DIR_COMMON"
  mkdir -p "$SCRIPT_DIR_COMMON" || {
    echo "Error: Failed to create directory $SCRIPT_DIR_COMMON" >&amp;2
    exit 1
  }
fi

# Create timestamp file if it doesn't exist (needed for find -newer)
if [ ! -f "$TIMESTAMP_FILE" ]; then
  echo "Creating initial timestamp file: $TIMESTAMP_FILE"
  date +%s > "$TIMESTAMP_FILE" || {
    echo "Error: Failed to create timestamp file $TIMESTAMP_FILE" >&amp;2
    exit 1
  }
fi

# Display modes
if [ "$DRY_RUN" == true ]; then
  echo "Dry run mode: showing files that would be processed."
fi
if [ "$FORCE_UPLOAD" == true ]; then
  echo "Force upload mode: processing all files."
fi
if [ "$SKIP_COMPILE_SYNC" == true ]; then
  echo "Skip compile mode enabled (--py): --py flag will be passed to upload script."
else
  echo "Default compile mode enabled: .py files (except main.py, boot.py) will be compiled by upload script."
fi

# Get list of files to process
FILES_TO_PROCESS=()
if [ "$FORCE_UPLOAD" == true ]; then
  echo "Finding all files in $DEVICE_DIR directory..."
  # Find all files, excluding the directory itself and potential hidden files if desired
  while IFS= read -r -d '' file; do
      # Optional: Exclude specific patterns if needed, e.g., hidden files: [[ $(basename "$file") != .* ]] &&
      FILES_TO_PROCESS+=("$file")
  done < <(find "$DEVICE_DIR" -type f -print0)
else
  echo "Finding modified files in $DEVICE_DIR since last sync ($TIMESTAMP_FILE)..."
  # Find files newer than the timestamp file
  while IFS= read -r -d '' file; do
      FILES_TO_PROCESS+=("$file")
  done < <(find "$DEVICE_DIR" -type f -newer "$TIMESTAMP_FILE" -print0)
fi

# Check if any files were found
if [ ${#FILES_TO_PROCESS[@]} -eq 0 ]; then
  echo "No files to sync."
  # Update timestamp even if no files changed, to reflect the check
  if [ "$DRY_RUN" == false ]; then
    date +%s > "$TIMESTAMP_FILE" || echo "Warning: Failed to update timestamp file $TIMESTAMP_FILE" >&amp;2
  fi
  exit 0
fi

echo "Found ${#FILES_TO_PROCESS[@]} files to process."

# --- Process Files ---
if [ "$DRY_RUN" == false ]; then
  echo "Processing files individually via upload script:"

  # Track if we should use AP IP for remaining uploads (determined by first failure)
  CURRENT_ESP_IP="$ESP_IP" # Start with the provided IP
  FORCE_AP_MODE_INTERNAL=false # Track if we switched to AP mode internally

  TOTAL_FILES=${#FILES_TO_PROCESS[@]}
  CURRENT_FILE_NUM=0
  SUCCESSFUL_UPLOADS=0

  for file in "${FILES_TO_PROCESS[@]}"; do
    CURRENT_FILE_NUM=$((CURRENT_FILE_NUM + 1))
    relative_path="${file#$DEVICE_DIR/}" # Get path relative to device/
    target_path="/$relative_path" # Target path on device (usually root + relative path)

    echo "------- Processing file $CURRENT_FILE_NUM of $TOTAL_FILES: $file -------"

    # Build the upload command arguments for upload.sh
    UPLOAD_CMD_ARGS=("--ip" "$CURRENT_ESP_IP") # Pass current IP
    if [ "$USE_AMPY" = true ]; then
      UPLOAD_CMD_ARGS+=("--ampy")
    fi
    if [ "$SKIP_COMPILE_SYNC" = true ]; then # Pass --py if sync was called with --py
      UPLOAD_CMD_ARGS+=("--py")
    fi
    UPLOAD_CMD_ARGS+=("$file") # The source file path
    UPLOAD_CMD_ARGS+=("$target_path") # The target path on device

    # Execute the upload command
    echo "Running: $SCRIPT_DIR_COMMON/upload.sh ${UPLOAD_CMD_ARGS[@]}"
    # Capture output to check for errors
    upload_output=$("$SCRIPT_DIR_COMMON/upload.sh" "${UPLOAD_CMD_ARGS[@]}" 2>&amp;1)
    upload_status=$?
    echo "$upload_output" # Show output from the upload script

    # Check if the upload succeeded
    if [ "$upload_status" -ne 0 ]; then
        echo "Error: Upload of $file failed (Status: $upload_status)." >&amp;2
        # Check if the failure was due to connection and we haven't forced AP mode yet
        # Look for the specific error message from make_request in common.sh
        if [ "$FORCE_AP_MODE_INTERNAL" = false ] &amp;&amp; echo "$upload_output" | grep -q "Connection to .* failed"; then
            echo "Upload failed due to connection, attempting fallback to AP IP ($AP_IP) for this and future uploads..."
            FORCE_AP_MODE_INTERNAL=true
            CURRENT_ESP_IP="$AP_IP" # Switch IP for subsequent calls

            # Rebuild command args with AP IP
            UPLOAD_CMD_ARGS=("--ip" "$CURRENT_ESP_IP") # Use AP_IP now
            if [ "$USE_AMPY" = true ]; then UPLOAD_CMD_ARGS+=("--ampy"); fi
            if [ "$SKIP_COMPILE_SYNC" = true ]; then UPLOAD_CMD_ARGS+=("--py"); fi
            UPLOAD_CMD_ARGS+=("$file")
            UPLOAD_CMD_ARGS+=("$target_path")

            # Retry the upload
            echo "Retrying with: $SCRIPT_DIR_COMMON/upload.sh ${UPLOAD_CMD_ARGS[@]}"
            upload_output=$("$SCRIPT_DIR_COMMON/upload.sh" "${UPLOAD_CMD_ARGS[@]}" 2>&amp;1)
            upload_status=$?
            echo "$upload_output"

            # Check if retry succeeded
            if [ "$upload_status" -ne 0 ]; then
              echo "Error: Upload of $file failed even with AP IP. Sync aborted." >&amp;2
              exit 1 # Abort sync on persistent failure
            else
              echo "Retry successful."
              SUCCESSFUL_UPLOADS=$((SUCCESSFUL_UPLOADS + 1))
            fi
        else
            # Upload failed for a reason other than initial connection, or failed after fallback
            echo "Sync aborted due to upload failure." >&amp;2
            exit 1 # Abort sync
        fi
    else
      # Upload succeeded on the first try (or was already in AP mode)
      SUCCESSFUL_UPLOADS=$((SUCCESSFUL_UPLOADS + 1))
    fi

    # Add a short delay between uploads if not using ampy (ampy is slower anyway)
    if [ "$USE_AMPY" = false ] &amp;&amp; [ $CURRENT_FILE_NUM -lt $TOTAL_FILES ]; then
      echo "Waiting briefly before next file upload..."
      sleep 0.5
    fi
  done

  echo "Sync finished. Successfully processed $SUCCESSFUL_UPLOADS out of $TOTAL_FILES files."

  # Reset the device if any files were successfully uploaded
  if [ $SUCCESSFUL_UPLOADS -gt 0 ]; then
    echo "Resetting device..."
    # Call the main run script (in the project root) to handle reset
    RESET_CMD_ARGS=()
    # Pass the IP that was last successfully used (or AP IP if fallback occurred)
    # Note: The original run script determines --ap flag based on args,
    # so passing --ip might be sufficient if run script is adapted correctly.
    # Alternatively, explicitly pass --ap if fallback occurred.
    if [ "$FORCE_AP_MODE_INTERNAL" = true ]; then
        RESET_CMD_ARGS+=("--ap") # Tell run script to use AP IP
    fi
     if [ "$USE_AMPY" = true ]; then
        RESET_CMD_ARGS+=("--ampy")
    fi
    RESET_CMD_ARGS+=("reset")

    # Construct path to the root run script
    ROOT_RUN_SCRIPT="$PROJECT_ROOT_DIR/run"

    if [ -x "$ROOT_RUN_SCRIPT" ]; then
        echo "Running: $ROOT_RUN_SCRIPT ${RESET_CMD_ARGS[@]}"
        "$ROOT_RUN_SCRIPT" "${RESET_CMD_ARGS[@]}"
    else
        echo "Error: Cannot find or execute root run script at $ROOT_RUN_SCRIPT" >&amp;2
        # Decide if this is a fatal error for sync
    fi
  else
    echo "No files were successfully uploaded, skipping reset."
  fi

else
  # Dry run: Show what the upload command would do based on --py flag
  echo "Would process these files via upload script (dry run):"
  for file in "${FILES_TO_PROCESS[@]}"; do
     base_name=$(basename "$file")
     relative_path="${file#$DEVICE_DIR/}"
     target_path="/$relative_path"
     action="Compile &amp; Upload" # Default action
     source_file="$file"
     target_file_name="$base_name" # Default target name

     if [[ "$file" == *.py ]]; then
        if [ "$SKIP_COMPILE_SYNC" == true ] || [ "$base_name" == "main.py" ] || [ "$base_name" == "boot.py" ]; then
            action="Upload .py" # Action if skipping compile
            target_file_name="$base_name"
        else
            # Default compilation case for .py files
            action="Compile &amp; Upload"
            target_file_name="${base_name%.py}.mpy"
        fi
     else
        # Non-python files are just uploaded
        action="Upload"
        target_file_name="$base_name"
     fi
     # Adjust target name based on compilation status for display
     if [[ "$action" == "Compile & Upload" ]]; then
         target_path="/${relative_path%.py}.mpy"
     fi
     echo "  $action $source_file -> $target_path"
  done
fi

# Update timestamp file only if not a dry run
if [ "$DRY_RUN" == false ]; then
  echo "Updating timestamp file: $TIMESTAMP_FILE"
  date +%s > "$TIMESTAMP_FILE" || {
    echo "Error: Failed to update timestamp file $TIMESTAMP_FILE" >&amp;2
    # Don't exit here, sync might have partially succeeded
  }
  echo "Timestamp updated."
fi

echo "Sync command finished."
exit 0