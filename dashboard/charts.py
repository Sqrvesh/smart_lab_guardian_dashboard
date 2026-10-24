"""
Real-time Plotly charts for Smart Lab Guardian:
- Risk Score timeline (0–100 scale with severity reference thresholds).
- Gas Response Index (0–100 GRI with Low/Elevated/High reference bands).
- Ambient Temperature profile (°C with warning and critical thresholds).
- Relative Humidity profile (% RH with warning thresholds).
- Time window filtering (1, 5, 15, 60 minutes, All) and buffer management.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

try:
    from smart_lab_guardian_dashboard.core.state_manager import StateManager
    from smart_lab_guardian_dashboard.core.sensor_registry import SensorRegistry
    from smart_lab_guardian_dashboard.core.evaluation_labels import format_evaluation_label
except ImportError:
    from core.state_manager import StateManager
    from core.sensor_registry import SensorRegistry
    from core.evaluation_labels import format_evaluation_label


PLOTLY_LAYOUT_DEFAULTS = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#111827",
    font=dict(color="#94a3b8", size=11),
    margin=dict(l=40, r=20, t=35, b=30),
    xaxis=dict(
        showgrid=True,
        gridcolor="#1f293d",
        zeroline=False,
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor="#1f293d",
        zeroline=False,
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
        font=dict(size=10),
    ),
)


def render_realtime_charts(
    state_manager: StateManager,
    sensor_registry: SensorRegistry,
):
    """
    Renders all interactive Plotly real-time telemetry charts.
    """
    st.markdown("### 📈 Live Telemetry Charts")

    # Time window selector controls
    c_win, c_clear = st.columns([4, 1])
    with c_win:
        win_choice = st.radio(
            "Time Window",
            ["Last 1 Min", "Last 5 Min", "Last 15 Min", "Last 60 Min", "All History"],
            index=1,
            horizontal=True,
            key="chart_window_choice",
        )
    with c_clear:
        st.write("")
        if st.button("🧹 Clear Chart Buffers", help="Clears buffered chart history"):
            state_manager.clear_all_history()
            st.rerun()

    window_map = {
        "Last 1 Min": 1,
        "Last 5 Min": 5,
        "Last 15 Min": 15,
        "Last 60 Min": 60,
        "All History": None,
    }
    window_minutes = window_map.get(win_choice, 5)

    chart_tabs = st.tabs([
        "⚠️ Risk Score",
        "🔬 Gas Response",
        "🌡️ Temperature",
        "💧 Humidity",
    ])

    # -----------------------------------------------------------------------
    # TAB 1: Risk Score Timeline
    # -----------------------------------------------------------------------
    with chart_tabs[0]:
        risk_data = state_manager.get_time_window_risk_data(window_minutes)

        if not risk_data:
            st.info("No risk evaluations recorded in the selected time window.")
        else:
            fig_risk = go.Figure()
            is_sim = any(d.get("source") == "SIMULATION" for d in risk_data)
            label_suffix = " (Simulated)" if is_sim else " (Live)"

            df_risk = pd.DataFrame(risk_data)

            # Format clean hover classes
            hover_classes = [
                format_evaluation_label(c) for c in df_risk.get("incident_class", ["Normal"] * len(df_risk))
            ]

            # Risk score trace
            fig_risk.add_trace(go.Scatter(
                x=df_risk["timestamp"],
                y=df_risk["risk_score"],
                name=f"Risk Score{label_suffix}",
                line=dict(color="#ef4444", width=2.5),
                fill="tozeroy",
                fillcolor="rgba(239, 68, 68, 0.08)",
                customdata=hover_classes,
                hovertemplate="<b>%{x|%H:%M:%S}</b><br>Risk: %{y:.0f}/100<br>Class: %{customdata}<extra></extra>",
            ))

            # Severity threshold reference lines
            fig_risk.add_hline(y=25, line_dash="dot", line_color="#10b981", annotation_text="Low/Medium (25)", annotation_font_size=9)
            fig_risk.add_hline(y=50, line_dash="dot", line_color="#f59e0b", annotation_text="Medium/High (50)", annotation_font_size=9)
            fig_risk.add_hline(y=80, line_dash="dash", line_color="#ef4444", annotation_text="High/Critical (80)", annotation_font_size=9)

            layout_args = dict(**PLOTLY_LAYOUT_DEFAULTS)
            layout_args.update(
                title=dict(text="Risk Score Evolution (0–100 Scale)", font=dict(color="#e2e8f0", size=13)),
                yaxis=dict(title="Risk Score (0 - 100)", range=[0, 105], showgrid=True, gridcolor="#1f293d"),
                height=320,
            )
            fig_risk.update_layout(**layout_args)
            st.plotly_chart(fig_risk, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 2: Gas Response Index (GRI) Timeline
    # -----------------------------------------------------------------------
    with chart_tabs[1]:
        gri_data = state_manager.get_time_window_gri_data(window_minutes)

        if not gri_data:
            st.info("No gas response samples in the selected time window.")
        else:
            df_g = pd.DataFrame(gri_data)
            fig_gri = go.Figure()
            fig_gri.add_trace(go.Scatter(
                x=df_g["timestamp"],
                y=df_g["value"],
                name="Gas Response Index (GRI)",
                line=dict(color="#eab308", width=2.5),
                fill="tozeroy",
                fillcolor="rgba(234, 179, 8, 0.08)",
                hovertemplate="<b>%{x|%H:%M:%S}</b><br>GRI: %{y:.1f} / 100<extra></extra>",
            ))

            # Reference bands for Low (0-20), Elevated (20-50), High (50-100)
            fig_gri.add_hline(y=20, line_dash="dot", line_color="#10b981", annotation_text="Low / Elevated (20)", annotation_font_size=9)
            fig_gri.add_hline(y=50, line_dash="dash", line_color="#f59e0b", annotation_text="Elevated / High (50)", annotation_font_size=9)

            layout_args = dict(**PLOTLY_LAYOUT_DEFAULTS)
            layout_args.update(
                title=dict(text="Gas Response Index (Human-Readable 0–100 Scale)", font=dict(color="#e2e8f0", size=13)),
                yaxis=dict(title="Response Index (0 - 100)", range=[0, 105], showgrid=True, gridcolor="#1f293d"),
                height=320,
            )
            fig_gri.update_layout(**layout_args)
            st.plotly_chart(fig_gri, use_container_width=True)
            st.caption("ℹ️ Gas Response Index represents normalized response relative to clean-air baseline. It is not an absolute gas concentration (ppm).")

    # -----------------------------------------------------------------------
    # TAB 3: Temperature Profile
    # -----------------------------------------------------------------------
    with chart_tabs[2]:
        temp_data = state_manager.get_time_window_data("temp_ambient", window_minutes)

        if not temp_data:
            st.info("No temperature samples in the selected time window.")
        else:
            fig_temp = go.Figure()
            df_temp = pd.DataFrame(temp_data)
            is_sim = any(d.get("source") == "SIMULATION" for d in temp_data)
            label_suffix = " (Simulated)" if is_sim else " (Live)"

            fig_temp.add_trace(go.Scatter(
                x=df_temp["timestamp"],
                y=df_temp["value"],
                name=f"Temperature (°C){label_suffix}",
                line=dict(color="#f97316", width=2.5),
                fill="tozeroy",
                fillcolor="rgba(249, 115, 22, 0.06)",
                hovertemplate="<b>%{x|%H:%M:%S}</b><br>Temperature: %{y:.2f} °C<extra></extra>",
            ))

            # Reference threshold lines for Temperature
            temp_def = sensor_registry.get_sensor("temp_ambient")
            if temp_def and temp_def.warning_thresholds:
                w_high = temp_def.warning_thresholds.get("high")
                if w_high:
                    fig_temp.add_hline(
                        y=w_high, line_dash="dash", line_color="#f59e0b",
                        annotation_text=f"Warning ({w_high}°C)", annotation_position="top left",
                        annotation_font_color="#f59e0b", annotation_font_size=10,
                    )
            if temp_def and temp_def.critical_thresholds:
                c_high = temp_def.critical_thresholds.get("high")
                if c_high:
                    fig_temp.add_hline(
                        y=c_high, line_dash="dash", line_color="#ef4444",
                        annotation_text=f"Critical ({c_high}°C)", annotation_position="top left",
                        annotation_font_color="#ef4444", annotation_font_size=10,
                    )

            layout_args = dict(**PLOTLY_LAYOUT_DEFAULTS)
            layout_args.update(
                title=dict(text="Ambient Temperature Profile (°C)", font=dict(color="#e2e8f0", size=13)),
                yaxis=dict(
                    title="Temperature (°C)",
                    showgrid=True,
                    gridcolor="#1f293d",
                ),
                height=320,
            )
            fig_temp.update_layout(**layout_args)
            st.plotly_chart(fig_temp, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 4: Relative Humidity Profile
    # -----------------------------------------------------------------------
    with chart_tabs[3]:
        hum_data = state_manager.get_time_window_data("humidity_rel", window_minutes)

        if not hum_data:
            st.info("No humidity samples in the selected time window.")
        else:
            fig_hum = go.Figure()
            df_hum = pd.DataFrame(hum_data)
            is_sim = any(d.get("source") == "SIMULATION" for d in hum_data)
            label_suffix = " (Simulated)" if is_sim else " (Live)"

            fig_hum.add_trace(go.Scatter(
                x=df_hum["timestamp"],
                y=df_hum["value"],
                name=f"Humidity (% RH){label_suffix}",
                line=dict(color="#38bdf8", width=2.5),
                fill="tozeroy",
                fillcolor="rgba(56, 189, 248, 0.06)",
                hovertemplate="<b>%{x|%H:%M:%S}</b><br>Humidity: %{y:.2f} % RH<extra></extra>",
            ))

            # Reference threshold lines for Humidity
            hum_def = sensor_registry.get_sensor("humidity_rel")
            if hum_def and hum_def.warning_thresholds:
                w_high = hum_def.warning_thresholds.get("high")
                if w_high:
                    fig_hum.add_hline(
                        y=w_high, line_dash="dash", line_color="#f59e0b",
                        annotation_text=f"High Warn ({w_high}%)", annotation_position="top left",
                        annotation_font_color="#f59e0b", annotation_font_size=10,
                    )
                w_low = hum_def.warning_thresholds.get("low")
                if w_low:
                    fig_hum.add_hline(
                        y=w_low, line_dash="dot", line_color="#f59e0b",
                        annotation_text=f"Low Warn ({w_low}%)", annotation_position="bottom left",
                        annotation_font_color="#f59e0b", annotation_font_size=10,
                    )

            layout_args = dict(**PLOTLY_LAYOUT_DEFAULTS)
            layout_args.update(
                title=dict(text="Relative Humidity Profile (% RH)", font=dict(color="#e2e8f0", size=13)),
                yaxis=dict(
                    title="Humidity (% RH)",
                    range=[0, 100],
                    showgrid=True,
                    gridcolor="#1f293d",
                ),
                height=320,
            )
            fig_hum.update_layout(**layout_args)
            st.plotly_chart(fig_hum, use_container_width=True)
