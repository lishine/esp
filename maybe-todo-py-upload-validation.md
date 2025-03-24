# Python File Validation for ESP32 MicroPython

This document outlines approaches for implementing Python file validation in an ESP32 MicroPython environment to prevent code with errors from being uploaded and causing device issues.

## Problem Statement

When uploading Python files with errors to an ESP32 running MicroPython, the device can get into an unrecoverable state if the erroneous file is imported during boot. This happens because:

1. MicroPython attempts to import the file with errors
2. The device halts or crashes due to the errors
3. Without physical access, it becomes difficult to recover the device

## Issues Identified During Implementation

Our attempt to implement Python validation revealed several important challenges:

### 1. Circular Dependency During Chunked Uploads

When uploading large Python files that require chunking, a circular dependency issue occurs:

- The chunked upload process needs to combine chunks and then validate the file
- If the validation code is in the same file being uploaded (like upload.py), it causes a circular dependency
- This results in the error: `'module' object has no attribute 'path'` because:
  - The old version of the file has been partially overwritten
  - The new version isn't fully written yet
  - The system tries to use this broken intermediate state

### 2. Different Types of Python Errors Require Different Detection Methods

Python has different types of errors that must be detected differently:

- **Syntax errors**: Can be caught by compiling the code without executing it
- **Name errors**: Only caught during execution (not during compilation)
- **Runtime errors**: Only caught when the specific code path is executed

### 3. MicroPython vs CPython Differences

MicroPython's error handling differs from standard CPython:

- **Path Handling**: MicroPython might have path functions directly in `os` rather than in `os.path`
- **Compiler Behavior**: MicroPython's `compile()` function might behave differently than CPython's

## Recommended Implementation Approach

Based on our findings, here's a recommended approach for safely implementing Python validation:

### 1. Separate Validation Code from Upload Handling

The validation code should be completely separate from the upload handling code:

- Create a standalone module (e.g., `code_validator.py`) for validation
- Keep upload handling in its own module (e.g., `upload.py`)
- Ensure the validation module doesn't depend on the upload module

### 2. Implement Validation in the Server, Not Upload Handler

Move validation logic to the server layer:

```python
# In server.py
@app.route("/upload/<path:target_path>", methods=["POST"])
async def upload_file(request, target_path):
    # Handle the upload (without validation)
    result, status_code = await handle_upload(request, target_path)

    # If upload successful and it's a Python file, validate it
    if status_code == 200 and target_path.endswith('.py'):
        try:
            from code_validator import validate_python_file
            is_valid, message = validate_python_file(target_path)

            if not is_valid:
                # Delete the invalid file
                try:
                    os.remove(target_path)
                except:
                    pass

                # Return error
                return json.dumps({
                    "success": False,
                    "error": f"Python validation failed: {message}"
                }), 400
        except Exception as e:
            # If validation fails, log but don't prevent upload
            log(f"Error during Python validation: {e}")

    # Return original result
    return result, status_code
```

### 3. Comprehensive Validation Function

Create a validation function that checks for both syntax and runtime errors:

```python
# In code_validator.py
def validate_python_file(file_path):
    """
    Validate a Python file by checking for syntax and runtime errors
    Returns (is_valid, message)
    """
    try:
        # Only validate .py files
        if not file_path.endswith('.py'):
            return True, "Not a Python file"

        log(f"Validating Python file: {file_path}")

        # Read the file
        try:
            with open(file_path, 'r') as f:
                code = f.read()
        except Exception as e:
            return False, f"Error reading file: {e}"

        # Check for empty file
        if not code.strip():
            return False, "File is empty or contains only whitespace"

        # Try to compile the code (syntax check)
        try:
            compiled_code = compile(code, file_path, 'exec')

            # Try to execute the compiled code in a controlled environment
            try:
                # Create a clean namespace to avoid polluting the global namespace
                namespace = {}
                exec(compiled_code, namespace)
                return True, "File is valid"
            except NameError as e:
                return False, f"Name error: {e}"
            except Exception as e:
                return False, f"Runtime error: {e}"
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        except Exception as e:
            return False, f"Compilation error: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"
```

### 4. Special Case for System Files

Add special handling for critical system files:

```python
# Skip validation for critical system files
SYSTEM_FILES = ['upload.py', 'server.py', 'boot.py', 'main.py', 'code_validator.py']
if any(target_path.endswith('/' + file) or target_path == file for file in SYSTEM_FILES):
    log(f"Skipping validation for system file: {target_path}")
    return True, "System file, validation skipped"
```

### 5. Backup and Restore Mechanism

Implement a backup/restore mechanism for critical files:

