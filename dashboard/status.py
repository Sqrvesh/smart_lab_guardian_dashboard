"""
Laboratory Status Hero Banner for Smart Lab Guardian.
Displays: incident class, risk score (0–100), persistent risk, severity badge,
prediction timestamp, source engine, and firmware explanation.
"""

import streamlit as st
from datetime import datetime
from typing import Optional

from smart_lab_guardian_dashboard.core.state_manager import IncidentState

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

    # Persistent risk display
    persist_risk = getattr(incident, "persist_risk", None)
    persist_html = ""
    if persist_risk is not None and persist_risk != incident.risk_score:
        persist_html = (
            f'<div style="font-size:0.72rem;color:#64748b;margin-top:2px;">'
            f'Persistent risk: <strong style="color:{style["color"]}">'
            f'{persist_risk:.0f}</strong>/100</div>'
        )

    # Confidence display
    mlp_conf = getattr(incident, "mlp_confidence", None)
    conf_html = ""
    if mlp_conf is not None:
        conf_html = f'<span style="color:#64748b;font-size:0.78rem;"> · {mlp_conf:.0f}% conf.</span>'

    scenario_html = ""
    if incident.scenario_name:
        scenario_html = (
            f' &bull; <strong>Scenario:</strong> '
            f'<span style="color:#f59e0b;">{incident.scenario_name}</span>'
        )

    st.html(f"""
    <div style="background:{style['bg']};border:1px solid {style['border']};
                border-left:8px solid {style['border']};border-radius:12px;
                padding:18px 24px;margin-bottom:20px;
                box-shadow:0 4px 16px rgba(0,0,0,0.3);">

      <div style="display:flex;justify-content:space-between;align-items:flex-start;
                  flex-wrap:wrap;gap:12px;">
        <div>
          <div style="font-size:0.78rem;font-weight:700;text-transform:uppercase;
                      letter-spacing:0.08em;color:#94a3b8;">
            Laboratory Status &amp; Incident Assessment
          </div>
          <div style="font-size:2.0rem;font-weight:800;color:#f8fafc;
                      letter-spacing:-0.02em;margin-top:2px;">
            {style['icon']} {incident.incident_class}{conf_html}
          </div>
          <div style="font-size:0.86rem;color:#cbd5e1;margin-top:4px;max-width:620px;
                      line-height:1.45;">
            {incident.why}
          </div>
        </div>

        <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap;">
          <div style="text-align:right;">
            <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                        color:#94a3b8;">Severity</div>
            <div style="margin-top:4px;font-size:0.9rem;font-weight:700;
                        padding:4px 14px;border-radius:6px;letter-spacing:0.05em;
                        background:{style['bg']};color:{style['color']};
                        border:1.5px solid {style['color']};">
              {style['label']}
            </div>
          </div>

          <div style="text-align:right;min-width:110px;">
            <div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;
                        color:#94a3b8;">Risk Score</div>
            <div style="font-size:2.4rem;font-weight:800;color:{style['color']};
                        line-height:1.0;margin-top:2px;">
              {incident.risk_score:.0f}<span style="font-size:1.0rem;color:#64748b;
              font-weight:500;">/100</span>
            </div>
            {persist_html}
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
