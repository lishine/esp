/*
 * ESP32-C3 ADC Sampling Sketch
 * This sketch samples ADC1_4 (GPIO4) and prints raw value and voltage to Serial
 */

#include "driver/adc.h"

// Define the ADC pin (GPIO4 corresponds to ADC1_4 on ESP32-C3)
#define ADC1_CHANNEL ADC1_CHANNEL_4  // ADC1_4 corresponds to GPIO4 on ESP32-C3

// ADC characteristics
const float adcVoltage = 3.3;  // Reference voltage is 3.3V

void setup() {
  // Initialize Serial communication
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for Serial port to connect
  }
  
  // Configure ADC
  adc1_config_width(ADC_WIDTH_BIT_12);  // Set ADC resolution to 12 bits
  adc1_config_channel_atten(ADC1_CHANNEL, ADC_ATTEN_DB_11);  // 11dB attenuation (0-3.3V range)
  
  Serial.println("ESP32-C3 ADC1_4 (Pin 4) Sampling");
  Serial.println("--------------------------------");
}

void loop() {
  // Read the analog value
  int rawValue = adc1_get_raw(ADC1_CHANNEL);
  
  // Convert the raw value to voltage (3.3V reference with 12-bit resolution)
  float voltage = (rawValue / 4095.0) * adcVoltage;
  
  // Print the results to Serial
  Serial.print("Raw ADC Value: ");
  Serial.print(rawValue);
  Serial.print("\tVoltage: ");
  Serial.print(voltage, 3);  // Print with 3 decimal places
  Serial.println(" V");
  
  // Small delay before the next reading
  delay(1000);  // Sample once per second
}