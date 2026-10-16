"""
Data freshness tracking and timeout evaluation for sensors and system status.
Prevents old readings from masquerading as live telemetry.
"""

from datetime import datetime
from typing import Optional, Tuple


class FreshnessStatus:
    FRESH = "FRESH"
    STALE = "STALE"
    NO_DATA = "NO DATA"
    NOT_CONFIGURED = "NOT CONFIGURED"


class FreshnessTracker:
    """
    Evaluates reading age against configurable thresholds.
    """

    def __init__(self, default_timeout_seconds: float = 4.0):
        self.default_timeout_seconds = default_timeout_seconds

    @staticmethod
    def get_age_seconds(timestamp: Optional[datetime], now: Optional[datetime] = None) -> Optional[float]:
        """Calculates age in seconds from timestamp to now."""
        if timestamp is None:
            return None
        if now is None:
            now = datetime.now()
        delta = (now - timestamp).total_seconds()
        return max(0.0, delta)

    def is_fresh(
        self,
        timestamp: Optional[datetime],
        timeout_seconds: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        """Returns True if the timestamp is within the freshness timeout."""
        if timestamp is None:
            return False
        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        age = self.get_age_seconds(timestamp, now)
        return age is not None and age <= timeout

    def evaluate_sensor_status(
        self,
        timestamp: Optional[datetime],
        is_installed: bool = True,
        timeout_seconds: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> str:
        """
        Determines the status tag: FRESH, STALE, NO DATA, or NOT CONFIGURED.
        """
        if not is_installed:
            return FreshnessStatus.NOT_CONFIGURED

        if timestamp is None:
            return FreshnessStatus.NO_DATA

        timeout = timeout_seconds if timeout_seconds is not None else self.default_timeout_seconds
        age = self.get_age_seconds(timestamp, now)
        if age is not None and age <= timeout:
            return FreshnessStatus.FRESH
        return FreshnessStatus.STALE

    def get_status_badge(
        self,
        status: str,
        age: Optional[float] = None,
    ) -> Tuple[str, str]:
        """
        Returns (badge_text, color_code).
        """
        if status == FreshnessStatus.FRESH:
            age_str = f" ({age:.1f}s ago)" if age is not None else ""
            return f"LIVE FRESH{age_str}", "#10b981"
        elif status == FreshnessStatus.STALE:
            age_str = f" ({age:.1f}s ago)" if age is not None else ""
            return f"STALE DATA{age_str}", "#64748b"
        elif status == FreshnessStatus.NOT_CONFIGURED:
            return "NOT CONFIGURED", "#475569"
        else:
            return "NO DATA", "#64748b"
