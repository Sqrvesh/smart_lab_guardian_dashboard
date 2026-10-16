"""
Human-readable presentation labels for TinyML and risk evaluation classes.
Maintains clean mapping between internal/firmware class names and user-facing labels.
"""

from typing import Optional

# Required canonical mappings
EVALUATION_LABEL_MAP = {
    # ── Primary requested mappings ─────────────────────────────────────────────
    "NORMAL_SYNTHETIC": "Normal",
    "SUSTAINED_MQ5_RISE_SYNTHETIC": "Sustained Gas Sensor Rise",
    "ABRUPT_MQ5_DEVIATION_SYNTHETIC": "Abrupt Gas Sensor Change",
    "COMBINED_ENVIRONMENTAL_CHANGE_SYNTHETIC": "Combined Environmental Change",

    # ── Common / legacy / firmware variants ────────────────────────────────────
    "NORMAL": "Normal",
    "SUSTAINED_MQ5_RISE": "Sustained Gas Sensor Rise",
    "GAS_RISING": "Sustained Gas Sensor Rise",
    "GAS_ELEVATED": "Sustained Gas Sensor Rise",
    "ELEVATED_GAS": "Sustained Gas Sensor Rise",
    "ABRUPT_MQ5_DEVIATION": "Abrupt Gas Sensor Change",
    "ABRUPT_CHANGE": "Abrupt Gas Sensor Change",
    "COMBINED_ENVIRONMENTAL_CHANGE": "Combined Environmental Change",
    "COMBINED_EVENT": "Combined Environmental Change",
    "ENV_CHANGE": "Combined Environmental Change",
    "ENVIRONMENTAL_CHANGE": "Combined Environmental Change",
    "RECOVERING": "Recovering",
    "RECOVERY": "Recovering",
    "OVERHEATING": "Overheating",
    "ENVIRONMENTAL_ANOMALY": "Environmental Anomaly",
    "MOTION_ACTIVITY": "Motion Activity",
    "GAS_HAZARD": "Gas Hazard",
}


def format_evaluation_label(class_name: Optional[str]) -> str:
    """
    Returns a clean, human-readable evaluation label for any class name.
    The default normal evaluation displays 'Normal', never 'NORMAL_SYNTHETIC' or 'normal_synthetic'.
    Preserves original identifiers internally while providing polished presentation.
    """
    if not class_name:
        return "Normal"

    raw = str(class_name).strip()
    upper = raw.upper()

    # Exact match in mapping
    if upper in EVALUATION_LABEL_MAP:
        return EVALUATION_LABEL_MAP[upper]

    # Suffix check for any unrecognized _SYNTHETIC variants
    if upper.endswith("_SYNTHETIC"):
        base = upper[:-10]
        if base in EVALUATION_LABEL_MAP:
            return EVALUATION_LABEL_MAP[base]
        cleaned = base.replace("_", " ").title()
        return cleaned or "Normal"

    # General fallback: replace underscores with spaces and title-case
    cleaned = upper.replace("_", " ").title()
    return cleaned if cleaned else "Normal"
