from machine import Pin, reset, ADC,UART,I2C
import time
import network
import socket
import _thread
import json
import struct
import time

i2c = I2C(0, scl=Pin(10), sda=Pin(9), freq=100000)
# devices = i2c.scan()
# print("I2C devices found:", [hex(device) for device in devices])


led = Pin(8, Pin.OUT)
led.on()
is_blinking = True

def led_turn_on():
    led.off()

def led_turn_off():
    led.on()


# while True:
#     led.value(not led.value())
#     time.sleep(1)


# INA226 Register addresses
CONFIG_REG = 0x00
SHUNT_VOLTAGE_REG = 0x01
BUS_VOLTAGE_REG = 0x02
INA226_ADDR = 0x40  # Modified I2C address

def write_register(reg_addr, value):
    data = bytearray([reg_addr, (value >> 8) & 0xFF, value & 0xFF])
    i2c.writeto(INA226_ADDR, data)

def read_register(reg_addr):
    i2c.writeto(INA226_ADDR, bytes([reg_addr]))
    data = i2c.readfrom(INA226_ADDR, 2)
    return (data[0] << 8) | data[1]

def configure_ina226():
    # Configure INA226
    # Reset bit[15] = 1, 16 avg samples bit[11:9]=111, 1.1ms conv time bit[8:6]=111,
    # 1.1ms conv time bit[5:3]=111, continuous mode bit[2:0]=111
    config = 0x4727
    write_register(CONFIG_REG, config)
    time.sleep_ms(1)  # Wait for configuration to take effect

def read_shunt_voltage():
    raw = read_register(SHUNT_VOLTAGE_REG)
    if raw > 32767:  # Handle negative values
        raw -= 65536
    return raw * 2.5e-6  # Convert to volts (LSB = 2.5µV)

def read_bus_voltage():
    raw = read_register(BUS_VOLTAGE_REG)
    return raw * 1.25e-3  # Convert to volts (LSB = 1.25mV)

# Main program
try:
    # First, scan I2C bus to verify device is present
    devices = i2c.scan()
    print("I2C devices found:", [hex(device) for device in devices])
    
    # Configure INA226
    configure_ina226()
    
    # while True:
    #     shunt_voltage = read_shunt_voltage()
    #     bus_voltage = read_bus_voltage()
    #     current = shunt_voltage / 0.001  # Using 0.1Ω shunt resistor
        
    #     print(f"Bus Voltage: {bus_voltage:.3f}V")
    #     print(f"Shunt Voltage: {shunt_voltage*1000:.3f}mV")
    #     print(f"Current: {current:.3f}A")
    #     print("-" * 20)
        
    #     led.value(not led.value())
    #     time.sleep(1)

except Exception as e:
    print("Error:", e)





# while True:
#     led.value(not led.value())
#     time.sleep(1)


# uart = UART(1, 115200)  # UART2, baud rate 115200
# uart.init(115200, bits=8, parity=None, stop=1, rx=20, tx=21)
uart = UART(1, baudrate=115200, tx=21, rx=20, bits=8, parity=None, stop=1)

def update_crc8(crc, crc_seed):
    crc_u = crc ^ crc_seed
    for i in range(8):
        crc_u = (0x7 ^ (crc_u << 1)) if (crc_u & 0x80) else (crc_u << 1)
    return crc_u & 0xFF

def get_crc8(buf, buflen):
    crc = 0
    for i in range(buflen):
        crc = update_crc8(buf[i], crc)
    return crc

def parse_kiss_telemetry(data):
    if data and len(data) >= 10:
        try:
            # Verify CRC
            received_crc = data[9]
            calculated_crc = get_crc8(data[:9], 9)
            if received_crc != calculated_crc:
                print(f"CRC mismatch: received {received_crc}, calculated {calculated_crc}")
                return None

            temperature = data[0]  # °C
            # print(f"Temperature: {temperature}°C")
            voltage = (data[1] << 8 | data[2]) / 100.0  # Volts
            current = (data[3] << 8 | data[4]) / 100.0  # Amps
            consumption = (data[5] << 8 | data[6])  # mAh
            erpm = (data[7] << 8 | data[8]) * 100   # Electrical RPM
            rpm = erpm // (12//2)  # For a 12-pole motor

            return {
                'voltage': voltage,
                'rpm': rpm,
                'temperature': temperature,
                'current': current,
                'consumption': consumption
            }
        except Exception as e:
            print(f"Error: {e}")
            return None
    return None

