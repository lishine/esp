import json
from machine import Pin
import uasyncio as asyncio
from log import log

from server_framework import (
    Response,
    Request,
    HTTP_OK,
    HTTP_BAD_REQUEST,
    HTTP_INTERNAL_ERROR,
    success_response,
    error_response,
)

from io_local import fan

BUZZER_PINS = [1, 2]
buzzer_pin_objs = []
_beep_task = None


async def gps_fixed():
    """Plays a sequence of 15 beeps (0.5s on, 0.7s off) to indicate GPS fix achieved."""
    sequence = []
    for _ in range(8):
        sequence.extend([(500, True), (700, False)])  # 0.5s on, 0.7s off
    await play_sequence_async(sequence)


def init_buzzer():
    global buzzer_pin_objs
    buzzer_pin_objs.clear()
    initialized_pins = []
    success = True
    try:
        for pin_num in BUZZER_PINS:
            try:
                pin_obj = Pin(pin_num, Pin.OUT, value=0)
                initialized_pins.append(pin_obj)
                log(f"Initialized buzzer Pin {pin_num}")
            except Exception as e:
                log(f"Error initializing buzzer Pin {pin_num}: {e}")
                success = False
                break

        if success:
            buzzer_pin_objs = initialized_pins
            log(f"Active Buzzer initialized on Pins: {BUZZER_PINS}")
            return True
        else:
            for pin_obj in initialized_pins:
                try:
                    pin_obj.value(0)
                except Exception as cleanup_e:
                    log(f"Error during cleanup for pin {pin_obj}: {cleanup_e}")
            buzzer_pin_objs.clear()
            return False

    except Exception as e:
        log(f"Unexpected error during multi-pin buzzer initialization: {e}")
        buzzer_pin_objs.clear()
        return False


def set_buzzer(state: bool):
    if not buzzer_pin_objs:
        log("Buzzer pins not initialized.")
        return

    value_to_set = 1 if state else 0
    for pin_obj in buzzer_pin_objs:
        try:
            pin_obj.value(value_to_set)
        except Exception as e:
            log(f"Error setting buzzer pin {pin_obj}: {e}")


async def beep_async(duration_ms: int = 100):
    if not buzzer_pin_objs:
        log("Buzzer not initialized.")
        return
    try:
        set_buzzer(True)
        await asyncio.sleep_ms(duration_ms)
        set_buzzer(False)
    except Exception as e:
        log(f"Error during async beep: {e}")
    finally:
        set_buzzer(False)


async def play_sequence_async(sequence: list):
    global _beep_task
    if not buzzer_pin_objs:
        log("Buzzer not initialized.")
        return

    if _beep_task:
        try:
            _beep_task.cancel()
        except asyncio.CancelledError:
            pass
        _beep_task = None

    async def _player():
        try:
            for duration_ms, state in sequence:
                set_buzzer(state)
                await asyncio.sleep_ms(duration_ms)
            set_buzzer(False)
        except asyncio.CancelledError:
            set_buzzer(False)
        except Exception as e:
            log(f"Error playing buzzer sequence: {e}")
            set_buzzer(False)
        finally:
            _beep_task = None

    _beep_task = asyncio.create_task(_player())


def stop_beep():
    global _beep_task
    if _beep_task:
        try:
            _beep_task.cancel()  # type: ignore
        except asyncio.CancelledError:
            pass
        _beep_task = None
    set_buzzer(False)


def handle_control_api(request: Request):
    try:
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
            body_str = "{}"
        else:
            body_str = str(request.body)

        data = json.loads(body_str)

        # Handle fan control
        if "on" in data:
            fan.set_fan(data["on"])
            return Response(
                body=json.dumps({"success": True, "fan_on": data["on"]}),
                status=HTTP_OK,
                headers={"Content-Type": "application/json"},
            )

        # Handle buzzer control
        command = data.get("command")
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

                asyncio.create_task(play_sequence_async(sequence_list))
                body, status = success_response({"message": "Sequence async started"})
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

        return Response(
            body=body, status=status, headers={"Content-Type": "application/json"}
        )

    except ValueError as e:
        log(f"Error: Invalid JSON received in control API: {e}")
        body, status = error_response(f"Invalid JSON data: {e}", HTTP_BAD_REQUEST)
        return Response(
            body=body, status=status, headers={"Content-Type": "application/json"}
        )
    except Exception as e:
        log(f"Error in control API: {e}")
        body, status = error_response(f"Server error: {str(e)}", HTTP_INTERNAL_ERROR)
        return Response(
            body=body, status=status, headers={"Content-Type": "application/json"}
        )
