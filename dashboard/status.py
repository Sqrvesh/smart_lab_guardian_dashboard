"""
Laboratory Status Hero Banner for Smart Lab Guardian.
Displays: incident class, risk score (0–100), persistent risk, severity badge,
prediction timestamp, source engine, and firmware explanation.
"""

import streamlit as st
from datetime import datetime
from typing import Optional

try:
    from smart_lab_guardian_dashboard.core.state_manager import IncidentState
    from smart_lab_guardian_dashboard.core.evaluation_labels import format_evaluation_label
except ImportError:
    from core.state_manager import IncidentState
    from core.evaluation_labels import format_evaluation_label

SEVERITY_STYLES = {
    "LOW": {
        "color": "#10b981",
        "bg": "rgba(16, 185, 129, 0.10)",
        "border": "#10b981",
        "label": "LOW RISK",
        "icon": "🟢",
    },
    "MEDIUM": {
        "color": "#f59e0b",
        "bg": "rgba(245, 158, 11, 0.10)",
        "border": "#f59e0b",
        "label": "MEDIUM RISK",
        "icon": "🟡",
    },
    "HIGH": {
        "color": "#f97316",
        "bg": "rgba(249, 115, 22, 0.10)",
        "border": "#f97316",
        "label": "HIGH RISK",
        "icon": "🟠",
    },
    "CRITICAL": {
        "color": "#ef4444",
        "bg": "rgba(239, 68, 68, 0.13)",
        "border": "#ef4444",
        "label": "CRITICAL",
        "icon": "🔴",
    },
    "STALE": {
        "color": "#94a3b8",
        "bg": "rgba(100, 116, 139, 0.12)",
        "border": "#64748b",
        "label": "STALE DATA",
        "icon": "⚪",
    },
}


def render_status_panel(
    incident: IncidentState,
    is_stale: bool = False,
    is_connected: bool = True,
):
    """Renders the primary status card."""
    severity = incident.severity.upper() if incident.severity else "LOW"
    if is_stale or not is_connected:
        style_key = "STALE"
    else:
        style_key = severity if severity in SEVERITY_STYLES else "LOW"

    style = SEVERITY_STYLES[style_key]

    ts_str = (
        incident.prediction_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        if incident.prediction_timestamp
        else "Awaiting first reading"
    )

    # Clean confidence display under Risk Score (replaces persistent risk)
    mlp_conf = getattr(incident, "mlp_confidence", None)
    conf_html = ""
    if mlp_conf is not None:
        conf_html = (
            f'<div style="font-size:0.75rem;color:#94a3b8;margin-top:4px;font-weight:500;white-space:nowrap;">'
            f'Confidence: <strong style="color:#e2e8f0;">{mlp_conf:.0f}%</strong></div>'
        )

    # Format scenario name without redundant "Scenario X:" prefix and dimmed color
    scenario_html = ""
    if incident.scenario_name:
        import re
        clean_scen = re.sub(r"^Scenario\s*\d+\s*:\s*", "", incident.scenario_name).strip()
        scenario_html = (
            f' &bull; <strong>Scenario:</strong> '
            f'<span style="color:#94a3b8;font-weight:500;">{clean_scen}</span>'
        )

    st.html(f"""
    <div style="background:{style['bg']};border:1px solid {style['border']};
                border-left:8px solid {style['border']};border-radius:12px;
                padding:18px 24px;margin-bottom:20px;
                box-shadow:0 4px 16px rgba(0,0,0,0.3);">

      <div style="display:flex;justify-content:space-between;align-items:center;
                  flex-wrap:wrap;gap:16px;">
        <div style="flex:1;min-width:280px;">
          <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;
                      letter-spacing:0.08em;color:#94a3b8;">
            Laboratory Status &amp; Incident Assessment
          </div>
          <div style="font-size:2.0rem;font-weight:800;color:#f8fafc;
                      letter-spacing:-0.02em;margin-top:2px;">
            {style['icon']} {format_evaluation_label(incident.incident_class)}
          </div>
          <div style="font-size:0.86rem;color:#cbd5e1;margin-top:4px;max-width:620px;
                      line-height:1.45;">
            {incident.why}
          </div>
        </div>

        <div style="display:flex;gap:20px;align-items:center;flex-shrink:0;">
          <div style="display:flex;align-items:center;justify-content:center;width:135px;flex-shrink:0;">
            <div style="font-size:0.85rem;font-weight:700;
                        padding:6px 0;width:130px;text-align:center;border-radius:6px;letter-spacing:0.05em;
                        background:{style['bg']};color:{style['color']};
                        border:1.5px solid {style['color']};white-space:nowrap;box-sizing:border-box;">
              {style['label']}
            </div>
          </div>

          <div style="text-align:right;min-width:115px;display:flex;flex-direction:column;align-items:flex-end;">
            <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                        color:#94a3b8;">Risk Score</div>
            <div style="font-size:2.4rem;font-weight:800;color:{style['color']};
                        line-height:1.0;margin-top:2px;">
              {incident.risk_score:.0f}<span style="font-size:1.0rem;color:#64748b;
              font-weight:500;">/100</span>
            </div>
            {conf_html}
          </div>
        </div>
      </div>

      <div style="display:flex;justify-content:space-between;align-items:center;
                  border-top:1px solid rgba(255,255,255,0.07);margin-top:12px;
                  padding-top:9px;font-size:0.76rem;color:#64748b;">
        <div>
          <strong>Source:</strong>
          <span style="color:#94a3b8;">{incident.model_source}</span>
          {scenario_html}
        </div>
        <div>
          <strong>Updated:</strong>
          <span style="font-family:monospace;color:#94a3b8;">{ts_str}</span>
        </div>
      </div>
    </div>
    """)
