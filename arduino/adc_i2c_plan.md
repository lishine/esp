# ESP32-C3 ADC/I2C Processing Plan (Revised v3)

## Objective

Read motor current via ADC (GPIO4) on an ESP32-C3 running Arduino code. Use ESP-IDF calibration functions (eFuse Two Point only) to convert readings to millivolts. Dynamically calculate the signal's mean level, frequency (using zero-crossing against the dynamic mean), and RMS voltage.

A "batch" of processing involves collecting data until either a target number of cycles (`NUM_CYCLES_AVERAGE`) is detected OR a maximum sample count (`MAX_SAMPLES_PER_BATCH`, calculated based on `MIN_EXPECTED_FREQ_HZ`) is reached. Average the frequency and RMS values over the valid cycles completed within that batch. If specific errors occur during batch collection (ADC read errors, invalid mean calculation, short cycles), the averaging for that batch is skipped. **If a batch completes due to the sample limit with zero cycles detected (e.g., DC input), calculate and report the overall RMS of the entire batch with a frequency of 0 Hz.**

Act as an I2C slave (address 0x08) to send the latest calculated frequency (Hz) and RMS (mV) as two `uint16_t` values (4 bytes total) to an ESP32-S3 master upon request. Aim for a reporting interval of approximately 1 second between the start of consecutive batches by calculating and applying a delay after each batch completes.

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
  - Target Sample Rate (`TARGET_SAMPLE_FREQ_HZ`): **80,000 Hz**
  - **Important:** Requires low source impedance (<10kΩ, ideally <1kΩ) driving the ADC pin, or use an op-amp buffer.
- **Calibration:**
  - Uses ESP-IDF `esp_adc_cal` library.
  - **Requires eFuse Two Point (TP) calibration values.** Initialization will fail if TP values are not present in the ESP32-C3's eFuse.
- **Processing Parameters:**
  - Averaging Window (Cycles): `NUM_CYCLES_AVERAGE = 10` cycles
  - **Minimum Expected Frequency:** `MIN_EXPECTED_FREQ_HZ = 20` Hz (Used for sample limit calculation)
  - **Maximum Expected Frequency:** `MAX_EXPECTED_FREQ_HZ = 300` Hz (Informational)
  - Max Samples per Batch (`MAX_SAMPLES_PER_BATCH`): Calculated as `(1.0 / MIN_EXPECTED_FREQ_HZ) * NUM_CYCLES_AVERAGE * TARGET_SAMPLE_FREQ_HZ` (approx. 40000 samples)
  - Target Reporting Interval: ~1000 ms

## Core Logic

### 1. ADC Calibration Initialization (`setup()`)

- (Unchanged from v2)

### 2. ADC Processing Task (`adcProcessingTask`)

- Runs continuously using FreeRTOS.
- **Main Loop:**
  1.  **Record Batch Start Time:** `batch_start_time = millis();`
  2.  **Read ADC Samples:** Read available samples via DMA (`adc_continuous_read`). Handle errors, set `batch_valid = false` on error.
  3.  **Convert & Calculate Dynamic Mean:** If read OK, convert raw samples to mV, calculate `dynamic_mean_level_mv`. Set `batch_valid = false` if no valid samples in buffer.
  4.  **Process Individual Samples:** Iterate through valid converted samples (`voltage_buffer[i] != UINT32_MAX`):
      - Increment `samples_in_current_batch`.
      - **Accumulate Batch Totals:** Increment `valid_samples_in_current_batch`, add to `sum_mv_current_batch`, add squared value to `sum_sq_current_batch`.
      - **Accumulate Cycle Totals:** Increment `samples_in_current_cycle`, add to `sum_mv_current_cycle`, add squared value to `sum_sq_current_cycle`.
      - **Zero-Crossing Detection:** Compare `current_mv` against `dynamic_mean_level_mv`.
      - **On Full Cycle Detected:**
        - Check `samples_in_current_cycle > 1`. If not, set `batch_valid = false`.
        - Calculate cycle frequency and RMS.
        - Store in circular buffers.
        - Increment `cycle_count`.
        - Reset cycle accumulators.
  5.  **Check for Batch Completion:** Check if `cycle_count >= NUM_CYCLES_AVERAGE` OR `samples_in_current_batch >= MAX_SAMPLES_PER_BATCH`.
  6.  **Handle Batch Completion:** If condition met:
      - Log completion reason.
      - **Conditional Processing:** Check `if (batch_valid)`.
        - If `true`:
          - Determine `cycles_to_average` (actual cycles completed, max `NUM_CYCLES_AVERAGE`).
          - **If `cycles_to_average > 0`:** Calculate average frequency and RMS from circular buffers. Update `latest_freq_hz` and `latest_rms_millivolts`. Log average results.
          - **If `cycles_to_average == 0` (DC Input / No Cycles Detected):**
            - Check if `valid_samples_in_current_batch > 0`.
            - If yes: Calculate overall batch RMS using `sum_mv_current_batch`, `sum_sq_current_batch`, and `valid_samples_in_current_batch`. Set `latest_freq_hz = 0`, update `latest_rms_millivolts`. Log batch RMS result.
            - If no: Log warning, reset globals to 0.
        - If `false`: Log skip message, reset globals to 0.
      - **Reset Batch State:** Reset `cycle_count`, `batch_valid`, `samples_in_current_batch`, and **batch accumulators** (`sum_mv_current_batch`, `sum_sq_current_batch`, `valid_samples_in_current_batch`).
      - **Calculate and Apply Delay:** Calculate `delay_ms` for ~1s interval, `vTaskDelay()`.
  7.  **Loop:** Continue to next batch.

