from machine import Pin, reset, ADC, UART, I2C
import machine
import time
import network
import socket
import _thread
import json
import struct
import time
import onewire, ds18x20
import sys

fsr_pin = Pin(4, Pin.IN)
fsr_adc = ADC(fsr_pin)
uart = UART(1, baudrate=115200, tx=21, rx=20, bits=8, parity=None, stop=1)


led = Pin(8, Pin.OUT)
led.on()
is_blinking = True

def led_turn_on():
    led.off()

def led_turn_off():
    led.on()

led_turn_on()

reset_cause = machine.reset_cause()
print("Reset cause:", reset_cause)

SHOULD_RUN = (machine.reset_cause() == machine.SOFT_RESET)

if not SHOULD_RUN:
    print("Stopping as requested by boot")
    import time
    while True:
        led.value(not led.value())
        time.sleep(0.1)  # Short sleep still allows interrupts

time.sleep(1)
led.value(not led.value())
time.sleep(1)
led.value(not led.value())
time.sleep(1)
led.value(not led.value())
time.sleep(1)
led.value(not led.value())

print("MMain thread free for uploads")

ds_pin = Pin(3, Pin.IN, Pin.PULL_UP)  # GPIO3 with internal pullup enabled
ds_sensor = ds18x20.DS18X20(onewire.OneWire(ds_pin))

roms = ds_sensor.scan()
if not roms:
    print("No DS18B20 sensors found!")

def read_temperature():
    try:
        # Start temperature conversion
        ds_sensor.convert_temp()
        # Wait for conversion to complete (750ms is typically enough)
        time.sleep_ms(750)
        
        # Read temperature from first sensor found
        if roms:
            temp = ds_sensor.read_temp(roms[0])
            return round(temp, 1)  # Round to 1 decimal place
        return None
    except Exception as e:
        print("Temperature read error:", e)
        return None


ds18_temperatures = []
# 0 - alum closer to mosfets (the flat without hole)
# 1 - upper heatsink (the flat with hole) 
# 2 - alum farther (the round cylinder)

def read_ds18b20_all():
    global ds18_temperatures
    while True:
        try:
            ds_sensor.convert_temp()
            time.sleep_ms(750)
            temps = [round(ds_sensor.read_temp(rom), 1) for rom in roms]
            ds18_temperatures = temps
        except Exception as e:
            print("DS18B20 error:", e)
        time.sleep(2)

def print_ds18_temperatures():
    while True:
        print("DS18 Temperatures:", ds18_temperatures)
        time.sleep(2)

# Start a new thread to print ds18_temperatures
# _thread.start_new_thread(print_ds18_temperatures, ())

# _thread.start_new_thread(read_ds18b20_all, ())


i2c = I2C(0, scl=Pin(10), sda=Pin(9), freq=100000)
# devices = i2c.scan()
# print("I2C devices found:", [hex(device) for device in devices])

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
    return raw * 2.5e-6  # Convert to volts (LSB = 2.5μV)

def read_bus_voltage():
    raw = read_register(BUS_VOLTAGE_REG)
    return raw * 1.25e-3  # Convert to volts (LSB = 1.25mV)

devices = i2c.scan()
print("I2C devices found:", [hex(device) for device in devices])


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

_thread.start_new_thread(blink_cycle, ())

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
                print("")
                # print(f"CRC mismatch: received {received_crc}, calculated {calculated_crc}")
                return None

            temperature = data[0]  # °C
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

esc_voltage = 0
esc_rpm = 0
esc_temp = 0
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
        time.sleep(0.2)

_thread.start_new_thread(read_esc_telemetry, ())


while True:
    shunt_voltage = read_shunt_voltage()
    t_close = ds18_temperatures[0] if len(ds18_temperatures) >= 1 else "N/A"
    t_upper = ds18_temperatures[1] if len(ds18_temperatures) >= 2 else "N/A"
    t_far = ds18_temperatures[2] if len(ds18_temperatures) >= 3 else "N/A"
    t_extra = ds18_temperatures[3] if len(ds18_temperatures) >= 4 else "N/A"
    print("voltage", esc_voltage, "rpm",esc_rpm,  "temperature",esc_temp,  "I", f"{abs(shunt_voltage / 0.0002):.1f}A")
    # print("T [ close", t_close, ", upper", t_upper, ", far", t_far, ", extra", t_extra, "] ; I", f"{abs(shunt_voltage / 0.0002):.1f}A")
    time.sleep(1)