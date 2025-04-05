#!/usr/bin/env bash
# Script to synchronize modified files from ./device directory to ESP32

# Source common functions and variables
# shellcheck source=./common.sh
source "$(dirname "$0")/common.sh" || { echo "Error: Unable to source common.sh" >&2; exit 1; }

# --- Argument Parsing ---
USE_MPREMOTE=false
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
        --mpremote)
        USE_MPREMOTE=true
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
    echo "Error: --ip <address> is required." >&2
    exit 1
fi
if [ ${#SYNC_ARGS[@]} -gt 0 ]; then
    echo "Warning: Unexpected arguments passed to sync: ${SYNC_ARGS[*]}" >&2
fi
# Export ESP_IP for potential use in subshells if needed, though upload.sh takes it as arg
export ESP_IP

# --- Sync Logic ---

# Ensure the timestamp directory exists
if [ ! -d "$SCRIPT_DIR_COMMON" ]; then
  echo "Creating directory: $SCRIPT_DIR_COMMON"
  mkdir -p "$SCRIPT_DIR_COMMON" || { echo "Error: Failed to create directory $SCRIPT_DIR_COMMON" >&2; exit 1; }
fi

# Create timestamp file if it doesn't exist
if [ ! -f "$TIMESTAMP_FILE" ]; then
  echo "Creating initial timestamp file: $TIMESTAMP_FILE"
  date +%s > "$TIMESTAMP_FILE" || { echo "Error: Failed to create timestamp file $TIMESTAMP_FILE" >&2; exit 1; }
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
  if ! git -C "$PROJECT_ROOT_DIR" rev-parse --is-inside-work-tree > /dev/null 2>&1; then
      echo "Warning: '$DEVICE_DIR' is not in a git repository. Falling back to finding all non-hidden files." >&2
      while IFS= read -r -d '' file; do FILES_TO_PROCESS+=("$file"); done < <(find "$DEVICE_DIR" -name '.*' -prune -o -type f -print0)
  else
      mapfile -t potential_files < <(git -C "$PROJECT_ROOT_DIR" ls-files --cached --others --exclude-standard --full-name "$DEVICE_DIR/")
      for file_rel_repo in "${potential_files[@]}"; do
          file_full_path="$PROJECT_ROOT_DIR/$file_rel_repo"
          if [[ -f "$file_full_path" ]]; then FILES_TO_PROCESS+=("$file_full_path"); fi
      done
  fi
else
  echo "Finding modified files in $DEVICE_DIR (respecting .gitignore) since last sync ($TIMESTAMP_FILE)..."
  if ! git -C "$PROJECT_ROOT_DIR" rev-parse --is-inside-work-tree > /dev/null 2>&1; then
      echo "Warning: '$DEVICE_DIR' is not in a git repository. Falling back to finding all modified files." >&2
      while IFS= read -r -d '' file; do FILES_TO_PROCESS+=("$file"); done < <(find "$DEVICE_DIR" -type f -newer "$TIMESTAMP_FILE" -print0)
  else
      last_sync_time=$(cat "$TIMESTAMP_FILE")
      mapfile -t potential_files < <(git -C "$PROJECT_ROOT_DIR" ls-files --cached --others --exclude-standard --full-name "$DEVICE_DIR/")
      for file_rel_repo in "${potential_files[@]}"; do
          file_full_path="$PROJECT_ROOT_DIR/$file_rel_repo"
          if [[ -f "$file_full_path" ]]; then
              mod_time=$(stat -f %m "$file_full_path" 2>/dev/null)
              if [[ -n "$mod_time" && "$mod_time" -gt "$last_sync_time" ]]; then FILES_TO_PROCESS+=("$file_full_path"); fi
          fi
      done
  fi
fi

# --- Filter out .mpy if corresponding .py is present and compilation is enabled ---
FILTERED_FILES=()
if [ "$SKIP_COMPILE_SYNC" == false ]; then
    declare -A py_files_present # Use associative array as a set for quick lookup
    # First pass: identify all .py files in the list
    for file in "${FILES_TO_PROCESS[@]}"; do
        if [[ "$file" == *.py ]]; then
            py_files_present["$file"]=1
        fi
    done
    # Second pass: build the filtered list
    for file in "${FILES_TO_PROCESS[@]}"; do
        if [[ "$file" == *.mpy ]]; then
            py_file="${file%.mpy}.py"
            if [[ -v py_files_present["$py_file"] ]]; then
                # Corresponding .py file exists in the list, skip this .mpy
                echo "Skipping redundant processing of $file (corresponding .py found)"
                continue
            fi
        fi
        # Keep the file if it's not a redundant .mpy
        FILTERED_FILES+=("$file")
    done
else
    # If skipping compile, keep all files
    FILTERED_FILES=("${FILES_TO_PROCESS[@]}")
fi


# Check if any files remain after filtering
if [ ${#FILTERED_FILES[@]} -eq 0 ]; then
  echo "No files to sync."
  if [ "$DRY_RUN" == false ]; then
    date +%s > "$TIMESTAMP_FILE" || echo "Warning: Failed to update timestamp file $TIMESTAMP_FILE" >&2
  fi
  exit 0
fi

echo "Found ${#FILTERED_FILES[@]} files to process after filtering."

# --- Process Files ---
if [ "$DRY_RUN" == false ]; then
  echo "Calling upload script for batch processing..."

  # Join the array into a comma-separated string
  file_list_str=$(printf "%s," "${FILTERED_FILES[@]}")
  file_list_str=${file_list_str%,} # Remove trailing comma

  # Build the upload command arguments for the single upload.sh call
  UPLOAD_CMD_ARGS=("--ip" "$ESP_IP")
  if [ "$USE_MPREMOTE" = true ]; then
    UPLOAD_CMD_ARGS+=("--mpremote")
  fi
  if [ "$SKIP_COMPILE_SYNC" = true ]; then
    UPLOAD_CMD_ARGS+=("--py")
  fi
  UPLOAD_CMD_ARGS+=("$file_list_str") # Pass the comma-separated list of files

  # Execute the single upload command
  echo "Running: $SCRIPT_DIR_COMMON/upload.sh ${UPLOAD_CMD_ARGS[*]}" # Use [*] for display clarity
  # Execute and capture output/status
  upload_output=$("$SCRIPT_DIR_COMMON/upload.sh" "${UPLOAD_CMD_ARGS[@]}" 2>&1)
  upload_status=$?
  echo "$upload_output" # Show output from the upload script

  # Check if the upload succeeded
  if [ "$upload_status" -ne 0 ]; then
      echo "Error: Upload script failed (Status: $upload_status). Sync aborted." >&2
      # Check for connection error specifically, maybe suggest --ap?
      if echo "$upload_output" | grep -q "Connection to .* failed"; then
          echo "Hint: Upload failed due to connection. Consider using '--ap' flag with the main './run' command if the device is in AP mode." >&2
      fi
      exit 1 # Abort sync
  else
    echo "Sync finished successfully."

    # Reset the device if upload was successful
    echo "Resetting device..."
    RESET_CMD_ARGS=()
    # Check if AP IP was used implicitly by upload.sh (difficult to know here)
    # For now, just pass flags based on sync args. Run script handles IP logic.
    if [ "$USE_MPREMOTE" = true ]; then
        RESET_CMD_ARGS+=("--mpremote")
    fi
    # If the original ESP_IP was the AP_IP, pass --ap
    if [ "$ESP_IP" == "$AP_IP" ]; then
         RESET_CMD_ARGS+=("--ap")
    fi
    RESET_CMD_ARGS+=("reset") # Command must be first for run script parsing

    ROOT_RUN_SCRIPT="$PROJECT_ROOT_DIR/run"
    if [ -x "$ROOT_RUN_SCRIPT" ]; then
        echo "Running: $ROOT_RUN_SCRIPT ${RESET_CMD_ARGS[*]}" # Use [*] for display
        "$ROOT_RUN_SCRIPT" "${RESET_CMD_ARGS[@]}"
    else
        echo "Error: Cannot find or execute root run script at $ROOT_RUN_SCRIPT" >&2
    fi
  fi

else
  # Dry run: Show the single command that would be executed
  echo "Would call upload script with these files (dry run):"
  file_list_str=$(printf "%s," "${FILTERED_FILES[@]}")
  file_list_str=${file_list_str%,} # Remove trailing comma

  UPLOAD_CMD_ARGS_DRYRUN=("--ip" "$ESP_IP")
   if [ "$USE_MPREMOTE" = true ]; then UPLOAD_CMD_ARGS_DRYRUN+=("--mpremote"); fi
   if [ "$SKIP_COMPILE_SYNC" = true ]; then UPLOAD_CMD_ARGS_DRYRUN+=("--py"); fi
   UPLOAD_CMD_ARGS_DRYRUN+=("$file_list_str")

  echo "  Command: $SCRIPT_DIR_COMMON/upload.sh ${UPLOAD_CMD_ARGS_DRYRUN[*]}"
  echo "  Files:"
  for file in "${FILTERED_FILES[@]}"; do
      echo "    - $file"
  done
fi

# Update timestamp file only if not a dry run and upload succeeded
if [ "$DRY_RUN" == false ] && [ "$upload_status" -eq 0 ]; then
  echo "Updating timestamp file: $TIMESTAMP_FILE"
  date +%s > "$TIMESTAMP_FILE" || { echo "Error: Failed to update timestamp file $TIMESTAMP_FILE" >&2; }
  echo "Timestamp updated."
fi

echo "Sync command finished."
exit $upload_status # Exit with the status of the upload script