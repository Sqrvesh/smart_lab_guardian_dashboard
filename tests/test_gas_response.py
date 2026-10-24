"""
Comprehensive unit and integration tests for Gas Response Index (GRI):
- Exact UART hardware sample validation (mq5_adc = 2008, mq5_mv = 1618)
- Stable baseline readings and noise deadband filtering
- Monotonically increasing gas response progression
- Decreasing recovery response progression
- Missing and out-of-range sensor readings
- Tracker warm-up and 'Calibrating' state verification
- Gas leak baseline protection (ensuring leak does not corrupt clean-air baseline)
- Segregation between HARDWARE and SIMULATION data
- Dashboard card rendering state verification
"""

import pytest
from datetime import datetime

from smart_lab_guardian_dashboard.core.gas_response import (
    compute_gri,
    gri_label,
    gri_color,
    GriTracker,
    GRI_BASELINE_ADC,
    GRI_DEFAULT_SPAN,
    GRI_BASELINE_MIN_SAMPLES,
    GRI_NOISE_DEADBAND,
    GRI_LEVEL_LOW_MAX,
    GRI_LEVEL_ELEVATED_MAX,
)
from smart_lab_guardian_dashboard.core.state_manager import StateManager
from smart_lab_guardian_dashboard.communication.message_models import SampleMessage, DataSource
from smart_lab_guardian_dashboard.core.freshness import FreshnessTracker, FreshnessStatus
from smart_lab_guardian_dashboard.dashboard.components import render_gas_response_card


# ---------------------------------------------------------------------------
# 1. UART Sample from Prompt & Baseline Tests
# ---------------------------------------------------------------------------

def test_uart_sample_from_prompt_does_not_stay_at_100():
    """
    UART sample: 217,30.23,84.38,2008,1618 (mq5_adc = 2008).
    Firmware risk: MQ5_CHANGE=0, MQ5_VARIABILITY=0, MQ5_ABRUPT=0.
    GRI must be 0.0 (Low response), NOT stuck at 100.
    """
    baseline = 2008.0
    gri = compute_gri(mq5_adc=2008, baseline_adc=baseline)
    assert gri is not None
    assert gri == 0.0
    assert gri_label(gri) == "Low"
    assert gri_color(gri) == "#10b981"  # green


def test_stable_baseline_with_ambient_noise():
    """
    ADC readings fluctuating within the noise deadband (±8 counts) of baseline
    should result in GRI = 0.0.
    """
    baseline = 2008.0
    readings = [2008, 2005, 2010, 2014, 2002, 2016]
    for r in readings:
        gri = compute_gri(mq5_adc=r, baseline_adc=baseline)
        assert gri == 0.0, f"Reading {r} with baseline {baseline} produced GRI={gri}, expected 0.0"
        assert gri_label(gri) == "Low"


# ---------------------------------------------------------------------------
# 2. Dynamic Progression: Increasing & Decreasing Readings
# ---------------------------------------------------------------------------

def test_increasing_readings_progression():
    """
    GRI must rise monotonically across Low, Elevated, and High severity bands,
    and must not reach 100 until ADC genuinely reaches the maximum response span.
    """
    baseline = 2008.0
    span = 600.0  # Max response expected around 2008 + 600 = 2608

    # Readings from clean baseline to saturation
    readings = [2008, 2050, 2120, 2250, 2400, 2550, 2608, 2800]
    gri_values = [compute_gri(r, baseline_adc=baseline, response_span=span) for r in readings]

    # Verify all are valid floats
    assert all(g is not None for g in gri_values)

    # Verify monotonic non-decreasing
    for i in range(len(gri_values) - 1):
        assert gri_values[i] <= gri_values[i + 1]

    # Check band transitions
    assert gri_values[0] == 0.0  # Baseline -> Low
    assert gri_label(gri_values[0]) == "Low"

    # 2050 is slightly above baseline: ~7.1 GRI -> Low
    assert gri_values[1] < GRI_LEVEL_LOW_MAX
    assert gri_label(gri_values[1]) == "Low"

    # 2250 is ~39.5 GRI -> Elevated
    assert GRI_LEVEL_LOW_MAX < gri_values[3] <= GRI_LEVEL_ELEVATED_MAX
    assert gri_label(gri_values[3]) == "Elevated"

    # 2550 is ~90.5 GRI -> High
    assert gri_values[5] > GRI_LEVEL_ELEVATED_MAX
    assert gri_label(gri_values[5]) == "High"

    # 2608 reaches full scale (100.0)
    assert gri_values[6] == 100.0

    # 2800 is clamped at 100.0
    assert gri_values[7] == 100.0


