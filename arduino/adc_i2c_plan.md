# ESP32-C3 ADC/I2C Processing Plan (Revised)

## Objective

Read motor current via ADC (GPIO4) on an ESP32-C3 running Arduino code. Use ESP-IDF calibration functions (eFuse Two Point only) to convert readings to millivolts. Dynamically calculate the signal's mean level, frequency (using zero-crossing against the dynamic mean), and RMS voltage. Average these values over 5 cycles. Act as an I2C slave (address 0x08) to send the latest averaged frequency (Hz) and RMS (mV) as two `uint16_t` values (4 bytes total) to an ESP32-S3 master upon request.

## Hardware & Configuration

- **MCU:** ESP32-C3
- **ADC Input Pin:** GPIO4
- **LED Pin:** GPIO8 (Optional: for status feedback)
- **I2C Pins:** GPIO0 (SDA), GPIO1 (SCL)
- **I2C Role:** Slave
- **I2C Address:** `0x08`
- **ADC Settings:**
  - Continuous DMA Mode
  - Attenuation: `ADC_ATTEN_DB_11` (Defines the input voltage range, e.g., 0-2.5V)
  - Bitwidth: `ADC_BITWIDTH_12` (Raw ADC values 0-4095)
  - Target Sample Rate (`TARGET_SAMPLE_FREQ_HZ`): ~50,000 Hz (Adjustable)
  - **Important:** Requires low source impedance (<10kΩ, ideally <1kΩ) driving the ADC pin, or use an op-amp buffer.
- **Calibration:**
  - Uses ESP-IDF `esp_adc_cal` library.
  - **Requires eFuse Two Point (TP) calibration values.** Initialization will fail if TP values are not present in the ESP32-C3's eFuse.
  - Default Vref: `DEFAULT_VREF` (Typically 1100mV, but check ESP-IDF documentation for the specific board/chip).
- **Averaging Window:** `NUM_CYCLES_AVERAGE = 5` cycles

## Core Logic

### 1. ADC Calibration Initialization (`setup()`)

- Include necessary ESP-IDF headers (`esp_adc_cal.h`).
- Check if eFuse Two Point calibration values are available using `esp_adc_cal_check_efuse(ESP_ADC_CAL_VAL_EFUSE_TP)`.
  - If `ESP_OK`:
    - Allocate memory for `esp_adc_cal_characteristics_t` structure (`adc_chars`).
    - Characterize the ADC using `esp_adc_cal_characterize(ADC_UNIT_1, ADC_ATTEN_DB_11, ADC_BITWIDTH_12, DEFAULT_VREF, adc_chars)`.
    - Verify the characterization type returned is `ESP_ADC_CAL_VAL_EFUSE_TP`. If not, log an error (calibration method mismatch).
    - Store the `adc_chars` structure globally for use in the processing task.
  - If eFuse TP values are _not_ available:
    - Log a critical error and halt or enter a safe state. This plan relies _exclusively_ on TP calibration.

### 2. ADC Processing Task (`adcProcessingTask`)

- Runs continuously using FreeRTOS.
- Reads ADC samples via DMA buffer (`adc_continuous_read`) into a local buffer (e.g., `sample_buffer`). The buffer should be large enough to hold samples for slightly more than the longest expected cycle to ensure full cycles can be captured.
- **Per Buffer Full / Processing Interval:**
  1.  **Calculate Dynamic Mean (Raw ADC):** Compute the average raw ADC value of all samples in the `sample_buffer`. This is `dynamic_mean_level_adc`, used for zero-crossing detection.
  2.  **Convert Samples to Voltage:** Iterate through the `sample_buffer`, converting each `raw_adc` sample to millivolts using `esp_adc_cal_raw_to_voltage(raw_adc, adc_chars)`. Store these `voltage_mv` values, perhaps in a parallel buffer or by replacing the raw values if memory is tight.
  3.  **Initialize Cycle Variables:** Reset sum-of-squared-voltage-deviations (`sum_sq_mv_deviation`), sample count (`samples_in_cycle`), zero-crossing state, etc.
  4.  **Iterate Through Samples for Cycle Processing:**
      - **Zero-Crossing Detection:** Compare `raw_adc` (from the original buffer) against `dynamic_mean_level_adc` to detect full cycles (e.g., rising edge to rising edge). Track the number of samples between crossings.
      - **RMS Accumulation (within a detected cycle):**
        - Once a full cycle's samples are identified (based on zero-crossings), calculate the mean voltage (`mean_voltage_mv`) of the _converted_ `voltage_mv` samples belonging _only_ to that specific cycle.
        - For each `voltage_mv` sample within that cycle, calculate the squared deviation: `pow(voltage_mv - mean_voltage_mv, 2)`.
        - Accumulate these squared deviations into `sum_sq_mv_deviation`.
        - Keep track of the number of samples in this specific cycle (`samples_in_cycle`).
  5.  **Per Full Cycle Detected (End of Cycle):**
      - Calculate period (samples between crossings / sample rate).
      - Calculate frequency (1 / period).
      - Calculate RMS voltage for the completed cycle: `cycle_rms_mv = sqrt(sum_sq_mv_deviation / samples_in_cycle)`.
      - Store calculated frequency and `cycle_rms_mv` in respective circular buffers (size `NUM_CYCLES_AVERAGE`).
      - Reset cycle variables (`sum_sq_mv_deviation`, `samples_in_cycle`).
      - Increment cycle counter.
  6.  **Averaging (Every `NUM_CYCLES_AVERAGE` Cycles):**
      - Calculate the average frequency (Hz) from the last `NUM_CYCLES_AVERAGE` values in the frequency buffer.
      - Calculate the average RMS (mV) from the last `NUM_CYCLES_AVERAGE` values in the RMS buffer.
      - Update `volatile` global variables: `latest_freq_hz` and `latest_rms_millivolts` (use mutex/critical section if necessary).
      - Reset cycle counter.
