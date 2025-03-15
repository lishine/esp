import socket
import _thread
import json
import machine

from log import log
from wifi import is_connected, get_ip, save_wifi_config
from fs import get_file_list, read_file


def handle_server():
    """Main HTTP server handler function"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 80))
    s.listen(5)

    while True:
        conn = None
        try:
            conn, addr = s.accept()
            request = conn.recv(4096)
            request = str(request)
            log(f"Received initial request of length: {len(request)}")

            if "/reset" in request:
                conn.send("HTTP/1.1 200 OK\n")
                conn.send("Content-Type: text/html\n")
                conn.send("Connection: close\n\n")
                conn.send("Resetting...")
                conn.close()
                machine.reset()

            elif "/download/" in request:
                filename = request.split("/download/")[1].split(" ")[0]
                content = read_file(filename)
                conn.send("HTTP/1.1 200 OK\n")
                conn.send("Content-Type: application/octet-stream\n")
                conn.send(f'Content-Disposition: attachment; filename="{filename}"\n')
                conn.send("Connection: close\n\n")
                conn.send(content)
                conn.close()

            elif "/list" in request:
                file_list = get_file_list()
                conn.send("HTTP/1.1 200 OK\n")
                conn.send("Content-Type: text/plain; charset=utf-8\n")
                conn.send("Connection: close\n\n")
                for line in file_list:
                    conn.send(line.encode("utf-8"))
                    conn.send(b"\n")
                conn.close()

            elif "/view/" in request:
                filename = request.split("/view/")[1].split(" ")[0]
                content = read_file(filename)
                conn.send("HTTP/1.1 200 OK\n")
                conn.send("Content-Type: text/plain\n")
                conn.send("Connection: close\n\n")
                conn.send(content + "\n")
                conn.close()

            elif "/settings" in request:
                if "POST" in request:
                    log("Received POST request to /settings")
                    try:
                        log("Extracting JSON data from request")

                        body_separator = "\\r\\n\\r\\n"
                        if body_separator in request:
                            parts = request.rsplit(body_separator, 1)
                            if len(parts) >= 2:
                                json_data = parts[1].strip()
                                log(f"Raw JSON data: {json_data}")

                                start_idx = json_data.find("{")
                                end_idx = json_data.rfind("}")

                                if (
                                    start_idx != -1
                                    and end_idx != -1
                                    and end_idx > start_idx
                                ):
                                    clean_json = json_data[start_idx : end_idx + 1]
                                    log(f"Cleaned JSON: {clean_json}")

                                    new_config = json.loads(clean_json)
                                    log(f"Parsed JSON data: {new_config}")
                                else:
                                    log("Could not find valid JSON object markers")
                                    raise ValueError(
                                        "Invalid JSON format - missing braces"
                                    )
                            else:
                                log("Could not split request body properly")
                                raise ValueError("Invalid request format")
                        else:
                            log("No body separator found in request")
                            raise ValueError("No request body found")

                        if "ssid" in new_config and "password" in new_config:
                            save_wifi_config(new_config)

                        else:
                            log("SSID or password missing in JSON data")
                    except Exception as e:
                        log(f"Error processing JSON data: {e}")

                    conn.send("HTTP/1.1 200 OK\n")
                    conn.send("Content-Type: application/json\n")
                    conn.send("Connection: close\n\n")
                    conn.send(
                        json.dumps(
                            {"success": True, "message": "Settings saved successfully"}
                        )
                    )
                    conn.close()
                else:
                    try:
                        with open("settings.html", "r") as f:
                            html = f.read()

                        from wifi import load_wifi_config

                        wifi_config = load_wifi_config()
                        is_wifi_connected = is_connected()
                        ip_address = get_ip()

                        log_link = ""
                        if is_wifi_connected:
                            log_link = f'<a href="http://{ip_address}/log" target="_blank" class="log-link">View Logs</a>'

                        html = html.replace(
                            'id="ssid" name="ssid"',
                            f'id="ssid" name="ssid" value="{wifi_config.get("ssid", "")}"',
                        )
                        html = html.replace(
                            'id="password" name="password"',
                            f'id="password" name="password" value="{wifi_config.get("password", "")}"',
                        )

                        status_html = f"""
        <h2>Connection Status</h2>
        <div class="status-item">
            <strong>Status:</strong> {"Connected" if is_wifi_connected else "Not connected"}
        </div>
        <div class="status-item">
            <strong>IP Address:</strong> {ip_address}
            {log_link}
        </div>
                        """
                        html = html.replace(
                            '<div class="status">', f'<div class="status">{status_html}'
                        )

                        conn.send("HTTP/1.1 200 OK\n")
                        conn.send("Content-Type: text/html\n")
                        conn.send("Connection: close\n\n")
                        conn.send(html)
                        conn.close()
                    except Exception as e:
                        log(f"Error serving settings.html: {e}")
                        conn.send("HTTP/1.1 500 Internal Server Error\n")
                        conn.send("Content-Type: text/html\n")
                        conn.send("Connection: close\n\n")
                        conn.send(
                            "<html><body><h1>500 Internal Server Error</h1><p>Failed to load settings page.</p></body></html>"
                        )
                        conn.close()

            elif "/log" in request:
                from log import log_buffer

                logs = log_buffer.get_all()

                if "Accept: text/html" in request:
                    log_entries_html = "No logs available"
                    if logs:
                        entries = []
                        for entry in logs:
                            entries.append(f"<div class='log-entry'>{entry}</div>")
                        log_entries_html = "".join(entries)

                    html_logs = f"""
<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Logs</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: monospace; margin: 0; padding: 20px; }}
        h1 {{ color: #333; }}
        .log-entry {{ margin-bottom: 5px; white-space: pre-wrap; }}
        .back-link {{ margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="back-link">
        <a href="/settings">Back to Settings</a>
    </div>
    <h1>ESP32 Logs</h1>
    <div class="logs">
        {log_entries_html}
    </div>
</body>
</html>
                    """
                    conn.send("HTTP/1.1 200 OK\n")
                    conn.send("Content-Type: text/html\n")
                    conn.send("Connection: close\n\n")
                    conn.send(html_logs)
                else:
                    logs_text = "\n".join(logs)
                    conn.send("HTTP/1.1 200 OK\n")
                    conn.send("Content-Type: text/plain\n")
                    conn.send("Connection: close\n\n")
                    conn.send(logs_text)
                conn.close()

            elif "/" == request.split(" ")[1]:
                conn.send("HTTP/1.1 303 See Other\n")
                conn.send("Location: /settings\n")
                conn.send("Connection: close\n\n")
                conn.close()

            else:
                conn.send("HTTP/1.1 404 Not Found\n")
                conn.send("Content-Type: text/html\n")
                conn.send("Connection: close\n\n")
                conn.send(
                    '<html><body><h1>404 Not Found</h1><p>The requested resource was not found on this server.</p><p><a href="/settings">Go to Settings</a></p></body></html>'
                )
                conn.close()
        except Exception as e:
            log("Error:", e)
            try:
                if conn is not None:
                    conn.close()
            except:
                pass


def start_server():
    """Start the web server in a separate thread"""
    _thread.start_new_thread(handle_server, ())
    log("Web server started")
