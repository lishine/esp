#include "led_handler.h"
#include "globals.h"
// #include <esp_log.h> // Using Serial.printf instead

static const char *TAG = "LEDHandler";

// --- Define Global Variables (declared extern in globals.h) ---
TaskHandle_t ledNormalFlashTaskHandle = NULL;

// --- Removed set_led_state function ---
// No longer needed as complex states are gone.

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
    // Simple heartbeat blink: 1s ON, 1s OFF
    const TickType_t blinkInterval = pdMS_TO_TICKS(5000);
    bool ledIsOn = false;

    while (1) {
        // Simple heartbeat blink
        ledIsOn = !ledIsOn;
        digitalWrite(LED_PIN, ledIsOn ? HIGH : LOW);
        vTaskDelayUntil(&lastWakeTime, blinkInterval);
    }
}