# Simple Upload Test Commands

Here are simple curl commands to test your ESP32 upload functionality. These commands will help diagnose if your upload route is being triggered.

## Create a Test File

First, create a simple test file:

```bash
echo "test data" > test_upload.txt
```

## Basic Upload Command

This command sends a simple POST request to the upload route:

```bash
# Get ESP32 IP from the ip file
ESP_IP=$(cat device/ip)
# Use the upload route with explicit file name
curl -v -X POST \
  -H "X-Chunk-Index: 0" \
  -H "X-Total-Chunks: 1" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@test_upload.txt" \
  "http://$ESP_IP/upload/test_upload.txt"
```

## Alternative Test Commands

If the basic command doesn't work, try these alternatives:

### Direct Upload Route

```bash
ESP_IP=$(cat device/ip)
curl -v -X POST \
  -H "X-Chunk-Index: 0" \
  -H "X-Total-Chunks: 1" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@test_upload.txt" \
  "http://$ESP_IP/upload"
```

### Form Upload Method

```bash
ESP_IP=$(cat device/ip)
curl -v -X POST \
  -F "file=@test_upload.txt" \
  "http://$ESP_IP/upload/test_upload.txt"
```

## Check Logs

After running any command, immediately check the logs:

```bash
ESP_IP=$(cat device/ip)
curl "http://$ESP_IP/log"
```

## One-liner Test

For a quick one-command test:

```bash
ESP_IP=$(cat device/ip) && echo "test" > test_upload.txt && curl -v -X POST -H "X-Chunk-Index: 0" -H "X-Total-Chunks: 1" -H "Content-Type: application/octet-stream" --data-binary "@test_upload.txt" "http://$ESP_IP/upload/test_upload.txt" && curl "http://$ESP_IP/log"
```

These commands should help determine if your upload route is being triggered at all.
