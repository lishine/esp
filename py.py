import serial

# ser = serial.Serial("/dev/tty.usbmodem1234561", 115200)  # Change to your port
ser = serial.Serial("/dev/tty.usbmodem57340490621", 115200)  # Change to your port
while True:
    print(ser.readline().decode("utf-8").strip())
