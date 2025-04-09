#include "button_handler.h"
#include "globals.h"
#include "calibration.h" // For saving calibration values
#include "led_handler.h"   // For LED feedback
// #include <esp_log.h> // Using Serial.printf instead

static const char *TAG = "ButtonHandler";

// Debounce parameters
const TickType_t DEBOUNCE_DELAY = pdMS_TO_TICKS(50); // 50 ms debounce time

// Calibration state machine
enum class CalState { IDLE, WAIT_FOR_LOW_REF, WAIT_FOR_HIGH_REF };
static CalState currentCalState = CalState::IDLE;
static int32_t cal_low_reading_temp = 0; // Temporary storage during calibration

// --- Button Monitor Task ---
void buttonMonitorTask(void *pvParameters) {
    Serial.printf("I (%s): Button Monitor Task started.\n", TAG);

    bool lastButtonState = HIGH; // Assuming INPUT_PULLUP, HIGH = not pressed
    bool currentButtonState = HIGH;
    TickType_t pressStartTime = 0;
    bool longPressTriggered = false;
    bool shortPressActionDone = false; // Flag to ensure short press action only happens once per press

    while (1) {
        // Serial.println("DEBUG: Button Task Loop Start"); // Removed basic task running check
        currentButtonState = digitalRead(BOOT_BUTTON_PIN);
        TickType_t currentTime = xTaskGetTickCount();

        // --- Debouncing ---
        if (currentButtonState != lastButtonState) {
            vTaskDelay(DEBOUNCE_DELAY);
            currentButtonState = digitalRead(BOOT_BUTTON_PIN); // Read again after delay
        }

        // --- State Change Detected ---
        if (currentButtonState != lastButtonState) {
            if (currentButtonState == LOW) { // Button Pressed
                pressStartTime = currentTime;
                longPressTriggered = false;
                shortPressActionDone = false; // Reset short press flag on new press
                Serial.printf("I (%s): Button Pressed.\n", TAG);
            } else { // Button Released
                Serial.printf("I (%s): Button Released.\n", TAG);
                TickType_t pressDuration = currentTime - pressStartTime;

                if (currentCalState == CalState::IDLE) { // --- Normal Operation Release ---
                    if (!longPressTriggered && !shortPressActionDone && pressDuration < MEAN_SET_HOLD_TIME_MS) {
                        // --- Short Press Action: Set Mean Level ---
                        Serial.printf("I (%s): Short press detected (duration: %lu ms). Setting mean level.\n", TAG, pdTICKS_TO_MS(pressDuration));
                        int32_t mean_reading = read_current_adc_value(); // Get current ADC reading
                        if (mean_reading != -1) {
                            waveform_mean_level_adc = mean_reading;
                            save_mean_level_nvs(waveform_mean_level_adc);
                            Serial.printf("I (%s): Set waveform mean level to ADC value: %ld\n", TAG, waveform_mean_level_adc);
                            // Provide LED feedback (blocking flash)
                            flash_led_blocking(LED_PIN, 2, 100, 100); // Example: 2 quick flashes
                        } else {
                            Serial.printf("E (%s): Failed to read ADC value for mean level setting.\n", TAG);
                            flash_led_blocking(LED_PIN, 5, 50, 50); // Error flash
                        }
                        shortPressActionDone = true; // Mark action as done
                    } else if (longPressTriggered) {
                         Serial.printf("I (%s): Button released after long press (calibration mode was entered).\n", TAG);
                         // No action needed on release after long press triggered cal mode
                    } else {
                         Serial.printf("I (%s): Button released (duration: %lu ms), no short press action taken.\n", TAG, pdTICKS_TO_MS(pressDuration));
                    }
                } else { // --- Calibration Mode Release ---
                     if (!shortPressActionDone) { // Only act if short press action wasn't already done for this press
                        if (currentCalState == CalState::WAIT_FOR_LOW_REF) {
                            // --- Calibration Step 1: Capture Low Ref ---
                            Serial.printf("I (%s): Button released in CAL_WAIT_LOW_REF state. Capturing low reference.\n", TAG);
                            cal_low_reading_temp = read_current_adc_value();
                            if (cal_low_reading_temp != -1) {
                                Serial.printf("I (%s): Captured Low Ref ADC: %ld\n", TAG, cal_low_reading_temp);
                                set_led_state(LedState::CAL_ZERO_SET); // Signal success
                                flash_led_blocking(LED_PIN, 1, 500, 0); // 1 long flash
                                currentCalState = CalState::WAIT_FOR_HIGH_REF; // Move to next state
                                set_led_state(LedState::CAL_SPAN_WAIT); // Signal waiting for next step
                                Serial.printf("I (%s): Now waiting for High Reference (apply %d mV and press button).\n", TAG, CAL_HIGH_MV);
                            } else {
                                Serial.printf("E (%s): Failed to read ADC for low reference.\n", TAG);
                                flash_led_blocking(LED_PIN, 5, 50, 50); // Error flash
                                // Optionally: Exit calibration mode on error?
                                // currentCalState = CalState::IDLE;
                                // set_led_state(LedState::NORMAL);
                            }
                        } else if (currentCalState == CalState::WAIT_FOR_HIGH_REF) {
                            // --- Calibration Step 2: Capture High Ref & Calculate ---
                            Serial.printf("I (%s): Button released in CAL_WAIT_HIGH_REF state. Capturing high reference.\n", TAG);
                            int32_t high_reading = read_current_adc_value();
                            if (high_reading != -1) {
                                Serial.printf("I (%s): Captured High Ref ADC: %ld\n", TAG, high_reading);
                                int32_t new_offset;
                                float new_factor;
                                if (calculate_calibration_factors(cal_low_reading_temp, high_reading, new_offset, new_factor)) {
                                    adc_zero_offset = new_offset;
                                    adc_scaling_factor = new_factor;
                                    save_zero_offset_nvs(adc_zero_offset);
                                    save_scaling_factor_nvs(adc_scaling_factor);
                                    Serial.printf("I (%s): Calibration successful. Offset: %ld, Factor: %.6f\n", TAG, adc_zero_offset, adc_scaling_factor);
                                    set_led_state(LedState::CAL_SPAN_SET); // Signal success
                                    flash_led_blocking(LED_PIN, 3, 150, 150); // 3 quick flashes
                                } else {
                                    Serial.printf("E (%s): Calibration factor calculation failed.\n", TAG);
                                    flash_led_blocking(LED_PIN, 5, 50, 50); // Error flash
                                }
                            } else {
                                Serial.printf("E (%s): Failed to read ADC for high reference.\n", TAG);
                                flash_led_blocking(LED_PIN, 5, 50, 50); // Error flash
                            }
                            // Exit calibration mode regardless of calculation success/failure
                            Serial.printf("I (%s): Exiting Calibration Mode.\n", TAG);
                            currentCalState = CalState::IDLE;
                            set_led_state(LedState::NORMAL); // Return LED task to normal
                        }
                        shortPressActionDone = true; // Mark action as done for this press
                     }
                }
            }
            lastButtonState = currentButtonState; // Update last state
        }

        // --- Check for Long Press (while button is held down) ---
        if (currentButtonState == LOW && !longPressTriggered) {
            TickType_t holdDuration = currentTime - pressStartTime;
            if (currentCalState == CalState::IDLE && holdDuration >= CALIBRATION_HOLD_TIME_MS) {
                // --- Long Press Action: Enter Calibration Mode ---
                Serial.printf("I (%s): Long press detected (%lu ms). Entering Calibration Mode.\n", TAG, pdTICKS_TO_MS(holdDuration));
                longPressTriggered = true; // Prevent re-triggering during the same hold
                currentCalState = CalState::WAIT_FOR_LOW_REF; // Set calibration state
                set_led_state(LedState::CAL_MODE_ENTRY); // Signal entry visually
                flash_led_blocking(LED_PIN, 5, 100, 100); // Example: 5 rapid flashes
                set_led_state(LedState::CAL_ZERO_WAIT); // Signal waiting for first step
                Serial.printf("I (%s): Calibration Mode Entered. Apply %d mV and press button.\n", TAG, CAL_LOW_MV);
                // Note: ADC processing task should ideally be paused here if possible
            }
        }

        vTaskDelay(pdMS_TO_TICKS(20)); // Check button state periodically
    }
}

// NOTE: read_current_adc_value() needs to be implemented, likely in adc_handler.cpp
// It should perform a single ADC read (or average a few) outside the continuous DMA context.
// This might require temporarily stopping/starting the continuous ADC or using a separate ADC configuration.
// For now, we assume it exists and returns a value or -1 on error.