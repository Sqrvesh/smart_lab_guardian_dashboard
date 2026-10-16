"""
Real-time Plotly charts for Smart Lab Guardian:
- Temperature and Humidity dual-axis/stacked charts with warning threshold reference lines.
- Risk Score & Severity timeline with incident markers.
- Motion Activity (PIR digital state & rolling count).
- Combustible Gas readings (when registered and active).
- Time window filtering (1, 5, 15, 60 minutes, All) and clear history controls.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from smart_lab_guardian_dashboard.core.state_manager import StateManager
from smart_lab_guardian_dashboard.core.sensor_registry import SensorRegistry


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
        st.write("")  # vertical spacing
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
        "🌡️ Temperature & Humidity",
        "⚠️ Risk Score Timeline",
        "🚶 PIR Motion Activity",
        "🔬 Gas Sensor (MQ-5)",
    ])

    # -----------------------------------------------------------------------
    # TAB 1: Temperature & Humidity
    # -----------------------------------------------------------------------
    with chart_tabs[0]:
        temp_data = state_manager.get_time_window_data("temp_ambient", window_minutes)
        hum_data = state_manager.get_time_window_data("humidity_rel", window_minutes)

        if not temp_data and not hum_data:
            st.info("No temperature or humidity samples in the selected time window.")
        else:
            fig = go.Figure()

            if temp_data:
                df_temp = pd.DataFrame(temp_data)
                is_sim = any(d.get("source") == "SIMULATION" for d in temp_data)
                label_suffix = " (Simulated)" if is_sim else " (Live)"
                fig.add_trace(go.Scatter(
                    x=df_temp["timestamp"],
                    y=df_temp["value"],
                    name=f"Temperature (°C){label_suffix}",
                    line=dict(color="#f97316", width=2.5),
                    yaxis="y1",
                ))

            if hum_data:
                df_hum = pd.DataFrame(hum_data)
                is_sim = any(d.get("source") == "SIMULATION" for d in hum_data)
                label_suffix = " (Simulated)" if is_sim else " (Live)"
                fig.add_trace(go.Scatter(
                    x=df_hum["timestamp"],
                    y=df_hum["value"],
                    name=f"Humidity (% RH){label_suffix}",
                    line=dict(color="#38bdf8", width=2.5),
                    yaxis="y2",
                ))

            # Reference threshold lines for Temperature
            temp_def = sensor_registry.get_sensor("temp_ambient")
            if temp_def and temp_def.warning_thresholds:
                w_high = temp_def.warning_thresholds.get("high")
                if w_high:
                    fig.add_hline(
                        y=w_high, line_dash="dash", line_color="#f59e0b",
                        annotation_text=f"Temp Warn ({w_high}°C)", annotation_position="top left",
                        annotation_font_color="#f59e0b", annotation_font_size=10,
                    )

            layout_args = dict(**PLOTLY_LAYOUT_DEFAULTS)
            layout_args.update(
                title=dict(text="HTS221 Environmental Profiles", font=dict(color="#e2e8f0", size=13)),
                yaxis=dict(
                    title=dict(text="Temperature (°C)", font=dict(color="#f97316")),
                    tickfont=dict(color="#f97316"),
                    showgrid=True,
                    gridcolor="#1f293d",
                ),
                yaxis2=dict(
                    title=dict(text="Humidity (% RH)", font=dict(color="#38bdf8")),
                    tickfont=dict(color="#38bdf8"),
                    overlaying="y",
                    side="right",
                    showgrid=False,
                ),
                height=320,
            )
            fig.update_layout(**layout_args)
            st.plotly_chart(fig, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 2: Risk Score Timeline
    # -----------------------------------------------------------------------
    with chart_tabs[1]:
        risk_data = state_manager.get_time_window_risk_data(window_minutes)
        if not risk_data:
            st.info("No risk evaluations recorded in the selected time window.")
        else:
            df_risk = pd.DataFrame(risk_data)
            is_sim = any(d.get("source") == "SIMULATION" for d in risk_data)
            label_suffix = " (Simulated)" if is_sim else " (STM32)"

            fig_risk = go.Figure()
            fig_risk.add_trace(go.Scatter(
                x=df_risk["timestamp"],
                y=df_risk["risk_score"],
                name=f"Reported Risk Score{label_suffix}",
                line=dict(color="#ef4444", width=3),
                fill="tozeroy",
                fillcolor="rgba(239, 68, 68, 0.1)",
            ))

            # Severity threshold lines (0-25 Low, 25-50 Med, 50-80 High, 80-100 Critical)
            fig_risk.add_hline(y=25, line_dash="dot", line_color="#10b981", annotation_text="Low/Medium (25)", annotation_font_size=9)
            fig_risk.add_hline(y=50, line_dash="dot", line_color="#f59e0b", annotation_text="Medium/High (50)", annotation_font_size=9)
            fig_risk.add_hline(y=80, line_dash="dash", line_color="#ef4444", annotation_text="High/Critical (80)", annotation_font_size=9)

            layout_args = dict(**PLOTLY_LAYOUT_DEFAULTS)
            layout_args.update(
                title=dict(text="Explainable Risk Score Evolution", font=dict(color="#e2e8f0", size=13)),
                yaxis=dict(title="Risk Score (0 - 100)", range=[0, 105], showgrid=True, gridcolor="#1f293d"),
                height=320,
            )
            fig_risk.update_layout(**layout_args)
            st.plotly_chart(fig_risk, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 3: PIR Motion Activity
    # -----------------------------------------------------------------------
    with chart_tabs[2]:
        pir_data = state_manager.get_time_window_data("pir_motion", window_minutes)
        if not pir_data:
            st.info("No PIR sensor data in the selected time window.")
        else:
            df_pir = pd.DataFrame(pir_data)
            fig_pir = go.Figure()
            fig_pir.add_trace(go.Scatter(
                x=df_pir["timestamp"],
                y=df_pir["value"],
                name="Instantaneous PIR Pin (PD14)",
                line=dict(color="#a855f7", width=2, shape="hv"),
                mode="lines+markers",
            ))

            layout_args = dict(**PLOTLY_LAYOUT_DEFAULTS)
            layout_args.update(
                title=dict(text="HC-SR501 PIR Digital State", font=dict(color="#e2e8f0", size=13)),
                yaxis=dict(title="Digital Logic (0=Clear, 1=Motion)", range=[-0.2, 1.2], tickvals=[0, 1], ticktext=["0 (Clear)", "1 (Detected)"], showgrid=True, gridcolor="#1f293d"),
                height=280,
            )
            fig_pir.update_layout(**layout_args)
            st.plotly_chart(fig_pir, use_container_width=True)

    # -----------------------------------------------------------------------
    # TAB 4: MQ-5 Gas Sensor
    # -----------------------------------------------------------------------
    with chart_tabs[3]:
        gas_data = state_manager.get_time_window_data("gas_mq5", window_minutes)
        gas_def = sensor_registry.get_sensor("gas_mq5")

        if not gas_data:
            if not gas_def or not gas_def.is_installed:
                st.markdown(
                    """
                    <div style="background: #1e293b; padding: 20px; border-radius: 8px; border: 1px dashed #475569; text-align: center;">
                        <h4 style="color: #94a3b8; margin: 0 0 6px 0;">MQ-5 Gas Sensor: Not Configured on Live Hardware</h4>
                        <p style="color: #64748b; font-size: 0.85rem; margin: 0;">
                            The MQ-5 combustible gas sensor is architected for future hardware integration. No live physical ADC stream is currently connected to the STM32 board.
                            <br/>To inspect extensible gas telemetry visualization, activate <strong>Scenario 10: Future gas sensor</strong> in the Simulator console.
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.info("MQ-5 gas sensor registered but no readings received yet.")
        else:
            df_gas = pd.DataFrame(gas_data)
            fig_gas = go.Figure()
            fig_gas.add_trace(go.Scatter(
                x=df_gas["timestamp"],
                y=df_gas["value"],
                name="MQ-5 Analog Reading (raw ADC counts)",
                line=dict(color="#eab308", width=2.5),
            ))

            if gas_def and gas_def.warning_thresholds:
                w_high = gas_def.warning_thresholds.get("high")
                if w_high:
                    fig_gas.add_hline(y=w_high, line_dash="dash", line_color="#f59e0b", annotation_text=f"Warning ({w_high} ADC)")
            if gas_def and gas_def.critical_thresholds:
                c_high = gas_def.critical_thresholds.get("high")
                if c_high:
                    fig_gas.add_hline(y=c_high, line_dash="dash", line_color="#ef4444", annotation_text=f"Critical ({c_high} ADC)")

            layout_args = dict(**PLOTLY_LAYOUT_DEFAULTS)
            layout_args.update(
                title=dict(text="MQ-5 Combustible Gas Analog Profile (Uncalibrated ADC)", font=dict(color="#e2e8f0", size=13)),
                yaxis=dict(title="ADC Counts (0 - 1023)", showgrid=True, gridcolor="#1f293d"),
                height=280,
            )
            fig_gas.update_layout(**layout_args)
            st.plotly_chart(fig_gas, use_container_width=True)
