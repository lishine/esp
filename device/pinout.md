# ESP32-S3 N16R8 Pinout Summary (Project IO)

This document summarizes the GPIO pin usage for this project based on the current configuration. Please verify against your specific board version.

**Note:** Pin numbers refer to the GPIO number.

## GPIO Pin Usage

| GPIO | Name(s)      | Role          | Current Usage                | Status   | Notes                                       |
| ---- | ------------ | ------------- | ---------------------------- | -------- | ------------------------------------------- |
| 0    | GPIO0        | I/O, ADC1_CH0 |                              | Free     |                                             |
| 1    | GPIO1        | I/O, ADC1_CH1 |                              | Free     |                                             |
| 2    | GPIO2, STRAP | I/O, ADC1_CH2 | **ESC Telemetry (UART1 TX)** | **Used** |                                             |
| 3    | GPIO3        | I/O, ADC1_CH3 |                              | Free     |                                             |
| 4    | GPIO4        | I/O, ADC1_CH4 | **Motor Current (ADC)**      | **Used** |                                             |
| 5    | GPIO5        | I/O, ADC2_CH0 |                              | Free     |                                             |
| 6    | GPIO6        | I/O           |                              | Free     |                                             |
| 7    | GPIO7        | I/O           | **ESC Telemetry (UART1 RX)** | **Used** |                                             |
| 8    | GPIO8, STRAP | I/O           |                              | Free     | Was previously LED                          |
| 9    | GPIO9, STRAP | I/O, Strap    | **DS18B20 (OneWire)**        | **Used** | boot, pull up 10k on board, add another 10k |
| 10   | GPIO10       | I/O           | **Buzzer**                   | **Used** |                                             |
| 20   | GPIO20       | I/O, UART     | **NEO-7M GPS (UART1 RX)**    | **Used** |                                             |
| 21   | GPIO21       | I/O, UART     | **NEO-7M GPS (UART1 TX)**    | **Used** |                                             |
| 48   | GPIO48       | I/O           | **NeoPixel LED**             | **Used** |                                             |

## Power Pins

| Pin Name         | Attached Sensors / Usage                                     | Notes                          |
| ---------------- | ------------------------------------------------------------ | ------------------------------ |
| 5V               |                                                              |                                |
| 3V3 me6211 500ma | NEO-7M 67ma, DS18B20, Motor Current Sensor, Buzzer 25ma      | Output from onboard regulator. |
| GND              | DS18B20, Motor Current Sensor, ESC Telemetry, NEO-7M, Buzzer | Common ground.                 |
| RST / EN         |                                                              | Reset / Enable pin.            |

### Table 3-1. Default Configuration of Strapping Pins

| Strapping Pin | Default Configuration | Bit Value |
| ------------- | --------------------- | --------- |
| GPIO0         | Weak pull-up          | 1         |
| GPIO3         | Floating              | –         |
| GPIO45        | Weak pull-down        | 0         |
| GPIO46        | Weak pull-down        | 0         |

Please note that the ADC2_CH... analog functions (see Table 2-8 Analog Functions) cannot be used with Wi-Fi simul- taneously.

36,37 - probably input only!