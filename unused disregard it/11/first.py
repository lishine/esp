from machine import Pin, reset, ADC
import time
import network
import socket
import _thread
import json


def reset_wifi():
    try:
        import usocket as socket
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        temp_socket.bind(('', 80))
        temp_socket.close()
    except:
        print("Resetting device...")
        time.sleep(1)
        reset()

reset_wifi()

# Setup ADC
fsr_pin = Pin(4, Pin.IN, Pin.PULL_DOWN)
fsr_adc = ADC(fsr_pin)

# Global variables
led = Pin(8, Pin.OUT)
led.on()
is_blinking = True
latest_voltage_min = 0
latest_voltage_max = 0
latest_voltage_avg = 0

# Basic HTML template
html = """<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Monitor</title>
    <style>
        body { font-family: Arial; text-align: center; }
        .readings { margin: 20px; }
        .progress-container {
            width: 80%;
            margin: 20px auto;
            background-color: #f0f0f0;
            border-radius: 5px;
            overflow: hidden;
        }
        .progress-bar {
            width: 0%;
            height: 30px;
            ttransition: width 0.3s ease-in-out;
        }
        .button { 
            background-color: #4CAF50; 
            border: none; 
            color: white; 
            padding: 15px 32px; 
            text-decoration: none; 
            display: inline-block; 
            font-size: 16px;
            margin: 4px 2px;
            cursor: pointer;
        }
        .button2 { background-color: #555555; }
        .button3 { background-color: #f4511e; }
    </style>
</head>
<body>
    <h1>ESP32 Monitor</h1>
    <div class="readings">
        <p>Min: <span id="min">--</span>V</p>
        <p>Max: <span id="max">--</span>V</p>
        <p>Avg: <span id="avg">--</span>V</p>
        <div class="progress-container">
            <div id="progress-bar" class="progress-bar"></div>
        </div>
    </div>
    <p>
        <button onclick="sendCommand('/light/on')" class="button">ON</button>
        <button onclick="sendCommand('/light/off')" class="button button2">OFF</button>
        <button onclick="sendCommand('/light/blink')" class="button button3" id="blinkBtn">BLINK</button>
    </p>
    <script>
        setInterval(() => {
            fetch('/data')
            .then(response => response.json())
            .then(data => {
                document.getElementById('min').textContent = data.min.toFixed(3);
                document.getElementById('max').textContent = data.max.toFixed(3);
                document.getElementById('avg').textContent = data.avg.toFixed(3);
                
                // Update progress bar
                const percentage = (data.avg / 3.3) * 100;
                const progressBar = document.getElementById('progress-bar');
                progressBar.style.width = percentage + '%';
                
                // Change color based on percentage
                let color;
                if (percentage <= 25) {
                    color = '#007bff'; // Blue
                } else if (percentage <= 50) {
                    color = '#28a745'; // Green
                } else if (percentage <= 75) {
                    color = '#ffc107'; // Yellow
                } else {
                    color = '#dc3545'; // Red
                }
                progressBar.style.backgroundColor = color;
            });
        }, 50);

        function sendCommand(cmd) {
            fetch(cmd)
            .then(response => response.json())
            .then(data => {
                if(data.blinking !== undefined) {
                    document.getElementById('blinkBtn').textContent = 
                        data.blinking ? 'STOP BLINK' : 'START BLINK';
                }
            });
        }
    </script>
</body>
</html>
"""

def led_turn_on():
    led.off()

def led_turn_off():
    led.on()

def blink_cycle():
    global is_blinking
    while True:
        if is_blinking:
            led_turn_on()
            time.sleep(0.5)
            led_turn_off()
            time.sleep(0.5)
        else:
            time.sleep(0.1)

def read_fsr():
    global latest_voltage_min, latest_voltage_max, latest_voltage_avg
    while True:
        raw = 0
        min_val = float('inf')
        max_val = 0
        m = 100
        i = m
        while i > 0:
            val = fsr_adc.read_uv()
            raw += val
            min_val = min(min_val, val)
            max_val = max(max_val, val)
            i -= 1
        avg = raw / m
        latest_voltage_avg = 3.3 * avg / 865000
        latest_voltage_min = 3.3 * min_val / 865000
        latest_voltage_max = 3.3 * max_val / 865000
        #print(f"Min: {latest_voltage_min:.3f}V, Max: {latest_voltage_max:.3f}V, Avg: {latest_voltage_avg:.3f}V")
        time.sleep(0.02)

def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    print(f"Trying to connect to {ssid}")
    
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            print("Connecting....")
            time.sleep(1)
    
    print("Connected!")
    print(f"IP address: {wlan.ifconfig()[0]}")
    return wlan.ifconfig()[0]

# Connect to WiFi
ip = connect_wifi('Bucha', 'yesandyes')

# Setup socket server
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('', 80))
s.listen(5)

# Start background threads
_thread.start_new_thread(blink_cycle, ())
_thread.start_new_thread(read_fsr, ())

print('Server listening on port 80...')
print(f'You can now connect to http://{ip}')

while True:
    try:
        conn, addr = s.accept()
        request = conn.recv(1024)
        request = str(request)
        # print('Connection from', addr)
        
        if '/data' in request:
            # Send JSON data
            response = {
                'min': latest_voltage_min,
                'max': latest_voltage_max,
                'avg': latest_voltage_avg
            }
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: application/json\n')
            conn.send('Connection: close\n\n')
            conn.sendall(json.dumps(response))
        
        elif '/light/' in request:
            # Handle LED commands
            if '/light/on' in request:
                is_blinking = False
                time.sleep(0.1)
                led_turn_on()
            elif '/light/off' in request:
                is_blinking = False
                time.sleep(0.1)
                led_turn_off()
            elif '/light/blink' in request:
                is_blinking = not is_blinking
            
            # Send response for LED commands
            response = {'blinking': is_blinking}
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: application/json\n')
            conn.send('Connection: close\n\n')
            conn.sendall(json.dumps(response))
        
        else:
            # Send main HTML page
            conn.send('HTTP/1.1 200 OK\n')
            conn.send('Content-Type: text/html\n')
            conn.send('Connection: close\n\n')
            conn.sendall(html)
        
        conn.close()

    except Exception as e:
        print('Error:', e)
        try:
            conn.close()
        except:
            pass

