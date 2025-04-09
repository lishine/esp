#include "led_handler.h"
#include "globals.h"
// #include <esp_log.h> // Using Serial.printf instead

static const char *TAG = "LEDHandler";

// --- Set LED State ---
// This function allows other tasks (like button handler) to request
// a temporary override of the normal flashing pattern.
void set_led_state(LedState newState) {
    // This simple implementation directly sets the global state.
    // A more robust implementation might use a queue or mutex
    // if contention between tasks setting the state is a concern.
    currentLedState = newState;
    // Serial.printf("D (%s): LED State changed to: %d\n", TAG, (int)newState); // Debug level, maybe too verbose
}

// --- Blocking LED Flash ---
// Used for immediate feedback (e.g., after calibration step)
void flash_led_blocking(int pin, int count, int on_ms, int off_ms) {
    Serial.printf("I (%s): Flashing LED %d times (On: %dms, Off: %dms)\n", TAG, count, on_ms, off_ms);
    pinMode(pin, OUTPUT); // Ensure pin is output
    for (int i = 0; i < count; ++i) {
        digitalWrite(pin, HIGH);
        vTaskDelay(pdMS_TO_TICKS(on_ms)); // Use vTaskDelay for FreeRTOS compatibility
        // Only turn off if not the last pulse or if off_ms > 0
        if (i < count - 1 || off_ms > 0) {
             digitalWrite(pin, LOW);
             if (off_ms > 0) {
                vTaskDelay(pdMS_TO_TICKS(off_ms));
             }
        }
    }
     // Ensure LED is left off after flashing sequence
     digitalWrite(pin, LOW);
     // Serial.printf("D (%s): Blocking flash complete.\n", TAG); // Debug level
}


// --- Normal LED Flash Task ---
void ledNormalFlashTask(void *pvParameters) {
    Serial.printf("I (%s): LED Normal Flash Task started.\n", TAG);
    TickType_t lastWakeTime = xTaskGetTickCount();
    const TickType_t normalOnTime = pdMS_TO_TICKS(4000);
    const TickType_t normalOffTime = pdMS_TO_TICKS(4000);
    bool ledIsOn = false;

    while (1) {
        // Serial.println("DEBUG: LED Task Loop Start"); // Removed basic task running check
        // Check if a temporary state override is active
        LedState stateSnapshot = currentLedState; // Take snapshot to avoid race conditions

        switch (stateSnapshot) {
            case LedState::NORMAL:
                // Normal 4s ON / 4s OFF cycle
                ledIsOn = !ledIsOn;
                digitalWrite(LED_PIN, ledIsOn ? HIGH : LOW);
                // Serial.printf("D (%s): Normal LED state: %s\n", TAG, ledIsOn ? "ON" : "OFF"); // Debug level
                vTaskDelayUntil(&lastWakeTime, ledIsOn ? normalOnTime : normalOffTime);
                break;

            // --- Handle Feedback Patterns (Blocking flashes are called directly) ---
            // These states are set by other tasks, and this task just waits
            // until the state is set back to NORMAL. The actual flashing for
            // feedback happens via direct calls to flash_led_blocking from
            // the button handler task immediately after setting the state.
            case LedState::CAL_MODE_ENTRY:
            case LedState::CAL_ZERO_WAIT:
            case LedState::CAL_ZERO_SET:
            case LedState::CAL_SPAN_WAIT:
            case LedState::CAL_SPAN_SET:
            case LedState::MEAN_SET:
                // While in a feedback state, this task just yields,
                // waiting for the button task to finish the feedback
                // and set the state back to NORMAL.
                // Serial.printf("D (%s): LED Task yielding, waiting for state NORMAL (current: %d)\n", TAG, (int)stateSnapshot); // Debug level
                digitalWrite(LED_PIN, LOW); // Ensure LED is off during feedback pauses
                ledIsOn = false; // Reset normal cycle state
                vTaskDelayUntil(&lastWakeTime, pdMS_TO_TICKS(100)); // Check state frequently
                break;

            default:
                Serial.printf("W (%s): Unhandled LED state: %d\n", TAG, (int)stateSnapshot);
                currentLedState = LedState::NORMAL; // Recover to normal state
                vTaskDelayUntil(&lastWakeTime, pdMS_TO_TICKS(100));
                break;
        }
    }
}