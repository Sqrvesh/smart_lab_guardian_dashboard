"""
Built-in scenario definitions for Smart Lab Guardian Simulator.
Implements 8 MQ-5-based scenarios (PIR removed) with deterministic message
sequences and automated pass/fail outcome validators.

All MLP predictions are illustrative simulation outputs, not actual
firmware model inference.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Any, Callable, Optional

from smart_lab_guardian_dashboard.communication.message_models import (
    SampleMessage,
    MlpMessage,
    RiskMessage,
    MalformedMessage,
    DiagnosticMessage,
    ProtocolMessage,
)
from smart_lab_guardian_dashboard.core.state_manager import StateManager
from smart_lab_guardian_dashboard.core.freshness import FreshnessStatus


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScenarioOutcomeAssertion:
    """An expected outcome to verify during or after scenario execution."""
    description: str
    check_fn: Callable[[StateManager], bool]
    passed: bool = False


@dataclass
class ScenarioTick:
    """A single discrete time step in a scenario run."""
    step_index: int
    delay_seconds: float
    messages: List[ProtocolMessage]
    status_summary: str


@dataclass
class Scenario:
    """Scenario specification and generator."""
    scenario_id: int
    name: str
    description: str
    total_steps: int
    expected_outcomes: List[str]
    generate_ticks: Callable[[datetime], List[ScenarioTick]]
    assertions: List[ScenarioOutcomeAssertion] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper: build a standard SimulationTick with Sample + MLP + Risk messages
# ---------------------------------------------------------------------------

def _make_tick(
    i: int,
    t: datetime,
    sample_id: int,
    temp: float,
    hum: float,
    mq5_adc: int,
    mq5_mv: int,
    mlp_class: str,
    mlp_conf: int,
    risk: float,
    persist_risk: float,
    severity: str,
    mq5_change: float,
    mq5_abrupt: int,
    mq5_var: float,
    recovery: int,
    why: str,
    scenario_name: str,
    delay: float = 2.0,
) -> ScenarioTick:
    """Convenience builder for a complete three-message simulation tick."""
    # Build explainable risk attribution breakdown for the scenario tick
    gas_contrib = max(3.0, min(100.0, (mq5_adc - 190.0) / (700.0 - 190.0) * 100.0))
    thermal_contrib = 5.0 if temp <= 25.5 else min(100.0, 5.0 + (temp - 25.5) / (37.0 - 25.5) * 95.0)
    hum_contrib = 4.0 if hum <= 55.0 else min(100.0, 4.0 + (hum - 55.0) / (85.0 - 55.0) * 96.0)
    if mq5_abrupt:
        dyn_contrib = min(100.0, 65.0 + abs(mq5_change) * 35.0)
    elif mq5_var > 0.15:
        dyn_contrib = min(85.0, mq5_var * 200.0)
    else:
        dyn_contrib = min(100.0, max(3.0, abs(mq5_change) * 75.0))
    ml_contrib = min(100.0, max(4.0, (risk * 0.85) + (float(mlp_conf) * 0.15)))

    contributions = {
        "GAS_RESPONSE": round(gas_contrib, 1),
        "GAS_DYNAMICS": round(dyn_contrib, 1),
        "THERMAL": round(thermal_contrib, 1),
        "HUMIDITY": round(hum_contrib, 1),
        "ML_MODEL": round(ml_contrib, 1),
    }

    return ScenarioTick(
        step_index=i + 1,
        delay_seconds=delay,
        messages=[
            SampleMessage(
                timestamp=t,
                sample_id=sample_id,
                temperature=temp,
                humidity=hum,
                mq5_adc=mq5_adc,
                mq5_mv=mq5_mv,
                source="SIMULATION",
                raw_line=f"{sample_id},{temp:.2f},{hum:.2f},{mq5_adc},{mq5_mv}",
            ),
            MlpMessage(
                timestamp=t,
                sample_id=sample_id,
                mlp_class=mlp_class,
                confidence=float(mlp_conf),
                raw_line=f"MLP_EXPERIMENTAL,CLASS={mlp_class},CONF={mlp_conf},SAMPLE_ID={sample_id}",
                source="SIMULATION",
                is_valid=True,
            ),
            RiskMessage(
                timestamp=t,
                risk_score=risk,
                persist_risk=persist_risk,
                severity=severity,
                mq5_change=mq5_change,
                mq5_abrupt=mq5_abrupt,
                mq5_variability=mq5_var,
                recovery=recovery,
                why=why,
                raw_line=(
                    f"RISK_EXPERIMENTAL,RISK={risk:.0f},PERSIST_RISK={persist_risk:.0f},"
                    f"SEVERITY={severity},MQ5_CHANGE={mq5_change:.3f},"
                    f"MQ5_ABRUPT={mq5_abrupt},MQ5_VAR={mq5_var:.3f},"
                    f"RECOVERY={recovery},WHY={why}"
                ),
                source="SIMULATION",
                is_valid=True,
                scenario_name=scenario_name,
                risk_contributions=contributions,
            ),
        ],
        status_summary=(
            f"Step {i+1}: {scenario_name} | Temp={temp:.1f}°C "
            f"Hum={hum:.1f}% MQ5={mq5_adc} ADC | Risk={risk:.0f} ({severity})"
        ),
    )


# ---------------------------------------------------------------------------
# Scenario 1: Normal Laboratory
# ---------------------------------------------------------------------------
def _gen_scenario_1(start_time: datetime) -> List[ScenarioTick]:
    ticks = []
    for i in range(6):
        t = start_time + timedelta(seconds=i * 2)
        temp = 25.2 + (i % 3) * 0.1
        hum = 52.0 + (i % 2) * 0.4
        adc = 195 + (i % 3)      # stable near baseline
        mv = 635 + (i % 3) * 3
        ticks.append(_make_tick(
            i=i, t=t, sample_id=i + 1,
            temp=temp, hum=hum, mq5_adc=adc, mq5_mv=mv,
            mlp_class="NORMAL", mlp_conf=92,
            risk=8.0, persist_risk=9.0, severity="LOW",
            mq5_change=0.01, mq5_abrupt=0, mq5_var=0.05, recovery=0,
            why="Stable baseline. Gas response within normal laboratory ambient range.",
            scenario_name="Scenario 1: Normal Laboratory",
        ))
    return ticks


# ---------------------------------------------------------------------------
# Scenario 2: Sustained Gas Sensor Rise
# ---------------------------------------------------------------------------
def _gen_scenario_2(start_time: datetime) -> List[ScenarioTick]:
    ticks = []
    adc_values = [200, 250, 320, 400, 490, 570, 640, 700]
    for i, adc in enumerate(adc_values):
        t = start_time + timedelta(seconds=i * 2)
        mv = int(adc * 3.25)
        risk = 8.0 + i * 11.0
        persist_risk = max(8.0, risk - 5)
        severity = "LOW" if risk < 25 else ("MEDIUM" if risk < 50 else ("HIGH" if risk < 80 else "CRITICAL"))
        mlp_class = "NORMAL" if i < 3 else ("GAS_RISING" if i < 6 else "GAS_ELEVATED")
        why = (
            f"Gradual MQ-5 rise detected. ADC={adc}. Sustained upward trend over {i+1} samples."
            if i >= 2 else "Baseline stable."
        )
        ticks.append(_make_tick(
            i=i, t=t, sample_id=i + 1,
            temp=25.5, hum=53.0, mq5_adc=adc, mq5_mv=mv,
            mlp_class=mlp_class, mlp_conf=max(60, 90 - i * 3),
            risk=min(100.0, risk), persist_risk=min(100.0, persist_risk),
            severity=severity,
            mq5_change=round((adc - 200) / 200, 3), mq5_abrupt=0,
            mq5_var=round(0.05 + i * 0.02, 3), recovery=0,
            why=why,
            scenario_name="Scenario 2: Sustained Gas Sensor Rise",
        ))
    return ticks


# ---------------------------------------------------------------------------
# Scenario 3: Abrupt Gas Sensor Change
# ---------------------------------------------------------------------------
def _gen_scenario_3(start_time: datetime) -> List[ScenarioTick]:
    ticks = []
    # Quiet → spike → gradual return
    adc_seq = [200, 205, 680, 720, 650, 490, 350, 250, 210, 200]
    for i, adc in enumerate(adc_seq):
        t = start_time + timedelta(seconds=i * 2)
        mv = int(adc * 3.25)
        abrupt = 1 if i == 2 else 0   # abrupt flag at spike onset
        change = round((adc - adc_seq[max(0, i - 1)]) / max(1, adc_seq[max(0, i - 1)]), 3)
        risk = 10.0 if i < 2 else (75.0 if i in (2, 3) else max(10.0, 75.0 - (i - 3) * 10))
        persist_risk = max(risk - 8, 8.0)
        severity = "LOW" if risk < 25 else ("MEDIUM" if risk < 50 else ("HIGH" if risk < 80 else "CRITICAL"))
        mlp_class = "ABRUPT_CHANGE" if i in (2, 3, 4) else "NORMAL"
        why = (
            "Sudden MQ-5 jump detected — possible transient gas release or sensor disturbance."
            if abrupt else (
                "Recovering toward baseline." if i >= 5 else "Stable baseline."
            )
        )
        ticks.append(_make_tick(
            i=i, t=t, sample_id=i + 1,
            temp=25.0, hum=52.0, mq5_adc=adc, mq5_mv=mv,
            mlp_class=mlp_class, mlp_conf=88,
            risk=risk, persist_risk=persist_risk, severity=severity,
            mq5_change=change, mq5_abrupt=abrupt, mq5_var=0.15 if i in (2, 3) else 0.05,
            recovery=max(0, i - 4),
            why=why, scenario_name="Scenario 3: Abrupt Gas Sensor Change",
        ))
    return ticks


# ---------------------------------------------------------------------------
# Scenario 4: Persistent Elevated Response
# ---------------------------------------------------------------------------
def _gen_scenario_4(start_time: datetime) -> List[ScenarioTick]:
    ticks = []
    # MQ-5 stays elevated across multiple windows — persistent risk builds
    base_adc = 480
    for i in range(10):
        t = start_time + timedelta(seconds=i * 2)
        adc = base_adc + (i % 3) * 8   # slight fluctuation around 480
        mv = int(adc * 3.25)
        risk = 40.0 + min(i * 4.0, 30.0)
        persist_risk = risk + min(i * 2.0, 15.0)   # persistence adds pressure
        severity = "MEDIUM" if risk < 50 else "HIGH"
        ticks.append(_make_tick(
            i=i, t=t, sample_id=i + 1,
            temp=25.5, hum=53.0, mq5_adc=adc, mq5_mv=mv,
            mlp_class="GAS_ELEVATED", mlp_conf=85,
            risk=risk, persist_risk=min(100, persist_risk), severity=severity,
            mq5_change=0.02, mq5_abrupt=0, mq5_var=0.08, recovery=0,
            why=f"MQ-5 has remained elevated for {i+1} consecutive windows. Persistent risk accumulating.",
            scenario_name="Scenario 4: Persistent Elevated Response",
        ))
    return ticks


# ---------------------------------------------------------------------------
# Scenario 5: Environmental Change with Gas Response
# ---------------------------------------------------------------------------
def _gen_scenario_5(start_time: datetime) -> List[ScenarioTick]:
    ticks = []
    steps = [
        (25.0, 52.0, 200, "NORMAL", 8.0, 9.0, "LOW"),
        (27.5, 60.0, 260, "NORMAL", 15.0, 16.0, "LOW"),
        (30.0, 68.0, 350, "ENV_CHANGE", 28.0, 30.0, "MEDIUM"),
        (32.5, 75.0, 430, "ENV_CHANGE", 48.0, 52.0, "MEDIUM"),
        (34.0, 80.0, 510, "GAS_ELEVATED", 65.0, 70.0, "HIGH"),
        (35.0, 82.0, 560, "GAS_ELEVATED", 75.0, 80.0, "HIGH"),
    ]
    for i, (temp, hum, adc, cls, risk, persist, sev) in enumerate(steps):
        t = start_time + timedelta(seconds=i * 2)
        mv = int(adc * 3.25)
        ticks.append(_make_tick(
            i=i, t=t, sample_id=i + 1,
            temp=temp, hum=hum, mq5_adc=adc, mq5_mv=mv,
            mlp_class=cls, mlp_conf=86,
            risk=risk, persist_risk=persist, severity=sev,
            mq5_change=round((adc - 200) / 200, 3), mq5_abrupt=0,
            mq5_var=0.06, recovery=0,
            why=f"Rising temperature ({temp:.1f}°C), humidity ({hum:.1f}% RH) and gas response co-occurring.",
            scenario_name="Scenario 5: Environmental Change",
        ))
    return ticks


# ---------------------------------------------------------------------------
# Scenario 6: Noisy Sensor
# ---------------------------------------------------------------------------
def _gen_scenario_6(start_time: datetime) -> List[ScenarioTick]:
    ticks = []
    noisy = [205, 310, 195, 420, 210, 380, 200, 350, 215, 390]
    for i, adc in enumerate(noisy):
        t = start_time + timedelta(seconds=i * 2)
        mv = int(adc * 3.25)
        var = 0.30 + (i % 3) * 0.05
        risk = 12.0 + (i % 4) * 8.0
        persist_risk = 15.0   # persistence stays low despite spikes
        severity = "LOW" if risk < 25 else "MEDIUM"
        ticks.append(_make_tick(
            i=i, t=t, sample_id=i + 1,
            temp=25.0, hum=52.0, mq5_adc=adc, mq5_mv=mv,
            mlp_class="NORMAL", mlp_conf=72,
            risk=risk, persist_risk=persist_risk, severity=severity,
            mq5_change=round((adc - 210) / 210, 3), mq5_abrupt=0,
            mq5_var=var, recovery=0,
            why=f"High MQ-5 variability ({var:.2f}). Pattern suggests sensor noise, not a sustained event.",
            scenario_name="Scenario 6: Noisy Sensor",
        ))
    return ticks


# ---------------------------------------------------------------------------
# Scenario 7: Recovery After Event
# ---------------------------------------------------------------------------
def _gen_scenario_7(start_time: datetime) -> List[ScenarioTick]:
    ticks = []
    # Peak then gradual decline in both instantaneous and persistent risk
    adc_seq = [700, 680, 600, 490, 380, 290, 240, 210, 200]
    risks    = [82, 75, 62, 50, 38, 26, 18, 12, 8]
    persists = [82, 80, 73, 62, 50, 38, 27, 18, 12]
    sevs = ["CRITICAL", "HIGH", "HIGH", "MEDIUM", "MEDIUM", "MEDIUM", "LOW", "LOW", "LOW"]
    for i, (adc, risk, persist, sev) in enumerate(zip(adc_seq, risks, persists, sevs)):
        t = start_time + timedelta(seconds=i * 2)
        mv = int(adc * 3.25)
        rec = max(0, i - 1)
        ticks.append(_make_tick(
            i=i, t=t, sample_id=i + 1,
            temp=25.0, hum=52.0, mq5_adc=adc, mq5_mv=mv,
            mlp_class="RECOVERING" if i >= 2 else "GAS_ELEVATED",
            mlp_conf=85,
            risk=float(risk), persist_risk=float(persist), severity=sev,
            mq5_change=round((adc - adc_seq[min(i + 1, len(adc_seq) - 1)]) / max(1, adc), 3),
            mq5_abrupt=0, mq5_var=0.06, recovery=rec,
            why=(
                f"Gas response returning toward baseline. Recovery window={rec}. "
                f"Persistent risk still elevated at {persist}."
            ),
            scenario_name="Scenario 7: Recovery After Event",
        ))
    return ticks


# ---------------------------------------------------------------------------
# Scenario 8: Combined Incident
# ---------------------------------------------------------------------------
def _gen_scenario_8(start_time: datetime) -> List[ScenarioTick]:
    ticks = []
    steps = [
        (25.0, 52.0, 200, "NORMAL",   8.0,  9.0, "LOW",      "Baseline stable."),
        (27.0, 58.0, 290, "NORMAL",   18.0, 19.0, "LOW",      "Minor gas and temperature rise."),
        (30.0, 65.0, 420, "GAS_RISING", 42.0, 44.0, "MEDIUM", "Simultaneous environmental and gas rise."),
        (33.5, 72.0, 570, "COMBINED_EVENT", 65.0, 68.0, "HIGH",
         "High temperature, humidity, and sustained gas sensor rise occurring together."),
        (36.0, 78.0, 650, "COMBINED_EVENT", 82.0, 86.0, "CRITICAL",
         "Critical combined event: gas elevated, temperature >35°C, humidity >75%. Multiple thresholds crossed."),
        (37.0, 80.0, 690, "COMBINED_EVENT", 90.0, 92.0, "CRITICAL",
         "Peak combined hazard. Recommend immediate investigation."),
    ]
    for i, (temp, hum, adc, cls, risk, persist, sev, why) in enumerate(steps):
        t = start_time + timedelta(seconds=i * 2)
        mv = int(adc * 3.25)
        ticks.append(_make_tick(
            i=i, t=t, sample_id=i + 1,
            temp=temp, hum=hum, mq5_adc=adc, mq5_mv=mv,
            mlp_class=cls, mlp_conf=89,
            risk=risk, persist_risk=persist, severity=sev,
            mq5_change=round((adc - 200) / 200, 3), mq5_abrupt=1 if i == 4 else 0,
            mq5_var=0.08, recovery=0,
            why=why, scenario_name="Scenario 8: Combined Incident",
        ))
    return ticks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_all_scenarios() -> List[Scenario]:
    """Returns definitions of all 8 built-in test scenarios."""
    return [
        Scenario(
            scenario_id=1,
            name="Scenario 1: Normal Laboratory",
            description=(
                "Stable temperature (24–27 °C), moderate humidity (40–60 %), "
                "and MQ-5 readings near clean-air baseline. Risk stays LOW."
            ),
            total_steps=6,
            expected_outcomes=[
                "Sensor readings remain within nominal envelopes",
                "MLP class remains 'NORMAL'",
                "Risk severity evaluates as 'LOW'",
                "Gas Response Index stays in 'Low' range",
            ],
            generate_ticks=_gen_scenario_1,
        ),
        Scenario(
            scenario_id=2,
            name="Scenario 2: Sustained Gas Sensor Rise",
            description=(
                "MQ-5 ADC readings gradually increase across consecutive samples, "
                "driving a sustained upward risk trend."
            ),
            total_steps=8,
            expected_outcomes=[
                "Gas Response Index increases monotonically",
                "MLP class transitions to GAS_RISING then GAS_ELEVATED",
                "Risk severity escalates from LOW to HIGH",
                "Persistent risk tracks instantaneous risk with lag",
            ],
            generate_ticks=_gen_scenario_2,
        ),
        Scenario(
            scenario_id=3,
            name="Scenario 3: Abrupt Gas Sensor Change",
            description=(
                "A sudden MQ-5 spike followed by gradual return toward baseline. "
                "Tests abrupt-change detection and recovery tracking."
            ),
            total_steps=10,
            expected_outcomes=[
                "MQ5_ABRUPT flag triggers at spike onset",
                "Risk jumps to HIGH then recovers",
                "Recovery window counter increments during decline",
                "Event timeline records the transition without duplicates",
            ],
            generate_ticks=_gen_scenario_3,
        ),
        Scenario(
            scenario_id=4,
            name="Scenario 4: Persistent Elevated Response",
            description=(
                "MQ-5 remains elevated across multiple windows. Persistent risk "
                "accumulates above the instantaneous reading."
            ),
            total_steps=10,
            expected_outcomes=[
                "Persistent risk exceeds instantaneous risk after 3+ windows",
                "Severity reaches HIGH",
                "Gas Response Index stays in Elevated or High range",
            ],
            generate_ticks=_gen_scenario_4,
        ),
        Scenario(
            scenario_id=5,
            name="Scenario 5: Environmental Change",
            description=(
                "Temperature and humidity rise alongside gas sensor response, "
                "simulating a spill or HVAC event."
            ),
            total_steps=6,
            expected_outcomes=[
                "Temperature and humidity cards show rising trend",
                "Gas response co-rises with environmental parameters",
                "Risk severity reaches HIGH with combined contributors",
            ],
            generate_ticks=_gen_scenario_5,
        ),
        Scenario(
            scenario_id=6,
            name="Scenario 6: Noisy Sensor",
            description=(
                "MQ-5 readings fluctuate with high variability. Tests stability "
                "of the risk engine against sensor noise."
            ),
            total_steps=10,
            expected_outcomes=[
                "MQ5_VAR (variability) remains high throughout",
                "MLP correctly classifies as NORMAL despite fluctuations",
                "Persistent risk stays LOW — transient spikes not amplified",
                "GRI does not spuriously alarm",
            ],
            generate_ticks=_gen_scenario_6,
        ),
        Scenario(
            scenario_id=7,
            name="Scenario 7: Recovery After Event",
            description=(
                "Readings return toward baseline and the persistent risk score "
                "gradually decreases after a peak event."
            ),
            total_steps=9,
            expected_outcomes=[
                "Instantaneous risk decreases with MQ-5 return to baseline",
                "Persistent risk declines more slowly than instantaneous",
                "Recovery window counter increases during recovery phase",
                "Risk history chart shows clear peak-and-decline shape",
            ],
            generate_ticks=_gen_scenario_7,
        ),
        Scenario(
            scenario_id=8,
            name="Scenario 8: Combined Incident",
            description=(
                "Gas sensor changes and environmental parameters (temperature, "
                "humidity) all deviate simultaneously."
            ),
            total_steps=6,
            expected_outcomes=[
                "Multiple risk contributors elevated concurrently",
                "Risk reaches CRITICAL (>80)",
                "MLP class transitions to COMBINED_EVENT",
                "Event timeline records the escalation",
            ],
            generate_ticks=_gen_scenario_8,
        ),
    ]
