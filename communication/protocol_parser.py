"""
Robust protocol parser for Smart Lab Guardian STM32 firmware communication.
Handles SAMPLE (5-field or legacy), MLP_EXPERIMENTAL, RISK_EXPERIMENTAL,
legacy INCIDENT lines, diagnostic lines, startup banners, and malformed frames.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List

try:
    from smart_lab_guardian_dashboard.communication.message_models import (
        SampleMessage,
        MlpMessage,
        RiskMessage,
        IncidentMessage,
        DiagnosticMessage,
        MalformedMessage,
        ProtocolMessage,
        SeverityLevel,
    )
except ImportError:
    from communication.message_models import (
        SampleMessage,
        MlpMessage,
        RiskMessage,
        IncidentMessage,
        DiagnosticMessage,
        MalformedMessage,
        ProtocolMessage,
        SeverityLevel,
    )

# Known valid classes from firmware TinyML model
KNOWN_INCIDENT_CLASSES = {
    "NORMAL",
    "ELEVATED_GAS",
    "GAS_LEAK",
    "OVERHEATING",
    "ENVIRONMENTAL_ANOMALY",
    "FIRE_RISK",
}

# Startup / banner indicator keywords (PIR INIT removed)
BANNER_KEYWORDS = [
    "SMART LAB GUARDIAN",
    "INITIALIZING",
    "SELF-TEST",
    "FIRMWARE",
    "BOOT",
    "STARTUP",
    "HTS221 INIT",
    "MQ5 INIT",
    "ADC INIT",
    "BUILD:",
    "STM32",
    "ARM CORTEX",
]


class ProtocolParser:
    """
    Parses raw ASCII lines received from the STM32L475VG UART interface.
    Resilient against partial transfers, noise, unexpected field orders,
    and missing or extraneous fields.
    """

    def __init__(self, source_label: str = "HARDWARE"):
        self.source_label = source_label

    def parse_line(self, line: Optional[str], timestamp: Optional[datetime] = None) -> Optional[ProtocolMessage]:
        """
        Parses a single line of text from the serial stream.
        Returns a typed ProtocolMessage or None if empty.
        """
        if timestamp is None:
            timestamp = datetime.now()

        if line is None:
            return None

        clean_line = line.strip()
        if not clean_line:
            return None

        # Check for diagnostic banners / startup self-test lines
        upper_line = clean_line.upper()
        if any(keyword in upper_line for keyword in BANNER_KEYWORDS) and not clean_line.startswith(
            ("SAMPLE", "INCIDENT", "FEATURES", "MLP", "RISK")
        ):
            return DiagnosticMessage(
                timestamp=timestamp,
                message=clean_line,
                is_banner=True,
                raw_line=clean_line,
                source=self.source_label,
            )

        # Check message category
        if clean_line.startswith(("MLP_EXPERIMENTAL", "MLP,")):
            return self._parse_mlp_line(clean_line, timestamp)
        elif clean_line.startswith(("RISK_EXPERIMENTAL", "RISK,")):
            return self._parse_risk_line(clean_line, timestamp)
        elif clean_line.startswith("INCIDENT"):
            return self._parse_incident_line(clean_line, timestamp)
        elif clean_line.startswith("FEATURES"):
            return self._parse_feature_line(clean_line, timestamp)
        elif clean_line.startswith("SAMPLE"):
            return self._parse_sample_line(clean_line, timestamp)
        else:
            return self._parse_unprefixed_line(clean_line, timestamp)

    def _parse_mlp_line(self, line: str, timestamp: datetime) -> ProtocolMessage:
        """
        Parses TinyML MLP inference line from STM32.
        Format: MLP_EXPERIMENTAL,CLASS=NORMAL,CONF=87,SAMPLE_ID=1
        """
        if line.startswith("MLP_EXPERIMENTAL"):
            content = line[len("MLP_EXPERIMENTAL"):].lstrip(",").strip()
        elif line.startswith("MLP"):
            content = line[len("MLP"):].lstrip(",").strip()
        else:
            content = line.strip()

        if not content:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason="Empty MLP payload",
                source=self.source_label,
            )

        sample_id: Optional[int] = None
        mlp_class: str = "NORMAL"
        confidence: Optional[float] = None

        tokens = [t.strip() for t in content.split(",") if t.strip()]
        for token in tokens:
            if "=" not in token:
                mlp_class = token.upper()
                continue
            k, v = token.split("=", 1)
            k = k.strip().upper()
            v = v.strip()
            if k == "CLASS":
                mlp_class = v.upper()
            elif k in ("CONF", "CONFIDENCE"):
                try:
                    confidence = float(v)
                except ValueError:
                    return MalformedMessage(
                        timestamp=timestamp,
                        raw_line=line,
                        error_reason=f"Invalid confidence value '{v}' in MLP line",
                        source=self.source_label,
                    )
            elif k in ("SAMPLE_ID", "ID", "SAMPLE"):
                try:
                    sample_id = int(float(v))
                except ValueError:
                    pass

        if confidence is not None and not (0.0 <= confidence <= 100.0):
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason=f"Confidence value {confidence} out of range [0, 100]",
                source=self.source_label,
            )

        return MlpMessage(
            timestamp=timestamp,
            sample_id=sample_id,
            mlp_class=mlp_class,
            confidence=confidence,
            raw_line=line,
            source=self.source_label,
            is_valid=True,
        )

    def _parse_risk_line(self, line: str, timestamp: datetime) -> ProtocolMessage:
        """
        Parses explainable risk assessment line from STM32.
        Format: RISK_EXPERIMENTAL,RISK=18,PERSIST_RISK=22,SEVERITY=LOW,MQ5_CHANGE=0.05,MQ5_ABRUPT=0,MQ5_VAR=0.12,RECOVERY=0,WHY=Stable baseline with normal gas response
        """
        prefix = "RISK_EXPERIMENTAL" if line.startswith("RISK_EXPERIMENTAL") else "RISK"
        raw_content = line[len(prefix):].lstrip(",").strip()

        if not raw_content:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason="Empty RISK payload",
                source=self.source_label,
            )

        # Extract WHY= field first to avoid splitting explanatory text containing commas
        why_text = ""
        pre_why = raw_content
        why_idx = line.find("WHY=")
        if why_idx != -1:
            why_text = line[why_idx + 4:].strip()
            pre_why = line[len(prefix):why_idx].lstrip(",").rstrip(",").strip()

        tokens = [t.strip() for t in pre_why.split(",") if t.strip()]

        risk_score: Optional[float] = None
        persist_risk: Optional[float] = None
        severity: Optional[str] = None
        mq5_change: Optional[float] = None
        mq5_abrupt: Optional[int] = None
        mq5_variability: Optional[float] = None
        recovery: Optional[int] = None

        for token in tokens:
            if "=" not in token:
                continue
            k, v = token.split("=", 1)
            k = k.strip().upper()
            v = v.strip()

            if k == "RISK":
                try:
                    risk_score = float(v)
                except ValueError:
                    return MalformedMessage(
                        timestamp=timestamp,
                        raw_line=line,
                        error_reason=f"Invalid risk value '{v}'",
                        source=self.source_label,
                    )
            elif k in ("PERSIST_RISK", "PERSISTENT_RISK", "PERSIST"):
                try:
                    persist_risk = float(v)
                except ValueError:
                    pass
            elif k == "SEVERITY":
                sev_enum = SeverityLevel.from_string(v)
                severity = sev_enum.value
            elif k in ("MQ5_CHANGE", "GAS_CHANGE", "CHANGE"):
                try:
                    mq5_change = float(v)
                except ValueError:
                    pass
            elif k in ("MQ5_ABRUPT", "ABRUPT"):
                try:
                    mq5_abrupt = int(float(v))
                except ValueError:
                    pass
            elif k in ("MQ5_VAR", "MQ5_VARIABILITY", "VAR", "VARIABILITY"):
                try:
                    mq5_variability = float(v)
                except ValueError:
                    pass
            elif k in ("RECOVERY", "REC"):
                try:
                    recovery = int(float(v))
                except ValueError:
                    pass

        if risk_score is None:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason="Missing required RISK score in RISK line",
                source=self.source_label,
            )

        if not (0.0 <= risk_score <= 100.0):
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason=f"Risk score {risk_score} out of range [0, 100]",
                source=self.source_label,
            )

        if not severity or severity == "UNKNOWN":
            if risk_score >= 80:
                severity = "CRITICAL"
            elif risk_score >= 50:
                severity = "HIGH"
            elif risk_score >= 25:
                severity = "MEDIUM"
            else:
                severity = "LOW"

        if not why_text:
            why_text = f"Risk evaluated at {risk_score:.0f} ({severity})"

        return RiskMessage(
            timestamp=timestamp,
            risk_score=risk_score,
            persist_risk=persist_risk,
            severity=severity,
            mq5_change=mq5_change,
            mq5_abrupt=mq5_abrupt,
            mq5_variability=mq5_variability,
            recovery=recovery,
            why=why_text,
            raw_line=line,
            source=self.source_label,
            is_valid=True,
        )

    def _parse_sample_line(self, line: str, timestamp: datetime) -> ProtocolMessage:
        """
        Parses lines starting with 'SAMPLE,' or 'SAMPLE '.
        Format: SAMPLE,sample_id,TEMP_C,HUMIDITY_RH,MQ5_ADC,MQ5_MV
        or legacy: SAMPLE,TEMP_C,HUMIDITY_RH
        """
        upper = line.upper()
        if any(h in upper for h in ("TEMP_C", "HUMIDITY", "MQ5_ADC", "MQ5_MV", "SAMPLE_ID", "PIR")):
            return DiagnosticMessage(
                timestamp=timestamp,
                message=f"Protocol Header: {line}",
                is_banner=False,
                raw_line=line,
                source=self.source_label,
            )

        parts = [p.strip() for p in line.split(",") if p.strip()]
        if parts and parts[0].upper() == "SAMPLE":
            parts = parts[1:]

        return self._parse_numeric_sample_parts(parts, line, timestamp)

    def _parse_unprefixed_line(self, line: str, timestamp: datetime) -> ProtocolMessage:
        """
        Handles lines without explicit prefix:
        - Header lines like SAMPLE_ID,TEMP_C,HUMIDITY_RH,MQ5_ADC,MQ5_MV
        - Raw numeric sample rows like 1,27.31,58.42,412,1340
        - Diagnostic logs
        """
        upper = line.upper()
        if any(h in upper for h in ("TEMP_C", "HUMIDITY", "MQ5_ADC", "MQ5_MV", "SAMPLE_ID")):
            return DiagnosticMessage(
                timestamp=timestamp,
                message=f"Protocol Header: {line}",
                is_banner=False,
                raw_line=line,
                source=self.source_label,
            )

        parts = [p.strip() for p in line.split(",") if p.strip()]
        is_numeric = True
        for part in parts:
            try:
                float(part)
            except ValueError:
                is_numeric = False
                break

        if is_numeric and len(parts) >= 3:
            return self._parse_numeric_sample_parts(parts, line, timestamp)

        return DiagnosticMessage(
            timestamp=timestamp,
            message=line,
            is_banner=False,
            raw_line=line,
            source=self.source_label,
        )

    def _parse_numeric_sample_parts(
        self, parts: List[str], raw_line: str, timestamp: datetime
    ) -> ProtocolMessage:
        """
        Parses numeric tokens into a SampleMessage.
        Supports:
        - 3 fields: (temp, hum, extra) OR (id, temp, hum)
        - 4 fields: (id, temp, hum, extra) OR (temp, hum, adc, mv)
        - 5 fields: (id, temp, hum, adc, mv)
        - 6+ fields: (id, temp, hum, adc, mv, extra1, extra2...)
        Validates:
        - temp in [-40, 125]
        - humidity in [0, 100]
        - mq5_adc in [0, 4095] (12-bit ADC)
        """
        if len(parts) < 3:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=raw_line,
                error_reason=f"Insufficient sample fields (expected at least 3, got {len(parts)})",
                source=self.source_label,
            )

        try:
            sample_id: Optional[int] = None
            temp_val: float
            hum_val: float
            mq5_adc: Optional[int] = None
            mq5_mv: Optional[int] = None
            extra_sensors: Dict[str, Any] = {}

            if len(parts) == 3:
                p0 = float(parts[0])
                p1 = float(parts[1])
                p2 = float(parts[2])
                # Check if parts[0] is an integer ID and parts[1], parts[2] look like temp, hum
                if (
                    p0.is_integer()
                    and p0 >= 0
                    and "." not in parts[0]
                    and ("." in parts[1] or "." in parts[2] or p1 > 10)
                ):
                    sample_id = int(p0)
                    temp_val = p1
                    hum_val = p2
                else:
                    # (temp, hum, extra)
                    temp_val = p0
                    hum_val = p1
                    if 0 <= p2 <= 4095:
                        mq5_adc = int(round(p2))
                    extra_sensors["extra_sensor_1"] = p2

            elif len(parts) == 4:
                p0 = float(parts[0])
                p1 = float(parts[1])
                p2 = float(parts[2])
                p3 = float(parts[3])

                # Disambiguate between (temp, hum, adc, mv) vs (id, temp, hum, extra)
                # If parts[0] has decimal point or p2 > 100, p2 cannot be humidity
                if "." in parts[0] or p2 > 100.0:
                    sample_id = None
                    temp_val = p0
                    hum_val = p1
                    mq5_adc = int(round(p2))
                    mq5_mv = int(round(p3))
                else:
                    sample_id = int(round(p0))
                    temp_val = p1
                    hum_val = p2
                    if 0 <= p3 <= 4095:
                        mq5_adc = int(round(p3))
                    extra_sensors["extra_sensor_1"] = p3

            else:
                # 5 or more fields: id, temp, hum, adc, mv, [extras...]
                sample_id = int(round(float(parts[0])))
                temp_val = float(parts[1])
                hum_val = float(parts[2])
                mq5_adc = int(round(float(parts[3])))
                mq5_mv = int(round(float(parts[4])))

                for idx, extra_part in enumerate(parts[5:]):
                    try:
                        extra_sensors[f"extra_sensor_{idx+1}"] = float(extra_part)
                    except ValueError:
                        extra_sensors[f"extra_sensor_{idx+1}"] = extra_part

            # Validate physical sensor ranges
            if not (-40.0 <= temp_val <= 125.0):
                return MalformedMessage(
                    timestamp=timestamp,
                    raw_line=raw_line,
                    error_reason=f"Temperature value {temp_val}°C out of valid physical range [-40, 125]",
                    source=self.source_label,
                )

            if not (0.0 <= hum_val <= 100.0):
                return MalformedMessage(
                    timestamp=timestamp,
                    raw_line=raw_line,
                    error_reason=f"Humidity value {hum_val}% out of valid physical range [0, 100]",
                    source=self.source_label,
                )

            if mq5_adc is not None and not (0 <= mq5_adc <= 4095):
                return MalformedMessage(
                    timestamp=timestamp,
                    raw_line=raw_line,
                    error_reason=f"MQ5 ADC value {mq5_adc} out of valid 12-bit range [0, 4095]",
                    source=self.source_label,
                )

            return SampleMessage(
                timestamp=timestamp,
                sample_id=sample_id,
                temperature=temp_val,
                humidity=hum_val,
                mq5_adc=mq5_adc,
                mq5_mv=mq5_mv,
                extra_sensors=extra_sensors,
                raw_line=raw_line,
                source=self.source_label,
                is_valid=True,
            )

        except (ValueError, TypeError) as e:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=raw_line,
                error_reason=f"Numeric conversion error in sample: {str(e)}",
                source=self.source_label,
            )

    def _parse_feature_line(self, line: str, timestamp: datetime) -> ProtocolMessage:
        """
        Backward compatibility for legacy FEATURES lines.
        Returns a DiagnosticMessage so legacy firmware output is safely handled.
        """
        content = line[len("FEATURES"):].lstrip(",").strip()
        if not content:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason="Empty FEATURES payload",
                source=self.source_label,
            )
        return DiagnosticMessage(
            timestamp=timestamp,
            message=f"Legacy FEATURES: {line}",
            is_banner=False,
            raw_line=line,
            source=self.source_label,
        )

    def _parse_incident_line(self, line: str, timestamp: datetime) -> ProtocolMessage:
        """
        Parses legacy lines starting with 'INCIDENT,'.
        Format:
        INCIDENT,OVERHEATING,RISK=85,SEVERITY=CRITICAL,ML_BASE=70,THERMAL=80,HUMIDITY=10,TREND=45,WHY=Rapid thermal rise...
        """
        why_text = ""
        pre_why = line
        why_idx = line.find("WHY=")
        if why_idx != -1:
            why_text = line[why_idx + 4:].strip()
            pre_why = line[:why_idx].rstrip(",")

        tokens = [t.strip() for t in pre_why.split(",") if t.strip()]

        if not tokens:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason="Empty INCIDENT payload",
                source=self.source_label,
            )

        tokens = tokens[1:]  # strip 'INCIDENT'
        if not tokens:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason="Missing incident class and risk parameters",
                source=self.source_label,
            )

        incident_class = "NORMAL"
        kv_tokens = []
        if "=" not in tokens[0]:
            incident_class = tokens[0].upper()
            kv_tokens = tokens[1:]
        else:
            kv_tokens = tokens

        risk_score: Optional[float] = None
        severity: Optional[str] = None
        risk_contributions: Dict[str, float] = {}

        for token in kv_tokens:
            if "=" not in token:
                continue
            k, v = token.split("=", 1)
            k = k.strip().upper()
            v = v.strip()

            if k == "RISK":
                try:
                    risk_score = float(v)
                except ValueError:
                    return MalformedMessage(
                        timestamp=timestamp,
                        raw_line=line,
                        error_reason=f"Invalid risk value '{v}'",
                        source=self.source_label,
                    )
            elif k == "SEVERITY":
                sev_enum = SeverityLevel.from_string(v)
                severity = sev_enum.value
            elif k == "CLASS":
                incident_class = v.upper()
            else:
                try:
                    risk_contributions[k] = float(v)
                except ValueError:
                    pass

        if risk_score is None:
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason="Missing required RISK score in INCIDENT line",
                source=self.source_label,
            )

        if not (0.0 <= risk_score <= 100.0):
            return MalformedMessage(
                timestamp=timestamp,
                raw_line=line,
                error_reason=f"Risk score {risk_score} out of range [0, 100]",
                source=self.source_label,
            )

        if not severity or severity == "UNKNOWN":
            if risk_score >= 80:
                severity = "CRITICAL"
            elif risk_score >= 50:
                severity = "HIGH"
            elif risk_score >= 25:
                severity = "MEDIUM"
            else:
                severity = "LOW"

        if not why_text:
            why_text = f"Classified as {incident_class} with risk score {risk_score:.0f}"

        return IncidentMessage(
            timestamp=timestamp,
            incident_class=incident_class,
            risk_score=risk_score,
            severity=severity,
            risk_contributions=risk_contributions,
            why=why_text,
            raw_line=line,
            source=self.source_label,
            is_valid=True,
        )
