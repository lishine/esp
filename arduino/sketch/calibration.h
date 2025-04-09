#ifndef CALIBRATION_H
#define CALIBRATION_H

#include "globals.h"

// --- Function Declarations ---

/**
 * @brief Initializes the Non-Volatile Storage (NVS) system.
 * Must be called once during setup.
 * @return true if initialization was successful, false otherwise.
 */
bool init_nvs();

/**
 * @brief Loads calibration values (offset, scaling factor, mean level)
 * from NVS into the global variables.
 * If values don't exist in NVS, globals retain their default values.
 */
void load_calibration_nvs();

/**
 * @brief Saves the given ADC voltage offset (in mV) to NVS.
 * @param offset_mv The calculated voltage offset.
 */
void save_voltage_offset_nvs(float offset_mv);

/**
 * @brief Saves the given ADC scaling factor (mV per ADC count) to NVS.
 * @param factor The calculated scaling factor.
 */
void save_scaling_factor_nvs(float factor);

/**
 * @brief Saves the given waveform mean level (raw ADC value) to NVS.
 * @param level The raw ADC reading corresponding to the signal's mean level.
 */
void save_mean_level_nvs(int32_t level);

/**
 * @brief Performs the two-point calibration calculation.
 * @param low_reading Raw ADC reading at CAL_LOW_MV.
 * @param high_reading Raw ADC reading at CAL_HIGH_MV.
 * @param out_offset_mv Reference to store the calculated voltage offset (in mV).
 * @param out_factor Reference to store the calculated scaling factor (mV/count).
 * @return true if calculation was successful, false if readings are invalid (e.g., equal).
 */
bool calculate_calibration_factors(int32_t low_reading, int32_t high_reading, float &out_offset_mv, float &out_factor);


#endif // CALIBRATION_H