"""
Gas Response Index (GRI) calculation for Smart Lab Guardian.
Converts raw MQ-5 ADC readings to a 0–100 human-readable relative response index.

Never labels output as ppm, %LEL, or an uncalibrated absolute gas concentration.
Provides documented relative mapping relative to a clean-air baseline.
"""

from typing import Optional, Tuple, Union
from collections import deque

# ── Documented Mapping & Calibration Constants ─────────────────────────────────
# Clean laboratory air reference baseline (used for simulation and default reference)
GRI_BASELINE_ADC: float = 200.0

# Nominal strong gas response ADC count
GRI_MAX_RESPONSE_ADC: float = 800.0

# Default full-scale response span above baseline (ADC counts)
# An increase of +600 ADC counts above baseline represents 100% relative gas response.
GRI_DEFAULT_SPAN: float = 600.0

# Minimum clean-air samples needed before dynamic baseline is considered calibrated
GRI_BASELINE_MIN_SAMPLES: int = 5

# Noise deadband around baseline (counts) to filter ambient fluctuations
GRI_NOISE_DEADBAND: float = 8.0

# 12-bit ADC full scale range [0, 4095]
GRI_MAX_ADC_VALUE: float = 4095.0

# Response level thresholds (GRI 0–100 scale)
GRI_LEVEL_LOW_MAX: float      = 20.0   # 0.0 – 20.0  → Low (clean ambient laboratory air)
GRI_LEVEL_ELEVATED_MAX: float = 50.0   # 20.0 – 50.0 → Elevated (early gas detection / notable rise)
                                       # 50.0 – 100.0 → High (strong gas response / hazardous excursion)


