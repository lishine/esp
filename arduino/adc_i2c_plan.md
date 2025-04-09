# ESP32-C3 ADC/I2C Processing Plan

## Objective

Read motor current via ADC (GPIO4) on an ESP32-C3 running Arduino code. Calculate the signal's frequency (using zero-crossing) and RMS voltage. Average these values over 5 cycles. Act as an I2C slave (address 0x08) to send the latest averaged frequency (Hz) and RMS (mV) as two `uint16_t` values (4 bytes total) to an ESP32-S3 master upon request.

## Hardware & Configuration

- **MCU:** ESP32-C3
- **ADC Input Pin:** GPIO4
- **Button Pin:** GPIO9 (for calibration and mean level setting)
- **LED Pin:** GPIO8 (for status feedback)
- **I2C Pins:** GPIO0 (SDA), GPIO1 (SCL)
- **I2C Role:** Slave
- **I2C Address:** `0x08`
- **ADC Settings:**
  - Continuous DMA Mode
  - Attenuation: `ADC_ATTEN_DB_11`
  - Bitwidth: `ADC_BITWIDTH_12`
  - Target Sample Rate (`TARGET_SAMPLE_FREQ_HZ`): ~50,000 Hz (Adjustable)
  - **Important:** Requires low source impedance (<10kΩ, ideally <1kΩ) driving the ADC pin, or use an op-amp buffer.
- **Calibration Reference Voltages:**
  - Low: `CAL_LOW_MV = 1000` (1.0V)
  - High: `CAL_HIGH_MV = 2000` (2.0V)
- **Averaging Window:** `NUM_CYCLES_AVERAGE = 5` cycles

## Core Logic

### 1. Calibration (Persistent via NVS)

- **Storage:** Non-Volatile Storage (NVS) namespace `adc_cal` stores:
  - `adc_zero_offset` (raw ADC reading at `CAL_LOW_MV`) - Key: `zero_offs`
  - `adc_scaling_factor` (mV per ADC count) - Key: `scale_fact`
  - `waveform_mean_level_adc` (raw ADC reading for zero-crossing) - Key: `mean_lvl`
- **Trigger:** Hold Button (GPIO9) for 5 seconds during normal operation.
- **Procedure:**
  1.  Enter Calibration Mode (indicated by LED). Pause normal processing.
  2.  User applies `CAL_LOW_MV` (1V) to ADC input.
  3.  User short-presses button -> System reads `cal_low_reading`. (LED confirmation).
  4.  User applies `CAL_HIGH_MV` (2V) to ADC input.
  5.  User short-presses button -> System reads `cal_high_reading`. (LED confirmation).
  6.  Calculate:
      - `offset = cal_low_reading` (Assuming 1V maps directly to offset for simplicity, adjust if 0V was used)
      - `factor = (CAL_HIGH_MV - CAL_LOW_MV) / (cal_high_reading - cal_low_reading)`
  7.  Save `offset` and `factor` to NVS.
  8.  Exit Calibration Mode (LED confirmation), resume normal operation.
- **Loading:** Calibration values are loaded from NVS during `setup()`.

### 2. Waveform Mean Level Setting (Zero-Crossing Reference)

- **Trigger:** Short press (< 3s) Button (GPIO9) during normal operation while the signal is active.
- **Action:**
  1.  Read current raw ADC value (`mean_reading`).
  2.  Update `waveform_mean_level_adc` global variable.
  3.  Save `mean_reading` to NVS (`mean_lvl` key).
  4.  Provide LED confirmation.

### 3. ADC Processing Task (`adcProcessingTask`)

- Runs continuously using FreeRTOS.
- Reads ADC samples via DMA buffer (`adc_continuous_read`).
- Loads calibrated `adc_zero_offset`, `adc_scaling_factor`, and `waveform_mean_level_adc` from globals (which were loaded from NVS).
- **Per Sample:**
  - Converts raw ADC to millivolts: `mV = (raw_adc - adc_zero_offset) * adc_scaling_factor`.
  - Updates sum-of-squares for the current cycle's RMS calculation.
  - Increments sample count for the current cycle.
- **Zero-Crossing Detection:** Compares `raw_adc` against `waveform_mean_level_adc` to detect full cycles (e.g., rising edge to rising edge).
- **Per Full Cycle:**
  - Calculate period (samples / sample rate).
  - Calculate RMS voltage for the cycle: `sqrt(sum_of_squares / samples_in_cycle)`.
  - Store period and RMS value in respective circular buffers (size 5).
  - Increment cycle counter.
- **Averaging (Every 5 Cycles):**
  - Calculate average frequency (Hz) from the last 5 periods.
  - Calculate average RMS (mV) from the last 5 RMS values.
  - Update `volatile` global variables: `latest_freq_hz` and `latest_rms_millivolts`.
  - Reset cycle counter.
