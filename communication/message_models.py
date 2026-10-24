"""
Typed data models for Smart Lab Guardian communication protocol.
Represents messages exchanged between the STM32L475VG firmware and the dashboard.
Supports multi-sensor samples (temperature, humidity, MQ-5 combustible gas ADC/mV),
embedded MLP neural network predictions, explainable risk assessments, and diagnostics.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Any, Union


class MessageType(Enum):
    SAMPLE = "SAMPLE"
    MLP = "MLP"
    RISK = "RISK"
    INCIDENT = "INCIDENT"
    DIAGNOSTIC = "DIAGNOSTIC"
    MALFORMED = "MALFORMED"
    EMPTY = "EMPTY"


class DataSource(Enum):
    HARDWARE = "HARDWARE"
    SIMULATION = "SIMULATION"


class SeverityLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_string(cls, val: str) -> "SeverityLevel":
        v = (val or "").strip().upper()
        for member in cls:
            if member.value == v:
                return member
        return cls.UNKNOWN


@dataclass
class SampleMessage:
    """Represents a raw or calibrated multi-sensor sample reading (temperature, humidity, MQ-5 gas)."""
    timestamp: datetime
    sample_id: Optional[int] = None
    temperature: Optional[float] = None  # in °C
    humidity: Optional[float] = None     # in % RH
    mq5_adc: Optional[int] = None        # 12-bit raw ADC count (0-4095)
    mq5_mv: Optional[int] = None         # Sensor output in millivolts
    extra_sensors: Dict[str, Any] = field(default_factory=dict)
    raw_line: str = ""
    source: str = "HARDWARE"
    is_valid: bool = True
    error_reason: Optional[str] = None

    @property
    def message_type(self) -> MessageType:
        return MessageType.SAMPLE


@dataclass
class MlpMessage:
    """Represents an embedded TinyML MLP classification packet from STM32."""
    timestamp: datetime
    sample_id: Optional[int] = None
    mlp_class: str = "NORMAL"
    confidence: Optional[float] = None
    raw_line: str = ""
    source: str = "HARDWARE"
    is_valid: bool = True
    error_reason: Optional[str] = None

    @property
    def message_type(self) -> MessageType:
        return MessageType.MLP


@dataclass
class RiskMessage:
    """Represents an explainable risk assessment packet from STM32."""
    timestamp: datetime
    risk_score: float = 0.0
    persist_risk: Optional[float] = None
    severity: str = "LOW"
    mq5_change: Optional[float] = None
    mq5_abrupt: Optional[int] = None
    mq5_variability: Optional[float] = None
    recovery: Optional[int] = None
    why: str = ""
    raw_line: str = ""
    source: str = "HARDWARE"
    scenario_name: Optional[str] = None
    is_valid: bool = True
    error_reason: Optional[str] = None
    risk_contributions: Dict[str, float] = field(default_factory=dict)

    @property
    def message_type(self) -> MessageType:
        return MessageType.RISK


@dataclass
class IncidentMessage:
    """Represents an explainable risk prediction and incident classification (legacy STM32 format)."""
    timestamp: datetime
    incident_class: str = "NORMAL"
    risk_score: float = 0.0
    persist_risk: Optional[float] = None
    severity: str = "LOW"
    risk_contributions: Dict[str, float] = field(default_factory=dict)
    # Standard components: ML_BASE, THERMAL, HUMIDITY, TREND, GAS (extensible)
    why: str = ""
    raw_line: str = ""
    source: str = "HARDWARE"
    scenario_name: Optional[str] = None
    is_valid: bool = True
    error_reason: Optional[str] = None

    @property
    def message_type(self) -> MessageType:
        return MessageType.INCIDENT


@dataclass
class DiagnosticMessage:
    """Represents startup banners, calibration logs, protocol headers, and diagnostic output."""
    timestamp: datetime
    message: str
    is_banner: bool = False
    raw_line: str = ""
    source: str = "HARDWARE"
    is_valid: bool = True

    @property
    def message_type(self) -> MessageType:
        return MessageType.DIAGNOSTIC


@dataclass
class MalformedMessage:
    """Represents a message that failed parsing or physical validation rules."""
    timestamp: datetime
    raw_line: str
    error_reason: str
    source: str = "HARDWARE"

    @property
    def message_type(self) -> MessageType:
        return MessageType.MALFORMED


ProtocolMessage = Union[
    SampleMessage,
    MlpMessage,
    RiskMessage,
    IncidentMessage,
    DiagnosticMessage,
    MalformedMessage,
]
