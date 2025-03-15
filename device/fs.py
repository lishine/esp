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
    """Read the contents of a file
    Args:
        filename: Path to the file
    """
    try:
        with open(filename, "r") as f:
            return f.read()
    except Exception as e:
        log(f"Error reading file {filename}: {e}")
        return f"Error reading file: {str(e)}"


def write_file(filename, content):
    """Write content to a file"""
    try:
        # Create directories if needed
        if "/" in filename:
            dir_path = "/".join(filename.split("/")[:-1])
            if dir_path and not create_dirs(dir_path):
                return False

        if isinstance(content, str):
            content = content.encode("utf-8")
        f = None
        try:
            f = open(filename, "wb")
            f.write(content)
        except Exception as e:
            log(f"Error writing to file {filename}: {e}")
            return False
        finally:
            getattr(f, "close", lambda: None)()
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


def create_dirs(path):
    """Create directories recursively"""
    try:
        parts = path.split("/")
        current_path = ""

        for part in parts:
            if not part:
                continue
            current_path = current_path + "/" + part if current_path else part
            if not exists(current_path):
                os.mkdir(current_path)
        return True
    except Exception as e:
        log(f"Error creating directories: {e}")
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
