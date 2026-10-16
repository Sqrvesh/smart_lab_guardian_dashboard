"""
Unit tests for ProtocolParser covering new firmware UART format:
- 5-field samples (sample_id, temp, humidity, mq5_adc, mq5_mv)
- MLP_EXPERIMENTAL inference packets
- RISK_EXPERIMENTAL explainable risk packets
- Diagnostic headers and startup banners
- Range validation (temperature, humidity, 12-bit MQ-5 ADC)
- Malformed inputs and edge cases
"""

from datetime import datetime
import pytest

from smart_lab_guardian_dashboard.communication.protocol_parser import ProtocolParser
from smart_lab_guardian_dashboard.communication.message_models import (
    SampleMessage,
    MlpMessage,
    RiskMessage,
    IncidentMessage,
    DiagnosticMessage,
    MalformedMessage,
    MessageType,
)


@pytest.fixture
def parser():
    return ProtocolParser(source_label="TEST_SUITE")


def test_parse_new_firmware_sample(parser):
    line = "1,27.31,58.42,412,1340"
    msg = parser.parse_line(line)
    assert isinstance(msg, SampleMessage)
    assert msg.sample_id == 1
    assert msg.temperature == 27.31
    assert msg.humidity == 58.42
    assert msg.mq5_adc == 412
    assert msg.mq5_mv == 1340
    assert msg.is_valid is True


def test_parse_mlp_experimental(parser):
    line = "MLP_EXPERIMENTAL,CLASS=NORMAL,CONF=87,SAMPLE_ID=1"
    msg = parser.parse_line(line)
    assert isinstance(msg, MlpMessage)
    assert msg.mlp_class == "NORMAL"
    assert msg.confidence == 87.0
    assert msg.sample_id == 1
    assert msg.is_valid is True


def test_parse_risk_experimental(parser):
    line = "RISK_EXPERIMENTAL,RISK=18,PERSIST_RISK=22,SEVERITY=LOW,MQ5_CHANGE=0.05,MQ5_ABRUPT=0,MQ5_VAR=0.12,RECOVERY=0,WHY=Stable baseline with normal gas response"
    msg = parser.parse_line(line)
    assert isinstance(msg, RiskMessage)
    assert msg.risk_score == 18.0
    assert msg.persist_risk == 22.0
    assert msg.severity == "LOW"
    assert msg.mq5_change == 0.05
    assert msg.mq5_abrupt == 0
    assert msg.mq5_variability == 0.12
    assert msg.recovery == 0
    assert "Stable baseline with normal gas response" in msg.why
    assert msg.is_valid is True


def test_parse_sample_header_as_diagnostic(parser):
    line = "SAMPLE_ID,TEMP_C,HUMIDITY_RH,MQ5_ADC,MQ5_MV"
    msg = parser.parse_line(line)
    assert isinstance(msg, DiagnosticMessage)
    assert "Protocol Header" in msg.message


def test_parse_prefixed_sample(parser):
    line = "SAMPLE,1,27.31,58.42"
    msg = parser.parse_line(line)
    assert isinstance(msg, SampleMessage)
    assert msg.is_valid is True


def test_parse_valid_incident(parser):
    line = "INCIDENT,OVERHEATING,RISK=85,SEVERITY=CRITICAL,ML_BASE=70,THERMAL=80,HUMIDITY=10,TREND=45,WHY=Rapid thermal rise: delta=2.4°C"
    msg = parser.parse_line(line)
    assert isinstance(msg, IncidentMessage)
    assert msg.incident_class == "OVERHEATING"
    assert msg.risk_score == 85.0
    assert msg.severity == "CRITICAL"
    assert msg.risk_contributions["THERMAL"] == 80.0
    assert "Rapid thermal rise" in msg.why


def test_parse_startup_banners_and_diagnostics(parser):
    lines = [
        "=== Smart Lab Guardian Firmware v2.0 ===",
        "Initializing HTS221... OK",
        "MQ5 INIT completed",
        "ML Model self-test: output NORMAL",
    ]
    for line in lines:
        msg = parser.parse_line(line)
        assert isinstance(msg, DiagnosticMessage)
        assert not isinstance(msg, (SampleMessage, IncidentMessage))


def test_parse_empty_and_whitespace(parser):
    assert parser.parse_line("") is None
    assert parser.parse_line("   \r\n  ") is None
    assert parser.parse_line(None) is None


def test_parse_out_of_range_temperature(parser):
    line = "1,350.0,50.0,400,1300"
    msg = parser.parse_line(line)
    assert isinstance(msg, MalformedMessage)
    assert "out of valid physical range" in msg.error_reason


def test_parse_out_of_range_humidity(parser):
    line = "SAMPLE,1,25.0,150.0"
    msg = parser.parse_line(line)
    assert isinstance(msg, MalformedMessage)
    assert "Humidity value" in msg.error_reason


def test_parse_out_of_range_mq5_adc(parser):
    line = "1,25.0,50.0,5000,1300"
    msg = parser.parse_line(line)
    assert isinstance(msg, MalformedMessage)
    assert "out of valid 12-bit range" in msg.error_reason


def test_parse_out_of_range_risk_score(parser):
    line = "RISK_EXPERIMENTAL,RISK=150,SEVERITY=LOW,WHY=Invalid risk"
    msg = parser.parse_line(line)
    assert isinstance(msg, MalformedMessage)
    assert "out of range" in msg.error_reason


def test_parse_missing_risk_score(parser):
    line = "RISK_EXPERIMENTAL,SEVERITY=LOW,WHY=No risk provided"
    msg = parser.parse_line(line)
    assert isinstance(msg, MalformedMessage)
    assert "Missing required RISK score" in msg.error_reason
