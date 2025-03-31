import serial

ser = serial.Serial("/dev/tty.usbmodem101", 115200)  # Change to your port
while True:
    print(ser.readline().decode("utf-8").strip())
