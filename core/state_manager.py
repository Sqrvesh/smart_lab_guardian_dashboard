"""
Central state manager for Smart Lab Guardian.
Coordinates sensor readings, TinyML MLP predictions, explainable risk assessments,
time-series history buffers, freshness checks, and event transitions.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

try:
    from smart_lab_guardian_dashboard.communication.message_models import (
        ProtocolMessage,
        SampleMessage,
        MlpMessage,
        RiskMessage,
        IncidentMessage,
        DiagnosticMessage,
        MalformedMessage,
        MessageType,
        DataSource,
    )
    from smart_lab_guardian_dashboard.core.sensor_registry import SensorRegistry, SensorDefinition
    from smart_lab_guardian_dashboard.core.freshness import FreshnessTracker, FreshnessStatus
    from smart_lab_guardian_dashboard.core.event_manager import EventManager, IncidentEvent
    from smart_lab_guardian_dashboard.core.configuration import ConfigManager
    from smart_lab_guardian_dashboard.core.gas_response import (
        GriTracker,
        compute_gri,
        gri_label,
        gri_color,
        GRI_BASELINE_ADC,
    )
    from smart_lab_guardian_dashboard.core.evaluation_labels import format_evaluation_label
except ImportError:
    from communication.message_models import (
        ProtocolMessage,
        SampleMessage,
        MlpMessage,
        RiskMessage,
        IncidentMessage,
        DiagnosticMessage,
        MalformedMessage,
        MessageType,
        DataSource,
    )
    from core.sensor_registry import SensorRegistry, SensorDefinition
    from core.freshness import FreshnessTracker, FreshnessStatus
    from core.event_manager import EventManager, IncidentEvent
    from core.configuration import ConfigManager
    from core.gas_response import (
        GriTracker,
        compute_gri,
        gri_label,
        gri_color,
        GRI_BASELINE_ADC,
    )
    from core.evaluation_labels import format_evaluation_label


@dataclass
class LiveSensorState:
    """Current live state of an individual sensor."""
    sensor_id: str
    current_value: Optional[Any] = None
    previous_value: Optional[Any] = None
    last_updated: Optional[datetime] = None
    trend: str = "STEADY"  # 'RISING', 'FALLING', 'STEADY'
    status: str = FreshnessStatus.NO_DATA
    source: str = "HARDWARE"


@dataclass
class IncidentState:
    """Current incident and risk state."""
    incident_class: str = "NORMAL"
    mlp_confidence: Optional[float] = None
    risk_score: float = 0.0
    persist_risk: Optional[float] = None
    severity: str = "LOW"
    why: str = "System initialized; awaiting telemetry"
    risk_contributions: Dict[str, float] = None
    prediction_timestamp: Optional[datetime] = None
    source: str = "HARDWARE"
    model_source: str = "STM32 EMBEDDED MLP"
    scenario_name: Optional[str] = None
    mq5_change: Optional[float] = None
    mq5_abrupt: Optional[int] = None
    mq5_variability: Optional[float] = None
    recovery: Optional[int] = None

    def __post_init__(self):
        if self.risk_contributions is None:
            self.risk_contributions = {
                "ML_BASE": 0.0,
                "THERMAL": 0.0,
                "HUMIDITY": 0.0,
                "TREND": 0.0,
                "GAS": 0.0,
            }


class StateManager:
    """
    Manages the global reactive state of the Smart Lab Guardian system.
    """

    def __init__(
        self,
        sensor_registry: Optional[SensorRegistry] = None,
        event_manager: Optional[EventManager] = None,
        freshness_tracker: Optional[FreshnessTracker] = None,
        max_history_points: int = 3000,
    ):
        self.sensor_registry = sensor_registry or SensorRegistry()
        self.event_manager = event_manager or EventManager()
        self.freshness_tracker = freshness_tracker or FreshnessTracker(default_timeout_seconds=4.0)
        self.max_history_points = max_history_points

        # Operational mode: HARDWARE or SIMULATION
        self.active_mode: str = DataSource.HARDWARE.value

        # Sensor states
        self.sensor_states: Dict[str, LiveSensorState] = {}
        for s in self.sensor_registry.get_all_sensors():
            self.sensor_states[s.sensor_id] = LiveSensorState(
                sensor_id=s.sensor_id,
                status=FreshnessStatus.NOT_CONFIGURED if not s.is_installed else FreshnessStatus.NO_DATA,
            )

        # Incident state
        self.incident_state = IncidentState()

        # Latest embedded MLP and explainable risk messages
        self.latest_mlp: Optional[MlpMessage] = None
        self.latest_risk: Optional[RiskMessage] = None

        # Rolling Gas Response Index tracker & history
        self.gri_tracker = GriTracker()
        self.gri_history: deque = deque(maxlen=self.max_history_points)

        # Bounded time-series buffers for Plotly charts: List of (timestamp, value, source)
        self.sensor_history: Dict[str, deque] = {
            s.sensor_id: deque(maxlen=self.max_history_points)
            for s in self.sensor_registry.get_all_sensors()
        }
        # Risk history: (timestamp, risk_score, persist_risk, severity, incident_class, source)
        self.risk_history: deque = deque(maxlen=self.max_history_points)
        # Raw message log buffer: (timestamp, msg_type, raw_line, status)
        self.raw_message_log: deque = deque(maxlen=500)

        # Health & communication statistics
        self.total_messages_processed: int = 0
        self.malformed_messages_count: int = 0
        self.last_hardware_timestamp: Optional[datetime] = None
        self.last_any_message_timestamp: Optional[datetime] = None

    @property
    def latest_features(self) -> Dict[str, float]:
        """Backward-compatibility stub for legacy callers."""
        return {}

    @property
    def features_timestamp(self) -> Optional[datetime]:
        """Backward-compatibility stub for legacy callers."""
        return None

    def set_mode(self, mode: str) -> None:
        """Switches between HARDWARE and SIMULATION mode."""
        norm_mode = (
            DataSource.HARDWARE.value
            if mode in ("LIVE HARDWARE", "HARDWARE", DataSource.HARDWARE.value)
            else DataSource.SIMULATION.value
        )
        if norm_mode != self.active_mode or (norm_mode == DataSource.SIMULATION.value and not self.gri_tracker.is_calibrated):
            self.active_mode = norm_mode
            if norm_mode == DataSource.SIMULATION.value:
                self.incident_state.model_source = "SIMULATION ENGINE"
                self.gri_tracker.reset()
                self.gri_tracker.set_configured_baseline(GRI_BASELINE_ADC)
            else:
                self.incident_state.model_source = "STM32 EMBEDDED MLP"
                self.gri_tracker.reset()
                self.gri_tracker.set_configured_baseline(None)

    def process_message(self, msg: ProtocolMessage) -> None:
        """
        Ingests and processes a parsed protocol message.
        Updates appropriate sensor values, MLP predictions, risk state, and history.
        """
        if msg is None:
            return

        self.total_messages_processed += 1
        now = msg.timestamp or datetime.now()
        self.last_any_message_timestamp = now
        if msg.source == DataSource.HARDWARE.value:
            self.last_hardware_timestamp = now

        # Log raw line
        self.raw_message_log.append({
            "timestamp": now,
            "type": msg.message_type.value,
            "raw": getattr(msg, "raw_line", ""),
            "source": msg.source,
            "valid": getattr(msg, "is_valid", True),
        })

        if isinstance(msg, MalformedMessage) or type(msg).__name__ == "MalformedMessage":
            self.malformed_messages_count += 1
            return

        if isinstance(msg, SampleMessage) or type(msg).__name__ == "SampleMessage":
            self._handle_sample_message(msg)

        elif isinstance(msg, MlpMessage) or type(msg).__name__ == "MlpMessage":
            self._handle_mlp_message(msg)

        elif isinstance(msg, RiskMessage) or type(msg).__name__ == "RiskMessage":
            self._handle_risk_message(msg)

        elif isinstance(msg, IncidentMessage) or type(msg).__name__ == "IncidentMessage":
            self._handle_incident_message(msg)

        elif isinstance(msg, DiagnosticMessage) or type(msg).__name__ == "DiagnosticMessage":
            # Banner / diagnostic logs stored in message log
            pass

    def _handle_sample_message(self, sample: SampleMessage) -> None:
        """Processes sensor sample updates."""
        # Segregate data sources: prevent stale simulation values from overwriting live hardware readings
        if sample.source and sample.source != self.active_mode:
            return

        now = sample.timestamp

        for s_def in self.sensor_registry.get_active_sensors():
            s_id = s_def.sensor_id
            val = self.sensor_registry.extract_value(sample, s_id)

            if s_id not in self.sensor_states:
                self.sensor_states[s_id] = LiveSensorState(sensor_id=s_id)
                self.sensor_history[s_id] = deque(maxlen=self.max_history_points)

            state = self.sensor_states[s_id]

            if val is not None:
                # Calculate trend for numeric values
                trend = "STEADY"
                if (
                    state.current_value is not None
                    and isinstance(val, (int, float))
                    and isinstance(state.current_value, (int, float))
                ):
                    delta = val - state.current_value
                    # For gas_mq5 ADC use noise margin of 8 counts; for temp/hum use 0.05
                    threshold = 8.0 if s_id == "gas_mq5" else 0.05
                    if delta > threshold:
                        trend = "RISING"
                    elif delta < -threshold:
                        trend = "FALLING"

                state.previous_value = state.current_value
                state.current_value = val
                state.last_updated = now
                state.trend = trend
                state.status = FreshnessStatus.FRESH
                state.source = sample.source

                # Append to chart history
                self.sensor_history[s_id].append({
                    "timestamp": now,
                    "value": val,
                    "source": sample.source,
                })

        # Update Gas Response Index (GRI) baseline & history
        if sample.mq5_adc is not None:
            self.gri_tracker.update(sample.mq5_adc)
            gri_val, _ = self.gri_tracker.compute(sample.mq5_adc)
            if gri_val is not None:
                self.gri_history.append({
                    "timestamp": now,
                    "value": gri_val,
                    "source": sample.source,
                })

    def _handle_mlp_message(self, mlp: MlpMessage) -> None:
        """Processes TinyML MLP classification packet."""
        self.latest_mlp = mlp
        now = mlp.timestamp or datetime.now()

        self.incident_state.incident_class = mlp.mlp_class
        self.incident_state.mlp_confidence = mlp.confidence
        self.incident_state.prediction_timestamp = now
        self.incident_state.source = mlp.source
        self.incident_state.model_source = (
            "STM32 EMBEDDED MLP" if mlp.source == DataSource.HARDWARE.value else "SIMULATION ENGINE"
        )

    def _handle_risk_message(self, risk: RiskMessage) -> None:
        """Processes explainable risk assessment packet."""
        self.latest_risk = risk
        now = risk.timestamp or datetime.now()

        self.incident_state.risk_score = risk.risk_score
        self.incident_state.persist_risk = risk.persist_risk
        self.incident_state.severity = risk.severity
        self.incident_state.why = risk.why
        self.incident_state.mq5_change = risk.mq5_change
        self.incident_state.mq5_abrupt = risk.mq5_abrupt
        self.incident_state.mq5_variability = risk.mq5_variability
        self.incident_state.recovery = risk.recovery
        self.incident_state.prediction_timestamp = now
        self.incident_state.source = risk.source
        if risk.scenario_name:
            self.incident_state.scenario_name = risk.scenario_name

        # Record into risk chart history with persist_risk
        self.risk_history.append({
            "timestamp": now,
            "risk_score": risk.risk_score,
            "persist_risk": risk.persist_risk,
            "severity": risk.severity,
            "incident_class": self.incident_state.incident_class,
            "source": risk.source,
        })

        # Update explainable risk contributions
        if getattr(risk, "risk_contributions", None):
            self.incident_state.risk_contributions = risk.risk_contributions.copy()
        else:
            self.incident_state.risk_contributions = self._compute_risk_contributions(risk)

        # Snapshot current sensor readings for incident event record (mq5_adc instead of pir)
        gri_val = self.gri_history[-1]["value"] if self.gri_history else None
        snapshot = {
            "temperature": self.sensor_states.get("temp_ambient", LiveSensorState(sensor_id="temp_ambient")).current_value,
            "humidity": self.sensor_states.get("humidity_rel", LiveSensorState(sensor_id="humidity_rel")).current_value,
            "mq5_adc": self.sensor_states.get("gas_mq5", LiveSensorState(sensor_id="gas_mq5")).current_value,
            "gri": gri_val,
            "baseline": self.gri_tracker.baseline if self.gri_tracker.is_calibrated else None,
        }

        # Check for event transition
        synth_incident = IncidentMessage(
            timestamp=now,
            incident_class=self.incident_state.incident_class,
            risk_score=risk.risk_score,
            persist_risk=risk.persist_risk,
            severity=risk.severity,
            why=risk.why,
            risk_contributions=self.incident_state.risk_contributions.copy(),
            source=risk.source,
            scenario_name=risk.scenario_name or self.incident_state.scenario_name,
        )
        self.event_manager.record_if_transition(
            incident=synth_incident,
            sensor_snapshot=snapshot,
        )

    def _compute_risk_contributions(self, risk: RiskMessage) -> Dict[str, float]:
        """Dynamically computes explainable risk contributions from sensor states and metrics."""
        temp_val = self.sensor_states.get("temp_ambient", LiveSensorState(sensor_id="temp_ambient")).current_value or 25.0
        hum_val = self.sensor_states.get("humidity_rel", LiveSensorState(sensor_id="humidity_rel")).current_value or 50.0
        mq5_val = self.sensor_states.get("gas_mq5", LiveSensorState(sensor_id="gas_mq5")).current_value or 200.0

        gas_contrib = max(3.0, min(100.0, (float(mq5_val) - 190.0) / (700.0 - 190.0) * 100.0))
        thermal_contrib = 5.0 if float(temp_val) <= 25.5 else min(100.0, 5.0 + (float(temp_val) - 25.5) / (37.0 - 25.5) * 95.0)
        hum_contrib = 4.0 if float(hum_val) <= 55.0 else min(100.0, 4.0 + (float(hum_val) - 55.0) / (85.0 - 55.0) * 96.0)

        mq5_change = risk.mq5_change or 0.0
        mq5_abrupt = risk.mq5_abrupt or 0
        mq5_var = risk.mq5_variability or 0.0

        if mq5_abrupt:
            dyn_contrib = min(100.0, 65.0 + abs(mq5_change) * 35.0)
        elif mq5_var > 0.15:
            dyn_contrib = min(85.0, mq5_var * 200.0)
        else:
            dyn_contrib = min(100.0, max(3.0, abs(mq5_change) * 75.0))

        conf = self.incident_state.mlp_confidence or 85.0
        ml_contrib = min(100.0, max(4.0, (risk.risk_score * 0.85) + (conf * 0.15)))

        return {
            "GAS_RESPONSE": round(gas_contrib, 1),
            "GAS_DYNAMICS": round(dyn_contrib, 1),
            "THERMAL": round(thermal_contrib, 1),
            "HUMIDITY": round(hum_contrib, 1),
            "ML_MODEL": round(ml_contrib, 1),
        }

    def _handle_incident_message(self, inc: IncidentMessage) -> None:
        """Processes risk evaluation and incident classification (backward compat)."""
        now = inc.timestamp

        self.incident_state.incident_class = inc.incident_class
        self.incident_state.risk_score = inc.risk_score
        self.incident_state.severity = inc.severity
        self.incident_state.why = inc.why
        self.incident_state.risk_contributions = inc.risk_contributions.copy()
        self.incident_state.prediction_timestamp = now
        self.incident_state.source = inc.source
        self.incident_state.scenario_name = inc.scenario_name
        self.incident_state.model_source = "STM32 EMBEDDED MLP" if inc.source == "HARDWARE" else "SIMULATION ENGINE"

        # Record into risk chart history
        self.risk_history.append({
            "timestamp": now,
            "risk_score": inc.risk_score,
            "persist_risk": getattr(inc, "persist_risk", inc.risk_score),
            "severity": inc.severity,
            "incident_class": inc.incident_class,
            "source": inc.source,
        })

        # Snapshot current sensor readings for incident event record
        gri_val = self.gri_history[-1]["value"] if self.gri_history else None
        snapshot = {
            "temperature": self.sensor_states.get("temp_ambient", LiveSensorState(sensor_id="temp_ambient")).current_value,
            "humidity": self.sensor_states.get("humidity_rel", LiveSensorState(sensor_id="humidity_rel")).current_value,
            "mq5_adc": self.sensor_states.get("gas_mq5", LiveSensorState(sensor_id="gas_mq5")).current_value,
            "gri": gri_val,
            "baseline": self.gri_tracker.baseline if self.gri_tracker.is_calibrated else None,
        }

        # Check for event transition
        self.event_manager.record_if_transition(
            incident=inc,
            sensor_snapshot=snapshot,
        )

    def refresh_freshness(self) -> None:
        """
        Evaluates current time against timestamps to update freshness badges.
        Marks stalled sensors or dead serial connections as STALE.
        """
        now = datetime.now()
        for s_def in self.sensor_registry.get_all_sensors():
            s_id = s_def.sensor_id
            if s_id in self.sensor_states:
                state = self.sensor_states[s_id]
                status = self.freshness_tracker.evaluate_sensor_status(
                    timestamp=state.last_updated,
                    is_installed=s_def.is_installed,
                    timeout_seconds=s_def.expected_update_interval * 3.5,
                    now=now,
                )
                state.status = status

    def is_hardware_data_stale(self, timeout_seconds: float = 6.0) -> bool:
        """Returns True if in HARDWARE mode and no valid message arrived recently."""
        if self.active_mode != DataSource.HARDWARE.value:
            return False
        if self.last_hardware_timestamp is None:
            return True
        age = self.freshness_tracker.get_age_seconds(self.last_hardware_timestamp)
        return age is not None and age > timeout_seconds

    def get_time_window_data(
        self,
        sensor_id: str,
        window_minutes: Optional[int] = 5,
    ) -> List[Dict[str, Any]]:
        """
        Filters sensor history buffer to the selected time window (1, 5, 15, 60 minutes, or None for all).
        """
        history = list(self.sensor_history.get(sensor_id, []))
        if not history or window_minutes is None:
            return history

        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        return [pt for pt in history if pt["timestamp"] >= cutoff]

    def get_time_window_risk_data(
        self,
        window_minutes: Optional[int] = 5,
    ) -> List[Dict[str, Any]]:
        """
        Filters risk history buffer to the selected time window.
        """
        history = list(self.risk_history)
        if not history or window_minutes is None:
            return history

        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        return [pt for pt in history if pt["timestamp"] >= cutoff]

    def get_time_window_gri_data(
        self,
        window_minutes: Optional[int] = 5,
    ) -> List[Dict[str, Any]]:
        """
        Filters Gas Response Index (GRI) history buffer to the selected time window.
        """
        history = list(self.gri_history)
        if not history or window_minutes is None:
            return history

        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        return [pt for pt in history if pt["timestamp"] >= cutoff]

    def clear_all_history(self) -> None:
        """Clears chart histories and event log."""
        for q in self.sensor_history.values():
            q.clear()
        self.risk_history.clear()
        self.gri_history.clear()
        self.gri_tracker.reset()
        self.raw_message_log.clear()
        self.event_manager.clear_events()