- Yields CPU (`vTaskDelay`).

### 4. I2C Communication (`i2cRequestEvent`)

- ISR triggered when I2C Master requests data.
- Reads the `volatile` `latest_freq_hz` and `latest_rms_millivolts`.
- Packs these two `uint16_t` values into a 4-byte buffer.
- Sends the buffer via `Wire.write()`.

### 5. Button Monitoring Task (`buttonMonitorTask`)

- Runs continuously using FreeRTOS.
- Debounces and monitors GPIO9.
- Detects short presses (< 3s) to trigger Mean Level setting.
- Detects long presses (>= 5s) to trigger entry into Calibration Mode.
- Manages state for Calibration Mode steps.

### 6. LED Task (`ledNormalFlashTask`)

- Runs continuously using FreeRTOS.
- Provides normal status indication (e.g., 4s ON, 4s OFF).
- Coordinates with Button Task/Calibration logic to allow override for feedback flashes (e.g., using flags or a queue).

## System Flow Diagram

```mermaid
graph TD
    subgraph ESP32-C3 (Arduino - Slave @ 0x08)
        A[Start] --> A1(Init Pins: LED, Button);
        A1 --> A2(Init NVS);
        A2 --> A3(Load Cal Vals from NVS);
        A3 --> B(Setup: Serial, ADC DMA, I2C Slave);
        B --> C(Register I2C onRequest);
        B --> D(Start ADC Processing Task);
        B --> E(Start Button Monitor Task);
        B --> F(Start Normal LED Flash Task);

        subgraph ADC Processing Task
            G[Loop] --> H(Read ADC DMA);
            H --> I{Process Samples};
            I -- Sample --> J(Convert to mV using cal factors);
            J --> K(Update Cycle RMS SumSq);
            K --> L(Incr Cycle Sample Count);
            L --> M{Zero Crossing vs mean_level?};
            M -- Full Cycle --> N(Calc Period &amp; Cycle RMS);
            N --> O(Store in Circ Buff [5]);
            O --> P{Have 5 Cycles?};
            P -- Yes --> Q(Update Averages -> latest_freq/rms);
            P -- No --> R(Yield);
            Q --> R;
            M -- No/Partial --> R;
            R --> G;
        end

        subgraph Button Monitor Task
            S[Loop] --> T(Read Button State);
            T --> U{Button Event?};
            U -- Held 5s --> V(Enter Calibration Mode);
            U -- Short Press (Normal Op) --> W(Read ADC -> new_mean);
            W --> X(Update global &amp; Save mean_level NVS);
            X --> Y(Trigger Mean Set LED Flash);
            U -- No Event / Other --> Z(Yield);
            Y --> Z;
            V --> Z;
            Z --> S;
        end

         subgraph Calibration Mode Logic (within Button Task or separate state machine)
            AA[Entered Cal Mode] --> AB(Wait for Button Press - Step 1: Apply 1V);
            AB -- Short Press --> AC(Read ADC -> cal_low_reading);
            AC --> AD(Store cal_low_reading);
            AD --> AE(Trigger Low Set LED Flash);
            AE --> AF(Wait for Button Press - Step 2: Apply 2V);
            AF -- Short Press --> AG(Read ADC -> cal_high_reading);
            AG --> AH(Calc offset &amp; scaling_factor using 1V/2V refs);
            AH --> AI(Save offset &amp; factor to NVS);
            AI --> AJ(Trigger High Set LED Flash);
            AJ --> AK(Exit Calibration Mode);
        end

        subgraph I2C onRequest Handler (ISR Context)
            CC[Master Requests Data] --> DD(Read volatile latest_freq/rms);
            DD --> EE(Pack u16, u16);
            EE --> FF(Wire.write(buffer, 4));
        end

        subgraph Normal LED Flash Task
            GG[Loop] --> HH(Check for Cal/Feedback Flash Request);
            HH -- No --> II(Toggle LED);
            HH -- Yes --> JJ(Skip Toggle);
            II --> KK(Delay 4s);
            JJ --> KK;
            KK --> GG;
        end

        C -.-> CC;
        V --> AA; // Enter Cal Mode
        AK --> S; // Exit Cal Mode
        Y -.-> HH;  // Feedback flash requests pre-empt normal flash
        AE -.-> HH;
        AJ -.-> HH;
    end

    subgraph ESP32-S3 (MicroPython - Master)
        MM[I2C Master Init @ 400kHz] --> NN[Loop/Trigger];
        NN --> OO[Request 4 bytes from Slave 0x08];
        OO --> PP[Read Data];
        PP --> QQ[Unpack u16 freq_hz, u16 rms_mV];
        QQ --> RR[Use Data];
        RR --> NN;
    end

    FF -.-> PP;
```

## Next Steps

Proceed to implementation in Code mode.
