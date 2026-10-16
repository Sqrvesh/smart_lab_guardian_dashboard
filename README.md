# Smart Lab Guardian Dashboard

**Context-Aware Multi-Sensor Incident Detection and Explainable Risk Prioritization System for Unattended Laboratories**

---

## 1. Overview & Embedded Architecture

**Smart Lab Guardian** is a real-time monitoring and incident explainability dashboard connected to an **STM32L475VG** microcontroller on the **B-L475E-IOT01A1** development board.

### Firmware & Hardware System
- **Microcontroller:** STM32L475VG (ARM Cortex-M4 @ 80 MHz, 1 MB Flash, 128 KB SRAM).
- **Development Board:** STMicroelectronics B-L475E-IOT01A1.
- **Environmental Sensor:** HTS221 capacitive digital relative humidity and temperature sensor.
- **Occupancy / Motion Sensor:** HC-SR501 Passive Infrared (PIR) sensor connected to STM32 `PD14` (Arduino `D2`).
- **Embedded TinyML Model:** Multilayer Perceptron (MLP) deployed and running directly on the STM32 microcontroller.
- **Input Features:** 9 features computed over rolling windows:
  1. `TAVG`: Temperature Average (°C)
  2. `TMIN`: Temperature Minimum (°C)
  3. `TMAX`: Temperature Maximum (°C)
  4. `TDELTA`: Temperature Delta / Gradient (°C)
  5. `HAVG`: Relative Humidity Average (% RH)
  6. `HMIN`: Relative Humidity Minimum (% RH)
  7. `HMAX`: Relative Humidity Maximum (% RH)
  8. `HDELTA`: Relative Humidity Delta (% RH)
  9. `PIRCOUNT`: Cumulative PIR trigger pulse count in window