# while True:
#     led.value(not led.value())
#     if uart.any():
#         data = uart.read()
#         telemetry = parse_kiss_telemetry(data)
#         print(telemetry)
#     time.sleep(1)


# def parse_status_byte(status):
#     # Byte 9 status flags
#     status_flags = {
#         0x01: "LOW_VOLTAGE",
#         0x02: "OVER_TEMPERATURE",
#         0x04: "OVER_CURRENT",
#         0x08: "OVER_RPM",
#         0x10: "STARTUP_FAIL",
#         0x20: "STALL"
#     }
    
#     active_flags = []
#     for bit, flag in status_flags.items():
#         if status & bit:
#             active_flags.append(flag)
#     return active_flags

# def parse_blheli_telemetry(data):
#     if data and len(data) >= 10:
#         try:
#             temperature = data[0]  # Temperature in °C
#             voltage = (data[1] << 8 | data[2]) / 100.0  # Voltage in V
#             current = (data[3] << 8 | data[4])  # Current in A
#             consumption = (data[5] << 8 | data[6])      # Consumption in mAh
#             rpm = (data[7] << 8 | data[8])
#             status = data[9]
#             status_flags = parse_status_byte(status)
            
#             # eRPM
            
#             # Debug RPM calculation
#             rpm_byte_high = data[7]
#             rpm_byte_low = data[8]
#             raw_rpm = (rpm_byte_high << 8 | rpm_byte_low)
#             erpm = raw_rpm * 100
            
#             #print(f"RPM bytes: High:{rpm_byte_high} Low:{rpm_byte_low} Raw:{raw_rpm} eRPM:{erpm}")
#             for i in range(3, 10):
#                 binary = bin(data[i])[2:]  # Remove '0b' prefix
#                 binary = '0' * (8 - len(binary)) + binary  # Pad with zeros
#                 print(f"Byte {i}: {binary}")            
#             #print(f"Status Flags: {status_flags}")
#             #return ""
#             return f"V:{voltage:06.2f} I:{current:06d} CON:{consumption:06d} RPM:{rpm:06d} T:{temperature:03d}C"
#         except:
#             return None
#     return None



#machine.reset()

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

# reset()
# Setup ADC
fsr_pin = Pin(4, Pin.IN)
fsr_adc = ADC(fsr_pin)
#fsr_adc.atten(ADC.ATTN_11DB)  # Full range: 0-3.3V
#fsr_adc.width(ADC.WIDTH_12BIT)  # 12-bit resolution

# Global variables



latest_voltage_min = 0
latest_voltage_max = 0
latest_voltage_avg = 0
esc_voltage = 0
esc_rpm = 0
esc_temp = 0

