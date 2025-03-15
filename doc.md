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
- Upload file:
  ```
  curl -F "file=@myfile.py" http://192.168.4.1/upload
  ```
- Download file:
  ```
  curl http://192.168.4.1/download/myfile.py -o myfile.py
  ```
- View file:
  ```
  curl http://192.168.4.1/view/myfile.py
  ```
- Reset device:
  ```
  curl http://192.168.4.1/reset
  ```

Add to boot.py or main.py, then call start_server().
Test with: `curl http://192.168.4.1/reset`

Example commands:

```
curl http://192.168.4.1/list
curl -F "file=@myfile.py" http://192.168.4.1/upload
curl http://192.168.4.1/reset
```
