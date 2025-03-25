import os
import time
from log import log


def format_size(size):
    """Format file size in human-readable format"""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f}K"
    else:
        return f"{size/(1024*1024):.1f}M"


def get_file_details(path="."):
    """Get detailed file listing with sizes and dates"""
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


def get_hierarchical_list_with_sizes(path=".", prefix="", is_last=True):
    """
    Get a recursive list of files in tree format with sizes
    """
    try:
        result = []
        files = os.listdir(path)
        files.sort()
        count = len(files)

        # Find the longest filename for proper alignment
        max_name_length = 0
        for file in files:
            name_len = len(file)
            if (os.stat(path + "/" + file if path != "." else file)[0] & 0x4000) != 0:
                name_len += 1  # Add 1 for the trailing slash
            if name_len > max_name_length:
                max_name_length = name_len

        # Add a bit of padding
        max_name_length += 2

        for i, file in enumerate(files):
            full_path = path + "/" + file if path != "." else file
            is_current_last = i == count - 1

            # Current line prefix
            line_prefix = prefix + ("└── " if is_current_last else "├── ")

            try:
                # Get file stats
                stat = os.stat(full_path)
                # Size in bytes
                size = stat[6]
                # Check if it's a directory
                is_dir = (stat[0] & 0x4000) != 0

                if is_dir:
                    # It's a directory
                    display_name = f"{file}/"
                    padding = " " * (max_name_length - len(display_name))
                    result.append(f"{line_prefix}{display_name}{padding}<DIR>")
                    # Recursively get files from subdirectory
                    subdir_prefix = prefix + ("    " if is_current_last else "│   ")
                    subdir_files = get_hierarchical_list_with_sizes(
                        full_path, subdir_prefix, is_current_last
                    )
                    if subdir_files:
                        result.extend(subdir_files)
                else:
                    # It's a file
                    padding = " " * (max_name_length - len(file))
                    result.append(
                        f"{line_prefix}{file}{padding}{format_size(size):>10}"
                    )
            except Exception as e:
                # Error accessing file/directory
                padding = " " * (max_name_length - len(file))
                result.append(f"{line_prefix}{file}{padding}{'ERROR':>10} ({str(e)})")

        # Add root directory indicator if at top level
        if prefix == "":
            result.insert(0, ".")

        return result
    except Exception as e:
        log(f"Error listing files: {e}")
        return ["Error listing files"]


def get_file_list(path=".", prefix="", is_last=True):
    """
    Get a recursive list of files in tree format with vertical lines
    """
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
    """Check if a file or directory exists"""
    try:
        os.stat(path)
        return True
    except:
        return False


def is_dir(path):
    """Check if a path is a directory"""
    try:
        return (os.stat(path)[0] & 0x4000) != 0
    except:
        return False


def remove_if_empty_or_file(path):
    """
    Remove a path if it's a file or an empty directory.
    Returns True if successfully removed, False otherwise.
    """
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
    """
    Remove empty parent directories recursively.
    """
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
    """
    Get a recursive list of files in JSON format
    Returns a list of dictionaries with file information
    """
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
