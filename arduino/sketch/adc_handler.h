#ifndef ADC_HANDLER_H
#define ADC_HANDLER_H

#include "globals.h"

// --- Function Declarations ---

/**
 * @brief Initializes the ADC in continuous mode with DMA and performs ESP-IDF calibration.
 * Configures the specified channel, attenuation, bitwidth, and sample rate.
 * Checks for eFuse Two Point calibration data and characterizes the ADC.
 * Stores calibration characteristics in the global `adc_chars`.
 * Starts the ADC conversion process.
 * @return true if initialization, calibration, and start were successful, false otherwise.
 */
bool init_adc();

/**
 * @brief Task function for reading ADC data from the DMA buffer
 * and processing it to calculate frequency and RMS voltage.
 * Reads samples, calculates dynamic mean level (raw ADC), converts samples to mV
 * using ESP-IDF calibration (`esp_adc_cal_raw_to_voltage`), detects zero-crossings,
 * calculates frequency and RMS voltage per cycle, averages results over N cycles,
 * and updates the shared global variables (`latest_freq_hz`, `latest_rms_millivolts`).
 * @param pvParameters Task parameters (unused).
 */
void adcProcessingTask(void *pvParameters);

// Removed function declarations no longer needed:
// int32_t read_current_adc_value(); // Mean level is now dynamic
// float convert_adc_to_mv(int32_t raw_adc); // Using esp_adc_cal_raw_to_voltage directly


#endif // ADC_HANDLER_H