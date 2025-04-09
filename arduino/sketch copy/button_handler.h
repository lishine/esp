#ifndef BUTTON_HANDLER_H
#define BUTTON_HANDLER_H

#include "globals.h"

// --- Function Declarations ---

/**
 * @brief Task function for monitoring the button state.
 * Handles debouncing, detects short and long presses,
 * and triggers calibration or mean level setting actions.
 * @param pvParameters Task parameters (unused).
 */
void buttonMonitorTask(void *pvParameters);

/**
 * @brief Reads the current raw ADC value.
 * This function might be better placed in adc_handler.h/cpp
 * if it needs access to ADC configuration details, but for simplicity
 * in triggering calibration, it can be declared here or called
 * via a function pointer/interface if needed.
 * Assumes ADC is already initialized.
 * @return The current raw ADC reading, or -1 on error.
 */
int32_t read_current_adc_value(); // Needs implementation, likely in adc_handler.cpp


#endif // BUTTON_HANDLER_H