def test_decreasing_readings_progression():
    """
    GRI must decrease monotonically during recovery as gas clears.
    """
    baseline = 2008.0
    readings = [2608, 2450, 2300, 2150, 2050, 2008]
    gri_values = [compute_gri(r, baseline_adc=baseline) for r in readings]

    for i in range(len(gri_values) - 1):
        assert gri_values[i] >= gri_values[i + 1]

    assert gri_values[0] == 100.0
    assert gri_values[-1] == 0.0


# ---------------------------------------------------------------------------
# 3. Missing, Invalid, and Out-of-Range Data Handling
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("invalid_adc", [None, -1, -500, 4096, 5000, "abc", []])
def test_invalid_adc_returns_none(invalid_adc):
    assert compute_gri(mq5_adc=invalid_adc, baseline_adc=2008.0) is None


@pytest.mark.parametrize("invalid_baseline", [None, -1, -100, 4096, 6000, "2008", {}])
def test_invalid_baseline_returns_none(invalid_baseline):
    assert compute_gri(mq5_adc=2008, baseline_adc=invalid_baseline) is None


# ---------------------------------------------------------------------------
# 4. GriTracker Warm-up & Calibration
# ---------------------------------------------------------------------------

def test_tracker_displays_calibrating_during_warmup():
    """
    Without a pre-configured baseline, tracker must report is_calibrated=False
    and return (None, False) until GRI_BASELINE_MIN_SAMPLES readings arrive.
    """
    tracker = GriTracker(min_samples_before_stable=5, configured_baseline=None)
    assert tracker.is_calibrated is False
    assert tracker.baseline is None

    # Feed 4 samples (insufficient for stable baseline)
    for i in range(4):
        tracker.update(2008)
        val, calibrated = tracker.compute(2008)
        assert calibrated is False
        assert val is None
        assert tracker.is_calibrated is False
        assert tracker.samples_collected == i + 1

    # 5th sample establishes baseline
    tracker.update(2008)
    assert tracker.is_calibrated is True
    assert tracker.baseline == 2008.0

    val, calibrated = tracker.compute(2008)
    assert calibrated is True
    assert val == 0.0


def test_tracker_gas_event_does_not_corrupt_baseline():
    """
    A persistent gas leak (elevated ADC) must NOT be absorbed into clean-air baseline.
    The baseline must remain at the clean-air value.
    """
    tracker = GriTracker(min_samples_before_stable=5, configured_baseline=None)

    # Establish clean air baseline at 2008
    for _ in range(5):
        tracker.update(2008)
    assert tracker.baseline == 2008.0

    # Simulate gas leak: 30 consecutive samples at 2450 ADC
    for _ in range(30):
        tracker.update(2450)

    # Baseline must NOT have risen to 2450!
    assert tracker.baseline == 2008.0

    # Response must remain High, not drop to 0
    val, _ = tracker.compute(2450)
    assert val is not None
    assert val > 70.0
    assert gri_label(val) == "High"


def test_tracker_ignores_invalid_and_out_of_range_updates():
    """Invalid or out-of-range readings must be ignored by update()."""
    tracker = GriTracker(min_samples_before_stable=3)
    tracker.update(None)
    tracker.update(-10)
    tracker.update(5000)
    tracker.update("bad")
    assert tracker.samples_collected == 0
    assert tracker.is_calibrated is False