### 3. I2C Communication (`i2cRequestEvent`)

- (Unchanged from v2)

### 4. LED Task (`ledStatusTask`) (Optional)

- (Unchanged from v2)

## System Flow Diagram (Revised v3)

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
            I[Loop: Start Batch] --> I1(Record batch_start_time)
            I1 --> J(Read ADC DMA -> raw_result_buffer);
            J --> J_ERR{Read OK?};
            J_ERR -- No (Timeout/Error) --> J_INV[Set batch_valid=false] --> J_DEL(Delay 50ms) --> I; // Start new batch on error
            J_ERR -- Yes --> K(Convert Samples -> voltage_buffer);
            K --> K1(Calc dynamic_mean_level_mv);
            K1 --> K_ERR{valid_samples > 0?};
            K_ERR -- No --> K_INV[Set batch_valid=false] --> L{Process Samples in Buffer};
            K_ERR -- Yes --> L;

            subgraph Process Samples in Buffer Loop
                L_Start --> L_IncBatch(Incr samples_in_batch, Acc Batch Sums) --> L_IncCyc(Incr samples_in_cycle, Acc Cycle Sums) --> L_Cross{Zero Crossing?};
                L_Cross -- Yes --> L_Rise{Rising Edge?};
                L_Rise -- Yes --> L_Full{Full Cycle?};
                L_Full -- Yes --> L_Len{Cycle Len > 1?};
                L_Len -- Yes --> L_Calc(Calc Cycle Freq/RMS) --> L_Store(Store in Circ Buff) --> L_IncCycCnt(Incr cycle_count) --> L_ResetCycAcc(Reset Cycle Acc) --> L_EndSample;
                L_Len -- No --> L_Inv[Set batch_valid=false] --> L_LogShort(Log Short) --> L_ResetCycAcc;
                L_Full -- No --> L_MarkRise(Mark Rising) --> L_EndSample;
                L_Rise -- No --> L_MarkFall(Mark Falling) --> L_EndSample;
                L_Cross -- No --> L_EndSample;
            end

            L --> L_Start;
            L_EndSample --> M{Batch End Condition Met?};

            M -- No --> J; // Continue reading for current batch
            M -- Yes --> N(Log Batch End Reason);
            N --> O{batch_valid == true?};
            O -- Yes --> P{Cycles > 0?};
            P -- Yes --> Q(Average Cycle Freq/RMS) --> Q_Upd(Update Globals) --> S(Reset Batch State);
            P -- No --> R{Valid Samples in Batch > 0?};
            R -- Yes --> R_Calc(Calc Batch RMS) --> R_Upd(Update Globals Freq=0) --> S;
            R -- No --> R_Warn(Log Warn, Reset Globals) --> S;
            O -- No --> T(Log Skip, Reset Globals) --> S;

            S --> U(Calc batch_proc_time);
            U --> V(Calc delay_ms = 1000 - proc_time);
            V --> W(Delay(delay_ms));
            W --> I; // Start next batch
        end

        subgraph I2C onRequest Handler (ISR Context)
            X[Master Requests Data] --> Y(Read volatile latest_freq/rms);
            Y --> Z(Pack u16, u16);
            Z --> AA(Wire.write(buffer, 4));
        end

        subgraph Status LED Task (Optional)
            BB[Loop] --> CC(Check System State);
            CC -- Normal --> DD(Toggle LED);
            CC -- Error --> EE(Show Error Pattern);
            DD --> FF(Delay);
            EE --> FF;
            FF --> BB;
        end

        F -.-> X; // I2C Request triggers handler
        G --> I; // Start ADC Task Loop
        H --> BB; // Start LED Task Loop
    end

    subgraph ESP32-S3 (MicroPython - Master)
        MM[I2C Master Init @ 400kHz] --> NN[Loop/Trigger];
        NN --> OO[Request 4 bytes from Slave 0x08];
        OO --> PP[Read Data];
        PP --> QQ[Unpack u16 freq_hz, u16 rms_mV];
        QQ --> RR[Use Data];
        RR --> NN;
    end

    AA -.-> PP; // Slave sends data to Master

    note right of M
      Batch End Condition:
      (cycle_count >= 10)
      OR
      (samples_in_current_batch >= 40000)
    end note
```

## Key Changes Summary (v3)

- Removed manual calibration and mean level setting; relies on ESP-IDF TP calibration and dynamic mean calculation.
- **Batch Cancellation:** Averaging is skipped if ADC read errors, zero valid samples for mean, or short cycles occur during batch collection. `batch_valid` flag tracks this. Globals reset if averaging skipped.
- **Dynamic Batch Termination:** Batch ends when `NUM_CYCLES_AVERAGE` (10) cycles are detected OR `MAX_SAMPLES_PER_BATCH` (~40000) samples are processed.
- **Fixed Reporting Interval:** Task calculates batch processing time and delays to achieve an approximate 1-second interval between batch starts.
- **Averaging Logic:** Averages are calculated over the _actual_ number of valid cycles completed within the batch (up to 10).
- **DC Input Handling:** If a batch completes with 0 cycles detected (due to sample limit), the overall RMS of the entire batch is calculated and reported with Frequency = 0 Hz.
- **Frequency Constants:** Added `MIN_EXPECTED_FREQ_HZ` and `MAX_EXPECTED_FREQ_HZ` to `globals.h`.
- Updated Mermaid diagram to reflect new logic flow, including DC handling.

## Next Steps

The implementation reflecting this plan is complete in `adc_handler.cpp` and `globals.h`. Next steps involve compiling, uploading, and testing the firmware on the ESP32-C3, specifically testing with a DC input to verify the batch RMS calculation and reporting. Monitor serial output.
