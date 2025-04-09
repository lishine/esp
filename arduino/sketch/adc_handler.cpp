#include "adc_handler.h"
#include "globals.h"
#include <cmath> // For sqrt
// #include <esp_adc_cal.h> // Included via globals.h now
// #include <esp_log.h> // Using Serial.printf instead
// #include <driver/adc.h> // Removed - adc1_get_raw no longer used

static const char *TAG = "ADCHandler";

// --- Define Global Variables (declared extern in globals.h) ---
esp_adc_cal_characteristics_t adc_chars; // Definition for ADC calibration characteristics
TaskHandle_t adcProcessingTaskHandle = NULL;
adc_continuous_handle_t adcHandle = NULL;
float cycle_periods[NUM_CYCLES_AVERAGE] = {0};
float cycle_rms_values[NUM_CYCLES_AVERAGE] = {0};
int cycle_buffer_index = 0;
int cycle_count = 0;

// static esp_adc_cal_characteristics_t *adc_chars = NULL; // Now a global extern variable `adc_chars`
// --- Static variables for processing state ---
static int32_t last_sample_mv = -1; // Initialize to invalid state (Using mV now)
static bool crossed_up = false;      // Tracks if last crossing was upwards
static uint32_t samples_in_current_cycle = 0;
static double sum_sq_current_cycle = 0.0; // Use double for accumulator precision
static double sum_mv_current_cycle = 0.0; // Accumulator for sum of mV in the current cycle

// --- Initialize ADC Continuous Mode & Perform Calibration ---
bool init_adc() {
    Serial.printf("I (%s): Initializing ADC and Calibration...\n", TAG);

    // 1. Check for eFuse Two Point calibration values
    esp_err_t ret_cal = esp_adc_cal_check_efuse(ESP_ADC_CAL_VAL_EFUSE_TP);
    if (ret_cal == ESP_ERR_NOT_SUPPORTED) {
        Serial.printf("E (%s): Calibration scheme not supported by this ESP32-C3!\n", TAG);
        return false;
    } else if (ret_cal == ESP_ERR_INVALID_VERSION) {
        Serial.printf("E (%s): Calibration version mismatch!\n", TAG);
        return false;
    } else if (ret_cal != ESP_OK) {
        Serial.printf("E (%s): eFuse Two Point calibration values not available! Cannot proceed.\n", TAG);
        return false; // Halt initialization as TP is required by the plan
    }

    // 2. Characterize ADC using Two Point values
    Serial.printf("I (%s): eFuse Two Point calibration values available. Characterizing...\n", TAG);
    // Note: adc_chars is now a global variable, no need to calloc here
    // Convert ADC_BITWIDTH enum for the calibration function
    adc_bits_width_t width_cal;
    switch (ADC_BITWIDTH) {
        case ADC_BITWIDTH_12: width_cal = ADC_WIDTH_BIT_12; break;
        // Add other cases if needed, though C3 likely only supports 12
        default: width_cal = ADC_WIDTH_BIT_12; break;
    }
    esp_adc_cal_value_t val_type = esp_adc_cal_characterize(ADC_UNIT, ADC_ATTEN, width_cal, 1100, &adc_chars); // Use literal 1100 as fallback (shouldn't be used with TP)
    if (val_type != ESP_ADC_CAL_VAL_EFUSE_TP) {
         Serial.printf("E (%s): Characterized using method (%d) other than expected Two Point! Cannot proceed.\n", TAG, val_type);
         // Consider clearing adc_chars or setting a flag? For now, fail init.
         return false;
    }
    Serial.printf("I (%s): Characterized successfully using Two Point Value.\n", TAG);

    // --- Continuous Mode Setup ---

    adc_continuous_handle_cfg_t adc_config = {
        // Allocate DMA buffer size. Larger can handle higher speeds/longer processing delays.
        // Must be multiple of SOC_ADC_DMA_MAX_BUFFER_SIZE if defined.
        .max_store_buf_size = ADC_DMA_BUF_SIZE, // Use increased buffer size from globals.h
        .conv_frame_size = ADC_CONV_FRAME_SIZE,
    };
    esp_err_t ret = adc_continuous_new_handle(&adc_config, &adcHandle);
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to create ADC continuous handle: %s\n", TAG, esp_err_to_name(ret));
        return false;
    }
    Serial.printf("I (%s): ADC continuous handle created.\n", TAG);

    // Revert to directly configuring the pattern using globals.h definitions
    adc_digi_pattern_config_t adc_pattern[1] = {0}; // Only one channel in the pattern
    adc_pattern[0].atten = ADC_ATTEN;
    adc_pattern[0].channel = ADC_CHANNEL; // Use the channel defined in globals.h
    adc_pattern[0].unit = ADC_UNIT;       // Use the unit defined in globals.h
    adc_pattern[0].bit_width = ADC_BITWIDTH;

    // Define the configuration for the continuous mode itself
    adc_continuous_config_t continuous_cfg = {
        .pattern_num = 1,
        .adc_pattern = adc_pattern,
        .sample_freq_hz = TARGET_SAMPLE_FREQ_HZ,
        .conv_mode = ADC_CONV_SINGLE_UNIT_1,
        .format = ADC_DIGI_OUTPUT_FORMAT_TYPE2,
    };

    // Pass the correct configuration structure type
    ret = adc_continuous_config(adcHandle, &continuous_cfg);
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to configure ADC continuous mode: %s\n", TAG, esp_err_to_name(ret));
        adc_continuous_deinit(adcHandle); // Clean up handle
        adcHandle = NULL;
        return false;
    }
    Serial.printf("I (%s): ADC continuous mode configured. Target Freq: %d Hz\n", TAG, TARGET_SAMPLE_FREQ_HZ);

    ret = adc_continuous_start(adcHandle);
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to start ADC continuous mode: %s\n", TAG, esp_err_to_name(ret));
        adc_continuous_deinit(adcHandle); // Clean up handle
        adcHandle = NULL;
        return false;
    }
    Serial.printf("I (%s): ADC continuous mode started.\n", TAG);
    return true;
}