- **Model Output Classes:** `NORMAL`, `MOTION_ACTIVITY`, `OVERHEATING`, `ENVIRONMENTAL_ANOMALY`.
- **Explainable Risk Engine:** Microcontroller-side weighted risk engine combining TinyML base risk (`ML_BASE`) with contextual modifiers (`THERMAL`, `HUMIDITY`, `TREND`, `MOTION`) to produce an authoritative total risk score (`0 - 100`), a severity classification (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`), and a human-readable explanation (`WHY`).
- **Communication Channel:** ST-LINK on-board Virtual COM Port over USB at 115200 baud (8-N-1, no flow control).

---

## 2. Project Structure

```
smart_lab_guardian_dashboard/
├── app.py                     # Streamlit application entrypoint
├── requirements.txt           # Pinned production dependencies
├── README.md                  # Comprehensive documentation and runbook
├── .gitignore                 # Version control ignore rules
│
├── dashboard/                 # Presentation and visualization layer
│   ├── layout.py              # Dark theme CSS, header bar, telemetry banner
│   ├── status.py              # Laboratory status hero card & severity indicator
│   ├── components.py          # Generic sensor cards, TinyML panel, risk attribution, event table
│   └── charts.py              # Interactive Plotly real-time telemetry charts
│
├── communication/             # Hardware communication layer
│   ├── message_models.py      # Typed dataclasses for protocol messages
│   ├── protocol_parser.py     # Resilient parser for UART ASCII format
│   └── serial_manager.py      # Thread-safe non-blocking serial worker & port scanner
│
├── core/                      # Application state and business logic
│   ├── sensor_registry.py     # Extensible sensor registration and field mapper
│   ├── state_manager.py       # Global telemetry state and bounded history buffers
│   ├── event_manager.py       # Incident transition recorder and duplicate suppressor
│   ├── freshness.py           # Telemetry age tracker and stale data flagging
│   └── configuration.py       # Config loader and default threshold provider
│
├── simulation/                # Scenario simulator and test console
│   ├── scenarios.py           # 10 deterministic scenario definitions
│   └── scenario_engine.py     # Simulation playback, stepping, and assertion checker
│
├── tests/                     # Automated Pytest suite (38 unit tests)
│   ├── test_parser.py         # Protocol parser robustness tests
│   ├── test_serial_manager.py # Mocked serial communication lifecycle tests
│   ├── test_freshness.py      # Stale state and timeout tests
│   ├── test_state_manager.py  # State transitions, suppression, and CSV export tests
│   └── test_scenarios.py      # Deterministic verification of all 10 scenarios
│
└── config/                    # Declarative configuration files
    ├── sensors.json           # Sensor definitions, units, and thresholds
    └── thresholds.json        # Global safety envelopes and timeout limits
```

---

## 3. Quick Start & Execution (Windows)

### Prerequisites
- Python 3.10 or 3.11 installed.

### Step 1: Virtual Environment Setup
Open PowerShell or Command Prompt in the project folder:
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment (PowerShell)
.venv\Scripts\Activate.ps1

# (Or in Command Prompt cmd.exe)
# .venv\Scripts\activate.bat
```

### Step 2: Install Dependencies
```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Step 3: Run Automated Tests
Execute the test suite to verify the installation:
```powershell
python -m pytest -v
```
*Expected: 38 passed in ~2 seconds.*

### Step 4: Launch the Dashboard
```powershell
streamlit run app.py
```
The browser will automatically open at `http://localhost:8501`.

---

## 4. Operational Modes: Hardware vs Simulation

### Mode 1: Simulation Mode (No Hardware Required)
1. In the sidebar under **Communication Mode**, select **SIMULATION**.
2. Select any scenario from the **Select Test Scenario** dropdown (1 through 10).
3. Use the control buttons:
   - **▶️ Play:** Starts automated progression at configurable speed.
   - **⏸️ Pause:** Freezes progression.
   - **⏭️ Step:** Advances one discrete time step.
   - **🔄 Reset:** Restarts the scenario from the beginning.
   - **⚡ Run Full Scenario Test:** Immediately evaluates all steps and validates outcome assertions.
4. An **Expected Outcomes** checklist dynamically displays green checkmarks as requirements are met.
5. All simulated metrics are prominently tagged with a `SIMULATION MODE ACTIVE` banner and labeled `(Simulated)` in charts.

### Mode 2: Live Hardware Mode (STM32 USB Connection)
1. Plug the **STM32 B-L475E-IOT01A1** board into your computer using a Micro-USB cable connected to the **ST-LINK USB connector (CN1)**.
2. In the dashboard sidebar, switch **Communication Mode** to **LIVE HARDWARE**.
3. Click the **🔄** button to refresh available COM ports.
4. Select the detected STMicroelectronics Virtual COM Port (e.g. `COM7`).
5. Ensure baud rate is set to `115200`.
6. Click **⚡ Connect**.
7. The status badge will switch to `SERIAL: CONNECTED` and live sensor telemetry will appear.

> [!IMPORTANT]
> **Serial Port Exclusivity:** Windows permits only one application to open a COM port at a time. If **PuTTY**, TeraTerm, or the Arduino Serial Monitor is open on the port, close it before clicking Connect in the dashboard.

---

## 5. Existing Firmware UART Protocol

The STM32 firmware transmits ASCII text lines terminated by `\r\n` at 115200 baud (8-N-1, no flow control).

### Supported Message Formats

#### 1. Sensor Samples (`SAMPLE`)
Emitted periodically as individual sensor measurements:
```
SAMPLE,TEMP_C,HUMIDITY_RH,PIR
1,31.19,55.59,1
SAMPLE,31.19,55.59,1
```
- The parser handles both prefixed (`SAMPLE,`) and indexed numeric rows (`1,31.19,55.59,1`).
- Physical bounds: Temperature `[-40, 125]` °C, Humidity `[0, 100]` % RH, PIR `0` or `1`.

#### 2. Rolling Feature Window (`FEATURES`)
Emitted by the feature extraction pipeline:
```
FEATURES,TAVG=31.22,TMIN=31.19,TMAX=31.26,TDELTA=0.07,HAVG=55.69,HMIN=55.60,HMAX=55.83,HDELTA=0.21,PIRCOUNT=10
```
- Transmits the 9 features fed into the STM32 MLP.
- Parsed dynamically by `KEY=VALUE` pairs. Unknown future features are preserved without crashing.

#### 3. Explainable Incident Prediction (`INCIDENT`)
Emitted by the inference engine:
```
INCIDENT,MOTION_ACTIVITY,RISK=26,SEVERITY=LOW,ML_BASE=20,THERMAL=15,HUMIDITY=0,TREND=0,MOTION=20,WHY=ML detected repeated PIR activity in the sensor window
```
- Token 1: Model predicted class (`NORMAL`, `MOTION_ACTIVITY`, `OVERHEATING`, `ENVIRONMENTAL_ANOMALY`).
- `RISK`: Total risk score (`0 - 100`).
- `SEVERITY`: `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- Contributory components: `ML_BASE`, `THERMAL`, `HUMIDITY`, `TREND`, `MOTION`.
- `WHY`: Human-readable explanation. The parser preserves spaces, commas, and punctuation within the explanation.

#### 4. Diagnostic & Startup Banners
Startup messages (e.g. `=== Smart Lab Guardian Firmware v1.0 ===`, `Initializing HTS221... OK`, `ML Model self-test: output NORMAL`) are intercepted, routed to the raw diagnostic inspector, and isolated from live sensor telemetry.

---

## 6. Extensible Sensor Architecture (Adding MQ-5 or New Sensors)

New sensors can be added through declarative configuration without modifying UI components or charting logic.

### How to Add a Sensor:
Edit [`smart_lab_guardian_dashboard/config/sensors.json`](file:///c:/data/ABHITHA/STUDY/COLLEGE/SEM-5/EMBEDDED/PROJECT/smart_lab_guardian_dashboard/config/sensors.json):
```json
{
  "sensor_id": "gas_mq5",
  "display_name": "MQ-5 Combustible Gas",
  "sensor_type": "gas",
  "unit": "raw ADC",
  "data_type": "analog",
  "description": "MQ-5 gas sensor connected to ADC1 Channel 5",
  "enabled": true,
  "expected_update_interval": 1.0,
  "warning_thresholds": { "high": 400.0 },
  "critical_thresholds": { "high": 700.0 },
  "chart_enabled": true,
  "source_field": "gas_raw",
  "calibration_status": "CALIBRATED",
  "is_installed": true
}
```

### Firmware Mapping:
When firmware emits extra columns or fields:
- Numeric sample lines: `1,25.40,55.10,0,380.0`
- The parser automatically attaches the extra column to `extra_sensors["extra_sensor_1"]` or `"gas_raw"`.
- The generic sensor card and chart automatically display the new sensor, its thresholds, trend arrows, and unit.

---

## 7. Built-In Simulation Scenarios

| Scenario | Name | Condition | Expected Outcome |
| :--- | :--- | :--- | :--- |
| **1** | Normal Laboratory | 25°C, 52% RH, no motion | Class: `NORMAL`, Severity: `LOW`, Risk: ~10 |
| **2** | Motion Activity | Normal temp/humidity, PIR pulses active | Class: `MOTION_ACTIVITY`, Motion risk elevated |
| **3** | Overheating | Thermal ramp from 26.5°C to 38.5°C | Class: `OVERHEATING`, Severity: `CRITICAL`, Thermal risk dominates |
| **4** | Environmental Anomaly | Rapid humidity spike to 88% RH | Class: `ENVIRONMENTAL_ANOMALY`, Humidity risk rises |
| **5** | Combined Incident | 37°C temp, 82% RH, PIR active | Multi-factor compounding risk (`CRITICAL`, >80) |
| **6** | Sensor Disconnected | Temp sensor halts updates | Temp flagged as `STALE`, other sensors unaffected |
| **7** | Communication Failure | Line noise followed by silence | Telemetry flagged as `STALE`, stale banner appears |
| **8** | Invalid Input | Malformed numbers (`31.XX`), missing fields | Corrupted messages quarantined, system remains online |
| **9** | Risk Transitions | LOW → MEDIUM → HIGH → CRITICAL → LOW | Status colors and event timeline update dynamically |
| **10** | Future Gas Sensor | MQ-5 raw ADC stream (180 to 750 ADC) | Renders generic card & chart using raw ADC units |

---

## 8. Troubleshooting Guide

### 1. "Port COM7 is busy or access denied"
- Cause: Another application (PuTTY, TeraTerm, Arduino IDE) currently holds an open handle to the COM port.
- Solution: Close all other serial terminal programs and click Connect again.

### 2. "Hardware Telemetry is Stale" warning banner
- Cause: Serial port is open, but no valid newline-terminated messages arrived within 6 seconds.
- Solution: Check that the ST-LINK board is powered and running firmware. Inspect the **Raw Protocol Inspector** at the bottom of the page to check if firmware output is visible.

### 3. "No Ports Found" in dropdown
- Cause: ST-LINK USB driver not recognized or USB cable disconnected.
- Solution: Reconnect the USB cable to port CN1 on the board and click the **🔄** button. Check Windows Device Manager under "Ports (COM & LPT)" for "STMicroelectronics STLink Virtual COM Port".

### 4. Malformed message count increasing
- Cause: Baud rate mismatch or electrical noise on the UART line.
- Solution: Verify baud rate matches firmware (default `115200`). Expand the **Raw Protocol Inspector** to examine raw strings.

---

## 9. Implemented Features & Verification

- [x] **Full Streamlit Application:** Modular architecture with responsive dark industrial UI.
- [x] **Zero Cloud / Local First:** Runs entirely on local machine without internet or database.
- [x] **Robust Protocol Parser:** Handles `SAMPLE`, `FEATURES`, `INCIDENT`, headers, and diagnostics.
- [x] **Spaces in Explanations:** Preserves complex `WHY` explanations containing commas and punctuation.
- [x] **Non-Blocking Serial Manager:** Dedicated background thread with thread-safe queue.
- [x] **Extensible Sensor Registry:** Declarative `sensors.json` supporting future sensors (MQ-5).
- [x] **Freshness Tracking:** Visible stale warnings when telemetry halts.
- [x] **Interactive Plotly Visualizations:** Temperature, humidity, risk timeline, and PIR state with time-window filtering.
- [x] **Event Timeline with Duplicate Suppression:** Records state transitions and supports CSV export.
- [x] **10 Built-In Test Scenarios:** Deterministic test suite with real-time outcome assertion checklist.
- [x] **Automated Test Suite:** 38 passing Pytest tests.
- [x] **Scientific Integrity:** No fabricated ML probabilities, fake ppm gas conversions, or simulated data masquerading as hardware data.
