import uasyncio as asyncio
import sys
from log import log  # Keep async logger
import server  # Needed here for get_app()

# wifi, ap, led are started in boot.py
# We only need the logger task here
# from led import led_turn_off # No longer needed here

# led_turn_off() # Should be handled by led thread init if needed


# --- Async Main Function ---
async def main():
    log("main.py: Starting asyncio tasks...")
    try:
        # Start the background logger task first

        # --- Background services (AP, WiFi, LED) are already started by boot.py ---

        # Get the configured Microdot app from server.py
        app = server.get_app()
        log("Microdot app retrieved.")

        # Start the Microdot server as a background task
        log("Creating Microdot server task...")
        asyncio.create_task(app.start_server(port=80, debug=True))
        log("Microdot server task created.")

        # Keep the main task running indefinitely so background tasks continue
        # This is primarily needed to keep the logger_task alive
        log("Entering main loop (logger task running, threads running)...")
        loop_count = 0
        while True:
            # Remove blocking call from loop: blink_sequence(3, 2, 0.1)
            await asyncio.sleep(15)  # Use await asyncio.sleep to yield control
            loop_count += 1
            log(f"Async main loop alive - iteration {loop_count}")  # Add periodic log

    except Exception as e:
        log("Error during async main execution:", e)
        sys.print_exception(e)
    finally:
        # Optional: Add cleanup logic here if needed
        log("Async main finished.")


# --- Start Event Loop ---
# This runs the main coroutine, which starts the logger task
# and then keeps the loop alive for it.
log("Starting asyncio event loop for logger...")
try:
    asyncio.run(main())
except KeyboardInterrupt:
    log("Keyboard interrupt, stopping.")
except Exception as e:
    log("Error running asyncio main loop:", e)
    sys.print_exception(e)
finally:
    # Resetting the loop is often good practice if the script might be re-imported
    asyncio.new_event_loop()
    log("Event loop finished.")
