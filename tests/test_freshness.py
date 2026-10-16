"""
Unit tests for data freshness and stale state tracking.
"""

from datetime import datetime, timedelta
import pytest

from smart_lab_guardian_dashboard.core.freshness import (
    FreshnessTracker,
    FreshnessStatus,
)


def test_freshness_evaluation():
    tracker = FreshnessTracker(default_timeout_seconds=4.0)
    now = datetime.now()

    # Just now -> FRESH
    assert tracker.is_fresh(now, now=now) is True
    assert tracker.evaluate_sensor_status(now, now=now) == FreshnessStatus.FRESH

    # 2 seconds ago -> FRESH
    t_recent = now - timedelta(seconds=2.0)
    assert tracker.is_fresh(t_recent, now=now) is True
    assert tracker.evaluate_sensor_status(t_recent, now=now) == FreshnessStatus.FRESH

    # 10 seconds ago -> STALE
    t_old = now - timedelta(seconds=10.0)
    assert tracker.is_fresh(t_old, now=now) is False
    assert tracker.evaluate_sensor_status(t_old, now=now) == FreshnessStatus.STALE

    # None -> NO DATA
    assert tracker.is_fresh(None, now=now) is False
    assert tracker.evaluate_sensor_status(None, now=now) == FreshnessStatus.NO_DATA

    # Uninstalled sensor -> NOT CONFIGURED
    assert tracker.evaluate_sensor_status(now, is_installed=False, now=now) == FreshnessStatus.NOT_CONFIGURED


def test_freshness_badge_formatting():
    tracker = FreshnessTracker()
    badge_fresh, color_fresh = tracker.get_status_badge(FreshnessStatus.FRESH, age=1.2)
    assert "LIVE FRESH" in badge_fresh
    assert color_fresh == "#10b981"

    badge_stale, color_stale = tracker.get_status_badge(FreshnessStatus.STALE, age=12.5)
    assert "STALE DATA" in badge_stale
    assert color_stale == "#64748b"

    badge_unconf, _ = tracker.get_status_badge(FreshnessStatus.NOT_CONFIGURED)
    assert badge_unconf == "NOT CONFIGURED"
