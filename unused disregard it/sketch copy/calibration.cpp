#include "calibration.h"
#include "globals.h" // Access to NVS keys, constants, and global vars
#include <nvs_flash.h>
#include <nvs.h>
// #include <esp_log.h> // Using Serial.printf instead

static const char *TAG = "Calibration";

// --- NVS Initialization ---
bool init_nvs() {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        // NVS partition was truncated and needs to be erased
        Serial.printf("W (%s): NVS partition problem (%s), erasing...\n", TAG, esp_err_to_name(ret));
        ESP_ERROR_CHECK(nvs_flash_erase());
        // Retry nvs_flash_init
        ret = nvs_flash_init();
    }
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to initialize NVS (%s)\n", TAG, esp_err_to_name(ret));
        return false;
    }
    return true;
}

// --- Load Calibration Data ---
void load_calibration_nvs() {
    esp_err_t ret;
    Serial.printf("I (%s): Opening NVS namespace: %s\n", TAG, NVS_NAMESPACE);
    ret = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &nvsHandle); // Open read/write
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to open NVS namespace '%s' (%s). Using default values.\n", TAG, NVS_NAMESPACE, esp_err_to_name(ret));
        // Keep default values defined in sketch.ino
        return;
    }
    Serial.printf("I (%s): NVS Namespace opened successfully.\n", TAG);

    // Load Zero Offset
    int32_t saved_offset = adc_zero_offset; // Start with default
    ret = nvs_get_i32(nvsHandle, NVS_KEY_ZERO_OFFSET, &saved_offset);
    switch (ret) {
        case ESP_OK:
            adc_zero_offset = saved_offset;
            Serial.printf("I (%s): Loaded '%s': %ld\n", TAG, NVS_KEY_ZERO_OFFSET, adc_zero_offset);
            break;
        case ESP_ERR_NVS_NOT_FOUND:
            Serial.printf("W (%s): '%s' not found in NVS. Using default: %ld\n", TAG, NVS_KEY_ZERO_OFFSET, adc_zero_offset);
            break;
        default:
            Serial.printf("E (%s): Error reading '%s' from NVS (%s)\n", TAG, NVS_KEY_ZERO_OFFSET, esp_err_to_name(ret));
    }

    // Load Scaling Factor (stored as float, needs conversion for NVS which doesn't directly support float)
    // We store it as int32 representing float * 1,000,000
    int32_t saved_factor_scaled = (int32_t)(adc_scaling_factor * 1000000.0f); // Default scaled
    ret = nvs_get_i32(nvsHandle, NVS_KEY_SCALE_FACTOR, &saved_factor_scaled);
     switch (ret) {
        case ESP_OK:
            adc_scaling_factor = (float)saved_factor_scaled / 1000000.0f;
            Serial.printf("I (%s): Loaded '%s': %.6f (from scaled %ld)\n", TAG, NVS_KEY_SCALE_FACTOR, adc_scaling_factor, saved_factor_scaled);
            break;
        case ESP_ERR_NVS_NOT_FOUND:
            Serial.printf("W (%s): '%s' not found in NVS. Using default: %.6f\n", TAG, NVS_KEY_SCALE_FACTOR, adc_scaling_factor);
            break;
        default:
            Serial.printf("E (%s): Error reading '%s' from NVS (%s)\n", TAG, NVS_KEY_SCALE_FACTOR, esp_err_to_name(ret));
    }


    // Load Waveform Mean Level
    int32_t saved_mean = waveform_mean_level_adc; // Start with default
    ret = nvs_get_i32(nvsHandle, NVS_KEY_MEAN_LEVEL, &saved_mean);
    switch (ret) {
        case ESP_OK:
            waveform_mean_level_adc = saved_mean;
            Serial.printf("I (%s): Loaded '%s': %ld\n", TAG, NVS_KEY_MEAN_LEVEL, waveform_mean_level_adc);
            break;
        case ESP_ERR_NVS_NOT_FOUND:
            Serial.printf("W (%s): '%s' not found in NVS. Using default: %ld\n", TAG, NVS_KEY_MEAN_LEVEL, waveform_mean_level_adc);
            break;
        default:
            Serial.printf("E (%s): Error reading '%s' from NVS (%s)\n", TAG, NVS_KEY_MEAN_LEVEL, esp_err_to_name(ret));
    }

    // Note: nvsHandle remains open for writing later. It's closed implicitly on restart
    // or could be closed manually if desired after setup. For simplicity here, keep it open.
    // nvs_close(nvsHandle);
}

// --- Save Calibration Data ---
void save_zero_offset_nvs(int32_t offset) {
    if (nvsHandle == 0) {
        Serial.printf("E (%s): NVS handle not initialized, cannot save offset.\n", TAG);
        return;
    }
    esp_err_t ret = nvs_set_i32(nvsHandle, NVS_KEY_ZERO_OFFSET, offset);
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to save '%s' to NVS (%s)\n", TAG, NVS_KEY_ZERO_OFFSET, esp_err_to_name(ret));
    } else {
        ret = nvs_commit(nvsHandle); // Commit changes
        if (ret != ESP_OK) {
            Serial.printf("E (%s): Failed to commit NVS changes for '%s' (%s)\n", TAG, NVS_KEY_ZERO_OFFSET, esp_err_to_name(ret));
        } else {
            Serial.printf("I (%s): Saved '%s': %ld\n", TAG, NVS_KEY_ZERO_OFFSET, offset);
        }
    }
}

