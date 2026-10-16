"""
Tests for SerialManager using mocked serial interface.
Validates port discovery, connection lifecycle, error handling,
queue draining, and thread cleanup without requiring hardware.
"""

from unittest.mock import MagicMock, patch
import pytest

from smart_lab_guardian_dashboard.communication.serial_manager import (
    SerialManager,
    SerialConnectionState,
)
from smart_lab_guardian_dashboard.communication.message_models import (
    SampleMessage,
    IncidentMessage,
)


def test_list_available_ports():
    with patch("serial.tools.list_ports.comports") as mock_comports:
        mock_port = MagicMock()
        mock_port.device = "COM7"
        mock_port.description = "STMicroelectronics STLink Virtual COM Port (COM7)"
        mock_port.hwid = "USB VID:PID=0483:374B"
        mock_comports.return_value = [mock_port]

        ports = SerialManager.list_available_ports()
        assert len(ports) == 1
        assert ports[0]["port"] == "COM7"
        assert "STLink" in ports[0]["description"]


def test_serial_connection_failure():
    manager = SerialManager()
    with patch("serial.Serial") as mock_serial:
        import serial
        mock_serial.side_effect = serial.SerialException("Port COM99 does not exist")

        success, err = manager.connect("COM99", 115200)
        assert success is False
        assert manager.state == SerialConnectionState.ERROR
        assert manager.connection_errors == 1
        assert "Port COM99 does not exist" in err


def test_serial_mock_read_and_drain():
    manager = SerialManager()
    mock_inst = MagicMock()
    mock_inst.is_open = True
    # Simulate lines emitted by firmware
    lines = [
        b"1,26.40,48.20,0\n",
        b"INCIDENT,NORMAL,RISK=10,SEVERITY=LOW,ML_BASE=5,THERMAL=5,HUMIDITY=0,TREND=0,MOTION=0,WHY=Environment normal\n",
        b"",
    ]
    mock_inst.readline.side_effect = lines

    with patch("serial.Serial", return_value=mock_inst):
        success, msg = manager.connect("COM7", 115200)
        assert success is True
        assert manager.is_connected() is True

        # Allow background reader thread a moment to process lines
        import time
        time.sleep(0.1)

        # Drain messages
        messages = manager.get_messages(10)
        assert len(messages) >= 1
        # Check that we received at least the sample message
        assert any(isinstance(m, SampleMessage) for m in messages)

        # Disconnect
        manager.disconnect()
        assert manager.state == SerialConnectionState.DISCONNECTED
        assert manager.is_connected() is False
