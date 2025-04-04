# ESP32 Setup and Usage Documentation

## Initial Setup

1. First start ESP
2. Erase flash:
   ```
   esptool.py --chip esp32c3 --port /dev/tty.usbmodem101 erase_flash
   ```
3. Write flash:
   ```
   esptool.py --chip esp32c3 --port /dev/tty.usbmodem101 --baud 460800 write_flash -z 0x0 ESP32_GENERIC_C3-20241129-v1.24.1.bin
   ```
4. Upload boot:
   ```
   ampy -p /dev/tty.usbmodem101 put main.py
   ```
5. Click reset button
6. Connect to AP

## API Usage

- List files:
  ```
  curl http://192.168.4.1/list
  ```
- Upload file to a specific path:
  ```
  curl -F "file=@myfile.py" http://192.168.4.1/upload/target_path
  ```
  Replace `target_path` with the desired file path on the device.
- Download file:
  ```
  curl http://192.168.4.1/download/myfile.py -o myfile.py
  ```
- View file:
  ```
  curl http://192.168.4.1/view/myfile.py
  ```
- Remove file or empty directory:
  ```
  curl http://192.168.4.1/rm/target_path
  ```
  Replace `target_path` with the file or directory path to be removed.

Add to boot.py or main.py, then call start_server().
Test with: `curl http://192.168.4.1/reset`

## Notes

- The `%` symbol in terminal output is a shell prompt that appears when a command completes without a newline character.
- After uploading code modules, run `/reset` to load them into the system.

```
curl http://192.168.4.1/list
curl -F "file=@myfile.py" http://192.168.4.1/upload
curl http://192.168.4.1/reset
```

## custom micropython build to disable serial on uart

gcl micropython
edit boards/ESP32_GENERIC_C3/mpconfigboard.h:

// This configuration is for a generic ESP32C3 board with 4MiB (or more) of flash.

#define MICROPY_HW_BOARD_NAME "ESP32C3 module"
#define MICROPY_HW_MCU_NAME "ESP32C3"

// Enable UART REPL for modules that have an external USB-UART and don't use native USB.
#define MICROPY_HW_ENABLE_UART_REPL (0)

// Disable UART REPL to free UART0
#define MICROPY_HW_UART_REPL (-1)
#define MICROPY_HW_ENABLE_UART_REPL (0)

## esp32-s3

c6 not enough memory for micropython

### programming

connect both ampy and esptool only to the direct connector
for esptool hold down boot and preset reset and then run command

esp_port() {
export ESP_PORT=$(ls /dev/tty.usbmodem\* | head -n 1);echo $ESP_PORT
}

esptool.py --port $ESP_PORT erase_flash
esptool.py --baud 460800 write_flash 0 ./ESP32_GENERIC_S3-SPIRAM_OCT-20241129-v1.24.1.bin

using mpremote
