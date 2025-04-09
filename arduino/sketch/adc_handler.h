#ifndef ADC_HANDLER_H
#define ADC_HANDLER_H

#include "globals.h"

// --- Function Declarations ---

/**
 * @brief Initializes the ADC in continuous mode with DMA.
 * Configures the specified channel, attenuation, bitwidth, and sample rate.
 * Starts the ADC conversion process.
 * @return true if initialization and start were successful, false otherwise.
 */
bool init_adc();

/**
 * @brief Task function for reading ADC data from the DMA buffer
 * and processing it to calculate frequency and RMS.
 * Handles zero-crossing detection, per-cycle calculations, averaging,
 * and updating the shared global variables.
 * @param pvParameters Task parameters (unused).
 */
void adcProcessingTask(void *pvParameters);

/**
 * @brief Reads a single raw ADC value from the configured channel.
 * NOTE: This function needs careful implementation. Reading a single value
 * while continuous DMA mode is active might require temporarily stopping
 * the continuous conversion, performing a single read using a different
 * ADC API (like adc1_get_raw), and then restarting continuous mode,
 * or potentially using a separate ADC unit/channel if available and suitable.
 * This implementation will attempt a simpler approach first.
 * @return The raw ADC reading (0-4095 for 12-bit), or -1 on error.
 */
int32_t read_current_adc_value();

/**
 * @brief Converts a raw ADC reading to millivolts using the calibrated
 * offset and scaling factor.
 * Formula: mV = ((raw_adc - adc_zero_offset) * adc_scaling_factor) + CAL_LOW_MV
 * @param raw_adc The raw ADC value (0-4095).
 * @return The calculated voltage in millivolts.
 */
float convert_adc_to_mv(int32_t raw_adc);


#endif // ADC_HANDLER_H