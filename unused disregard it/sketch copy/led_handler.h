#ifndef LED_HANDLER_H
#define LED_HANDLER_H

#include "globals.h"

// --- Function Declarations ---

/**
 * @brief Task function for handling the normal LED flashing pattern.
 * Can be overridden by calibration/feedback flashes.
 * @param pvParameters Task parameters (unused).
 */
void ledNormalFlashTask(void *pvParameters);

/**
 * @brief Helper function to flash the LED with a specific pattern.
 * This function blocks until the pattern is complete.
 * Used for immediate feedback during calibration/mean set.
 * @param pin The GPIO pin number of the LED.
 * @param count Number of times to flash.
 * @param on_ms Duration the LED stays ON in milliseconds.
 * @param off_ms Duration the LED stays OFF in milliseconds.
 */
void flash_led_blocking(int pin, int count, int on_ms, int off_ms);

/**
 * @brief Sets the desired LED state, allowing the ledNormalFlashTask
 * to be temporarily overridden for feedback patterns.
 * @param newState The desired LedState.
 */
void set_led_state(LedState newState);


#endif // LED_HANDLER_H