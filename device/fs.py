import os
from log import log


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
                os.listdir(full_path)
                # It's a directory
                result.append(line_prefix + file + "/")
                # Recursively get files from subdirectory
                subdir_prefix = prefix + ("    " if is_current_last else "│   ")
                subdir_files = get_file_list(full_path, subdir_prefix, is_current_last)
                if subdir_files:
                    result.extend(subdir_files)
            except:
                # Not a directory or can't access, treat as file
                result.append(line_prefix + file)

        # Add root directory indicator if at top level
        if prefix == "":
            result.insert(0, ".")

        return result
    except Exception as e:
        log(f"Error listing files: {e}")
        return ["Error listing files"]


def read_file(filename):
    """Read the contents of a file"""
    try:
        with open(filename, "r") as f:
            return f.read()
    except Exception as e:
        log(f"Error reading file {filename}: {e}")
        return f"Error reading file: {str(e)}"


def write_file(filename, content):
    """Write content to a file"""
    try:
        with open(filename, "w") as f:
            f.write(content)
        return True
    except Exception as e:
        log(f"Error writing to file {filename}: {e}")
        return False


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