# Basic HTML template
html = """<!DOCTYPE html>
<html>
<head>
    <title>ESP32 Monitor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { 
            font-family: Arial; 
            text-align: center;
            margin: 0;
            padding: 10px;
        }
        h1 {
            font-size: 24px;
            margin: 15px 0;
        }
        .readings { 
            margin: 15px auto;
            max-width: 100%;
        }
        .readings p {
            margin: 10px 0;
            font-size: 16px;
        }
        .progress-container {
            width: 90%;
            margin: 15px auto;
            background-color: #f0f0f0;
            border-radius: 5px;
            overflow: hidden;
        }
        .progress-bar {
            width: 0%;
            height: 25px;
            transition: width 0.03s ease-in-out;
        }
        .button-container {
            display: flex;
            flex-direction: row;
            justify-content: center;
            gap: 10px;
            flex-wrap: wrap;
            margin: 15px auto;
            max-width: 90%;
        }
        .button { 
            background-color: #4CAF50; 
            border: none; 
            color: white; 
            padding: 12px 24px; 
            text-decoration: none; 
            font-size: 14px;
            margin: 0;
            cursor: pointer;
            border-radius: 5px;
            flex: 1;
            min-width: 80px;
            touch-action: manipulation;
        }
        .button2 { background-color: #555555; }
        .button3 { background-color: #f4511e; }

        @media (max-width: 480px) {
            .button {
                padding: 10px 20px;
                font-size: 14px;
                width: 100%;
            }
            .progress-container {
                width: 95%;
            }
            .readings p {
                font-size: 14px;
            }
        }
    </style>
</head>
<body>
    <h1>ESP32 Monitor</h1>
    <div class="readings">
        <p>Min: <span id="min">--</span>V</p>
        <p>Max: <span id="max">--</span>V</p>
        <p>Avg: <span id="avg">--</span>V</p>
        <p>Current: <span id="current">--</span>A</p>
        <h2>ESC Telemetry</h2>
        <p>ESC Voltage: <span id="esc_voltage">--</span>V</p>
        <p>ESC RPM: <span id="esc_rpm">--</span></p>
        <p>ESC Temp: <span id="esc_temp">--</span>&deg;C</p>
        <div class="progress-container">
            <div id="progress-bar" class="progress-bar"></div>
        </div>
    </div>
    <div class="button-container">
        <button onclick="sendCommand('/light/on')" class="button">ON</button>
        <button onclick="sendCommand('/light/off')" class="button button2">OFF</button>
        <button onclick="sendCommand('/light/blink')" class="button button3" id="blinkBtn">BLINK</button>
    </div>
    <script>
        setInterval(() => {
            fetch('/data')
            .then(response => response.json())
            .then(data => {
                document.getElementById('min').textContent = data.min.toFixed(3);
                document.getElementById('max').textContent = data.max.toFixed(3);
                document.getElementById('avg').textContent = data.avg.toFixed(3);
                document.getElementById('current').textContent = data.current.toFixed(1);
                document.getElementById('esc_voltage').textContent = data.esc_voltage;
                document.getElementById('esc_rpm').textContent = data.esc_rpm;
                document.getElementById('esc_temp').textContent = data.esc_temp;
                
                const percentage = (data.avg / 3.3) * 100;
                const progressBar = document.getElementById('progress-bar');
                progressBar.style.width = percentage + '%';
                
                let color;
                if (percentage <= 25) {
                    color = '#007bff';
                } else if (percentage <= 50) {
                    color = '#28a745';
                } else if (percentage <= 75) {
                    color = '#ffc107';
                } else {
                    color = '#dc3545';
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

def read_esc_telemetry():
    global esc_voltage, esc_rpm, esc_temp
    while True:
        if uart.any():
            data = uart.read()
            telemetry = parse_kiss_telemetry(data)
            if telemetry:
                esc_voltage = telemetry['voltage']
                esc_rpm = telemetry['rpm']
                esc_temp = telemetry['temperature']
        time.sleep(0.02)

def read_fsr():
    global latest_voltage_min, latest_voltage_max, latest_voltage_avg
    while True:
        raw = 0
        min_val = float('inf')
        max_val = 0
        m = 100  # Reduced samples for testing
        i = m
        readings = []
        while i > 0:
            val = fsr_adc.read_uv()
            readings.append(val)
            i -= 1
            time.sleep_ms(1)  # Small delay between readings
        
        # Filter out outliers
        readings.sort()
        filtered = readings[10:-10]  # Remove 10 highest and lowest
        
        min_val = min(filtered)
        max_val = max(filtered)
        avg = sum(filtered) / len(filtered)
        
        latest_voltage_avg = 3.3 * avg / 865000
        latest_voltage_min = 3.3 * min_val / 865000
        latest_voltage_max = 3.3 * max_val / 865000
 #       print(f"Min: {latest_voltage_min:.3f}V, Max: {latest_voltage_max:.3f}V, Avg: {latest_voltage_avg:.3f}V")
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

_thread.start_new_thread(blink_cycle, ())

# Connect to WiFi
ip = connect_wifi('Bucha', 'yesandyes')

# Setup socket server
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(('', 80))
s.listen(5)


# Start background threads
_thread.start_new_thread(read_fsr, ())
_thread.start_new_thread(read_esc_telemetry, ())

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
            shunt_voltage = read_shunt_voltage()
            response = {
                'min': latest_voltage_min,
                'max': latest_voltage_max,
                'avg': latest_voltage_avg,
                'current': shunt_voltage / 0.0002,
                'esc_voltage': esc_voltage,
                'esc_rpm': esc_rpm,
                'esc_temp': esc_temp
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
        print('eError:', e)
        try:
            conn.close()
        except:
            pass