- Yields CPU (`vTaskDelay`).

### 3. I2C Communication (`i2cRequestEvent`)

- ISR triggered when I2C Master requests data.
- Reads the `volatile` `latest_freq_hz` and `latest_rms_millivolts`.
- Packs these two `uint16_t` values into a 4-byte buffer.
- Sends the buffer via `Wire.write()`.
- **Note:** Ensure reads of `latest_freq_hz` and `latest_rms_millivolts` are safe (atomic or protected if updates in the ADC task are not atomic). `uint16_t` reads/writes are typically atomic on ESP32.

### 4. LED Task (`ledStatusTask`) (Optional)

- Runs continuously using FreeRTOS.
- Provides basic status indication (e.g., blinking LED) to show the system is running.
- Could potentially indicate error states (e.g., calibration failure).

## System Flow Diagram (Revised)

```mermaid
graph TD
    subgraph ESP32-C3 (Arduino - Slave @ 0x08)
        A[Start] --> A1(Init Pins: LED?);
        A1 --> B(Setup: Serial, ADC DMA, I2C Slave);
        B --> C(Check eFuse TP Cal);
        C -- OK --> D(Characterize ADC -> adc_chars);
        C -- Fail --> E(Error State / Halt);
        D --> F(Register I2C onRequest);
        D --> G(Start ADC Processing Task);
        D --> H(Start Status LED Task?);

        subgraph ADC Processing Task
            I[Loop] --> J(Read ADC DMA -> sample_buffer);
            J --> K(Calc dynamic_mean_level_adc from buffer);
            K --> L(Convert all samples -> voltage_mv & Calc mean_voltage_mv);
            L --> M{Process Samples in Buffer};
            M -- Sample --> N(Update SumSq Voltage Deviation for cycle);
            N --> O(Incr Cycle Sample Count);
            O --> P{Zero Crossing vs dynamic_mean_level_adc?};
            P -- Full Cycle --> Q(Calc Freq & Cycle RMS Voltage);
            Q --> R(Store Freq/RMS in Circ Buff [5]);
            R --> S{Have 5 Cycles?};
            S -- Yes --> T(Update Averages -> latest_freq/rms);
            S -- No --> U(Yield);
            T --> U;
            P -- No/Partial --> V(Next Sample or Yield);
            V --> M;
            U --> I;
        end

        subgraph I2C onRequest Handler (ISR Context)
            W[Master Requests Data] --> X(Read volatile latest_freq/rms);
            X --> Y(Pack u16, u16);
            Y --> Z(Wire.write(buffer, 4));
        end

        subgraph Status LED Task (Optional)
            AA[Loop] --> BB(Check System State);
            BB -- Normal --> CC(Toggle LED);
            BB -- Error --> DD(Show Error Pattern);
            CC --> EE(Delay);
            DD --> EE;
            EE --> AA;
        end

        F -.-> W; // I2C Request triggers handler
        G --> I; // Start ADC Task Loop
        H --> AA; // Start LED Task Loop
    end

    subgraph ESP32-S3 (MicroPython - Master)
        MM[I2C Master Init @ 400kHz] --> NN[Loop/Trigger];
        NN --> OO[Request 4 bytes from Slave 0x08];
        OO --> PP[Read Data];
        PP --> QQ[Unpack u16 freq_hz, u16 rms_mV];
        QQ --> RR[Use Data];
        RR --> NN;
    end

    Z -.-> PP; // Slave sends data to Master
```

## Key Changes Summary

- Removed manual calibration (button, NVS, `CAL_LOW_MV`, `CAL_HIGH_MV`).
- Relies solely on ESP-IDF `esp_adc_cal` with eFuse Two Point data.
- Removed manual mean level setting (button, NVS).
- Mean level (`dynamic_mean_level_adc`) is calculated dynamically from sample buffers.
- RMS voltage is calculated using the standard formula on the _voltage_ values (obtained via `esp_adc_cal_raw_to_voltage`), based on deviations from the dynamically calculated mean _voltage_ of each cycle.
- Frequency calculation uses zero-crossings against the dynamic _raw_ mean level.
- Removed `buttonMonitorTask`.
- Simplified `ledNormalFlashTask` to an optional `ledStatusTask`.
- Updated Mermaid diagram significantly.

## Next Steps

Implement the code changes based on this updated plan.
