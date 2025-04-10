#include "globals.h"

// --- Include header files for other modules ---
// These will contain the function declarations for initialization and tasks
#include "adc_handler.h"
#include "i2c_handler.h"
#include "led_handler.h" // Kept as optional status indicator

// --- Global Variables are now defined in their respective handler .cpp files ---

void setup() {
  Serial.begin(115200);
  delay(100); // Allow serial to initialize
  Serial.println("--- ESP32-C3 ADC/I2C Processor Starting ---"); // Use Serial for early debug
  delay(100);

  // 1. Set ADC Pin Mode (Important before ADC init)

  pinMode(ADC_PIN_NUM, INPUT);
  Serial.printf("DEBUG: Set GPIO %d to INPUT mode.\n", ADC_PIN_NUM);
  delay(100);


  // 2. Initialize Hardware Pins (LED only)
  Serial.println("DEBUG: Initializing GPIO pins...");
  delay(100);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW); // Start with LED off
  Serial.println("DEBUG: GPIO Pins Initialized.");
  delay(100);

  // 3. Initialize I2C Slave
  Serial.println("DEBUG: Initializing I2C Slave...");
  delay(100);
  init_i2c_slave(); // Function defined in i2c_handler.cpp
  Serial.println("DEBUG: I2C Slave Initialized.");
  delay(100);

  Serial.println("DEBUG: Initializing ADC Continuous Mode...");
  delay(100);
  if (!init_adc()) { // Function defined in adc_handler.cpp
      Serial.println("ADC Initialization Failed!");
      // Handle error - perhaps blink LED rapidly?
      while(1) {
          digitalWrite(LED_PIN, !digitalRead(LED_PIN));
          delay(100);
      }
  }
  Serial.println("DEBUG: ADC Initialized and Started.");
  delay(100);

  Serial.println("DEBUG: Creating FreeRTOS Tasks...");
  delay(100);

  xTaskCreatePinnedToCore(
      adcProcessingTask,      // Task function
      "ADC Processing Task",  // Name of the task
      8192,                   // Stack size in words (Increased from 4096)
      NULL,                   // Task input parameter
      4,                      // Priority of the task (Reduced from 5)
      &adcProcessingTaskHandle, // Task handle
      0                       // Core where the task should run (ESP32-C3 only has Core 0)
  );
  Serial.println("DEBUG: ADC Task Created.");
  delay(100);

Serial.println("DEBUG: Attempting to create LED Task..."); // <-- Added log
delay(100); // <-- Added delay for stability

BaseType_t ledTaskCreated = xTaskCreatePinnedToCore( // <-- Check return value
    ledNormalFlashTask,
    "LED Flash Task",
    2048, // Increased stack size for LED task
    NULL,
    2,     // Low priority
    &ledNormalFlashTaskHandle,
    0      // Core 0 for button/IO?
);

if (ledTaskCreated == pdPASS) { // <-- Check if creation succeeded
  Serial.println("DEBUG: LED Task Creation SUCCEEDED.");
} else {
  Serial.printf("DEBUG: LED Task Creation FAILED! Code: %d\n", ledTaskCreated); // <-- Print error code if failed
}
delay(100);
  delay(100);

  Serial.println("--- Setup Complete ---");
  delay(100);
}

void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000)); // Nothing critical here, yield time
}