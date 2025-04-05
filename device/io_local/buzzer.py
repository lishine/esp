import json
import gc
import os
from machine import Pin
import uasyncio as asyncio
from log import log
import time

# Use absolute imports from device root (since device/ maps to /)
from server_framework import (
    Response,
    Request,
    HTTP_OK,
    HTTP_BAD_REQUEST,
    HTTP_NOT_FOUND,
    HTTP_INTERNAL_ERROR,
    success_response,
    error_response,
    HTTPServer,
)
from fs import exists


# --- Configuration ---
BUZZER_PIN = 1

# --- State ---
buzzer_pin_obj = None  # Changed from buzzer_pwm
_beep_task = None


# --- Initialization ---
def init_buzzer():
    """Initializes the buzzer pin as a simple output."""
    global buzzer_pin_obj
    try:
        # Initialize the pin as output
        buzzer_pin_obj = Pin(BUZZER_PIN, Pin.OUT)
        buzzer_pin_obj.value(0)  # Ensure it's off initially
        log(f"Active Buzzer initialized on Pin {BUZZER_PIN}")
        return True
    except Exception as e:
        log(f"Error initializing Active Buzzer on Pin {BUZZER_PIN}: {e}")
        buzzer_pin_obj = None
        return False


# --- Control Functions ---


def set_buzzer(state):
    """
    Sets the active buzzer state immediately.

    Args:
        state (bool): True (or 1) to turn on, False (or 0) to turn off.
    """
    if buzzer_pin_obj is None:
        log("Buzzer not initialized.")
        return

    try:
        value = 1 if state else 0
        buzzer_pin_obj.value(value)
        # log(f"Buzzer {'ON' if value else 'OFF'}")
    except Exception as e:
        log(f"Error setting buzzer state: {e}")


async def beep_async(duration_ms=100):
    """Plays a short beep asynchronously (active buzzer)."""
    if buzzer_pin_obj is None:
        log("Buzzer not initialized.")
        return
    try:
        set_buzzer(True)
        await asyncio.sleep_ms(duration_ms)
        set_buzzer(False)
    except Exception as e:
        log(f"Error during async beep: {e}")
    finally:
        # Ensure buzzer is off even if task is cancelled
        set_buzzer(False)


def beep_sync(duration_ms=100):
    """Plays a short beep synchronously (active buzzer, blocks)."""
    if buzzer_pin_obj is None:
        log("Buzzer not initialized.")
        return
    try:
        set_buzzer(True)
        time.sleep_ms(duration_ms)
        set_buzzer(False)
    except Exception as e:
        log(f"Error during sync beep: {e}")
    finally:
        set_buzzer(False)


async def play_sequence_async(sequence):
    """
    Plays a sequence of beeps/silences asynchronously (active buzzer).
    Sequence is a list of tuples: [(duration_ms1, state1), (duration_ms2, state2), ...]
    Where state is True/1 for ON, False/0 for OFF.
    """
    global _beep_task
    if buzzer_pin_obj is None:
        log("Buzzer not initialized.")
        return

    # Cancel any ongoing sequence
    if _beep_task:
        try:
            _beep_task.cancel()
        except asyncio.CancelledError:
            pass
        _beep_task = None

    async def _player():
        try:
            for duration_ms, state in sequence:
                set_buzzer(state)  # Set ON or OFF
                await asyncio.sleep_ms(duration_ms)
            set_buzzer(False)  # Ensure off at the end
        except asyncio.CancelledError:
            set_buzzer(False)  # Ensure off if cancelled
            # log("Buzzer sequence cancelled.")
        except Exception as e:
            log(f"Error playing buzzer sequence: {e}")
            set_buzzer(False)  # Ensure off on error
        finally:
            _beep_task = None  # Clear task reference when done

    _beep_task = asyncio.create_task(_player())


def stop_beep():
    """Stops any currently playing beep or sequence."""
    global _beep_task
    if _beep_task:
        try:
            _beep_task.cancel()  # type: ignore # Pylance might complain about Task type
        except asyncio.CancelledError:
            pass
        _beep_task = None
    set_buzzer(False)  # Ensure it's off


# --- HTTP Route Registration ---


