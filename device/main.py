print("start loading modules at main")
import uasyncio as asyncio
import sys
import time
import _thread

from log import log, _log_writer_thread_func
import led
from led import set_green_led
import wifi
from wifi import manage_wifi_led_status
import ap
from http_server import start_https_server
from cpu_measure import idle_task, measure_cpu

import io_local.init_io as init_io
import io_local.esc_telemetry as esc_telemetry
import io_local.gps_reader as gps_reader
import io_local.ds18b20 as ds18b20
import io_local.motor_current_i2c as motor_current_i2c
import io_local.throttle_reader as throttle_reader
import io_local.data_log as data_log

print("end loading modules at main")

time.sleep(1)
print("main")


async def main():
    try:
        log("Init IO")
        init_io.init_io()

        log("Starting threads")
        asyncio.create_task(led.led_task())
        ap.start_ap(essid="DDDEV", password="aaaaaaaa")
        set_green_led(True)
        _thread.start_new_thread(wifi.wifi_thread_manager, ())
        _thread.start_new_thread(_log_writer_thread_func, ())

        log("Starting HTTPS server...")
        start_https_server()  # Starts the always-on HTTPS server in its own thread

        log("Starting conditional HTTP server monitor thread...")
        # This thread will wait for STA to connect and then start the HTTP server
        # _thread.start_new_thread(start_conditional_http_server, ())

        log("Starting async tasks")
        esc_telemetry.start_esc_reader()
        ds18b20.start_ds18b20_reader()
        gps_reader.start_gps_reader()
        asyncio.create_task(idle_task())
        asyncio.create_task(measure_cpu())
        asyncio.create_task(manage_wifi_led_status())
        # Start the data logging tasks from the data_log module
        asyncio.create_task(data_log.data_report_task())
        asyncio.create_task(data_log.data_log_task())
        asyncio.create_task(data_log.error_log_task())
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