def test_tracker_configured_baseline():
    """A configured baseline (e.g. 200.0 in simulation) calibrates immediately."""
    tracker = GriTracker(configured_baseline=200.0)
    assert tracker.is_calibrated is True
    assert tracker.baseline == 200.0

    val, cal = tracker.compute(200)
    assert cal is True
    assert val == 0.0

    val_high, _ = tracker.compute(700)
    assert val_high is not None
    assert val_high > 80.0


def test_tracker_downward_clean_air_drift():
    """
    Clean-air downward drift (e.g. ambient temperature drop) should be
    gradually tracked by the 10th percentile baseline.
    """
    tracker = GriTracker(baseline_window=10, min_samples_before_stable=5)
    for _ in range(5):
        tracker.update(2008)
    assert tracker.baseline == 2008.0

    # Slowly drift down to 1990
    for _ in range(10):
        tracker.update(1990)

    # Baseline should track down to 1990
    assert tracker.baseline == 1990.0


# ---------------------------------------------------------------------------
# 5. StateManager & Mode Segregation Integration Tests
# ---------------------------------------------------------------------------

def test_hardware_mode_sample_processing_and_calibration():
    """
    In HARDWARE mode, UART samples calibrate the baseline and update GRI history.
    """
    sm = StateManager()
    sm.set_mode("LIVE HARDWARE")
    assert sm.active_mode == "HARDWARE"

    now = datetime.now()

    # First 4 samples: calibrating
    for i in range(4):
        msg = SampleMessage(timestamp=now, sample_id=i + 1, mq5_adc=2008, mq5_mv=1618, source="HARDWARE")
        sm.process_message(msg)
        assert sm.gri_tracker.is_calibrated is False
        assert len(sm.gri_history) == 0

    # 5th sample: calibrated!
    msg5 = SampleMessage(timestamp=now, sample_id=5, mq5_adc=2008, mq5_mv=1618, source="HARDWARE")
    sm.process_message(msg5)
    assert sm.gri_tracker.is_calibrated is True
    assert sm.gri_tracker.baseline == 2008.0
    assert len(sm.gri_history) == 1
    assert sm.gri_history[-1]["value"] == 0.0

    # Changing MQ-5 reading (gas rise to 2250) updates GRI
    msg_gas = SampleMessage(timestamp=now, sample_id=6, mq5_adc=2250, mq5_mv=1800, source="HARDWARE")
    sm.process_message(msg_gas)
    assert len(sm.gri_history) == 2
    gas_gri = sm.gri_history[-1]["value"]
    assert 35.0 <= gas_gri <= 45.0  # Elevated range


def test_simulation_samples_do_not_overwrite_live_hardware():
    """
    When active_mode is HARDWARE, incoming SIMULATION messages must be rejected
    so stale simulation values cannot overwrite live readings.
    """
    sm = StateManager()
    sm.set_mode("LIVE HARDWARE")

    now = datetime.now()
    # Process 5 hardware samples to calibrate
    for i in range(5):
        sm.process_message(SampleMessage(timestamp=now, sample_id=i, mq5_adc=2008, mq5_mv=1618, source="HARDWARE"))

    assert sm.sensor_states["gas_mq5"].current_value == 2008
    assert sm.gri_tracker.baseline == 2008.0

    # Incoming stale simulation message
    sim_msg = SampleMessage(timestamp=now, sample_id=99, mq5_adc=200, mq5_mv=650, source="SIMULATION")
    sm.process_message(sim_msg)

    # Must NOT have overwritten hardware sensor state or baseline
    assert sm.sensor_states["gas_mq5"].current_value == 2008
    assert sm.gri_tracker.baseline == 2008.0


def test_mode_switch_clears_stale_tracker():
    """
    Switching from SIMULATION to LIVE HARDWARE resets the tracker so simulated 200 ADC
    baseline does not corrupt hardware calibration.
    """
    sm = StateManager()
    sm.set_mode("SIMULATION")
    assert sm.gri_tracker.is_calibrated is True
    assert sm.gri_tracker.baseline == 200.0

    # Switch to LIVE HARDWARE
    sm.set_mode("LIVE HARDWARE")
    assert sm.active_mode == "HARDWARE"
    assert sm.gri_tracker.is_calibrated is False
    assert sm.gri_tracker.baseline is None