def register_buzzer_routes(app: HTTPServer):
    """Registers the buzzer HTML and API routes using decorators."""
    log("Registering buzzer routes...")

    @app.route("/buzzer", methods=["GET"])
    def serve_buzzer_page(request: Request):
        """Serves the buzzer control HTML page."""
        # Correct path for the device's root filesystem
        html_file = "/io_local/buzzer.html"
        # We need 'exists' here. Ensure it's imported or passed if necessary.
        # For now, assume 'exists' is available in this scope via http_server.
        # If not, the check needs adjustment or removal.
        # Let's try importing it directly here as well for robustness.

        if not exists(html_file):
            log(f"Error: Buzzer HTML file not found at {html_file}")
            body, status = error_response(
                "Buzzer control page not found.", HTTP_NOT_FOUND
            )
            return Response(
                body=body, status=status, headers={"Content-Type": "application/json"}
            )

        try:
            with open(html_file, "r") as f:
                content = f.read()
            gc.collect()
            return Response(
                body=content,
                status=HTTP_OK,
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        except Exception as e:
            log(f"Error reading {html_file}: {e}")
            body, status = error_response(
                f"Server error reading buzzer page: {str(e)}", HTTP_INTERNAL_ERROR
            )
            return Response(
                body=body, status=status, headers={"Content-Type": "application/json"}
            )

    @app.route("/api/buzzer", methods=["POST"])
    def handle_buzzer_api(request: Request):  # Changed from async def to def
        """Handles API commands for the buzzer."""
        try:
            # Check if body is bytes and decode if necessary
            if isinstance(request.body, bytes):
                try:
                    body_str = request.body.decode("utf-8")
                except UnicodeDecodeError:
                    body, status = error_response(
                        "Invalid UTF-8 data in request body", HTTP_BAD_REQUEST
                    )
                    return Response(
                        body=body,
                        status=status,
                        headers={"Content-Type": "application/json"},
                    )
            elif isinstance(request.body, str):
                body_str = request.body
            elif request.body is None:
                body_str = "{}"  # Default to empty JSON object if body is None
            else:
                log(f"Warning: Unexpected request body type: {type(request.body)}")
                body_str = str(request.body)  # Attempt conversion

            data = json.loads(body_str)  # Use ujson's loads
            command = data.get("command")

            log(f"Buzzer API command: {command}, Data: {data}")

            if command == "set":
                state = data.get("state", False)
                set_buzzer(bool(state))
                body, status = success_response({"message": f"Buzzer set to {state}"})

            elif command == "beep":
                duration = data.get("duration_ms", 100)
                try:
                    duration_int = int(duration)
                    if duration_int <= 0:
                        raise ValueError("Duration must be positive")
                    # Don't block the server, run beep asynchronously
                    asyncio.create_task(beep_async(duration_int))
                    body, status = success_response(
                        {"message": f"Beep async ({duration_int}ms) started"}
                    )
                except ValueError as e:
                    body, status = error_response(
                        f"Invalid duration_ms value: {e}", HTTP_BAD_REQUEST
                    )

            elif command == "sequence":
                sequence_str = data.get("data", "")
                sequence_list = []
                try:
                    parts = sequence_str.split(",")
                    for part in parts:
                        part = part.strip()
                        if not part:
                            continue
                        duration_str, state_str = part.split(":")
                        duration_ms = int(duration_str.strip())
                        state_val = int(state_str.strip())
                        if state_val not in [0, 1]:
                            raise ValueError("State must be 0 or 1")
                        if duration_ms <= 0:
                            raise ValueError("Duration must be positive")
                        state = bool(state_val)
                        sequence_list.append((duration_ms, state))

                    if not sequence_list:
                        raise ValueError("Empty sequence data")

                    # Don't block the server, run sequence asynchronously
                    asyncio.create_task(play_sequence_async(sequence_list))
                    body, status = success_response(
                        {"message": "Sequence async started"}
                    )
                except Exception as e:
                    log(f"Error parsing sequence string '{sequence_str}': {e}")
                    body, status = error_response(
                        f"Invalid sequence format: {e}", HTTP_BAD_REQUEST
                    )

            elif command == "stop":
                stop_beep()
                body, status = success_response({"message": "Buzzer stopped"})

            else:
                body, status = error_response(
                    f"Unknown command: {command}", HTTP_BAD_REQUEST
                )

            # Ensure body is a string or bytes before passing to Response
            if not isinstance(body, (str, bytes)):
                body = str(body)

            return Response(
                body=body, status=status, headers={"Content-Type": "application/json"}
            )

        except ValueError as e:  # MicroPython ujson raises ValueError for decode errors
            log(f"Error: Invalid JSON received in buzzer API: {e}")
            body, status = error_response(f"Invalid JSON data: {e}", HTTP_BAD_REQUEST)
            return Response(
                body=body, status=status, headers={"Content-Type": "application/json"}
            )
        except Exception as e:
            log(f"Error in buzzer API: {e}")
            body, status = error_response(
                f"Server error: {str(e)}", HTTP_INTERNAL_ERROR
            )
            return Response(
                body=body, status=status, headers={"Content-Type": "application/json"}
            )

    log("Buzzer routes registered using decorators.")
