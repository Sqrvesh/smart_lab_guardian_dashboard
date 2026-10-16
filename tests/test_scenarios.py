"""
Automated validation of all 10 built-in test scenarios.
Verifies the complete pipeline: data models, state manager, risk calculation,
event transitions, and outcome assertion checks.
"""

import pytest

from smart_lab_guardian_dashboard.core.state_manager import StateManager
from smart_lab_guardian_dashboard.simulation.scenario_engine import ScenarioEngine
from smart_lab_guardian_dashboard.simulation.scenarios import get_all_scenarios


@pytest.fixture
def clean_engine():
    sm = StateManager()
    sm.set_mode("SIMULATION")
    return ScenarioEngine(sm)


@pytest.mark.parametrize("scenario_id", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
def test_all_scenarios_pass_deterministic(clean_engine, scenario_id):
    clean_engine.select_scenario(scenario_id)
    result = clean_engine.run_all_deterministic()

    assert result["all_passed"] is True, (
        f"Scenario {scenario_id} ({result['scenario_name']}) failed some checks: {result['checks']}"
    )


def test_scenario_source_labeling(clean_engine):
    clean_engine.select_scenario(3)  # Overheating
    clean_engine.run_all_deterministic()

    # Verify that model source is SIMULATION, not STM32
    assert clean_engine.state_manager.incident_state.model_source == "SIMULATION ENGINE"
    assert clean_engine.state_manager.incident_state.source == "SIMULATION"

    # Verify chart data has source labeled as SIMULATION
    temp_hist = clean_engine.state_manager.sensor_history["temp_ambient"]
    assert len(temp_hist) > 0
    assert all(pt["source"] == "SIMULATION" for pt in temp_hist)
