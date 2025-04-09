#include "adc_handler.h"
#include "globals.h"
#include <cmath> // For sqrt
// #include <esp_log.h> // Using Serial.printf instead
#include <driver/adc.h> // For adc1_get_raw (used cautiously)
// #include <esp_adc/adc_continuous_io.h> // Header not found, reverting change

static const char *TAG = "ADCHandler";

// --- Static variables for processing state ---
static int32_t last_sample_raw = -1; // Initialize to invalid state
static bool crossed_up = false;      // Tracks if last crossing was upwards
static uint32_t samples_in_current_cycle = 0;
static double sum_sq_current_cycle = 0.0; // Use double for accumulator precision

// --- Initialize ADC Continuous Mode ---
bool init_adc() {
    // --- Pre-configure the specific ADC channel (Attempting workaround for timeouts) ---
    // Configure ADC1 width and attenuation for the specific channel
    // Note: This uses the single-shot API, hoping it influences the continuous setup.
    // Map adc_bitwidth_t to adc_bits_width_t for the single-shot API call
    adc_bits_width_t width_bit;
    switch (ADC_BITWIDTH) {
        // Add cases for other bitwidths if needed
        case ADC_BITWIDTH_12:
        default:
            width_bit = ADC_WIDTH_BIT_12;
            break;
    }
    esp_err_t config_ret = adc1_config_width(width_bit);
    if (config_ret != ESP_OK) {
         Serial.printf("W (%s): Failed to configure ADC1 width: %s\n", TAG, esp_err_to_name(config_ret));
         // Continue anyway, maybe not fatal
    } else {
         Serial.printf("I (%s): Configured ADC1 width to %d bits.\n", TAG, ADC_BITWIDTH);
    }
    config_ret = adc1_config_channel_atten(ADC1_CHANNEL_4, ADC_ATTEN); // Use specific enum ADC1_CHANNEL_4
     if (config_ret != ESP_OK) {
         Serial.printf("W (%s): Failed to configure ADC1 channel %d attenuation: %s\n", TAG, (int)ADC1_CHANNEL_4, esp_err_to_name(config_ret));
         // Continue anyway
    } else {
         Serial.printf("I (%s): Configured ADC1 channel %d attenuation to %d.\n", TAG, (int)ADC1_CHANNEL_4, (int)ADC_ATTEN);
    }
    // --- End of Pre-configuration ---

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

// --- Convert Raw ADC to Millivolts ---
// Uses the revised formula based on storing reading at CAL_LOW_MV as offset
float convert_adc_to_mv(int32_t raw_adc) {
    // Formula: mV = ((raw_adc - adc_zero_offset) * adc_scaling_factor) + CAL_LOW_MV
    // Ensure adc_scaling_factor is not zero if loaded incorrectly
    if (adc_scaling_factor == 0.0f) {
        // Avoid division by zero or incorrect scaling
        // Return raw value or some indicator? For now, return 0.
        return 0.0f;
    }
    return ((float)(raw_adc - adc_zero_offset) * adc_scaling_factor) + (float)CAL_LOW_MV;
}


// --- ADC Processing Task ---
void adcProcessingTask(void *pvParameters) {
    Serial.printf("I (%s): ADC Processing Task started.\n", TAG);

    uint8_t result[ADC_CONV_FRAME_SIZE] = {0}; // Buffer to store DMA results
    uint32_t ret_num = 0; // Number of bytes read

    // Initialize processing state
    last_sample_raw = -1;
    crossed_up = false;
    samples_in_current_cycle = 0;
    sum_sq_current_cycle = 0.0;
    cycle_buffer_index = 0;
    cycle_count = 0;

    // Initialize circular buffers (optional, they are global)
    for(int i=0; i<NUM_CYCLES_AVERAGE; ++i) {
        cycle_periods[i] = 0.0f;
        cycle_rms_values[i] = 0.0f;
    }

    uint8_t consecutive_timeouts = 0;
    uint32_t total_successful_reads = 0;
    
    Serial.printf("I (%s): ADC Task starting with sample rate %d Hz, buffer size %d bytes\n",
                 TAG, TARGET_SAMPLE_FREQ_HZ, ADC_DMA_BUF_SIZE);
                 
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

        // Read data from ADC DMA buffer
        // Change timeout from 0 (indefinite) to 100ms - this helps prevent blocking forever
        // and allows handling other tasks if ADC isn't producing data
        esp_err_t ret = adc_continuous_read(adcHandle, result, ADC_CONV_FRAME_SIZE, &ret_num, 0);

        if (ret == ESP_OK) {
            consecutive_timeouts = 0; // Reset timeout counter on success
            total_successful_reads++;
            
            // Print bytes read every 100 successful operations
            if (total_successful_reads % 100 == 0) {
                Serial.printf("D (%s): Read %lu bytes from ADC.\n", TAG, ret_num);
            }
            
            for (int i = 0; i < ret_num; i += SOC_ADC_DIGI_RESULT_BYTES) {
                adc_digi_output_data_t *p = (adc_digi_output_data_t *)&result[i];
                // Check if data is from the expected channel using type2 members
                if (p->type2.channel == ADC_CHANNEL) {
                    int32_t current_raw = p->type2.data;
                    // Serial.printf("V (%s): Raw ADC: %ld\n", TAG, current_raw); // Verbose level

                    // Initialize last_sample_raw on first run
                    if (last_sample_raw == -1) {
                        last_sample_raw = current_raw;
                    }

                    // --- Process Sample ---
                    samples_in_current_cycle++;
                    float current_mv = convert_adc_to_mv(current_raw);
                    sum_sq_current_cycle += ((double)current_mv * (double)current_mv); // Use double for sum

                    // --- Zero-Crossing Detection ---
                    // Check if the signal crossed the mean level
                    bool above_mean_now = (current_raw >= waveform_mean_level_adc);
                    bool above_mean_before = (last_sample_raw >= waveform_mean_level_adc);

                    if (above_mean_now != above_mean_before) { // A crossing occurred
                        if (above_mean_now) { // Crossed upwards (rising edge)
                            // Serial.printf("D (%s): Rising edge detected at sample %lu\n", TAG, samples_in_current_cycle); // Debug level
                            if (crossed_up) {
                                // --- Full Cycle Detected (Rising Edge to Rising Edge) ---
                                if (samples_in_current_cycle > 1) { // Need at least 2 samples for a cycle
                                    float period_seconds = (float)samples_in_current_cycle / TARGET_SAMPLE_FREQ_HZ;
                                    float rms_mv = sqrt(sum_sq_current_cycle / samples_in_current_cycle);

                                    Serial.printf("D (%s): Cycle %d: Samples=%lu, Period=%.6fs, RMS=%.2fmV\n", TAG,
                                             cycle_count + 1, samples_in_current_cycle, period_seconds, rms_mv); // Debug level

                                    // Store in circular buffers
                                    cycle_periods[cycle_buffer_index] = period_seconds;
                                    cycle_rms_values[cycle_buffer_index] = rms_mv;

                                    cycle_count++;

                                    // --- Averaging ---
                                    if (cycle_count >= NUM_CYCLES_AVERAGE) {
                                        double sum_periods = 0.0;
                                        double sum_rms = 0.0;
                                        for (int j = 0; j < NUM_CYCLES_AVERAGE; ++j) {
                                            sum_periods += cycle_periods[j];
                                            sum_rms += cycle_rms_values[j];
                                        }
                                        float avg_period = sum_periods / NUM_CYCLES_AVERAGE;
                                        float avg_rms = sum_rms / NUM_CYCLES_AVERAGE;
                                        float avg_freq = (avg_period > 0.000001f) ? (1.0f / avg_period) : 0.0f; // Avoid div by zero

                                        // Update volatile globals (atomically for uint16_t)
                                        latest_freq_hz = (uint16_t)round(avg_freq);
                                        latest_rms_millivolts = (uint16_t)round(avg_rms);

                                        Serial.printf("I (%s): Avg (5 cycles): Freq=%.2fHz (%u), RMS=%.2fmV (%u)\n", TAG,
                                                 avg_freq, latest_freq_hz, avg_rms, latest_rms_millivolts);

                                        cycle_count = 0; // Reset for next average batch
                                    }

                                    // Increment circular buffer index
                                    cycle_buffer_index = (cycle_buffer_index + 1) % NUM_CYCLES_AVERAGE;

                                } else {
                                     Serial.printf("W (%s): Cycle detected with <= 1 sample? Skipping.\n", TAG);
                                }
                                // Reset for next cycle measurement
                                samples_in_current_cycle = 0;
                                sum_sq_current_cycle = 0.0;

                            } // else: First rising edge, don't calculate cycle yet
                            crossed_up = true; // Mark that we are now above mean after rising edge
                        } else { // Crossed downwards (falling edge)
                             // Serial.printf("D (%s): Falling edge detected at sample %lu\n", TAG, samples_in_current_cycle); // Debug level
                             crossed_up = false; // Mark that we are now below mean
                        }
                    } // End of crossing check

                    last_sample_raw = current_raw; // Update for next iteration

                } // End check for correct channel
            } // End loop through samples in buffer
        } else if (ret == ESP_ERR_TIMEOUT) {
            consecutive_timeouts++;
            
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
        } else {
            Serial.printf("E (%s): ADC Read Error: %s\n", TAG, esp_err_to_name(ret));
            // Consider error handling: re-init ADC?
            vTaskDelay(pdMS_TO_TICKS(1000));
        }

        // Increase task delay to reduce CPU load and power consumption
        // Adjust this value based on your timing requirements
        vTaskDelay(pdMS_TO_TICKS(5));
    } // End while(1)
}


