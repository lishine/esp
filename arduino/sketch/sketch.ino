#include "globals.h"

// --- Include header files for other modules ---
// These will contain the function declarations for initialization and tasks
#include "calibration.h"
#include "adc_handler.h"
#include "button_handler.h"
#include "i2c_handler.h"
#include "led_handler.h"

// --- Define Global Variables (declared extern in globals.h) ---
TaskHandle_t adcProcessingTaskHandle = NULL;
TaskHandle_t buttonMonitorTaskHandle = NULL;
TaskHandle_t ledNormalFlashTaskHandle = NULL;
adc_continuous_handle_t adcHandle = NULL;
nvs_handle_t nvsHandle = 0; // NVS handle is uint32_t

// Default calibration values (will be overwritten by NVS or calibration)
float adc_voltage_offset = 0.0f; // Default: Assume 0 mV offset initially
float adc_scaling_factor = 1.0; // Default: Assume 1 mV per ADC count initially
int32_t waveform_mean_level_adc = 2048; // Default: Midpoint for 12-bit ADC

// Processing Buffers & State
float cycle_periods[NUM_CYCLES_AVERAGE] = {0};
float cycle_rms_values[NUM_CYCLES_AVERAGE] = {0};
int cycle_buffer_index = 0;
int cycle_count = 0;

// Shared Results
volatile uint16_t latest_freq_hz = 0;
volatile uint16_t latest_rms_millivolts = 0;

// LED State Control
volatile LedState currentLedState = LedState::NORMAL;

// --- Define NVS Constants (declared extern in globals.h) ---
const char* NVS_NAMESPACE = "adc_cal";
const char* NVS_KEY_VOLTAGE_OFFSET = "volt_offs"; // Renamed key
const char* NVS_KEY_SCALE_FACTOR = "scale_fact";
const char* NVS_KEY_MEAN_LEVEL = "mean_lvl";

// --- Setup Function ---
void setup() {
  Serial.begin(115200);
  delay(100); // Allow serial to initialize
  Serial.println("--- ESP32-C3 ADC/I2C Processor Starting ---"); // Use Serial for early debug
  // Set ESP log level to Verbose for all tags to ensure task logs appear
  Serial.println("DEBUG: Set ESP log level to VERBOSE");
  delay(100);

  // 1. Initialize NVS
  Serial.println("DEBUG: Initializing NVS...");
  delay(100);
  if (!init_nvs()) {
      Serial.println("NVS Initialization Failed!");
      // Consider halting or specific error handling
      // For now, continue with default calibration values
  } else {
      Serial.println("DEBUG: NVS Initialized.");
      delay(100);
      // 2. Load Calibration Data
      Serial.println("DEBUG: Loading calibration data from NVS...");
      delay(100);
      load_calibration_nvs(); // Function defined in calibration.cpp
      Serial.printf("DEBUG: Loaded Offset: %.4f mV, Scale Factor: %.4f, Mean Level: %ld\n",
                    adc_voltage_offset, adc_scaling_factor, waveform_mean_level_adc);
      delay(100);
      // Explicitly set ADC pin to INPUT mode before ADC init
      pinMode(ADC_PIN_NUM, INPUT);
      Serial.printf("DEBUG: Set GPIO %d to INPUT mode.\n", ADC_PIN_NUM);
      delay(100);
  }


  // 3. Initialize Hardware Pins (Button, LED)
  Serial.println("DEBUG: Initializing GPIO pins...");
  delay(100);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BOOT_BUTTON_PIN, INPUT_PULLUP);
  digitalWrite(LED_PIN, LOW); // Start with LED off
  Serial.println("DEBUG: GPIO Pins Initialized.");
  delay(100);

  // 4. Initialize I2C Slave
  Serial.println("DEBUG: Initializing I2C Slave...");
  delay(100);
  init_i2c_slave(); // Function defined in i2c_handler.cpp
  Serial.println("DEBUG: I2C Slave Initialized.");
  delay(100);

  // 5. Initialize and Start ADC Continuous Mode
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

  // 6. Create FreeRTOS Tasks
  Serial.println("DEBUG: Creating FreeRTOS Tasks...");
  delay(100);

  xTaskCreatePinnedToCore(
      adcProcessingTask,      // Task function
      "ADC Processing Task",  // Name of the task
      4096,                   // Stack size in words
      NULL,                   // Task input parameter
      5,                      // Priority of the task (higher number = higher priority)
      &adcProcessingTaskHandle, // Task handle
      0                       // Core where the task should run (ESP32-C3 only has Core 0)
  );
  Serial.println("DEBUG: ADC Task Created.");
  delay(100);

  xTaskCreatePinnedToCore(
      buttonMonitorTask,
      "Button Monitor Task",
      2048, // Smaller stack for button monitoring
      NULL,
      3,     // Lower priority than ADC
      &buttonMonitorTaskHandle,
      0      // Core 0 for button/IO?
  );
   Serial.println("DEBUG: Button Task Created.");
   delay(100);

  xTaskCreatePinnedToCore(
      ledNormalFlashTask,
      "LED Flash Task",
      2048, // Increased stack size for LED task
      NULL,
      2,     // Low priority
      &ledNormalFlashTaskHandle,
      0      // Core 0 for button/IO?
  );
  Serial.println("DEBUG: LED Task Created.");
  delay(100);

  Serial.println("--- Setup Complete ---");
  delay(100);
}

// --- Main Loop ---
// The main loop is often minimal when using FreeRTOS tasks
void loop() {
  vTaskDelay(pdMS_TO_TICKS(1000)); // Nothing critical here, yield time

}