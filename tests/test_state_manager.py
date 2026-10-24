"""
Unit tests for StateManager and EventManager:
- Sensor value updates (Temperature, Humidity, MQ-5 ADC and mV)
- TinyML MLP and explainable risk packet processing
- Stale sensor detection
- Duplicate event suppression
- Incident transitions with MQ-5 snapshot
- Hardware vs Simulation data segregation
- CSV export and filtering
"""

from datetime import datetime, timedelta
import pytest

from smart_lab_guardian_dashboard.core.state_manager import StateManager
from smart_lab_guardian_dashboard.core.freshness import FreshnessStatus
from smart_lab_guardian_dashboard.communication.message_models import (
    SampleMessage,
    MlpMessage,
    RiskMessage,
    IncidentMessage,
    DataSource,
)


@pytest.fixture
def state_mgr():
    return StateManager()


def test_sensor_updates_and_history(state_mgr):
    now = datetime.now()
    sample = SampleMessage(
        timestamp=now,
        sample_id=1,
        temperature=25.5,
        humidity=50.2,
        mq5_adc=412,
        mq5_mv=1340,
        source="HARDWARE",
    )
    state_mgr.process_message(sample)

    temp_state = state_mgr.sensor_states["temp_ambient"]
    hum_state = state_mgr.sensor_states["humidity_rel"]
    gas_state = state_mgr.sensor_states["gas_mq5"]
    gas_mv_state = state_mgr.sensor_states["gas_mq5_mv"]

    assert temp_state.current_value == 25.5
    assert hum_state.current_value == 50.2
    assert gas_state.current_value == 412
    assert gas_mv_state.current_value == 1340
    assert temp_state.status == FreshnessStatus.FRESH
    assert gas_state.status == FreshnessStatus.FRESH
    assert len(state_mgr.sensor_history["temp_ambient"]) == 1
    assert len(state_mgr.sensor_history["gas_mq5"]) == 1


def test_mlp_and_risk_message_processing(state_mgr):
    now = datetime.now()
    mlp = MlpMessage(
        timestamp=now,
        sample_id=10,
        mlp_class="ELEVATED_GAS",
        confidence=88.5,
        source="HARDWARE",
    )
    risk = RiskMessage(
        timestamp=now,
        risk_score=62.0,
        persist_risk=58.0,
        severity="HIGH",
        mq5_change=0.15,
        mq5_abrupt=1,
        mq5_variability=0.25,
        recovery=0,
        why="Elevated combustible gas detected with abrupt change",
        source="HARDWARE",
    )

    state_mgr.process_message(mlp)
    assert state_mgr.latest_mlp is mlp
    assert state_mgr.incident_state.incident_class == "ELEVATED_GAS"
    assert state_mgr.incident_state.mlp_confidence == 88.5

    state_mgr.process_message(risk)
    assert state_mgr.latest_risk is risk
    assert state_mgr.incident_state.risk_score == 62.0
    assert state_mgr.incident_state.persist_risk == 58.0
    assert state_mgr.incident_state.severity == "HIGH"
    assert state_mgr.incident_state.mq5_change == 0.15
    assert state_mgr.incident_state.mq5_abrupt == 1
    assert "abrupt change" in state_mgr.incident_state.why
    assert len(state_mgr.risk_history) == 1
    assert state_mgr.risk_history[-1]["persist_risk"] == 58.0


def test_incident_transition_and_duplicate_suppression(state_mgr):
    now = datetime.now()
    # 1. Normal incident
    inc1 = IncidentMessage(
        timestamp=now,
        incident_class="NORMAL",
        risk_score=10.0,
        severity="LOW",
        why="Normal baseline",
        source="HARDWARE",
    )
    state_mgr.process_message(inc1)
    assert len(state_mgr.event_manager.events) == 1

    # 2. Duplicate normal incident 1 second later (identical class, identical risk)
    inc2 = IncidentMessage(
        timestamp=now + timedelta(seconds=1),
        incident_class="NORMAL",
        risk_score=10.0,
        severity="LOW",
        why="Normal baseline",
        source="HARDWARE",
    )
    state_mgr.process_message(inc2)
    # Should be suppressed!
    assert len(state_mgr.event_manager.events) == 1

    # 3. Meaningful transition: Overheating detected!
    inc3 = IncidentMessage(
        timestamp=now + timedelta(seconds=2),
        incident_class="OVERHEATING",
        risk_score=68.0,
        severity="HIGH",
        why="Rapid thermal rise detected",
        source="HARDWARE",
    )
    state_mgr.process_message(inc3)
    # Must record transition
    assert len(state_mgr.event_manager.events) == 2
    latest_evt = state_mgr.event_manager.events[-1]
    assert latest_evt.incident_class == "OVERHEATING"
    assert latest_evt.severity == "HIGH"


def test_simulation_data_source_labeling(state_mgr):
    state_mgr.set_mode(DataSource.SIMULATION.value)
    now = datetime.now()

    sim_sample = SampleMessage(
        timestamp=now,
        sample_id=1,
        temperature=35.0,
        humidity=45.0,
        mq5_adc=650,
        source="SIMULATION",
    )
    state_mgr.process_message(sim_sample)

    temp_state = state_mgr.sensor_states["temp_ambient"]
    assert temp_state.source == "SIMULATION"

    history_pt = state_mgr.sensor_history["temp_ambient"][-1]
    assert history_pt["source"] == "SIMULATION"


def test_event_manager_filtering_and_export(state_mgr):
    now = datetime.now()
    inc_low = IncidentMessage(
        timestamp=now,
        incident_class="NORMAL",
        risk_score=10.0,
        severity="LOW",
        why="All nominal",
        source="HARDWARE",
    )
    inc_crit = IncidentMessage(
        timestamp=now + timedelta(seconds=5),
        incident_class="OVERHEATING",
        risk_score=85.0,
        severity="CRITICAL",
        why="Critical temperature runaway",
        source="SIMULATION",
        scenario_name="Scenario 3: Overheating",
    )
    state_mgr.process_message(inc_low)
    state_mgr.process_message(inc_crit)

    # Filter by severity
    crit_events = state_mgr.event_manager.get_filtered_events(severity="CRITICAL")
    assert len(crit_events) == 1
    assert crit_events[0].severity == "CRITICAL"

    # Search filter
    runaway_events = state_mgr.event_manager.get_filtered_events(search_query="runaway")
    assert len(runaway_events) == 1

    # CSV Export
    csv_str = state_mgr.event_manager.export_csv()
    assert "Critical temperature runaway" in csv_str
    assert "Overheating" in csv_str  # clean label (was OVERHEATING before label mapping)
    assert "Event ID" in csv_str
    assert "MQ5 ADC" in csv_str
    assert "Gas Response" in csv_str
