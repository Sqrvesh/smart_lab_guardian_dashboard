"""
Extensible sensor registry for Smart Lab Guardian.
Decouples sensor definitions, units, thresholds, and mappings from UI rendering.
Supports physical sensors (HTS221 Temp/Hum, MQ-5 Gas ADC and mV) or synthetic test streams.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable

try:
    from smart_lab_guardian_dashboard.communication.message_models import SampleMessage
    from smart_lab_guardian_dashboard.core.configuration import ConfigManager
except ImportError:
    from communication.message_models import SampleMessage
    from core.configuration import ConfigManager


@dataclass
class SensorDefinition:
    """
    Metadata and operational parameters for an environmental or activity sensor.
    """
    sensor_id: str
    display_name: str
    sensor_type: str  # 'temperature', 'humidity', 'gas', 'pressure', etc.
    unit: str         # '°C', '% RH', 'ADC', 'mV', etc.
    data_type: str    # 'float', 'int', 'analog', 'digital'
    description: str = ""
    enabled: bool = True
    expected_update_interval: float = 1.0  # seconds
    warning_thresholds: Optional[Dict[str, float]] = None   # e.g., {'high': 400.0}
    critical_thresholds: Optional[Dict[str, float]] = None  # e.g., {'high': 700.0}
    chart_enabled: bool = True
    source_field: str = ""   # Maps to SampleMessage field: 'temperature', 'humidity', 'mq5_adc', 'mq5_mv', or extra_sensors key
    calibration_status: str = "CALIBRATED"  # 'CALIBRATED', 'UNCALIBRATED', 'NOT CONFIGURED', 'SIMULATED'
    is_installed: bool = True
    custom_extractor: Optional[Callable[[SampleMessage], Optional[Any]]] = None

    def format_value(self, value: Any) -> str:
        """Formats the raw sensor value into a human-readable display string."""
        if value is None:
            if not self.is_installed:
                return "NOT CONFIGURED"
            return "NO DATA"

        if isinstance(value, (int, float)):
            if self.unit in ("°C", "% RH"):
                return f"{value:.2f} {self.unit}"
            elif self.unit == "ADC":
                return f"{int(value)} ADC"
            elif self.unit == "mV":
                return f"{int(value)} mV"
            elif self.unit == "raw ADC":
                return f"{int(value)} ADC counts (Uncalibrated)"
            elif self.unit:
                return f"{value:.2f} {self.unit}"
            return f"{value:.2f}"

        return str(value)

    def evaluate_threshold(self, value: Optional[float]) -> str:
        """Returns 'NORMAL', 'WARNING', 'CRITICAL', or 'UNKNOWN'."""
        if value is None or not isinstance(value, (int, float)):
            return "UNKNOWN"

        if self.critical_thresholds:
            high = self.critical_thresholds.get("high")
            low = self.critical_thresholds.get("low")
            if high is not None and value >= high:
                return "CRITICAL"
            if low is not None and value <= low:
                return "CRITICAL"

        if self.warning_thresholds:
            high = self.warning_thresholds.get("high")
            low = self.warning_thresholds.get("low")
            if high is not None and value >= high:
                return "WARNING"
            if low is not None and value <= low:
                return "WARNING"

        return "NORMAL"


class SensorRegistry:
    """
    Central registry managing all available sensor definitions.
    """

    def __init__(self):
        self._sensors: Dict[str, SensorDefinition] = {}
        self.load_default_sensors()

    def register_sensor(self, sensor: SensorDefinition) -> None:
        """Registers or updates a sensor definition."""
        self._sensors[sensor.sensor_id] = sensor

    def unregister_sensor(self, sensor_id: str) -> bool:
        """Removes a sensor from the registry."""
        if sensor_id in self._sensors:
            del self._sensors[sensor_id]
            return True
        return False

    def get_sensor(self, sensor_id: str) -> Optional[SensorDefinition]:
        """Retrieves sensor definition by ID."""
        return self._sensors.get(sensor_id)

    def get_all_sensors(self) -> List[SensorDefinition]:
        """Returns all registered sensor definitions."""
        return list(self._sensors.values())

    def get_active_sensors(self) -> List[SensorDefinition]:
        """Returns all enabled sensors."""
        return [s for s in self._sensors.values() if s.enabled]

    def extract_value(self, sample: SampleMessage, sensor_id: str) -> Optional[Any]:
        """Extracts the appropriate reading for a sensor from a SampleMessage."""
        sensor = self.get_sensor(sensor_id)
        if not sensor:
            return None

        if sensor.custom_extractor:
            return sensor.custom_extractor(sample)

        sf = sensor.source_field.lower()
        if sf == "temperature":
            return sample.temperature
        elif sf == "humidity":
            return sample.humidity
        elif sf in ("mq5_adc", "gas_mq5", "gas_adc"):
            return sample.mq5_adc
        elif sf in ("mq5_mv", "gas_mq5_mv", "gas_mv"):
            return sample.mq5_mv
        elif sf in sample.extra_sensors:
            return sample.extra_sensors[sf]
        elif sensor.sensor_id in sample.extra_sensors:
            return sample.extra_sensors[sensor.sensor_id]

        # Check fallback generic sensor column names (e.g. extra_sensor_1)
        for k, v in sample.extra_sensors.items():
            if sf in k.lower():
                return v

        return None

    def load_default_sensors(self) -> None:
        """Loads default sensors from sensors.json config file or defaults."""
        config_path = ConfigManager.get_config_path("sensors.json")
        loaded = False
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data.get("sensors", []):
                        defn = SensorDefinition(
                            sensor_id=item["sensor_id"],
                            display_name=item["display_name"],
                            sensor_type=item.get("sensor_type", "generic"),
                            unit=item.get("unit", ""),
                            data_type=item.get("data_type", "float"),
                            description=item.get("description", ""),
                            enabled=item.get("enabled", True),
                            expected_update_interval=item.get("expected_update_interval", 1.0),
                            warning_thresholds=item.get("warning_thresholds"),
                            critical_thresholds=item.get("critical_thresholds"),
                            chart_enabled=item.get("chart_enabled", True),
                            source_field=item.get("source_field", ""),
                            calibration_status=item.get("calibration_status", "CALIBRATED"),
                            is_installed=item.get("is_installed", True),
                        )
                        self.register_sensor(defn)
                    loaded = True
            except Exception:
                loaded = False

        if not loaded:
            # Fallback code-defined defaults (PIR removed, MQ-5 ADC and mV enabled)
            self.register_sensor(SensorDefinition(
                sensor_id="temp_ambient",
                display_name="Ambient Temperature",
                sensor_type="temperature",
                unit="°C",
                data_type="float",
                description="HTS221 temperature sensor on B-L475E-IOT01A1",
                enabled=True,
                warning_thresholds={"high": 30.0, "low": 18.0},
                critical_thresholds={"high": 35.0, "low": 15.0},
                source_field="temperature",
                calibration_status="CALIBRATED",
                is_installed=True,
            ))
            self.register_sensor(SensorDefinition(
                sensor_id="humidity_rel",
                display_name="Relative Humidity",
                sensor_type="humidity",
                unit="% RH",
                data_type="float",
                description="HTS221 humidity sensor on B-L475E-IOT01A1",
                enabled=True,
                warning_thresholds={"high": 70.0, "low": 30.0},
                critical_thresholds={"high": 80.0, "low": 20.0},
                source_field="humidity",
                calibration_status="CALIBRATED",
                is_installed=True,
            ))
            self.register_sensor(SensorDefinition(
                sensor_id="gas_mq5",
                display_name="MQ-5 Combustible Gas",
                sensor_type="gas",
                unit="ADC",
                data_type="analog",
                description="MQ-5 combustible gas sensor raw 12-bit ADC reading",
                enabled=True,
                warning_thresholds={"high": 400.0},
                critical_thresholds={"high": 700.0},
                source_field="mq5_adc",
                calibration_status="CALIBRATED",
                is_installed=True,
                chart_enabled=True,
            ))
            self.register_sensor(SensorDefinition(
                sensor_id="gas_mq5_mv",
                display_name="MQ-5 Gas Voltage",
                sensor_type="gas",
                unit="mV",
                data_type="analog",
                description="MQ-5 combustible gas sensor analog output in millivolts",
                enabled=True,
                warning_thresholds={"high": 1500.0},
                critical_thresholds={"high": 2500.0},
                source_field="mq5_mv",
                calibration_status="CALIBRATED",
                is_installed=True,
                chart_enabled=False,
            ))
