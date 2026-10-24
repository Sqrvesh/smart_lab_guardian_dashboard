"""
Event and timeline manager for Smart Lab Guardian.
Maintains history of incident transitions, suppresses duplicate events,
and supports searching, filtering, and CSV export.
"""

import io
import uuid
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any
import pandas as pd

try:
    from smart_lab_guardian_dashboard.communication.message_models import IncidentMessage
    from smart_lab_guardian_dashboard.core.gas_response import compute_gri, gri_label
    from smart_lab_guardian_dashboard.core.evaluation_labels import format_evaluation_label
except ImportError:
    from communication.message_models import IncidentMessage
    from core.gas_response import compute_gri, gri_label
    from core.evaluation_labels import format_evaluation_label


@dataclass
class IncidentEvent:
    """Represents a recorded laboratory incident or meaningful state transition."""
    event_id: str
    timestamp: datetime
    incident_class: str
    risk_score: float
    severity: str
    sensor_snapshot: Dict[str, Any]
    explanation: str
    source: str = "HARDWARE"
    scenario_name: Optional[str] = None
    risk_contributions: Optional[Dict[str, float]] = None
    persist_risk: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts to a dictionary suitable for tabular display and export."""
        snap = self.sensor_snapshot or {}
        mq5_val = snap.get("mq5_adc")
        gri_val = snap.get("gri")

        gas_resp_label = "-"
        if gri_val is not None and isinstance(gri_val, (int, float)):
            gas_resp_label = gri_label(gri_val)
        elif mq5_val is not None and isinstance(mq5_val, (int, float)):
            base = snap.get("baseline")
            gri = compute_gri(mq5_val, baseline_adc=base)
            gas_resp_label = gri_label(gri)

        return {
            "Event ID": self.event_id,
            "Timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "Incident Class": format_evaluation_label(self.incident_class),
            "Risk Score": f"{self.risk_score:.1f}",
            "Persist Risk": f"{self.persist_risk:.1f}" if self.persist_risk is not None else "-",
            "Severity": self.severity,
            "Temperature (°C)": f"{snap.get('temperature', '-'):.2f}" if isinstance(snap.get('temperature'), (int, float)) else "-",
            "Humidity (% RH)": f"{snap.get('humidity', '-'):.2f}" if isinstance(snap.get('humidity'), (int, float)) else "-",
            "MQ5 ADC": f"{int(mq5_val)}" if isinstance(mq5_val, (int, float)) else "-",
            "Gas Response": gas_resp_label,
            "Explanation": self.explanation,
            "Source": self.source,
            "Scenario": self.scenario_name or "-",
        }


class EventManager:
    """
    Manages the incident event history with duplicate suppression,
    filtering, search, and tabular export.
    """

    def __init__(self, max_events: int = 1000):
        self.max_events = max_events
        self.events: deque[IncidentEvent] = deque(maxlen=max_events)
        self.last_recorded_event: Optional[IncidentEvent] = None
        self._id_counter = 1

    def record_if_transition(
        self,
        incident: IncidentMessage,
        sensor_snapshot: Dict[str, Any],
        min_risk_delta: float = 8.0,
        min_repeat_interval_seconds: float = 30.0,
    ) -> Optional[IncidentEvent]:
        """
        Records an incident event only if a meaningful transition occurred:
        1. First event ever, OR
        2. Incident class changed, OR
        3. Severity level changed, OR
        4. Risk score shifted by at least min_risk_delta, OR
        5. Active hazard persisted for longer than min_repeat_interval_seconds.
        Avoids spamming duplicate events on periodic refresh.
        """
        now = incident.timestamp or datetime.now()

        should_record = False
        if self.last_recorded_event is None:
            # First incoming incident
            should_record = True
        else:
            last = self.last_recorded_event
            class_changed = last.incident_class != incident.incident_class
            severity_changed = last.severity != incident.severity
            risk_delta = abs(last.risk_score - incident.risk_score) >= min_risk_delta
            time_elapsed = (now - last.timestamp).total_seconds() >= min_repeat_interval_seconds
            is_active_incident = incident.severity in ("MEDIUM", "HIGH", "CRITICAL")

            if class_changed or severity_changed or risk_delta:
                should_record = True
            elif is_active_incident and time_elapsed:
                should_record = True

        if should_record:
            event = IncidentEvent(
                event_id=f"EVT-{self._id_counter:04d}",
                timestamp=now,
                incident_class=incident.incident_class,
                risk_score=incident.risk_score,
                persist_risk=getattr(incident, "persist_risk", None),
                severity=incident.severity,
                sensor_snapshot=sensor_snapshot.copy(),
                explanation=incident.why,
                source=incident.source,
                scenario_name=incident.scenario_name,
                risk_contributions=incident.risk_contributions.copy() if incident.risk_contributions else {},
            )
            self._id_counter += 1
            self.events.append(event)
            self.last_recorded_event = event
            return event

        return None

    def get_filtered_events(
        self,
        severity: Optional[str] = None,
        incident_class: Optional[str] = None,
        source: Optional[str] = None,
        search_query: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[IncidentEvent]:
        """Returns filtered list of events matching specified criteria."""
        result = list(self.events)

        if severity and severity.upper() != "ALL":
            result = [e for e in result if e.severity.upper() == severity.upper()]

        if incident_class and incident_class.upper() != "ALL":
            target = incident_class.upper()
            result = [
                e for e in result
                if e.incident_class.upper() == target
                or format_evaluation_label(e.incident_class).upper() == target
            ]

        if source and source.upper() != "ALL":
            result = [e for e in result if e.source.upper() == source.upper()]

        if start_time:
            result = [e for e in result if e.timestamp >= start_time]

        if end_time:
            result = [e for e in result if e.timestamp <= end_time]

        if search_query:
            q = search_query.lower()
            result = [
                e for e in result
                if q in e.explanation.lower()
                or q in e.incident_class.lower()
                or q in format_evaluation_label(e.incident_class).lower()
                or q in e.severity.lower()
                or q in e.event_id.lower()
            ]

        # Reverse order so newest events are first
        result.reverse()

        if limit:
            result = result[:limit]

        return result

    def to_dataframe(self, events: Optional[List[IncidentEvent]] = None) -> pd.DataFrame:
        """Converts list of events (or all events) to a pandas DataFrame."""
        ev_list = events if events is not None else list(reversed(self.events))
        columns = [
            "Event ID", "Timestamp", "Incident Class", "Risk Score", "Persist Risk",
            "Severity", "Temperature (°C)", "Humidity (% RH)",
            "MQ5 ADC", "Gas Response", "Explanation", "Source", "Scenario"
        ]
        if not ev_list:
            return pd.DataFrame(columns=columns)
        data = [e.to_dict() for e in ev_list]
        return pd.DataFrame(data)

    def export_csv(self, events: Optional[List[IncidentEvent]] = None) -> str:
        """Exports events as CSV formatted string."""
        df = self.to_dataframe(events)
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return buf.getvalue()

    def clear_events(self) -> None:
        """Clears all recorded events."""
        self.events.clear()
        self.last_recorded_event = None
