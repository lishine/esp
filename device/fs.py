import os
import time
from log import log


def format_size(size):
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f}K"
    else:
        return f"{size/(1024*1024):.1f}M"


def get_file_details(path="."):
    try:
        result = []
        files = os.listdir(path)
        files.sort()

        for file in files:
            full_path = path + "/" + file if path != "." else file
            try:
                # Get file stats
                stat = os.stat(full_path)
                # Size in bytes
                size = stat[6]
                # Modification time (if available)
                try:
                    mtime = time.localtime(stat[8])
                    date_str = f"{mtime[0]}-{mtime[1]:02d}-{mtime[2]:02d} {mtime[3]:02d}:{mtime[4]:02d}"
                except:
                    date_str = "N/A"

                # Check if it's a directory
                is_dir = (stat[0] & 0x4000) != 0

                # Format the line
                if is_dir:
                    result.append(f"d {date_str}  {'<DIR>':>10}  {file}/")
                else:
                    result.append(f"- {date_str}  {format_size(size):>10}  {file}")
            except Exception as e:
                result.append(f"? {'ERROR':>19}  {file} ({str(e)})")

        return result
    except Exception as e:
        log(f"Error getting file details: {e}")
        return [f"Error listing files: {str(e)}"]


def get_hierarchical_list_with_sizes(path=".", prefix="", _initial_files=None):
    """
    # Define current_dir_name early to avoid unbound error in final except block
    # Use string splitting for basename, as uos may not have os.path.basename
    """
    current_dir_name = path.split("/")[-1] if "/" in path else path
    try:
        result = []
        files_to_process = []
        is_truncated_list = False
        # current_dir_name = os.path.basename(path) if path != "." else "." # Moved up

        if _initial_files is not None:
            # Using a pre-defined list (potentially truncated with None marker)
            files_to_process = _initial_files
            is_truncated_list = True
        else:
            # List the directory if no initial list provided
            try:
                files_to_process = os.listdir(path)
                files_to_process.sort()
            except OSError as e:
                log(f"Error listing directory '{path}': {e}")
                # Return error indication that can be appended by the caller
                return [f"{prefix}└── Error listing contents: {e}"]

        count = len(files_to_process)

        # Calculate max_name_length based on files_to_process (excluding None)
        max_name_length = 0
        for item in files_to_process:
            if item is None:
                continue  # Skip ellipsis marker
            name_len = len(item)
            item_full_path = path + "/" + item if path != "." else item
            try:
                # Check if item is a directory to add trailing slash length
                if (os.stat(item_full_path)[0] & 0x4000) != 0:
                    name_len += 1
            except OSError:
                pass  # Ignore stat errors for length calculation
            if name_len > max_name_length:
                max_name_length = name_len
        max_name_length += 2  # Add padding

        # --- Loop through the provided or listed files ---
        for i, file in enumerate(files_to_process):
            is_current_last = i == count - 1
            line_prefix = prefix + ("└── " if is_current_last else "├── ")

            # Handle ellipsis marker (if present from truncation)
            if file is None:
                ellipsis_padding = " " * (max_name_length - 3)  # Padding for "..."
                result.append(f"{line_prefix}{'...'}{ellipsis_padding}")
                continue

            # Process regular file/dir name
            full_path = path + "/" + file if path != "." else file

            try:
                stat = os.stat(full_path)
                size = stat[6]
                is_dir = (stat[0] & 0x4000) != 0

                if is_dir:
                    # --- Process Directory ---
                    display_name = f"{file}/"
                    padding = " " * (max_name_length - len(display_name))
                    result.append(f"{line_prefix}{display_name}{padding}<DIR>")

                    # --- Recursive Call Logic (with potential truncation for 'logs') ---
                    subdir_prefix = prefix + (
                        "    " if is_current_last else "│   "
                    )  # Use current item's last status for connector
                    subdir_items_to_pass = (
                        None  # Default to no truncation / normal listing
                    )

                    # Check if this subdir is 'logs' and needs truncation
                    if file == "logs":
                        try:
                            subdir_items_list = os.listdir(full_path)
                            if len(subdir_items_list) > 10:
                                subdir_items_list.sort()
                                # Create truncated list with None marker for ellipsis
                                subdir_items_to_pass = (
                                    subdir_items_list[:3]
                                    + [None]
                                    + subdir_items_list[-3:]
                                )
                            # else: No truncation needed, subdir_items_to_pass remains None
                        except OSError as e:
                            # Error listing logs dir, append error message and skip recursion for it
                            result.append(f"{subdir_prefix}└── Error listing logs: {e}")
                            continue  # Skip recursion for this directory

                    # Make the recursive call
                    # Pass is_current_last to the next level (determines its line prefix)
                    # Pass subdir_items_to_pass (truncated list or None)
                    subdir_files_result = get_hierarchical_list_with_sizes(
                        full_path,
                        subdir_prefix,
                        _initial_files=subdir_items_to_pass,
                    )
                    if subdir_files_result:
                        result.extend(subdir_files_result)
                    # --- End Recursive Call Logic ---

                else:
                    # --- Process File ---
                    padding = " " * (max_name_length - len(file))
                    result.append(
                        f"{line_prefix}{file}{padding}{format_size(size):>10}"
                    )
            except OSError as e:  # Error stating the item 'file'
                # Error accessing file/directory during loop
                padding = " " * (max_name_length - len(file))
                result.append(f"{line_prefix}{file}{padding}{'ERROR':>10} ({str(e)})")

        # Add root directory indicator only if at top level AND not processing a predefined list
        if prefix == "" and path == "." and not is_truncated_list:
            result.insert(0, ".")

        return result
    except Exception as e:  # Catch-all for unexpected errors in the function
        log(f"General error in get_hierarchical_list_with_sizes for path '{path}': {e}")
        # Return a more specific error message for the level, including the exception
        return [f"{prefix}└── Error processing directory '{current_dir_name}': {e}"]


