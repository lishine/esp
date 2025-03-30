import uasyncio as asyncio
import sys
import esp32  # Import esp32 module for heap info
import gc  # Import garbage collector module for mem_free
import log  # Import the whole log module
import server  # Needed here for get_app()
import led  # Import the led module
import wifi  # Import the new wifi module
import ap  # Import the ap module


async def main():
    log.log("main.py: Starting...")
    try:
        # Start synchronous services first
        log.log("Starting AP...")
        ap.start_ap(essid="DDDEV", password="")  # Start AP synchronously
        log.log(f"AP Started: http://{ap.get_ap_ip()} (SSID: DDDEV)")

        # --- Start background asyncio tasks ---
        log.log("Starting asyncio tasks...")
        log.log("Creating LED task...")
        asyncio.create_task(led.led_task())
        log.log("LED task created.")

        log.log("Creating WiFi management task...")
        asyncio.create_task(wifi.manage_wifi_connection())
        log.log("WiFi management task created.")
        log.log("WiFi management task created.")  # Duplicate log message? Keep for now.

        log.log("Creating Log Writer task...")
        # Note: _log_writer_task is intentionally private but needs to be started
        asyncio.create_task(log._log_writer_task())
        log.log("Log Writer task created.")

        # Get the configured Microdot app from server.py
        app = server.get_app()
        log.log("Microdot app retrieved.")

        # Start the Microdot server as a background task
        log.log("Creating Microdot server task...")
        asyncio.create_task(app.start_server(port=80, debug=True))
        log.log("Microdot server task created.")

        # Keep the main task running indefinitely so background tasks continue
        # This is primarily needed to keep the logger_task alive
        log.log("Entering main loop (logger task running, threads running)...")
        loop_count = 0
        while True:
            # Remove blocking call from loop: blink_sequence(3, 2, 0.1)
            await asyncio.sleep(15)  # Use await asyncio.sleep to yield control
            loop_count += 1
            log.log(
                f"Async main loop alive - iteration {loop_count}"
            )  # Add periodic log

            # Log largest contiguous free block in data heaps
            try:
                # Get IDF Heap Info
                heap_info = esp32.idf_heap_info(
                    esp32.HEAP_DATA
                )  # List of (total, free, largest_free, min_free)
                max_free_block = 0
                total_free = 0
                num_regions = len(heap_info)
                for heap in heap_info:
                    total_free += heap[1]
                    if heap[2] > max_free_block:
                        max_free_block = heap[2]

                # Get MicroPython Heap Info
                upy_free = gc.mem_free()

                log.log(
                    f"Mem: IDF TotalFree={total_free}, MaxBlock={max_free_block}, Regions={num_regions}; UPy Free={upy_free}"
                )
            except Exception as heap_err:
                log.log(f"Error getting memory info: {heap_err}")

    except Exception as e:
        log.log("Error during async main execution:", e)
        sys.print_exception(e)
    finally:
        # Optional: Add cleanup logic here if needed
        log.log("Async main finished.")


log.log("Starting asyncio event loop for logger...")
try:
    asyncio.run(main())
except KeyboardInterrupt:
    log.log("Keyboard interrupt, stopping.")
except Exception as e:
    log.log("Error running asyncio main loop:", e)
    sys.print_exception(e)
finally:
    # Resetting the loop is often good practice if the script might be re-imported
    asyncio.new_event_loop()
    log.log("Event loop finished.")
