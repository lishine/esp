from machine import Pin
import uasyncio as asyncio
from log import log
import time

# --- Configuration ---
BUZZER_PIN = 10  # GPIO10 (Pinout Table)

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


# Example Usage (can be called from elsewhere)
# init_buzzer()
# asyncio.run(beep_async(200))
# asyncio.run(play_sequence_async([(100, True), (50, False), (150, True)]))