void adcProcessingTask(void *pvParameters) {
    Serial.printf("I (%s): ADC Processing Task started.\n", TAG);

    uint8_t raw_result_buffer[ADC_CONV_FRAME_SIZE] = {0}; // Buffer to store raw DMA results
    uint32_t voltage_buffer[ADC_READ_LEN] = {0}; // Buffer to store converted voltage values (mV)
    uint32_t bytes_read = 0; // Number of bytes read from DMA

    // Initialize processing state
    static bool batch_valid = true; // Flag to track if the current averaging batch is valid
    // last_sample_raw = -1; // Removed, using last_sample_mv now
    crossed_up = false;
    last_sample_mv = -1; // Reset mV tracking too
    samples_in_current_cycle = 0;
    sum_sq_current_cycle = 0.0;
    sum_mv_current_cycle = 0.0; // Reset new accumulator
    cycle_buffer_index = 0;
    cycle_count = 0;
    
    // Initialize circular buffers (optional, they are global)
    for(int i=0; i<NUM_CYCLES_AVERAGE; ++i) {
        cycle_periods[i] = 0.0f;
        cycle_rms_values[i] = 0.0f;
    }

    uint8_t consecutive_timeouts = 0;
    uint32_t total_successful_reads = 0;
    static unsigned long lastPrintTime = 0; // For throttling voltage print
    
    Serial.printf("I (%s): ADC Task starting. Sample Rate: %d Hz, Read Length: %d samples, Avg Cycles: %d\n",
                 TAG, TARGET_SAMPLE_FREQ_HZ, ADC_READ_LEN, NUM_CYCLES_AVERAGE);
    while (1) {
        // Add periodic health report every ~5 seconds (assuming ~5ms per iteration)
        if (total_successful_reads % 1000 == 0 && total_successful_reads > 0) {
            Serial.printf("I (%s): ADC Task health: %lu successful reads, %u timeouts in current streak\n",
                         TAG, total_successful_reads, consecutive_timeouts);
        }
        if (!adcHandle) {
             Serial.printf("E (%s): ADC handle is NULL, skipping read.\n", TAG);
             vTaskDelay(pdMS_TO_TICKS(1000));
             continue;
        }

        esp_err_t ret = adc_continuous_read(adcHandle, raw_result_buffer, ADC_CONV_FRAME_SIZE, &bytes_read, 100);

        if (ret == ESP_OK) {
            consecutive_timeouts = 0; // Reset timeout counter on success
            total_successful_reads++;
            
            // --- Convert samples and calculate dynamic mean voltage ---
            int samples_in_buffer = bytes_read / SOC_ADC_DIGI_RESULT_BYTES;
            // Declare sum and count before the loop
            double voltage_sum = 0.0;
            int valid_samples = 0;
            for (int i = 0; i < samples_in_buffer; ++i) {
                 adc_digi_output_data_t *p = (adc_digi_output_data_t *)&raw_result_buffer[i * SOC_ADC_DIGI_RESULT_BYTES];
                 if (p->type2.channel == ADC_CHANNEL) {
                     int32_t raw_adc = p->type2.data; // Declare raw_adc here
                     // Convert to voltage using ESP-IDF calibration
                     voltage_buffer[i] = esp_adc_cal_raw_to_voltage(raw_adc, &adc_chars);
                     // Check if calibration seems valid (basic check)
                     // Note: esp_adc_cal_raw_to_voltage returns 0 if chars is invalid,
                     // which might be a valid reading. A more robust check might involve
                     // checking if adc_chars itself is valid if init failed partially.
                     // For now, assume init succeeded if we reach here.
                     voltage_sum += voltage_buffer[i];
                     valid_samples++;
                 } else { // Handle unexpected channel data
                     // Serial.printf("W (%s): Data received from unexpected channel %d\n", TAG, p->type2.channel);
                     voltage_buffer[i] = UINT32_MAX; // Mark as invalid
                 }
            }
            // Calculate dynamic mean using mV values
            double dynamic_mean_level_mv = (valid_samples > 0) ? (voltage_sum / valid_samples) : 0.0; // Fallback to 0.0 if no valid samples
            if (valid_samples == 0) {
                // Log this specific issue and invalidate the batch
                Serial.printf("W (%s): Zero valid samples in buffer, invalidating current batch.\n", TAG);
                batch_valid = false;
            }
            // --- Process Samples using converted voltages and dynamic mean voltage ---
            for (int i = 0; i < samples_in_buffer; i++) {
                // adc_digi_output_data_t *p = (adc_digi_output_data_t *)&raw_result_buffer[i * SOC_ADC_DIGI_RESULT_BYTES]; // No longer needed inside loop
                // Check if data is from the expected channel using type2 members
                // Ensure we only process valid, converted samples
                if (voltage_buffer[i] != UINT32_MAX) {
                    uint32_t current_mv = voltage_buffer[i]; // Use pre-converted voltage

                    // Initialize last_sample_mv on first valid run (Moved up)
                    if (last_sample_mv == -1) {
                         last_sample_mv = current_mv;
                    }

                    // --- Process Sample ---
                    samples_in_current_cycle++;
                    // Incrementally update sums for RMS calculation
                    double current_mv_double = (double)current_mv;
                    sum_mv_current_cycle += current_mv_double;
                    sum_sq_current_cycle += current_mv_double * current_mv_double;
                    
                    // --- Debug Print Voltage (approx once per second) ---
                    unsigned long currentTime = millis(); // Declare currentTime here
                    if (currentTime - lastPrintTime >= 1000) {
                        Serial.printf("D (%s): Sample mV: %lu\n", TAG, current_mv);
                        lastPrintTime = currentTime;
                    }
                    // --- End Debug Print ---

                    // Note: RMS calculation is deferred until a full cycle is detected
                    // --- Zero-Crossing Detection ---
                    // Check if the signal crossed the DYNAMIC mean voltage level
                    bool above_mean_now = (current_mv >= dynamic_mean_level_mv);
                    bool above_mean_before = (last_sample_mv >= dynamic_mean_level_mv);
                    if (above_mean_now != above_mean_before) { // A crossing occurred
                        if (above_mean_now) { // Crossed upwards (rising edge)
                            // Serial.printf("D (%s): Rising edge detected at sample %lu\n", TAG, samples_in_current_cycle); // Debug level
                            if (crossed_up) {
                                // --- Full Cycle Detected (Rising Edge to Rising Edge) ---
                                if (samples_in_current_cycle > 1) { // Need at least 2 samples for a valid cycle
                                    float period_seconds = (float)samples_in_current_cycle / TARGET_SAMPLE_FREQ_HZ;
                                    float frequency_hz = (period_seconds > 1e-9) ? (1.0f / period_seconds) : 0.0f;

                                    // --- Calculate Mean and RMS using accumulated values ---
                                    double mean_voltage_mv = sum_mv_current_cycle / samples_in_current_cycle;
                                    double mean_sq = mean_voltage_mv * mean_voltage_mv;
                                    double sum_sq_over_n = sum_sq_current_cycle / samples_in_current_cycle;
                                    float rms_mv = 0.0f;
                                    if (sum_sq_over_n >= mean_sq) { // Avoid sqrt of negative due to precision issues
                                       rms_mv = sqrt(sum_sq_over_n - mean_sq);
                                    } else {
                                       // This might happen with very stable DC signals or precision errors
                                       // Serial.printf("W (%s): sum_sq_over_n < mean_sq (%.4f < %.4f), setting RMS to 0\n", TAG, sum_sq_over_n, mean_sq);
                                       rms_mv = 0.0f; // Or handle as an error/warning
                                    }
                                    // --- End Incremental RMS Calculation ---

                                    Serial.printf("D (%s): Cycle %d: Samples=%lu, Period=%.6fs, Freq=%.2fHz, RMS=%.2fmV (Mean mV: %.2f)\n", TAG,
                                             cycle_count + 1, samples_in_current_cycle, period_seconds, frequency_hz, rms_mv, mean_voltage_mv); // Removed dynamic_mean_level_mv from this log

                                    // Store in circular buffers
                                    // Store frequency (Hz) and RMS (mV) in circular buffers
                                    cycle_periods[cycle_buffer_index] = frequency_hz; // Storing frequency now, not period
                                    cycle_rms_values[cycle_buffer_index] = rms_mv;

                                    cycle_count++;

                                    // --- Averaging ---
                                    if (cycle_count >= NUM_CYCLES_AVERAGE) {
                                        if (batch_valid) { // Check if the batch is still valid
                                            // --- Perform Averaging ---
                                            double sum_freq = 0.0;
                                            double sum_rms = 0.0;
                                            for (int j = 0; j < NUM_CYCLES_AVERAGE; ++j) {
                                                sum_freq += cycle_periods[j]; // Variable now holds frequency
                                                sum_rms += cycle_rms_values[j];
                                            }
                                            float avg_freq = sum_freq / NUM_CYCLES_AVERAGE;
                                            float avg_rms = sum_rms / NUM_CYCLES_AVERAGE;

                                            // Update volatile globals (atomically for uint16_t)
                                            latest_freq_hz = (uint16_t)round(avg_freq);
                                            latest_rms_millivolts = (uint16_t)round(avg_rms);

                                            Serial.printf("I (%s): Avg (%d cycles): Freq=%.2fHz (%u), RMS=%.2fmV (%u)\n", TAG,
                                                     NUM_CYCLES_AVERAGE, avg_freq, latest_freq_hz, avg_rms, latest_rms_millivolts);
                                        } else {
                                            // Log that the average calculation is being skipped
                                            Serial.printf("W (%s): Batch invalidated due to errors during collection, skipping average calculation.\n", TAG);
                                        }
                                        // Reset cycle count and validity flag regardless of whether averaging occurred
                                        cycle_count = 0;
                                        batch_valid = true; // Reset for the next batch
                                    }

                                    // Increment circular buffer index
                                    cycle_buffer_index = (cycle_buffer_index + 1) % NUM_CYCLES_AVERAGE;

                                } else {
                                     Serial.printf("W (%s): Cycle detected with <= 1 sample? Skipping and invalidating batch.\n", TAG);
                                     batch_valid = false; // Invalidate the batch if a short cycle occurs
                                }
                                // Reset for next cycle measurement
                                samples_in_current_cycle = 0;
                                sum_mv_current_cycle = 0.0; // Reset accumulators
                                sum_sq_current_cycle = 0.0;

                            } // else: First rising edge, don't calculate cycle yet
                            crossed_up = true; // Mark that we are now above mean after rising edge
                        } else { // Crossed downwards (falling edge)
                             // Serial.printf("D (%s): Falling edge detected at sample %lu\n", TAG, samples_in_current_cycle); // Debug level
                             crossed_up = false; // Mark that we are now below mean
                        }
                    } // End of crossing check

                    last_sample_mv = current_mv; // Update mV tracking for next iteration

                } // End check for valid sample (voltage_buffer[i] != UINT32_MAX)
            } // End second for loop (processing samples)
        } // <<< THIS BRACE CLOSES: if (ret == ESP_OK)
        else if (ret == ESP_ERR_TIMEOUT) { // Start else if block correctly
             consecutive_timeouts++;
             batch_valid = false; // Invalidate batch on timeout
             // Only log every few timeouts to avoid flooding the Serial console
             if (consecutive_timeouts == 1 || consecutive_timeouts % 5 == 0) {
                 Serial.printf("W (%s): ADC Read Timeout #%u! ADC might not be sampling at expected rate.\n",
                              TAG, consecutive_timeouts);
                 Serial.printf("D (%s): DMA buffer state - Samples: %lu, Cycle count: %d\n",
                              TAG, samples_in_current_cycle, cycle_count);
             }
             // Try a longer delay if we're experiencing many consecutive timeouts
             uint32_t delay_ms = (consecutive_timeouts > 10) ? 250 : 100;
             vTaskDelay(pdMS_TO_TICKS(delay_ms));
             // If we have too many consecutive timeouts, log a warning about potential hardware issues
             if (consecutive_timeouts == 20) {
                 Serial.printf("E (%s): 20 consecutive ADC timeouts! Hardware may need attention.\n", TAG);
             }
        } else { // Handle other errors
             Serial.printf("E (%s): ADC Read Error: %s. Invalidating current batch.\n", TAG, esp_err_to_name(ret));
             batch_valid = false; // Invalidate batch on other read errors
             // Consider error handling: re-init ADC?
             vTaskDelay(pdMS_TO_TICKS(1000));
        }

        vTaskDelay(pdMS_TO_TICKS(5)); // Adjust this value based on timing requirements

    } // End while(1)
}
