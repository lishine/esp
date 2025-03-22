# Minimal Upload Test Command

This single command will test your upload functionality and immediately show the logs:

```bash
# From the device directory (where your ip file is located)
ESP_IP=$(cat ip) && echo "test" > test.txt && curl -v -X POST \
  -H "X-Chunk-Index: 0" \
  -H "X-Total-Chunks: 1" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@test.txt" \
  "http://$ESP_IP/upload/test.txt" && curl "http://$ESP_IP/log"
```

For testing with your existing up.txt file:

```bash
ESP_IP=$(cat ip) && curl -v -X POST \
  -H "X-Chunk-Index: 0" \
  -H "X-Total-Chunks: 1" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@up.txt" \
  "http://$ESP_IP/upload/up.txt" && curl "http://$ESP_IP/log"
```

After running this, we should either see the upload succeed or get useful log information about what's failing.

Once we identify the specific issue, we can switch to Code mode to implement the fix:

```
<switch_mode>
<mode_slug>code</mode_slug>
<reason>Implement code fixes for the upload functionality</reason>
</switch_mode>
```