// --- Read Single ADC Value ---
// WARNING: Calling this while continuous mode is active is problematic.
// The continuous driver controls the ADC configuration. Using adc1_get_raw
// might work sometimes but can conflict with the continuous driver's state
// or return invalid data if the ADC is configured differently by the driver.
// A robust solution would involve:
// 1. Signaling the adcProcessingTask to pause.
// 2. Stopping continuous mode (`adc_continuous_stop`).
// 3. Configuring ADC1 for single read (`adc1_config_width`, `adc1_config_channel_atten`).
// 4. Performing the read (`adc1_get_raw`).
// 5. Re-starting continuous mode (`adc_continuous_start`).
// 6. Signaling the adcProcessingTask to resume.
// This adds significant complexity.
//
// This simpler implementation attempts a direct read using adc1_get_raw,
// assuming the continuous driver *might* leave the basic channel config usable.
// **This is NOT guaranteed and may fail or give incorrect readings.**
int32_t read_current_adc_value() {
    Serial.printf("W (%s): Attempting single ADC read using adc1_get_raw - may conflict with continuous mode!\n", TAG);

    // Ensure correct ADC unit is configured for single reads (might be redundant if already done)
    // adc1_config_width(ADC_BITWIDTH); // Might conflict!
    // adc1_config_channel_atten(ADC_CHANNEL, ADC_ATTEN); // Might conflict!

    // Use the specific enum type adc1_channel_t expects (ADC1_CHANNEL_4 corresponds to ADC_CHANNEL_4)
    int raw_value = adc1_get_raw(ADC1_CHANNEL_4);

    if (raw_value == -1) {
        Serial.printf("E (%s): adc1_get_raw failed to read channel %d.\n", TAG, (int)ADC_CHANNEL);
        return -1;
    } else {
        Serial.printf("I (%s): Single read adc1_get_raw value: %d\n", TAG, raw_value);
        return (int32_t)raw_value;
    }
}