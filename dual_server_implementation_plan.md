# Dual HTTP/HTTPS Server Implementation Plan for ESP32 (Minimal main.py Changes)

## 1. Objective

To configure the ESP32 to run two web server instances simultaneously, each in its own thread:

- An **HTTPS server** that is always active, primarily for secure communication when the ESP32 is in Access Point (AP) mode.
- An **HTTP server** that is conditionally active, starting only when the ESP32 successfully connects to a local Wi-Fi network (Station mode, STA), intended for easier local development.

This setup will address the mixed content browser error when accessing the ESP32 from an HTTPS frontend (`pages.dev`) while providing a simpler HTTP endpoint for local development.

## 2. Network Configuration (AP+STA Mode)

The ESP32 will be configured to operate in AP+STA mode.

- AP mode setup (e.g., `ap.start_ap()`) and STA connection attempts (e.g., via `wifi.wifi_thread_manager()`) will continue to be initiated from `main.py` as per the current structure.
- The conditional HTTP server will rely on the status provided by the STA connection managed by `wifi.py`.

## 3. Server Implementation Strategy

Servers will be launched via functions in `http_server.py`, which are called from `main.py`. Each actual server (`app.run`) instance will operate in its own dedicated thread.

- **HTTPS Server:**
  - **Activation:** Always runs. Launched by a modified `start_server()` (e.g., renamed to `start_https_server()`) in `http_server.py`, which is called from `main.py`.
  - **Protocol:** HTTPS, using `ussl` module.
  - **Certificate:** Uses `/cert.pem` and `/key.pem` files located in the device's root filesystem.
  - **Port:** 443.
  - **Binding:** `0.0.0.0` (to be accessible on all interfaces, AP and STA).
- **HTTP Server:**
  - **Activation:** Conditionally. A new function, `start_conditional_http_server()`, will be created in `http_server.py`. This function will be started in a thread from `main.py`.
  - Inside its thread, `start_conditional_http_server()` will monitor the STA connection status (e.g., by calling `wifi.is_connected()`).
  - If/when STA mode connects, `start_conditional_http_server()` will then launch the actual HTTP server (using `app.run()`) in yet another new thread.
  - **Protocol:** HTTP.
  - **Port:** 80.
  - **Binding:** `0.0.0.0`.

## 4. Code Structure and Modifications

### 4.1. `device/server_framework.py`

- The `HTTPServer.run(self, port, ssl_context=None)` method will be updated:
  - It will accept an `ssl_context` parameter (defaulting to `None`).
  - If `ssl_context` is provided (for the HTTPS server), after the main server socket `accepts` a client connection, the `client_socket` will be wrapped: `secure_client_socket = ssl_context.wrap_socket(client_socket, server_side=True)`.
  - The `self.handle_client` method will then be called with this `secure_client_socket` (or the plain `client_socket` if no SSL context).
- The `handle_client` method, and subsequently `parse_request` and `send_response`, need to correctly handle both plain and `ussl`-wrapped sockets. For `ussl`-wrapped sockets, `client_socket.read()` might be preferred over `client_socket.recv()`, and `client_socket.write()` over `client_socket.send()`. This will be verified during implementation.

### 4.2. `device/http_server.py`

- The existing `start_server()` function (currently at line 765) will be **renamed to `start_https_server()`**.
  - This function will be responsible for:
    1.  Loading `/cert.pem` and `/key.pem`.
    2.  Creating an `ussl.SSLContext(ussl.PROTOCOL_TLS_SERVER)`.
    3.  Loading the certificate and key into the context.
    4.  Importing the `app` instance from `device.server_framework`.
    5.  Starting a new thread for the HTTPS server: `_thread.start_new_thread(lambda: app.run(port=443, ssl_context=the_ssl_context), ())`.
- A **new function `start_conditional_http_server()`** will be added:
  - This function is intended to be run in its own thread, started by `main.py`.
  - It will contain a loop that periodically (e.g., every few seconds) checks `wifi.is_connected()`.
  - A flag will be used to ensure the HTTP server thread is started only once.
  - When `wifi.is_connected()` returns `True` for the first time and the HTTP server thread has not yet been started:
    - It will log the STA connection.
    - It will import the `app` instance from `device.server_framework`.
    - It will start a new thread for the HTTP server: `_thread.start_new_thread(lambda: app.run(port=80, ssl_context=None), ())`.
    - Set the flag to indicate the HTTP server thread has been launched.
    - The loop in `start_conditional_http_server` can then terminate or continue if more sophisticated monitoring is needed later (e.g., to stop the HTTP server if STA disconnects, though this adds complexity). For now, a start-once approach is simpler.

### 4.3. `device/main.py`

- The existing calls `ap.start_ap(...)` (line 37) and `_thread.start_new_thread(wifi.wifi_thread_manager, ())` (line 39) will remain unchanged.
- The line `start_server()` (line 41) will be changed to call `http_server.start_https_server()`.
- A new line will be added, after `wifi.wifi_thread_manager` is started, to launch the conditional HTTP server monitor: `_thread.start_new_thread(http_server.start_conditional_http_server, ())`.

### 4.4. `device/ap.py` and `device/wifi.py`

- These files will remain unchanged. `wifi.is_connected()` will be the key function used by `http_server.py` to determine STA status.

## 5. Frontend Configuration

The frontend application (`pages.dev` site) will need to be configured to use the correct base URL depending on the environment:

- **Production/Field (accessing ESP32 AP):** `https://192.168.4.1` (or `https://192.168.4.1:443`)
- **Local Development (accessing ESP32 on LAN via STA):** `http://<ESP_LAN_IP>` (or `http://<ESP_LAN_IP>:80`)
  This can be managed using environment variables in the frontend build process (e.g., `VITE_API_BASE_URL`).
