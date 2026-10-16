"""
Gas Response Index (GRI) calculation for Smart Lab Guardian.
Converts raw MQ-5 ADC readings to a 0–100 human-readable index.
Never labels output as ppm, %LEL, or any calibrated gas concentration.
"""

from typing import Optional, Tuple
from collections import deque

# ── Constants ──────────────────────────────────────────────────────────────────
GRI_BASELINE_ADC = 200          # Expected ADC counts in clean laboratory air
GRI_MAX_RESPONSE_ADC = 800      # ADC counts representing strong gas response
GRI_BASELINE_MIN_SAMPLES = 5    # Samples needed before baseline is considered stable

# Response level thresholds (GRI 0–100)
GRI_LEVEL_LOW_MAX      = 20.0   # 0–20  → Low
GRI_LEVEL_ELEVATED_MAX = 50.0   # 20–50 → Elevated
# 50–100 → High


def compute_gri(
    mq5_adc: Optional[int],
    baseline_adc: Optional[float] = None,
    max_response_adc: float = GRI_MAX_RESPONSE_ADC,
) -> Optional[float]:
    """
    Compute Gas Response Index [0, 100] from raw ADC reading.

    Args:
        mq5_adc:        Raw ADC counts from MQ-5 (0–4095 for 12-bit).
        baseline_adc:   Established baseline (clean-air ADC value).
                        If None, uses the configured default.
        max_response_adc: ADC value representing a strong/saturated response.

    Returns:
        GRI value in [0, 100], or None if input is invalid.
    """
    if mq5_adc is None or not isinstance(mq5_adc, (int, float)):
        return None

    base = baseline_adc if baseline_adc is not None else GRI_BASELINE_ADC
    span = max_response_adc - base
    if span <= 0:
        span = 1.0  # guard divide-by-zero

    raw_response = float(mq5_adc) - base
    gri = (raw_response / span) * 100.0
    return max(0.0, min(100.0, gri))


def gri_label(gri: Optional[float]) -> str:
    """Returns a human-readable response label for the GRI value."""
    if gri is None:
        return "No Data"
    if gri <= GRI_LEVEL_LOW_MAX:
        return "Low"
    if gri <= GRI_LEVEL_ELEVATED_MAX:
        return "Elevated"
    return "High"


def gri_color(gri: Optional[float]) -> str:
    """Returns a severity colour for the GRI value."""
    if gri is None:
        return "#64748b"
    if gri <= GRI_LEVEL_LOW_MAX:
        return "#10b981"   # green
    if gri <= GRI_LEVEL_ELEVATED_MAX:
        return "#f59e0b"   # amber
    return "#ef4444"       # red


class GriTracker:
    """
    Maintains a rolling baseline and computes GRI for incoming samples.
    Uses a warm-up period before the baseline is considered reliable.
    """

    def __init__(
        self,
        baseline_window: int = 30,
        min_samples_before_stable: int = GRI_BASELINE_MIN_SAMPLES,
        configured_baseline: float = GRI_BASELINE_ADC,
        max_response_adc: float = GRI_MAX_RESPONSE_ADC,
    ):
        self._window: deque[float] = deque(maxlen=baseline_window)
        self._min_stable = min_samples_before_stable
        self._configured_baseline = configured_baseline
        self._max_response = max_response_adc

    def update(self, mq5_adc: Optional[int]) -> None:
        """Add a new reading to the rolling baseline window."""
        if mq5_adc is not None and isinstance(mq5_adc, (int, float)):
            self._window.append(float(mq5_adc))

    @property
    def is_calibrated(self) -> bool:
        """True once enough samples have been collected for a stable baseline."""
        return len(self._window) >= self._min_stable

    @property
    def baseline(self) -> float:
        """Current rolling-minimum baseline (clean-air estimate)."""
        if not self._window:
            return self._configured_baseline
        # Use the 10th percentile of recent readings as clean-air estimate
        sorted_vals = sorted(self._window)
        idx = max(0, int(len(sorted_vals) * 0.10))
        return sorted_vals[idx]

    def compute(self, mq5_adc: Optional[int]) -> Tuple[Optional[float], bool]:
        """
        Returns (gri_value, is_calibrated).
        gri_value is None if input is invalid.
        """
        if not self.is_calibrated:
            return None, False
        gri = compute_gri(mq5_adc, self.baseline, self._max_response)
        return gri, True

    def reset(self) -> None:
        self._window.clear()
