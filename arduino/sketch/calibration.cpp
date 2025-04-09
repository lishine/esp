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

    // Load Voltage Offset (stored as float * 1,000,000)
    int32_t saved_offset_scaled = (int32_t)(adc_voltage_offset * 1000000.0f); // Default scaled
    ret = nvs_get_i32(nvsHandle, NVS_KEY_VOLTAGE_OFFSET, &saved_offset_scaled); // Use new key
    switch (ret) {
        case ESP_OK:
            adc_voltage_offset = (float)saved_offset_scaled / 1000000.0f; // Convert back to float
            Serial.printf("I (%s): Loaded '%s': %.4f mV (from scaled %ld)\n", TAG, NVS_KEY_VOLTAGE_OFFSET, adc_voltage_offset, saved_offset_scaled);
            break;
        case ESP_ERR_NVS_NOT_FOUND:
            Serial.printf("W (%s): '%s' not found in NVS. Using default: %.4f mV\n", TAG, NVS_KEY_VOLTAGE_OFFSET, adc_voltage_offset);
            break;
        default:
            Serial.printf("E (%s): Error reading '%s' from NVS (%s)\n", TAG, NVS_KEY_VOLTAGE_OFFSET, esp_err_to_name(ret));
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
// Renamed function and changed parameter type
void save_voltage_offset_nvs(float offset_mv) {
    if (nvsHandle == 0) {
        Serial.printf("E (%s): NVS handle not initialized, cannot save voltage offset.\n", TAG);
        return;
    }
    // Store as scaled integer
    int32_t offset_scaled = (int32_t)(offset_mv * 1000000.0f);
    esp_err_t ret = nvs_set_i32(nvsHandle, NVS_KEY_VOLTAGE_OFFSET, offset_scaled); // Use new key
    if (ret != ESP_OK) {
        Serial.printf("E (%s): Failed to save '%s' to NVS (%s)\n", TAG, NVS_KEY_VOLTAGE_OFFSET, esp_err_to_name(ret));
    } else {
        ret = nvs_commit(nvsHandle); // Commit changes
        if (ret != ESP_OK) {
            Serial.printf("E (%s): Failed to commit NVS changes for '%s' (%s)\n", TAG, NVS_KEY_VOLTAGE_OFFSET, esp_err_to_name(ret));
        } else {
             Serial.printf("I (%s): Saved '%s': %.4f mV (as scaled %ld)\n", TAG, NVS_KEY_VOLTAGE_OFFSET, offset_mv, offset_scaled);
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
// Changed signature for out_offset type
bool calculate_calibration_factors(int32_t low_reading, int32_t high_reading, float &out_offset_mv, float &out_factor) {
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

    // Calculate scaling factor (mV per ADC count) - unchanged
    out_factor = (float)delta_mv / (float)delta_reading;

    // *** Correct Calculation for Voltage Offset ***
    // Formula: Voltage = (Raw * Factor) + Offset_mV
    // -> Offset_mV = Voltage - (Raw * Factor)
    // Using the low point: Offset_mV = CAL_LOW_MV - (low_reading * out_factor)
    out_offset_mv = (float)CAL_LOW_MV - ((float)low_reading * out_factor); // Correct calculation

    Serial.printf("I (%s): Calculated Voltage Offset: %.4f mV\n", TAG, out_offset_mv); // Update log message
    Serial.printf("I (%s): Calculated Scaling Factor: %.6f mV/count\n", TAG, out_factor);

    return true;
}

// Removed incorrect example conversion function comment block