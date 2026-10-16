"""
Configuration loader for Smart Lab Guardian.
Reads settings from JSON configs with graceful fallbacks.
"""

import json
import os
from typing import Dict, Any

DEFAULT_CONFIG = {
    "system": {
        "freshness_timeout_seconds": 4.0,
        "hardware_stale_warning_seconds": 6.0,
        "max_history_points": 3000,
        "max_event_history": 1000,
        "default_baudrate": 115200,
    },
    "risk_thresholds": {
        "low_max": 24.9,
        "medium_max": 49.9,
        "high_max": 79.9,
        "critical_min": 80.0,
    },
    "event_suppression": {
        "min_risk_delta_to_trigger": 8.0,
        "min_repeat_interval_seconds": 30.0,
    },
}


class ConfigManager:
    """Provides application configuration and path utilities."""

    @staticmethod
    def get_base_dir() -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    @classmethod
    def get_config_path(cls, filename: str) -> str:
        return os.path.join(cls.get_base_dir(), "config", filename)

    @classmethod
    def load_thresholds(cls) -> Dict[str, Any]:
        path = cls.get_config_path("thresholds.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_CONFIG
