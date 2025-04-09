#include "i2c_handler.h"
#include "globals.h"
#include <Wire.h> // Arduino I2C library
// #include <esp_log.h> // Using Serial.printf instead

static const char *TAG = "I2CHandler";

// --- Define Global Variables (declared extern in globals.h) ---
volatile uint16_t latest_freq_hz = 0;
volatile uint16_t latest_rms_millivolts = 0;

// --- Initialize I2C Slave ---
void init_i2c_slave() {
    // Note: Wire.begin(address) automatically sets SDA/SCL pins based on board definition
    // For ESP32, default is usually GPIO21 (SDA), GPIO22 (SCL).
    // We need GPIO0 (SDA) and GPIO1 (SCL) as per pinout.md.
    // Explicitly set pins *before* Wire.begin().
    bool success = Wire.setPins(0, 1); // SDA=GPIO0, SCL=GPIO1
    if (!success) {
         Serial.printf("E (%s): Failed to set I2C pins (SDA=0, SCL=1).\n", TAG);
         // Handle error appropriately
         return;
    }
    Serial.printf("I (%s): Set I2C pins: SDA=0, SCL=1\n", TAG);

    Wire.begin(I2C_SLAVE_ADDR);
    Serial.printf("I (%s): I2C Slave started with address 0x%02X\n", TAG, I2C_SLAVE_ADDR);

    // Register the request handler function
    Wire.onRequest(i2cRequestEvent);
    Serial.printf("I (%s): I2C onRequest handler registered.\n", TAG);
}

// --- I2C Request Event Handler ---
// This function is called in an ISR context when the master requests data
void i2cRequestEvent() {
    // Prepare the data buffer (4 bytes: uint16_t freq, uint16_t rms)
    uint8_t buffer[4];

    // Read the volatile global variables atomically (should be safe for uint16_t on ESP32)
    uint16_t freq = latest_freq_hz;
    uint16_t rms = latest_rms_millivolts;

    // Serial.printf("D (%s): I2C request received. Sending Freq: %u Hz, RMS: %u mV\n", TAG, freq, rms); // Debug level

    // Pack the data (assuming Little Endian for both ESP32s)
    buffer[0] = freq & 0xFF;         // Frequency LSB
    buffer[1] = (freq >> 8) & 0xFF;  // Frequency MSB
    buffer[2] = rms & 0xFF;          // RMS LSB
    buffer[3] = (rms >> 8) & 0xFF;   // RMS MSB

    // Send the buffer to the master
    size_t bytes_written = Wire.write(buffer, sizeof(buffer));

    if (bytes_written != sizeof(buffer)) {
         Serial.printf("W (%s): I2C write failed or wrote partial data (%d bytes)\n", TAG, bytes_written);
    } else {
         // Serial.printf("D (%s): Sent %d bytes via I2C.\n", TAG, bytes_written); // Debug level
    }
}