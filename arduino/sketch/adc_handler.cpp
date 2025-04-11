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

// static esp_adc_cal_characteristics_t *adc_chars = NULL; // Now a global extern variable `adc_chars`
// --- Static variables for processing state ---
static int32_t last_sample_mv = -1; // Initialize to invalid state (Using mV now)

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
        .flags = 0 // Added to address warning
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

    // Calculate max samples for the batch based on lowest expected frequency (20Hz) and average count
    const uint32_t MAX_SAMPLES_PER_BATCH = (uint32_t)((1.0 / MIN_EXPECTED_FREQ_HZ) * NUM_CYCLES_AVERAGE * TARGET_SAMPLE_FREQ_HZ);
    Serial.printf("I (%s): Max samples per batch set to %lu\n", TAG, MAX_SAMPLES_PER_BATCH);


    uint8_t raw_result_buffer[ADC_CONV_FRAME_SIZE] = {0}; // Buffer to store raw DMA results
    uint32_t voltage_buffer[ADC_READ_LEN] = {0}; // Buffer to store converted voltage values (mV)
    uint32_t bytes_read = 0; // Number of bytes read from DMA

    // Initialize processing state
    static bool batch_valid = true; // Flag to track if the current averaging batch is valid
    static uint32_t samples_in_current_batch = 0; // Counter for total valid samples within the current batch
    static double sum_mv_current_batch = 0.0;     // Accumulator for sum of mV for the entire batch
    static double sum_sq_current_batch = 0.0;    // Accumulator for sum of squares of mV for the entire batch
    static uint32_t valid_samples_in_current_batch = 0; // Counter for valid samples in the entire batch (for DC RMS)

    last_sample_mv = -1;

    uint8_t consecutive_timeouts = 0;
    uint32_t total_successful_reads = 0;
    static unsigned long lastPrintTime = 0; // For throttling voltage print
    
    Serial.printf("I (%s): ADC Task starting. Sample Rate: %d Hz, Read Length: %d samples, Avg Cycles: %d\n",
                 TAG, TARGET_SAMPLE_FREQ_HZ, ADC_READ_LEN, NUM_CYCLES_AVERAGE);

    static uint32_t actual_batch_start_time = 0; // Track start time of the batch interval
    if (actual_batch_start_time == 0) { // Initialize on first run
        actual_batch_start_time = millis();
    }
 
    // Timing statistics for adc_continuous_read within a batch
    uint64_t batch_read_time_sum_us = 0;
    uint32_t batch_read_time_min_us = UINT32_MAX;
    uint32_t batch_read_time_max_us = 0;
    uint32_t batch_read_count = 0;
    uint64_t total_batch_samples_read = 0; // Accumulator for total samples read in main loop
    uint32_t batch_samples_min = UINT32_MAX; // Min samples per main read call
    uint32_t batch_samples_max = 0;          // Max samples per main read call
 
    // Statistics for processing time between main reads
    uint64_t processing_time_sum_us = 0;
    uint32_t processing_time_min_us = UINT32_MAX;
    uint32_t processing_time_max_us = 0;
    uint32_t processing_read_count = 0; // Count of reads used for processing time calc
    static uint32_t last_read_complete_time_us = 0; // Time the previous read finished
 
    // Timing statistics for adc_continuous_read within the discard loop
    uint64_t discard_read_time_sum_us = 0;
    uint32_t discard_read_time_min_us = UINT32_MAX;
    uint32_t discard_read_time_max_us = 0;
    uint32_t discard_read_count = 0;
    uint64_t total_discard_samples_read = 0; // Accumulator for total samples read in discard loop
    uint32_t discard_samples_min = UINT32_MAX; // Min samples per discard read call
    uint32_t discard_samples_max = 0;          // Max samples per discard read call
    uint32_t SAFETY_MARGIN_MS = 3;          // Max samples per discard read call
    uint32_t theoretical_acquisition_time_ms = (ADC_READ_LEN * 1000.0) / TARGET_SAMPLE_FREQ_HZ;
    // uint32_t processing_time_ms = 9 * ADC_READ_LEN / 512; // Removed unused variable

    while (1)
    {
        // uint32_t batch_start_time = millis(); // REMOVED - No longer needed here
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

        uint32_t read_start_us = micros(); // Start timing
        esp_err_t ret = adc_continuous_read(adcHandle, raw_result_buffer, ADC_CONV_FRAME_SIZE, &bytes_read, 30);
        uint32_t read_end_us = micros(); // End timing
 
        if (ret == ESP_OK) {
            uint32_t duration_us = read_end_us - read_start_us;
            batch_read_time_sum_us += duration_us;
            batch_read_time_min_us = min(batch_read_time_min_us, duration_us);
            batch_read_time_max_us = max(batch_read_time_max_us, duration_us);
            batch_read_count++;
 
            // Calculate samples and update sample stats for the main read
            int samples_in_buffer = bytes_read / SOC_ADC_DIGI_RESULT_BYTES;
            total_batch_samples_read += samples_in_buffer;
            batch_samples_min = min(batch_samples_min, (uint32_t)samples_in_buffer);
            batch_samples_max = max(batch_samples_max, (uint32_t)samples_in_buffer);
 
            // Calculate processing time since last read completed
            if (last_read_complete_time_us != 0) { // Skip first iteration
                 uint32_t current_processing_time_us = read_start_us - last_read_complete_time_us;
                 processing_time_sum_us += current_processing_time_us;
                 processing_time_min_us = min(processing_time_min_us, current_processing_time_us);
                 processing_time_max_us = max(processing_time_max_us, current_processing_time_us);
                 processing_read_count++;
            }
            last_read_complete_time_us = read_end_us; // Store end time for next iteration's calc
 
            consecutive_timeouts = 0; // Reset timeout counter on success
            total_successful_reads++;
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
            // double dynamic_mean_level_mv = (valid_samples > 0) ? (voltage_sum / valid_samples) : 0.0; // Removed unused variable
                    // Serial.printf("D (%s): Buffer Valid Samples: %d, Dynamic Mean: %.2f mV\n", TAG, valid_samples, dynamic_mean_level_mv); // Already commented
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
                    samples_in_current_batch++; // Increment batch sample counter


                    // --- Process Sample ---
                    double current_mv_double = (double)current_mv;

                    // Also update batch-level accumulators
                    sum_mv_current_batch += current_mv_double;
                    sum_sq_current_batch += current_mv_double * current_mv_double;
                    valid_samples_in_current_batch++;
                    
                    // --- Debug Print Voltage (approx once per second) ---
                    unsigned long currentTime = millis(); // Declare currentTime here
                    if (currentTime - lastPrintTime >= 1000) {
                        Serial.printf("D (%s): Sample mV: %lu\n", TAG, current_mv);
                        lastPrintTime = currentTime;
                    }
                    // --- End Debug Print ---


                    } // Moved brace from line 248 to here to fix current_mv scope
                // } // Removed extra brace
            } // End second for loop (processing samples)

            // --- NEW BATCH COMPLETION CHECK (Based primarily on sample count) ---
            if (samples_in_current_batch >= MAX_SAMPLES_PER_BATCH) {
                Serial.printf("D (%s): Batch ended: Sample limit (%lu) reached.\n", TAG, samples_in_current_batch);

                // --- Averaging / Calculation (Conditional on batch validity) ---
                // DEBUG: Log batch state before averaging
                // Serial.printf("D (%s): Batch End Check: Valid=%d, CycleCount=%d, ValidSamplesInBatch=%lu\n", TAG, batch_valid, cycle_count, valid_samples_in_current_batch);
                if (batch_valid) {
                    if (valid_samples_in_current_batch > 0) {
                        double batch_mean_mv = sum_mv_current_batch / valid_samples_in_current_batch;
                        double batch_mean_sq = batch_mean_mv * batch_mean_mv;
                        double batch_sum_sq_over_n = sum_sq_current_batch / valid_samples_in_current_batch;
                        float batch_rms_mv = 0.0f;
                        if (batch_sum_sq_over_n >= batch_mean_sq) {
                            batch_rms_mv = sqrt(batch_sum_sq_over_n - batch_mean_sq);
                        }
                        latest_rms_millivolts = (uint16_t)round(batch_rms_mv);
                        Serial.printf("I (%s): Batch ended: Batch RMS=%.2fmV (%u) over %lu samples\n", TAG,
                                 batch_rms_mv, latest_rms_millivolts, valid_samples_in_current_batch);
                    } else {
                        Serial.printf("W (%s): Batch ended with 0 valid samples. Resetting results.\n", TAG);
                        latest_rms_millivolts = 0;
                    }
                } else {
                    // Log that the average calculation is being skipped due to invalid batch
                    Serial.printf("W (%s): Batch invalidated during collection, skipping calculation.\n", TAG);
                    latest_rms_millivolts = 0;
                }

                // --- Report ADC Read Timing and Sample Stats ---
                if (batch_read_count > 0) {
                    float avg_read_time_us = (float)batch_read_time_sum_us / batch_read_count;
                    float avg_batch_samples = (float)total_batch_samples_read / batch_read_count;
                    Serial.printf("I (%s): ADC Main Read Stats (Batch): Count=%lu, TotalSamples=%llu, MinSamples=%lu, MaxSamples=%lu, AvgSamples=%.2f | MinTime=%lu us, MaxTime=%lu us, AvgTime=%.2f us\n", TAG,
                                  batch_read_count, total_batch_samples_read, batch_samples_min, batch_samples_max, avg_batch_samples,
                                  batch_read_time_min_us, batch_read_time_max_us, avg_read_time_us);
 
                    // --- Report Processing Time Stats ---
                    if (processing_read_count > 0) {
                         float avg_processing_time_us = (float)processing_time_sum_us / processing_read_count;
                         Serial.printf("I (%s): Processing Time Stats (Batch): Count=%lu, Min=%lu us, Max=%lu us, Avg=%.2f us\n", TAG,
                                       processing_read_count, processing_time_min_us, processing_time_max_us, avg_processing_time_us);
                    } else {
                         Serial.printf("D (%s): Processing Time Stats (Batch): Not enough reads yet.\n", TAG);
                    }
                } else {
                    Serial.printf("W (%s): ADC Read Timing (Batch): No successful reads in this batch.\n", TAG);
                }
 
                // Reset timing stats for next batch
                batch_read_time_sum_us = 0;
                batch_read_time_min_us = UINT32_MAX;
                batch_read_time_max_us = 0;
                batch_read_count = 0;
                total_batch_samples_read = 0; // Reset sample accumulator
                batch_samples_min = UINT32_MAX; // Reset min samples per call
                batch_samples_max = 0;          // Reset max samples per call
 
                // Reset processing time stats for next batch
                processing_time_sum_us = 0;
                processing_time_min_us = UINT32_MAX;
                processing_time_max_us = 0;
                processing_read_count = 0;
                last_read_complete_time_us = 0; // Reset to prevent calculation across batch boundary
                // --- Reset state for the next batch ---
                batch_valid = true; // Assume next batch is valid until proven otherwise
                samples_in_current_batch = 0; // Reset batch sample counter
                sum_mv_current_batch = 0.0;     // Reset batch accumulators
                sum_sq_current_batch = 0.0;
                valid_samples_in_current_batch = 0;

                // --- Replace Delay with Discard Reads ---
                uint32_t batch_end_time = millis();
                uint32_t total_batch_duration_ms = batch_end_time - actual_batch_start_time;
                int32_t delay_ms = TARGET_BATCH_INTERVAL_MS - total_batch_duration_ms;
 
                if (delay_ms > 0) {
                    Serial.printf("D (%s): Total Batch Duration: %lu ms, Entering discard-read loop for %ld ms\n", TAG, total_batch_duration_ms, delay_ms);
                    uint32_t discard_loop_end_time = millis() + delay_ms;
                    // Use a static buffer to avoid stack allocation in the loop if preferred,
                    // but local should be fine given the size and context.
                    uint8_t discard_buffer[ADC_CONV_FRAME_SIZE]; // Temporary buffer for discarded reads
                    uint32_t discard_bytes_read = 0;
                    while (millis() < discard_loop_end_time) {
                        uint32_t discard_read_start_us = micros(); // Start timing discard read
                        // Read with minimal timeout (0) to keep ADC active and drain DMA buffer quickly
                        // We don't strictly need the return value here, but capture it in case of future debugging needs
                        /* esp_err_t discard_ret = */ adc_continuous_read(adcHandle, discard_buffer, ADC_CONV_FRAME_SIZE, &discard_bytes_read, 30); // Removed unused variable discard_ret
                        uint32_t discard_read_end_us = micros(); // End timing discard read
 
                        // Update discard timing stats
                        uint32_t discard_duration_us = discard_read_end_us - discard_read_start_us;
                        discard_read_time_sum_us += discard_duration_us;
                        discard_read_time_min_us = min(discard_read_time_min_us, discard_duration_us);
                        discard_read_time_max_us = max(discard_read_time_max_us, discard_duration_us);
                        discard_read_count++;

                        // Calculate samples and update sample stats for the discard read
                        int discard_samples_read = discard_bytes_read / SOC_ADC_DIGI_RESULT_BYTES;
                        total_discard_samples_read += discard_samples_read;
                        discard_samples_min = min(discard_samples_min, (uint32_t)discard_samples_read);
                        discard_samples_max = max(discard_samples_max, (uint32_t)discard_samples_read);
                        vTaskDelay(pdMS_TO_TICKS(theoretical_acquisition_time_ms-SAFETY_MARGIN_MS+2));
                        // No delay needed here, adc_continuous_read with 0 timeout should return quickly
                    }
                    Serial.printf("D (%s): Discard-read loop finished.\n", TAG);
 
                    // --- Report Discard Read Timing and Sample Stats ---
                    if (discard_read_count > 0) {
                        float avg_discard_read_time_us = (float)discard_read_time_sum_us / discard_read_count;
                        float avg_discard_samples_read = (float)total_discard_samples_read / discard_read_count;
                        // Changed Bytes to Samples
                        Serial.printf("I (%s): ADC Discard Read Stats: Count=%lu, TotalSamples=%llu, MinSamples=%lu, MaxSamples=%lu, AvgSamples=%.2f | MinTime=%lu us, MaxTime=%lu us, AvgTime=%.2f us\n", TAG,
                                      discard_read_count, total_discard_samples_read, discard_samples_min, discard_samples_max, avg_discard_samples_read,
                                      discard_read_time_min_us, discard_read_time_max_us, avg_discard_read_time_us);
                    } else {
                         Serial.printf("D (%s): ADC Discard Read Timing: No discard reads performed in this loop.\n", TAG);
                    }
                    // Reset discard timing stats for next potential loop
                    discard_read_time_sum_us = 0;
                    discard_read_time_min_us = UINT32_MAX;
                    discard_read_time_max_us = 0;
                    discard_read_count = 0;
                    total_discard_samples_read = 0; // Reset total sample accumulator
                    discard_samples_min = UINT32_MAX; // Reset min samples per call
                    discard_samples_max = 0;          // Reset max samples per call
 
                } else {
                     Serial.printf("W (%s): Batch processing (%lu ms) exceeded target interval (%d ms). No discard loop needed.\n",
                                  TAG, total_batch_duration_ms, TARGET_BATCH_INTERVAL_MS);
                     // Yield briefly even if overrun to allow other tasks
                     vTaskDelay(pdMS_TO_TICKS(10));
                }
                actual_batch_start_time = millis(); // Update start time for the *next* batch interval
            } // --- End of NEW batch completion block ---
        }
        else if (ret == ESP_ERR_TIMEOUT) { // Start else if block correctly
             consecutive_timeouts++;
             batch_valid = false; // Invalidate batch on timeout
             // Only log every few timeouts to avoid flooding the Serial console
             if (consecutive_timeouts == 1 || consecutive_timeouts % 5 == 0) {
                 Serial.printf("W (%s): ADC Read Timeout #%u! ADC might not be sampling at expected rate.\n",
                              TAG, consecutive_timeouts);
                 Serial.printf("D (%s): DMA buffer state - Samples in batch: %lu\n", TAG, samples_in_current_batch);
             }
             // Short fixed delay on timeout, interval timing is handled after a *successful* batch completion
             // vTaskDelay(pdMS_TO_TICKS(50)); // Commented out: Let main loop yield handle it
             // If we have too many consecutive timeouts, log a warning about potential hardware issues
             if (consecutive_timeouts == 20) {
                 Serial.printf("E (%s): 20 consecutive ADC timeouts! Hardware may need attention.\n", TAG);
             }
        } else { // Handle other errors
             Serial.printf("E (%s): ADC Read Error: %s. Invalidating current batch.\n", TAG, esp_err_to_name(ret));
             batch_valid = false; // Invalidate batch on other read errors
             // Consider error handling: re-init ADC?
             // Short fixed delay on error, interval timing is handled after a *successful* batch completion
             // vTaskDelay(pdMS_TO_TICKS(50)); // Commented out: Let main loop yield handle it
        }

        // Removed fixed delay - now handled by calculated delay after batch completion
        vTaskDelay(pdMS_TO_TICKS(12)); // <-- MOVED INSIDE: Yield control briefly every loop iteration
    } // End while(1)
} // <-- ADDED: Closing brace for adcProcessingTask function