void save_scaling_factor_nvs(float factor) {
     if (nvsHandle == 0) {
        Serial.printf("E (%s): NVS handle not initialized, cannot save factor.\n", TAG);
        return;
    }
    // Store as scaled integer
    int32_t factor_scaled = (int32_t)(factor * 1000000.0f);
    esp_err_t ret = nvs_set_i32(nvsHandle, NVS_KEY_SCALE_FACTOR, factor_scaled);
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to save '%s' to NVS (%s)\n", TAG, NVS_KEY_SCALE_FACTOR, esp_err_to_name(ret));
    } else {
        ret = nvs_commit(nvsHandle); // Commit changes
        if (ret != ESP_OK) {
            Serial.printf("E (%s): Failed to commit NVS changes for '%s' (%s)\n", TAG, NVS_KEY_SCALE_FACTOR, esp_err_to_name(ret));
        } else {
             Serial.printf("I (%s): Saved '%s': %.6f (as scaled %ld)\n", TAG, NVS_KEY_SCALE_FACTOR, factor, factor_scaled);
        }
    }
}

void save_mean_level_nvs(int32_t level) {
    if (nvsHandle == 0) {
        Serial.printf("E (%s): NVS handle not initialized, cannot save mean level.\n", TAG);
        return;
    }
    esp_err_t ret = nvs_set_i32(nvsHandle, NVS_KEY_MEAN_LEVEL, level);
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to save '%s' to NVS (%s)\n", TAG, NVS_KEY_MEAN_LEVEL, esp_err_to_name(ret));
    } else {
        ret = nvs_commit(nvsHandle); // Commit changes
        if (ret != ESP_OK) {
            Serial.printf("E (%s): Failed to commit NVS changes for '%s' (%s)\n", TAG, NVS_KEY_MEAN_LEVEL, esp_err_to_name(ret));
        } else {
            Serial.printf("I (%s): Saved '%s': %ld\n", TAG, NVS_KEY_MEAN_LEVEL, level);
        }
    }
}

// --- Calculate Calibration Factors ---
bool calculate_calibration_factors(int32_t low_reading, int32_t high_reading, int32_t &out_offset, float &out_factor) {
    Serial.printf("I (%s): Calculating factors from Low Reading: %ld (at %d mV), High Reading: %ld (at %d mV)\n",
                  TAG, low_reading, CAL_LOW_MV, high_reading, CAL_HIGH_MV);

    int32_t delta_reading = high_reading - low_reading;
    int32_t delta_mv = CAL_HIGH_MV - CAL_LOW_MV;

    if (delta_reading == 0) {
        Serial.printf("E (%s): Calibration failed: Low and High ADC readings are identical (%ld).\n", TAG, low_reading);
        return false;
    }
    if (delta_mv <= 0) {
         Serial.printf("E (%s): Calibration failed: CAL_HIGH_MV (%d) must be greater than CAL_LOW_MV (%d).\n", TAG, CAL_HIGH_MV, CAL_LOW_MV);
         return false;
    }

    // Calculate scaling factor (mV per ADC count)
    out_factor = (float)delta_mv / (float)delta_reading;

    // Calculate zero offset (raw ADC reading at 0mV, extrapolated)
    // Formula: Voltage = (Raw - Offset) * Factor
    // -> Offset = Raw - (Voltage / Factor)
    // Using the low point: Offset = low_reading - (CAL_LOW_MV / out_factor)
    // Note: This calculates the theoretical offset at 0mV, not the reading at CAL_LOW_MV.
    // Let's adjust the plan slightly: store the reading at CAL_LOW_MV as the offset,
    // and adjust the conversion formula accordingly. This is simpler.
    // New approach: Store reading at CAL_LOW_MV as offset.
    // Conversion: mV = ((raw_adc - adc_zero_offset) * adc_scaling_factor) + CAL_LOW_MV

    // *** Revised Calculation based on storing reading at CAL_LOW_MV as offset ***
    out_offset = low_reading; // Store the actual reading at the low reference voltage
    out_factor = (float)delta_mv / (float)delta_reading; // Factor remains the same (mV per count)

    Serial.printf("I (%s): Calculated Offset (Reading at %d mV): %ld\n", TAG, CAL_LOW_MV, out_offset);
    Serial.printf("I (%s): Calculated Scaling Factor: %.6f mV/count\n", TAG, out_factor);

    return true;
}

// --- Revised Conversion Function (Example - will live in adc_handler.cpp) ---
// float convert_adc_to_mv(int32_t raw_adc) {
//     // Uses the offset (reading at CAL_LOW_MV) and scaling factor
//     return ((float)(raw_adc - adc_zero_offset) * adc_scaling_factor) + CAL_LOW_MV;
// }