def get_file_list(path=".", prefix="", is_last=True):
    try:
        result = []
        files = os.listdir(path)
        files.sort()
        count = len(files)

        for i, file in enumerate(files):
            full_path = path + "/" + file if path != "." else file
            is_current_last = i == count - 1

            # Current line prefix
            line_prefix = prefix + ("└── " if is_current_last else "├── ")

            try:
                # Check if it's a directory (try to list it)
                is_dir = False
                try:
                    os.listdir(full_path)
                    is_dir = True
                except:
                    pass

                if is_dir:
                    # It's a directory
                    result.append(f"{line_prefix}{file}/")
                    # Recursively get files from subdirectory
                    subdir_prefix = prefix + ("    " if is_current_last else "│   ")
                    subdir_files = get_file_list(
                        full_path, subdir_prefix, is_current_last
                    )
                    if subdir_files:
                        result.extend(subdir_files)
                else:
                    # It's a file
                    result.append(f"{line_prefix}{file}")
            except Exception as e:
                # Error accessing file/directory
                result.append(f"{line_prefix}{file} (ERROR: {str(e)})")

        return result
    except Exception as e:
        log(f"Error listing files: {e}")
        return ["Error listing files"]


def exists(path):
    try:
        os.stat(path)
        return True
    except:
        return False


def is_dir(path):
    try:
        return (os.stat(path)[0] & 0x4000) != 0
    except:
        return False


def remove_if_empty_or_file(path):
    try:
        if not exists(path):
            return False

        if is_dir(path):
            # Only remove directory if it's empty
            if len(os.listdir(path)) == 0:
                os.rmdir(path)
                return True
            return False
        else:
            # It's a file, remove it
            os.remove(path)
            return True
    except Exception as e:
        log(f"Error removing {path}: {e}")
        return False


def remove_empty_parents(path):
    try:
        if "/" not in path:
            return True

        parent_dir = "/".join(path.split("/")[:-1])
        if not parent_dir:
            return True

        # Check if parent directory exists and is empty
        if (
            exists(parent_dir)
            and is_dir(parent_dir)
            and len(os.listdir(parent_dir)) == 0
        ):
            os.rmdir(parent_dir)
            # Recursively check grandparent directories
            return remove_empty_parents(parent_dir)

        return True
    except Exception as e:
        log(f"Error removing parent directories for {path}: {e}")
        return False


def get_hierarchical_json(path=".", include_dirs=True):
    log("get_hierarchical_json")
    try:
        result = []
        files = os.listdir(path)
        files.sort()

        for file in files:
            full_path = path + "/" + file if path != "." else file
            try:
                # Get file stats
                stat = os.stat(full_path)
                # Size in bytes
                size = stat[6]
                # Check if it's a directory
                is_dir = (stat[0] & 0x4000) != 0

                # Create file entry
                entry = {
                    "name": file,
                    "path": full_path,
                    "is_dir": is_dir,
                    "size": size,
                    "size_formatted": format_size(size) if not is_dir else "<DIR>",
                }

                # Add children for directories
                if is_dir:
                    if include_dirs:
                        entry["children"] = get_hierarchical_json(
                            full_path, include_dirs
                        )
                        result.append(entry)
                else:
                    # It's a file
                    result.append(entry)

            except Exception as e:
                # Error accessing file/directory
                result.append({"name": file, "path": full_path, "error": str(e)})

        return result
    except Exception as e:
        log(f"Error creating JSON file list: {e}")
        return []
