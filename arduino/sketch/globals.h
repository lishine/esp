#ifndef GLOBALS_H
#define GLOBALS_H

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_adc/adc_continuous.h>
// #include <nvs.h> // Removed - NVS no longer used
#include <esp_adc_cal.h> // Added for ESP-IDF calibration
// --- Pin Definitions ---
const int ADC_PIN_NUM = 4; // GPIO4 for ADC input (Confirm this corresponds to ADC1_CH4)
const int LED_PIN = 8;
// const int BOOT_BUTTON_PIN = 9; // Removed

// --- I2C Configuration ---
const uint8_t I2C_SLAVE_ADDR = 0x08;

// --- ADC Configuration ---
// Choose ADC unit and channel based on ADC_PIN_NUM
// For GPIO4 on ESP32-C3, it's ADC1_CHANNEL_4
const adc_unit_t ADC_UNIT = ADC_UNIT_1;
const adc_channel_t ADC_CHANNEL = ADC_CHANNEL_4; // Verify this matches ADC_PIN_NUM for C3
const adc_atten_t ADC_ATTEN = ADC_ATTEN_DB_11; // ~0-2.5V or ~0-3.1V range depending on Vref/chip
const adc_bitwidth_t ADC_BITWIDTH = ADC_BITWIDTH_12; // 12-bit resolution (0-4095)
const int TARGET_SAMPLE_FREQ_HZ = 80000; 
const int ADC_READ_LEN = 256; // Number of samples to read from DMA buffer at once
const int ADC_DMA_BUF_SIZE = 1024 * 8; 
const int ADC_CONV_FRAME_SIZE = ADC_READ_LEN * SOC_ADC_DIGI_RESULT_BYTES; // Bytes per DMA frame
// const uint32_t DEFAULT_VREF = 1100; // Removed - No longer used

// --- Processing Configuration ---
const int NUM_CYCLES_AVERAGE = 10; // Average over 5 full cycles

// --- Calibration Configuration Removed ---
// const uint32_t CALIBRATION_HOLD_TIME_MS = 5000;
// const uint32_t MEAN_SET_HOLD_TIME_MS = 3000;
// const int CAL_LOW_MV = 1000;
// const int CAL_HIGH_MV = 2000;
// extern const char* NVS_NAMESPACE;
// extern const char* NVS_KEY_VOLTAGE_OFFSET;
// extern const char* NVS_KEY_SCALE_FACTOR;
// extern const char* NVS_KEY_MEAN_LEVEL;

// --- Global Variables (declared extern, defined in .cpp files) ---

// Handles
extern TaskHandle_t adcProcessingTaskHandle;
// extern TaskHandle_t buttonMonitorTaskHandle; // Removed
extern TaskHandle_t ledNormalFlashTaskHandle; // Kept for optional status LED
extern adc_continuous_handle_t adcHandle;
// extern nvs_handle_t nvsHandle; // Removed
extern esp_adc_cal_characteristics_t adc_chars; // Added for ESP-IDF calibration

// Calibration Values (Removed - Now handled by adc_chars)
// extern float adc_voltage_offset;
// extern float adc_scaling_factor;
// extern int32_t waveform_mean_level_adc; // Mean level calculated dynamically
// Processing Buffers & State
extern float cycle_periods[NUM_CYCLES_AVERAGE]; // Stores periods of last N cycles (in seconds)
extern float cycle_rms_values[NUM_CYCLES_AVERAGE]; // Stores RMS of last N cycles (in mV)
extern int cycle_buffer_index;
extern int cycle_count; // How many cycles measured since last average calculation

// Shared Results (updated by ADC task, read by I2C handler)
extern volatile uint16_t latest_freq_hz;
extern volatile uint16_t latest_rms_millivolts;

// LED State Control (Removed - No more button feedback)
// enum class LedState { NORMAL, CAL_MODE_ENTRY, CAL_ZERO_WAIT, CAL_ZERO_SET, CAL_SPAN_WAIT, CAL_SPAN_SET, MEAN_SET };
// extern volatile LedState currentLedState;


#endif // GLOBALS_H