def compute_gri(
    mq5_adc: Optional[Union[int, float]],
    baseline_adc: Optional[float] = None,
    max_response_adc: Optional[float] = None,
    response_span: float = GRI_DEFAULT_SPAN,
    noise_deadband: float = GRI_NOISE_DEADBAND,
) -> Optional[float]:
    """
    Compute Gas Response Index [0, 100] from raw ADC reading relative to baseline.

    Documented Mapping:
    1. Input Validation:
       - mq5_adc must be a number in [0, 4095].
       - baseline_adc must be a number in [0, 4095]. If None, returns None (uncalibrated).
    2. Span Calculation:
       - If max_response_adc > baseline_adc:
           Span = max_response_adc - baseline_adc
         Else:
           Span = response_span (default 600.0 counts).
       - Span is clamped to remaining headroom: min(Span, 4095.0 - baseline_adc).
    3. Noise Filtering:
       - Delta = mq5_adc - baseline_adc.
       - If Delta <= noise_deadband:
           GRI = 0.0 (ambient noise rejection).
    4. Relative Scaling:
       - Effective Delta = Delta - noise_deadband
       - Effective Span  = max(1.0, Span - noise_deadband)
       - GRI = (Effective Delta / Effective Span) * 100.0
       - Clamped to [0.0, 100.0].

    Args:
        mq5_adc:          Raw ADC counts from MQ-5 (0–4095 for 12-bit).
        baseline_adc:     Established clean-air baseline ADC value.
                          If None, returns None to indicate calibration is required.
        max_response_adc: Target ADC representing strong response.
        response_span:    Default span above baseline if max_response_adc is omitted or <= baseline.
        noise_deadband:   ADC counts near baseline treated as clean-air noise (default 8.0).

    Returns:
        GRI value in [0.0, 100.0], or None if input or baseline is invalid.
    """
    if mq5_adc is None or not isinstance(mq5_adc, (int, float)):
        return None
    if mq5_adc < 0 or mq5_adc > GRI_MAX_ADC_VALUE:
        return None

    if baseline_adc is None or not isinstance(baseline_adc, (int, float)):
        return None
    if baseline_adc < 0 or baseline_adc > GRI_MAX_ADC_VALUE:
        return None

    base = float(baseline_adc)
    reading = float(mq5_adc)

    # Determine dynamic span safely, guarding against max_response_adc <= baseline
    if max_response_adc is not None and isinstance(max_response_adc, (int, float)) and max_response_adc > base:
        span = float(max_response_adc) - base
    else:
        span = float(response_span)

    if span <= 0:
        span = GRI_DEFAULT_SPAN

    # Clamp span to available ADC headroom above baseline if baseline is near ceiling
    headroom = max(1.0, GRI_MAX_ADC_VALUE - base)
    span = min(span, headroom)

    # Calculate delta above baseline
    delta = reading - base

    # Rejection of sub-baseline drift and clean-air noise
    if delta <= noise_deadband:
        return 0.0

    # Effective response calculation
    eff_delta = delta - noise_deadband
    eff_span = max(1.0, span - noise_deadband)

    raw_gri = (eff_delta / eff_span) * 100.0
    return max(0.0, min(100.0, round(raw_gri, 1)))


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
    Maintains a rolling clean-air baseline and computes GRI for incoming samples.
    Handles sensor warm-up, noisy readings, invalid values, and baseline updates.
    """

    def __init__(
        self,
        baseline_window: int = 30,
        min_samples_before_stable: int = GRI_BASELINE_MIN_SAMPLES,
        configured_baseline: Optional[float] = None,
        max_response_adc: Optional[float] = None,
        response_span: float = GRI_DEFAULT_SPAN,
        noise_deadband: float = GRI_NOISE_DEADBAND,
    ):
        self._window: deque[float] = deque(maxlen=baseline_window)
        self._min_stable: int = min_samples_before_stable
        self._configured_baseline: Optional[float] = (
            float(configured_baseline) if configured_baseline is not None else None
        )
        self._max_response: Optional[float] = (
            float(max_response_adc) if max_response_adc is not None else None
        )
        self._response_span: float = float(response_span)
        self._noise_deadband: float = float(noise_deadband)

    def set_configured_baseline(self, baseline: Optional[float]) -> None:
        """Sets or clears a manually configured baseline."""
        self._configured_baseline = float(baseline) if baseline is not None else None

    def set_response_span(self, span: float) -> None:
        """Sets the dynamic response span."""
        if span > 0:
            self._response_span = float(span)

    def set_max_response_adc(self, max_adc: Optional[float]) -> None:
        """Sets the target maximum response ADC count."""
        self._max_response = float(max_adc) if max_adc is not None else None

    def update(self, mq5_adc: Optional[Union[int, float]]) -> None:
        """
        Add a new reading to the rolling baseline window.
        Rejects invalid values, out-of-range readings, and elevated gas excursions.
        """
        if mq5_adc is None or not isinstance(mq5_adc, (int, float)):
            return
        if not (0 <= mq5_adc <= GRI_MAX_ADC_VALUE):
            return

        val = float(mq5_adc)

        # Warm-up / uncalibrated phase: collect initial clean-air readings
        if not self.is_calibrated:
            self._window.append(val)
            return

        # Once calibrated: protect clean-air baseline from gas leak contamination.
        # Gas spikes must NOT be allowed to inflate the clean-air baseline.
        current_base = self.baseline
        if current_base is not None:
            # Only accept readings that are in the Low response region (clean ambient air)
            # or lower (downward clean-air drift / temperature stabilization)
            max_allowed_for_baseline = current_base + (self._response_span * (GRI_LEVEL_LOW_MAX / 100.0))
            if val <= max_allowed_for_baseline:
                self._window.append(val)
        else:
            self._window.append(val)

    @property
    def is_calibrated(self) -> bool:
        """True if configured baseline is set or sufficient warm-up readings have been collected."""
        if self._configured_baseline is not None and 0 <= self._configured_baseline <= GRI_MAX_ADC_VALUE:
            return True
        return len(self._window) >= self._min_stable

    @property
    def baseline(self) -> Optional[float]:
        """Current clean-air baseline estimate (or None if uncalibrated)."""
        if self._configured_baseline is not None and 0 <= self._configured_baseline <= GRI_MAX_ADC_VALUE:
            return self._configured_baseline
        if len(self._window) < self._min_stable:
            return None
        # Robust clean-air estimate: 10th percentile of clean readings in window
        sorted_vals = sorted(self._window)
        idx = max(0, int(len(sorted_vals) * 0.10))
        return sorted_vals[idx]

    @property
    def samples_collected(self) -> int:
        """Number of valid warm-up readings collected so far."""
        return len(self._window)

    @property
    def min_stable_samples(self) -> int:
        """Minimum readings required before baseline is established."""
        return self._min_stable

    def compute(self, mq5_adc: Optional[Union[int, float]]) -> Tuple[Optional[float], bool]:
        """
        Returns (gri_value, is_calibrated).
        If not calibrated, returns (None, False).
        If calibrated, returns (gri_value, True).
        """
        if not self.is_calibrated:
            return None, False

        base = self.baseline
        if base is None:
            return None, False

        gri = compute_gri(
            mq5_adc,
            baseline_adc=base,
            max_response_adc=self._max_response,
            response_span=self._response_span,
            noise_deadband=self._noise_deadband,
        )
        return gri, True

    def reset(self) -> None:
        """Clears rolling baseline window and resets calibration."""
        self._window.clear()