```python
def backup_file(file_path):
    """Create a backup of a file"""
    backup_path = file_path + ".bak"
    try:
        # Check if file exists
        try:
            os.stat(file_path)
            src = None
            dst = None
            try:
                src = open(file_path, "rb")
                dst = open(backup_path, "wb")
                while True:
                    chunk = src.read(512)
                    if not chunk:
                        break
                    dst.write(chunk)
                return True, backup_path
            finally:
                if src:
                    src.close()
                if dst:
                    dst.close()
        except OSError:
            return False, None
    except Exception as e:
        log(f"Error creating backup: {e}")
        return False, None

def restore_from_backup(file_path):
    """Restore a file from its backup"""
    backup_path = file_path + ".bak"
    try:
        # Check if backup exists
        try:
            os.stat(backup_path)
            # Remove current file
            try:
                os.stat(file_path)
                os.remove(file_path)
            except:
                pass

            # Restore from backup
            src = None
            dst = None
            try:
                src = open(backup_path, "rb")
                dst = open(file_path, "wb")
                while True:
                    chunk = src.read(512)
                    if not chunk:
                        break
                    dst.write(chunk)
                return True, "Restored from backup"
            finally:
                if src:
                    src.close()
                if dst:
                    dst.close()
        except OSError:
            return False, "No backup found"
    except Exception as e:
        return False, f"Error restoring: {e}"
```

## Alternative Implementation: Safe Boot System

As an alternative or complementary approach, implement a safe boot system:

```python
# In boot.py
import sys
import machine
import time
from log import log

# Flag file to indicate boot attempts
BOOT_COUNTER_FILE = 'boot_attempts.txt'
MAX_BOOT_ATTEMPTS = 3

def increment_boot_counter():
    try:
        try:
            with open(BOOT_COUNTER_FILE, 'r') as f:
                count = int(f.read().strip() or '0')
        except:
            count = 0

        count += 1

        with open(BOOT_COUNTER_FILE, 'w') as f:
            f.write(str(count))

        return count
    except:
        return 999  # Assume high count if can't read/write

def reset_boot_counter():
    try:
        with open(BOOT_COUNTER_FILE, 'w') as f:
            f.write('0')
    except:
        pass

# Check boot counter
boot_count = increment_boot_counter()

log(f"ESP32 Device Starting... (Boot attempt: {boot_count}/{MAX_BOOT_ATTEMPTS})")

# If too many boot attempts, enter recovery mode
if boot_count >= MAX_BOOT_ATTEMPTS:
    log("Too many failed boot attempts, entering recovery mode")
    # Reset counter for next boot
    reset_boot_counter()

    # Start minimal recovery system
    try:
        import ap
        ap.start_ap(essid="DDDEV_RECOVERY", password="")

        # Start minimal recovery server
        try:
            # Import only essential modules
            import minimal_server
            minimal_server.start()
        except Exception as e:
            log("Error starting recovery server:", e)
    except Exception as e:
        log("Critical error in recovery mode:", e)

else:
    # Normal boot
    try:
        # Import modules that might fail
        try:
            import ap
            import wifi
            import server

            ap.start_ap(essid="DDDEV", password="")
            wifi.start_wifi()
            server.start_server()

            # Boot successful, reset counter
            reset_boot_counter()

        except Exception as e:
            log("Error during initialization:", e)
            # Counter will remain incremented for next boot
    except Exception as e:
        log("Critical boot error:", e)
```

## Considerations for Implementation

1. **Memory Constraints**: Error checking adds overhead, so be mindful of memory usage
2. **Performance Impact**: Validation, especially execution, can be resource-intensive
3. **Security Implications**: Executing unknown code has security risks
4. **Error Recovery**: Always have a fallback mechanism to recover from errors
5. **System Files**: Be extremely careful when validating system files to avoid bricking the device

## Testing Methodology

Any implementation should be thoroughly tested with:

1. Valid Python files (should pass validation)
2. Files with syntax errors (should fail validation)
3. Files with name errors (should fail validation)
4. Files with runtime errors (should fail validation)
5. Large files requiring chunked uploads
6. Critical system files
7. Edge cases (empty files, non-Python files, etc.)

## Conclusion

Implementing Python validation on an ESP32 requires careful architecture to avoid circular dependencies, especially during chunked uploads. The recommended approach is to:

1. Keep validation code completely separate from upload handling
2. Move validation to the server layer, after upload is complete
3. Skip validation for critical system files
4. Use both compilation and execution to catch different types of errors
5. Consider implementing a safe boot system as a fallback

These strategies should help prevent bad code from causing device failures while maintaining the ability to upload all types of files, including large Python files.
