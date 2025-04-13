import uasyncio as asyncio
import sys
import time
import _thread


from log import log, _log_writer_thread_func
import led
import wifi
from wifi import manage_wifi_led_status
import ap
from http_server import start_server
from cpu_measure import idle_task, measure_cpu

import io_local.init_io as init_io
import io_local.esc_telemetry as esc_telemetry
import io_local.gps_reader as gps_reader
import io_local.ds18b20 as ds18b20
import io_local.motor_current_i2c as motor_current_i2c
import io_local.throttle_reader as throttle_reader

time.sleep(2)
print("main")


async def main():
    try:
        log("Init IO")
        init_io.init_io()

        log("Starting threads")
        ap.start_ap(essid="DDDEV", password="")
        _thread.start_new_thread(wifi.wifi_thread_manager, ())
        _thread.start_new_thread(_log_writer_thread_func, ())
        start_server()

        log("Starting async tasks")
        asyncio.create_task(led.led_task())
        esc_telemetry.start_esc_reader()
        ds18b20.start_ds18b20_reader()
        gps_reader.start_gps_reader()
        asyncio.create_task(idle_task())
        asyncio.create_task(measure_cpu())
        asyncio.create_task(manage_wifi_led_status())
        motor_current_i2c.start_rms_motor_current_i2c_reader()
        throttle_reader.start_throttle_reader()

        log("Entering main loop (logger task running, threads running)...")
        loop_count = 0
        while True:
            await asyncio.sleep(1)
            loop_count += 1
            log(f"LOOP {loop_count}")
    except Exception as e:
        log("Error during async main execution:", e)
        sys.print_exception(e)
    finally:
        log("Async main finished.")


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
