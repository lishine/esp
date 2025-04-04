#!/usr/bin/env bash
# Script to synchronize modified files from ./device directory to ESP32

# Source common functions and variables
# shellcheck source=./common.sh
source "$(dirname "$0")/common.sh" || { echo "Error: Unable to source common.sh" >&2; exit 1; } # Fixed >&2

# --- Argument Parsing ---
USE_MPREMOTE=false # Renamed from USE_AMPY
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
        --mpremote) # Renamed from --ampy
        USE_MPREMOTE=true # Renamed from USE_AMPY
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
    echo "Error: --ip <address> is required." >&2 # Fixed >&2
    exit 1
fi
if [ ${#SYNC_ARGS[@]} -gt 0 ]; then
    echo "Warning: Unexpected arguments passed to sync: ${SYNC_ARGS[*]}" >&2 # Fixed >&2
fi
# Export ESP_IP for potential use in subshells if needed, though upload.sh takes it as arg
export ESP_IP

# --- Sync Logic (Adapted from original run script) ---

# Ensure the timestamp directory exists (it's SCRIPT_DIR_COMMON now)
if [ ! -d "$SCRIPT_DIR_COMMON" ]; then
  echo "Creating directory: $SCRIPT_DIR_COMMON"
  mkdir -p "$SCRIPT_DIR_COMMON" || {
    echo "Error: Failed to create directory $SCRIPT_DIR_COMMON" >&2; # Fixed >&2
    exit 1;
  }
fi

# Create timestamp file if it doesn't exist (needed for find -newer)
if [ ! -f "$TIMESTAMP_FILE" ]; then
  echo "Creating initial timestamp file: $TIMESTAMP_FILE"
  date +%s > "$TIMESTAMP_FILE" || {
    echo "Error: Failed to create timestamp file $TIMESTAMP_FILE" >&2; # Fixed >&2
    exit 1;
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
  echo "Finding all files in $DEVICE_DIR (respecting .gitignore)..."
  # Check if DEVICE_DIR is within a git repository
  if ! git -C "$PROJECT_ROOT_DIR" rev-parse --is-inside-work-tree > /dev/null 2>&1; then
      echo "Warning: '$DEVICE_DIR' is not in a git repository. Falling back to finding all non-hidden files." >&2
      # Fallback to find behavior (excluding hidden) if not in a git repo
      while IFS= read -r -d '' file; do
          FILES_TO_PROCESS+=("$file")
      done < <(find "$DEVICE_DIR" -name '.*' -prune -o -type f -print0)
  else
      # Use git ls-files to get all non-ignored files (tracked & untracked) within DEVICE_DIR
      mapfile -t potential_files < <(git -C "$PROJECT_ROOT_DIR" ls-files --cached --others --exclude-standard --full-name "$DEVICE_DIR/")
      for file_rel_repo in "${potential_files[@]}"; do
          # Construct full path from project root
          file_full_path="$PROJECT_ROOT_DIR/$file_rel_repo"
          # Ensure the file actually exists and is a file
          if [[ -f "$file_full_path" ]]; then
              FILES_TO_PROCESS+=("$file_full_path")
          fi
      done
  fi
else
  echo "Finding modified files in $DEVICE_DIR (respecting .gitignore) since last sync ($TIMESTAMP_FILE)..."
  # Check if DEVICE_DIR is within a git repository
  if ! git -C "$PROJECT_ROOT_DIR" rev-parse --is-inside-work-tree > /dev/null 2>&1; then
      echo "Warning: '$DEVICE_DIR' is not in a git repository. Falling back to finding all modified files." >&2
      # Fallback to original find behavior if not in a git repo
      while IFS= read -r -d '' file; do
          FILES_TO_PROCESS+=("$file")
      done < <(find "$DEVICE_DIR" -type f -newer "$TIMESTAMP_FILE" -print0)
  else
      # Use git ls-files to respect .gitignore, then filter by modification time
      last_sync_time=$(cat "$TIMESTAMP_FILE")
      # Get list of non-ignored files (tracked & untracked) within DEVICE_DIR relative to repo root
      # Use mapfile/readarray for safer filename handling
       mapfile -t potential_files < <(git -C "$PROJECT_ROOT_DIR" ls-files --cached --others --exclude-standard --full-name "$DEVICE_DIR/")

      for file_rel_repo in "${potential_files[@]}"; do
          # Construct full path from project root
          file_full_path="$PROJECT_ROOT_DIR/$file_rel_repo"
          # Ensure the file actually exists (git ls-files might list deleted but staged files)
          # And ensure it's a file, not a directory listed somehow
          if [[ -f "$file_full_path" ]]; then
              # Get modification time (macOS compatible)
              # Handle potential errors during stat
              mod_time=$(stat -f %m "$file_full_path" 2>/dev/null)
              if [[ -n "$mod_time" && "$mod_time" -gt "$last_sync_time" ]]; then
                  FILES_TO_PROCESS+=("$file_full_path")
              fi
          fi
      done
  fi
fi

# Check if any files were found
if [ ${#FILES_TO_PROCESS[@]} -eq 0 ]; then
  echo "No files to sync."
  # Update timestamp even if no files changed, to reflect the check
  if [ "$DRY_RUN" == false ]; then
    date +%s > "$TIMESTAMP_FILE" || echo "Warning: Failed to update timestamp file $TIMESTAMP_FILE" >&2 # Fixed >&2
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
    relative_path="${file#$DEVICE_DIR/}" # Get path relative to device/, e.g., "ap.py" or "subdir/foo.py"
    target_dir=$(dirname "/$relative_path") # Get target directory, e.g., "/" or "/subdir"

    # --- Check to skip redundant .mpy upload if .py exists and compilation is on ---
    if [[ "$file" == *.mpy ]] && [ "$SKIP_COMPILE_SYNC" == false ]; then
        py_file="${file%.mpy}.py"
        # Check if the corresponding .py file is also in the list of files to process
        py_file_found=false
        for item in "${FILES_TO_PROCESS[@]}"; do
            if [[ "$item" == "$py_file" ]]; then
                py_file_found=true
                break
            fi
        done

        if [ "$py_file_found" = true ]; then
            echo "Skipping direct processing of $file, corresponding .py file will handle compilation/upload."
            continue # Skip to the next file in FILES_TO_PROCESS
        fi
    fi
    # --- End of redundancy check ---

    echo "------- Processing file $CURRENT_FILE_NUM of $TOTAL_FILES: $file -------"

    # Build the upload command arguments for upload.sh
    UPLOAD_CMD_ARGS=("--ip" "$CURRENT_ESP_IP") # Pass current IP
    if [ "$USE_MPREMOTE" = true ]; then # Renamed from USE_AMPY
      UPLOAD_CMD_ARGS+=("--mpremote") # Renamed from --ampy
    fi
    if [ "$SKIP_COMPILE_SYNC" = true ]; then # Pass --py if sync was called with --py
      UPLOAD_CMD_ARGS+=("--py")
    fi
    UPLOAD_CMD_ARGS+=("$file") # The source file path
    UPLOAD_CMD_ARGS+=("$target_dir") # The target directory on device

    # Execute the upload command
    echo "Running: $SCRIPT_DIR_COMMON/upload.sh ${UPLOAD_CMD_ARGS[@]}"
    # Capture output to check for errors
    upload_output=$("$SCRIPT_DIR_COMMON/upload.sh" "${UPLOAD_CMD_ARGS[@]}" 2>&1) # Fixed 2>&1
    upload_status=$?
    echo "$upload_output" # Show output from the upload script

    # Check if the upload succeeded
    if [ "$upload_status" -ne 0 ]; then
        echo "Error: Upload of $file failed (Status: $upload_status)." >&2 # Fixed >&2
        # Check if the failure was due to connection and we haven't forced AP mode yet
        # Look for the specific error message from make_request in common.sh
        if [ "$FORCE_AP_MODE_INTERNAL" = false ] && echo "$upload_output" | grep -q "Connection to .* failed"; then # Fixed &&
            echo "Upload failed due to connection, attempting fallback to AP IP ($AP_IP) for this and future uploads..."
            FORCE_AP_MODE_INTERNAL=true
            CURRENT_ESP_IP="$AP_IP" # Switch IP for subsequent calls

            # Rebuild command args with AP IP
            UPLOAD_CMD_ARGS=("--ip" "$CURRENT_ESP_IP") # Use AP_IP now
            if [ "$USE_MPREMOTE" = true ]; then UPLOAD_CMD_ARGS+=("--mpremote"); fi # Renamed
            if [ "$SKIP_COMPILE_SYNC" = true ]; then UPLOAD_CMD_ARGS+=("--py"); fi
            UPLOAD_CMD_ARGS+=("$file") # The source file path
            UPLOAD_CMD_ARGS+=("$target_dir") # The target directory on device

            # Retry the upload
            echo "Retrying with: $SCRIPT_DIR_COMMON/upload.sh ${UPLOAD_CMD_ARGS[@]}"
            upload_output=$("$SCRIPT_DIR_COMMON/upload.sh" "${UPLOAD_CMD_ARGS[@]}" 2>&1) # Fixed 2>&1
            upload_status=$?
            echo "$upload_output"

            # Check if retry succeeded
            if [ "$upload_status" -ne 0 ]; then
              echo "Error: Upload of $file failed even with AP IP. Sync aborted." >&2 # Fixed >&2
              exit 1 # Abort sync on persistent failure
            else
              echo "Retry successful."
              SUCCESSFUL_UPLOADS=$((SUCCESSFUL_UPLOADS + 1))
            fi
        else
            # Upload failed for a reason other than initial connection, or failed after fallback
            echo "Sync aborted due to upload failure." >&2 # Fixed >&2
            exit 1 # Abort sync
        fi
    else
      # Upload succeeded on the first try (or was already in AP mode)
      SUCCESSFUL_UPLOADS=$((SUCCESSFUL_UPLOADS + 1))
    fi

    # Add a short delay between uploads if not using ampy (ampy is slower anyway)
    # Add a short delay between uploads if not using mpremote (HTTP uploads)
    if [ "$USE_MPREMOTE" = false ] && [ $CURRENT_FILE_NUM -lt $TOTAL_FILES ]; then # Renamed from USE_AMPY
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
    RESET_CMD_ARGS+=("reset") # Add the command first
     if [ "$USE_MPREMOTE" = true ]; then # Renamed from USE_AMPY
        RESET_CMD_ARGS+=("--mpremote") # Renamed from --ampy
    fi

    # Construct path to the root run script
    ROOT_RUN_SCRIPT="$PROJECT_ROOT_DIR/run"

    if [ -x "$ROOT_RUN_SCRIPT" ]; then
        echo "Running: $ROOT_RUN_SCRIPT ${RESET_CMD_ARGS[@]}"
        "$ROOT_RUN_SCRIPT" "${RESET_CMD_ARGS[@]}"
    else
        echo "Error: Cannot find or execute root run script at $ROOT_RUN_SCRIPT" >&2 # Fixed >&2
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
     relative_path="${file#$DEVICE_DIR/}" # e.g., "ap.py" or "subdir/foo.py"
     target_dir=$(dirname "/$relative_path") # e.g., "/" or "/subdir"
     action="Compile & Upload" # Default action
     source_file="$file"
     target_file_name="$base_name" # Default target name

     if [[ "$file" == *.py ]]; then
        if [ "$SKIP_COMPILE_SYNC" == true ] || [ "$base_name" == "main.py" ] || [ "$base_name" == "boot.py" ]; then
            action="Upload .py" # Action if skipping compile
            target_file_name="$base_name" # Target is .py
        else
            # Default compilation case for .py files
            action="Compile & Upload"
            target_file_name="${base_name%.py}.mpy" # Target is .mpy
        fi
     else
        # Non-python files are just uploaded
        action="Upload"
        target_file_name="$base_name" # Target is original name
     fi

     # Construct the final target path for display, ensuring correct directory handling
     # dirname "/" gives "/", dirname "/foo.py" gives "/"
     # dirname "/subdir/foo.py" gives "/subdir"
     if [[ "$target_dir" == "/" ]]; then
         final_target_path="/$target_file_name"
     else
         final_target_path="$target_dir/$target_file_name"
     fi

     echo "  $action $source_file -> $final_target_path"
  done
fi

# Update timestamp file only if not a dry run
if [ "$DRY_RUN" == false ]; then
  echo "Updating timestamp file: $TIMESTAMP_FILE"
  date +%s > "$TIMESTAMP_FILE" || {
    echo "Error: Failed to update timestamp file $TIMESTAMP_FILE" >&2; # Fixed >&2
    # Don't exit here, sync might have partially succeeded
  }
  echo "Timestamp updated."
fi

echo "Sync command finished."
exit 0