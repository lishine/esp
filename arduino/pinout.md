# ESP32-C3 SuperMini Pinout Summary (Project IO)

This document summarizes the GPIO pin usage for this project based on the current configuration. Please verify against your specific board version.

**Note:** Pin numbers refer to the GPIO number.

## GPIO Pin Usage

| GPIO | Name(s)      | Role          | Current Usage           | Status   | Notes                      |
| ---- | ------------ | ------------- | ----------------------- | -------- | -------------------------- |
| 0    | GPIO0        | I/O, ADC1_CH0 | i2c sda 2.2k pull up    | **Used** |                            |
| 1    | GPIO1        | I/O, ADC1_CH1 | i2c scl 2.2k pull up    | **Used** |                            |
| 2    | GPIO2, STRAP | I/O, ADC1_CH2 |                         | Free     |                            |
| 3    | GPIO3        | I/O, ADC1_CH3 |                         | Free     |                            |
| 4    | GPIO4        | I/O, ADC1_CH4 | **Motor Current (ADC)** | **Used** |                            |
| 5    | GPIO5        | I/O, ADC2_CH0 |                         | Free     |                            |
| 6    | GPIO6        | I/O           |                         | Free     |                            |
| 7    | GPIO7        | I/O           |                         | Free     |                            |
| 8    | GPIO8, STRAP | I/O           |                         | Free     |                            |
| 9    | GPIO9, STRAP | I/O, Strap    |                         | Free     | boot, pull up 10k on board |
| 10   | GPIO10       | I/O           |                         | Free     |                            |
| 20   | GPIO20       | I/O, UART     |                         | Free     |                            |
| 21   | GPIO21       | I/O, UART     |                         | Free     |                            |

## Power Pins

| Pin Name         | Attached Sensors / Usage                                     | Notes                          |
| ---------------- | ------------------------------------------------------------ | ------------------------------ |
| 5V               |                                                              |                                |
| 3V3 me6211 500ma | NEO-7M 67ma, DS18B20, Motor Current Sensor, Buzzer 25ma      | Output from onboard regulator. |
| GND              | DS18B20, Motor Current Sensor, ESC Telemetry, NEO-7M, Buzzer | Common ground.                 |
| RST / EN         |                                                              | Reset / Enable pin.            |
