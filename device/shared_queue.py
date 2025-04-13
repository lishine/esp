# device/shared_queue.py
import uasyncio as asyncio  # Keep asyncio alias for Event if needed by queue.py
from lib.queue import Queue, QueueFull, QueueEmpty  # Import custom queue and exceptions
from log import log  # Optional: for logging queue creation if desired

_test_queue_instance = None


def get_test_queue():
    """Lazily creates and returns the singleton test queue instance."""
    global _test_queue_instance
    if _test_queue_instance is None:
        log("Creating shared test queue instance.")  # Log creation
        _test_queue_instance = Queue(20)  # Use the imported custom Queue
    return _test_queue_instance
