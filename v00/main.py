# main.py
from machine import Pin, reset
import time
import network
import socket
import _thread  # For running blink cycle in parallel

# First, try to close any existing sockets
try:
    import usocket as socket
    temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    temp_socket.bind(('', 80))
    temp_socket.close()
except:
    print("Resetting device...")
    time.sleep(1)
    reset()

led = Pin(8, Pin.OUT)
led.on()  

# Global flag to control blinking
is_blinking = False

def led_turn_on():
    led.off()

def led_turn_off():
    led.on()

def blink_startup():
    for _ in range(5):
        led_turn_on()
        time.sleep(0.5)
        led_turn_off()
        time.sleep(0.5)

def long_blink():
    led_turn_on()
    time.sleep(2)
    led_turn_off()

# Blink cycle function to run in separate thread
def blink_cycle():
    global is_blinking
    while True:
        if is_blinking:
            led_turn_on()
            time.sleep(0.5)
            led_turn_off()
            time.sleep(0.5)
        else:
            time.sleep(0.1)  # Small delay when not blinking

blink_startup()

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    print(f"Trying to connect to {ssid}")
    print(f"Current status: {wlan.status()}")
    
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            print("Connecting....")
            time.sleep(1)
    
    print("Connected!")
    print(f"IP address: {wlan.ifconfig()[0]}")
    return wlan.ifconfig()[0]

ip = connect_wifi('Bucha', 'yesandyes')

html = """<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Web Server</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial; text-align: center; margin:0px auto; padding: 25px; }
        .button { background-color: #4CAF50; border: none; color: white; padding: 16px 40px;
                text-decoration: none; font-size: 30px; margin: 2px; cursor: pointer;}
        .button2 { background-color: #555555;}
        .button3 { background-color: #f4511e;}
        .info { color: #555555; font-size: 14px; }
    </style>
</head>
<body>
    <h1>ESP32 Web Server</h1>
    <p class="info">Device IP: %s</p>
    <p>LED state: <strong>%s</strong></p>
    <p><a href="/light/on"><button class="button">ON</button></a></p>
    <p><a href="/light/off"><button class="button button2">OFF</button></a></p>
    <p><a href="/light/blink"><button class="button button3">%s</button></a></p>
</body>
</html>
"""

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('', 80))
s.listen(5)

# Start blink cycle in separate thread
_thread.start_new_thread(blink_cycle, ())

print('Server listening on port 80...')
print(f'You can now connect to http://{ip}')
long_blink()

while True:
    try:
        conn, addr = s.accept()
        request = conn.recv(1024)
        request = str(request)
        print('Got a connection from %s' % str(addr))
        
        led_on = not led.value()
        if '/light/on' in request:
            is_blinking = False  # Stop blinking if it was blinking
            time.sleep(0.1)      # Small delay to ensure blink cycle stops
            led_turn_on()
            led_on = True
        elif '/light/off' in request:
            is_blinking = False  # Stop blinking if it was blinking
            time.sleep(0.1)      # Small delay to ensure blink cycle stops
            led_turn_off()
            led_on = False
        elif '/light/blink' in request:
            is_blinking = not is_blinking  # Toggle blinking state
            
        # Update response to include blinking state
        blink_text = "STOP BLINK" if is_blinking else "START BLINK"
        response = html % (ip, 'ON' if led_on else 'OFF', blink_text)
        conn.send('HTTP/1.1 200 OK\n')
        conn.send('Content-Type: text/html\n')
        conn.send('Connection: close\n\n')
        conn.sendall(response)
        conn.close()

    except Exception as e:
        print('Error:', e)
        try:
            conn.close()
        except:
            pass

