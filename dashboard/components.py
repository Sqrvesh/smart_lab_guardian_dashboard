"""
UI Components for Smart Lab Guardian:
- Sensor metric cards (Temperature, Humidity, Gas Response Index, Risk).
- MQ-5 technical details panel (raw ADC / mV, firmware MQ-5 metrics).
- Explainable risk breakdown chart.
- Incident event timeline table with search, filter, and CSV export.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any

from smart_lab_guardian_dashboard.core.sensor_registry import SensorDefinition, SensorRegistry
from smart_lab_guardian_dashboard.core.state_manager import LiveSensorState, IncidentState, StateManager
from smart_lab_guardian_dashboard.core.freshness import FreshnessStatus, FreshnessTracker
from smart_lab_guardian_dashboard.core.event_manager import EventManager, IncidentEvent
from smart_lab_guardian_dashboard.core.gas_response import GriTracker, gri_label, gri_color


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

_SEVERITY_COLORS = {
    "LOW":      "#10b981",
    "MEDIUM":   "#f59e0b",
    "HIGH":     "#f97316",
    "CRITICAL": "#ef4444",
}

def _sev_color(sev: str) -> str:
    return _SEVERITY_COLORS.get(sev.upper() if sev else "", "#94a3b8")


# ---------------------------------------------------------------------------
# 1. Top-row metric cards
# ---------------------------------------------------------------------------

def _metric_card(
    title: str,
    value: str,
    sub: str = "",
    accent: str = "#38bdf8",
    badge_text: str = "",
    badge_color: str = "#64748b",
    icon: str = "",
    extra_html: str = "",
) -> None:
    st.html(f"""
    <div style="background:linear-gradient(145deg,#131b2e 0%,#172036 100%);
                border:1px solid #23314f;border-top:3px solid {accent};
                border-radius:10px;padding:16px 18px 12px;
                box-shadow:0 4px 12px rgba(0,0,0,0.35);">
      <div style="display:flex;justify-content:space-between;align-items:center;
                  margin-bottom:6px;">
        <span style="font-size:0.78rem;font-weight:600;text-transform:uppercase;
                     letter-spacing:0.07em;color:#94a3b8;">{icon} {title}</span>
        <span style="font-size:0.68rem;font-weight:700;padding:2px 8px;
                     border-radius:5px;letter-spacing:0.05em;
                     color:{badge_color};border:1px solid {badge_color};">
          {badge_text}
        </span>
      </div>
      <div style="font-size:1.85rem;font-weight:700;color:#f8fafc;
                  letter-spacing:-0.02em;line-height:1.15;">{value}</div>
      <div style="font-size:0.76rem;color:#94a3b8;margin-top:5px;">{sub}</div>
      {extra_html}
    </div>
    """)


def render_top_row_cards(
    incident: IncidentState,
    sensor_states: Dict[str, LiveSensorState],
    freshness_tracker: FreshnessTracker,
    gri_tracker: GriTracker,
    is_stale: bool = False,
) -> None:
    """Renders the four top-row metric cards: Risk, Gas, Temperature, Humidity."""
    col_risk, col_gas, col_temp, col_hum = st.columns(4)

    # ── Risk card ──────────────────────────────────────────────────────────
    with col_risk:
        sev = incident.severity.upper() if incident.severity else "LOW"
        risk_col = _sev_color(sev)
        persist_risk = getattr(incident, "persist_risk", None)
        persist_sub = (
            f"Persistent: {persist_risk:.0f}/100"
            if persist_risk is not None and persist_risk != incident.risk_score
            else "No persistence data"
        )
        _metric_card(
            title="Overall Risk",
            value=f"{incident.risk_score:.0f} / 100",
            sub=persist_sub,
            accent=risk_col,
            badge_text=sev,
            badge_color=risk_col,
            icon="⚠️",
        )

    # ── Gas Response Index card ────────────────────────────────────────────
    with col_gas:
        gas_state = sensor_states.get("gas_mq5")
        mq5_adc: Optional[int] = None
        if gas_state and gas_state.current_value is not None:
            mq5_adc = int(gas_state.current_value)

        gri_val, calibrated = gri_tracker.compute(mq5_adc)

        if not calibrated:
            gri_display = "Calibrating…"
            gri_col = "#64748b"
            gri_lbl = "Warming up"
            gri_sub = "Collecting baseline samples"
        else:
            gri_col = gri_color(gri_val)
            gri_lbl = gri_label(gri_val)
            gri_display = f"{gri_val:.0f} / 100" if gri_val is not None else "No Data"
            gri_sub = f"ADC: {mq5_adc}" if mq5_adc is not None else "No reading"

        _metric_card(
            title="Gas Response Index",
            value=gri_display,
            sub=gri_sub,
            accent=gri_col,
            badge_text=gri_lbl.upper(),
            badge_color=gri_col,
            icon="🔬",
        )

    # ── Temperature card ───────────────────────────────────────────────────
    with col_temp:
        temp_state = sensor_states.get("temp_ambient")
        temp_val = temp_state.current_value if temp_state else None
        age = freshness_tracker.get_age_seconds(temp_state.last_updated if temp_state else None)
        badge, badge_col = freshness_tracker.get_status_badge(
            temp_state.status if temp_state else FreshnessStatus.NO_DATA, age
        )
        temp_display = f"{temp_val:.2f} °C" if isinstance(temp_val, float) else "No Data"
        trend = temp_state.trend if temp_state else "STEADY"
        trend_icon = {"RISING": "↗", "FALLING": "↘", "STEADY": "→"}.get(trend, "→")
        _metric_card(
            title="Temperature",
            value=temp_display,
            sub=f"Trend: {trend_icon} {trend.title()}",
            accent="#f97316",
            badge_text=badge,
            badge_color=badge_col,
            icon="🌡️",
        )

    # ── Humidity card ──────────────────────────────────────────────────────
    with col_hum:
        hum_state = sensor_states.get("humidity_rel")
        hum_val = hum_state.current_value if hum_state else None
        h_age = freshness_tracker.get_age_seconds(hum_state.last_updated if hum_state else None)
        h_badge, h_badge_col = freshness_tracker.get_status_badge(
            hum_state.status if hum_state else FreshnessStatus.NO_DATA, h_age
        )
        hum_display = f"{hum_val:.2f} % RH" if isinstance(hum_val, float) else "No Data"
        h_trend = hum_state.trend if hum_state else "STEADY"
        h_trend_icon = {"RISING": "↗", "FALLING": "↘", "STEADY": "→"}.get(h_trend, "→")
        _metric_card(
            title="Relative Humidity",
            value=hum_display,
            sub=f"Trend: {h_trend_icon} {h_trend.title()}",
            accent="#38bdf8",
            badge_text=h_badge,
            badge_color=h_badge_col,
            icon="💧",
        )


# ---------------------------------------------------------------------------
# Reusable Generic Sensor Cards
# ---------------------------------------------------------------------------

def render_sensor_card(
    sensor_def: SensorDefinition,
    sensor_state: LiveSensorState,
    freshness_tracker: FreshnessTracker,
) -> None:
    """
    Renders an individual sensor card dynamically using its definition and state.
    Supports physical sensors (HTS221 Temp, Hum, MQ-5 Gas ADC/mV).
    """
    card_title = sensor_def.display_name
    unit = sensor_def.unit
    val = sensor_state.current_value
    status = sensor_state.status

    # Trend symbol
    trend_icons = {
        "RISING": "↗ Rising",
        "FALLING": "↘ Falling",
        "STEADY": "→ Steady",
    }
    trend_display = trend_icons.get(sensor_state.trend, "→ Steady")

    # Status badge
    age = freshness_tracker.get_age_seconds(sensor_state.last_updated)
    badge_text, badge_color = freshness_tracker.get_status_badge(status, age)

    # Threshold evaluation
    threshold_eval = "NORMAL"
    threshold_color = "#10b981"
    if isinstance(val, (int, float)):
        threshold_eval = sensor_def.evaluate_threshold(val)
        if threshold_eval == "CRITICAL":
            threshold_color = "#ef4444"
        elif threshold_eval == "WARNING":
            threshold_color = "#f59e0b"

    # Display value formatting
    formatted_val = sensor_def.format_value(val)

    # Sub-note
    sub_note = ""
    if sensor_def.sensor_type == "gas":
        if sensor_def.unit == "ADC":
            sub_note = "Raw 12-bit ADC count (Hardware; NOT ppm)"
        elif sensor_def.unit == "mV":
            sub_note = "Estimated analog sensor voltage"
    elif sensor_def.warning_thresholds:
        warn_high = sensor_def.warning_thresholds.get("high")
        crit_high = (sensor_def.critical_thresholds or {}).get("high")
        limits = []
        if warn_high is not None:
            limits.append(f"Warn: {warn_high}{unit}")
        if crit_high is not None:
            limits.append(f"Crit: {crit_high}{unit}")
        sub_note = "Thresholds: " + " | ".join(limits)

    st.markdown(
        f"""
        <div class="slg-card" style="border-top: 3px solid {threshold_color};">
            <div class="slg-card-header">
                <span>{card_title}</span>
                <span class="slg-badge" style="background: rgba(0,0,0,0.3); color: {badge_color}; border: 1px solid {badge_color}; font-size: 0.7rem;">
                    {badge_text}
                </span>
            </div>
            <div class="slg-card-value">
                {formatted_val}
            </div>
            <div style="font-size: 0.78rem; color: #94a3b8; margin-top: 6px;">
                {sub_note}
            </div>
            <div class="slg-card-footer">
                <span>Trend: <strong style="color: #cbd5e1;">{trend_display}</strong></span>
                <span>ID: <code style="color: #64748b;">{sensor_def.sensor_id}</code></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_all_sensor_cards(
    sensor_registry: SensorRegistry,
    sensor_states: Dict[str, LiveSensorState],
    freshness_tracker: FreshnessTracker,
) -> None:
    """Renders grid of all registered sensor cards."""
    sensors = [s for s in sensor_registry.get_all_sensors() if s.enabled]
    if not sensors:
        st.info("No sensors registered.")
        return

    cols = st.columns(len(sensors))
    for col, s_def in zip(cols, sensors):
        with col:
            s_state = sensor_states.get(
                s_def.sensor_id,
                LiveSensorState(sensor_id=s_def.sensor_id, status=FreshnessStatus.NO_DATA),
            )
            render_sensor_card(s_def, s_state, freshness_tracker)


# ---------------------------------------------------------------------------
# TinyML Embedded Inference Panel
# ---------------------------------------------------------------------------

def render_tinyml_panel(
    incident: IncidentState,
    latest_features: Optional[Dict[str, float]] = None,
    features_timestamp: Optional[datetime] = None,
    is_stale: bool = False,
) -> None:
    """
    Renders TinyML Embedded Prediction Panel & Firmware Telemetry.
    """
    st.markdown("### 🧠 TinyML Embedded Prediction & Telemetry")

    col_pred, col_details = st.columns([1, 2])

    with col_pred:
        mlp_class = incident.incident_class
        conf_str = f"{incident.mlp_confidence:.0f}%" if getattr(incident, "mlp_confidence", None) is not None else "N/A"
        sev = incident.severity.upper() if incident.severity else "LOW"
        risk_col = _sev_color(sev)
        st.markdown(
            f"""
            <div class="slg-card" style="height: 100%;">
                <div class="slg-card-header">
                    <span>Embedded TinyML Output</span>
                    <span style="font-size: 0.75rem; color: #38bdf8;">{incident.model_source}</span>
                </div>
                <div style="font-size: 1.6rem; font-weight: 700; color: #38bdf8; margin: 8px 0;">
                    {mlp_class}
                </div>
                <div style="font-size: 0.85rem; color: #94a3b8;">
                    Confidence: <strong style="color: #f8fafc;">{conf_str}</strong>
                </div>
                <div style="font-size: 0.75rem; color: #64748b; margin-top: 6px;">
                    Risk Level: <strong style="color: {risk_col};">{sev} ({incident.risk_score:.0f}/100)</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_details:
        st.markdown(
            """
            <div style="font-size: 0.85rem; font-weight: 600; text-transform: uppercase; color: #94a3b8; margin-bottom: 6px;">
                Firmware Telemetry & MQ-5 Dynamics
            </div>
            """,
            unsafe_allow_html=True,
        )
        f1, f2, f3 = st.columns(3)
        with f1:
            st.metric("MQ-5 Change", f"{incident.mq5_change:.3f}" if getattr(incident, "mq5_change", None) is not None else "—")
            st.metric("Persist Risk", f"{incident.persist_risk:.0f}" if getattr(incident, "persist_risk", None) is not None else "—")
        with f2:
            st.metric("Abrupt Change", "Yes" if getattr(incident, "mq5_abrupt", None) else "No")
            rec = getattr(incident, "recovery", None)
            st.metric("Recovery Window", f"{rec}" if rec is not None else "—")
        with f3:
            st.metric("MQ-5 Variability", f"{incident.mq5_variability:.3f}" if getattr(incident, "mq5_variability", None) is not None else "—")
            st.metric("Severity", incident.severity)


# ---------------------------------------------------------------------------
# 2. MQ-5 technical details / MLP panel
# ---------------------------------------------------------------------------

def render_mq5_panel(state_manager: StateManager) -> None:
    """
    Renders MQ-5 raw readings, firmware MQ-5 metrics, and MLP prediction details.
    Shown inside a collapsible expander so it doesn't clutter the main view.
    """
    latest_risk = getattr(state_manager, "latest_risk", None)
    latest_mlp  = getattr(state_manager, "latest_mlp",  None)
    gas_state   = state_manager.sensor_states.get("gas_mq5")
    gas_mv_state = state_manager.sensor_states.get("gas_mq5_mv")

    mq5_adc = gas_state.current_value if gas_state and gas_state.current_value is not None else None
    mq5_mv  = gas_mv_state.current_value if gas_mv_state and gas_mv_state.current_value is not None else None

    with st.expander("🔬 MQ-5 Technical Details & MLP Prediction", expanded=False):
        col_raw, col_metrics, col_mlp = st.columns(3)

        with col_raw:
            st.markdown("**Raw MQ-5 Readings**")
            st.metric("ADC Count", f"{int(mq5_adc)}" if mq5_adc is not None else "—",
                      help="Raw 12-bit ADC value (0–4095). Not a calibrated gas concentration.")
            st.metric("Voltage (mV)", f"{int(mq5_mv)}" if mq5_mv is not None else "—",
                      help="Estimated sensor output voltage in millivolts.")
            st.caption("⚠️ ADC counts and voltage are hardware readings, not gas concentration units.")

        with col_metrics:
            st.markdown("**Firmware MQ-5 Metrics**")
            if latest_risk:
                st.metric("MQ5 Change", f"{latest_risk.mq5_change:.3f}" if latest_risk.mq5_change is not None else "—",
                          help="Normalised rate of change between consecutive MQ-5 readings.")
                st.metric("Abrupt Change", "Yes" if latest_risk.mq5_abrupt else "No",
                          help="1 if firmware detected a sudden jump in MQ-5 readings.")
                st.metric("MQ5 Variability", f"{latest_risk.mq5_variability:.3f}" if latest_risk.mq5_variability is not None else "—",
                          help="Variance of recent MQ-5 readings in the firmware window.")
                st.metric("Recovery Window", f"{latest_risk.recovery}" if latest_risk.recovery is not None else "—",
                          help="Number of consecutive windows where MQ-5 has been declining.")
            else:
                st.info("No firmware MQ-5 metrics received yet.")

        with col_mlp:
            st.markdown("**MLP Classifier (Illustrative)**")
            if latest_mlp:
                st.metric("Predicted Class", latest_mlp.mlp_class)
                if latest_mlp.confidence is not None:
                    st.metric("Confidence", f"{latest_mlp.confidence:.0f}%")
                if latest_mlp.sample_id is not None:
                    st.metric("Sample ID", str(latest_mlp.sample_id))
                st.caption(
                    "ℹ️ In simulation mode, MLP outputs are illustrative, not actual "
                    "firmware inference."
                )
            elif state_manager.active_mode == "SIMULATION":
                st.info("Start a scenario to see MLP predictions.")
            else:
                st.info("Awaiting MLP_EXPERIMENTAL record from firmware.")


# ---------------------------------------------------------------------------
# 3. Explainable risk breakdown
# ---------------------------------------------------------------------------

def render_explainability_panel(incident: IncidentState) -> None:
    """Risk contribution breakdown bar chart + firmware WHY explanation."""
    st.markdown("### 🔍 Risk Contribution Breakdown")

    col_chart, col_why = st.columns([3, 2])

    with col_chart:
        contribs = incident.risk_contributions or {}
        if not contribs:
            st.info("No risk contribution data in the current record.")
        else:
            df_c = pd.DataFrame([
                {"Component": k.replace("_", " ").title(), "Score": v}
                for k, v in contribs.items()
            ])
            import plotly.express as px
            fig = px.bar(
                df_c,
                x="Score",
                y="Component",
                orientation="h",
                color="Score",
                color_continuous_scale=["#10b981", "#f59e0b", "#ef4444"],
                range_color=[0, 100],
            )
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94a3b8", size=12),
                margin=dict(l=0, r=10, t=10, b=10),
                height=200,
                xaxis=dict(showgrid=True, gridcolor="#1e293b", range=[0, 100]),
                yaxis=dict(showgrid=False, autorange="reversed"),
                coloraxis_showscale=False,
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_why:
        why = incident.why or "No explanation available."
        st.html(f"""
        <div style="background:linear-gradient(145deg,#131b2e 0%,#172036 100%);
                    border:1px solid #23314f;border-radius:10px;
                    padding:14px 16px;height:100%;">
          <div style="font-size:0.78rem;font-weight:600;text-transform:uppercase;
                      color:#94a3b8;margin-bottom:8px;letter-spacing:0.07em;">
            Firmware Explanation
          </div>
          <div style="font-size:0.93rem;color:#f8fafc;font-style:italic;
                      line-height:1.5;">
            &ldquo;{why}&rdquo;
          </div>
          <div style="margin-top:10px;font-size:0.72rem;color:#475569;">
            Risk score is reported by firmware. Components serve as attribution only.
          </div>
        </div>
        """)


# ---------------------------------------------------------------------------
# 4. Event timeline
# ---------------------------------------------------------------------------

def render_event_timeline(event_manager: EventManager) -> None:
    """Filterable, searchable event timeline with CSV export."""
    st.markdown("### 📜 Incident Event Timeline")

    f1, f2, f3, f4, f5 = st.columns([1.5, 1.5, 1.5, 2.5, 1])

    with f1:
        sev_filter = st.selectbox(
            "Severity", ["ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
            index=0, key="evt_filter_sev",
        )
    with f2:
        class_filter = st.selectbox(
            "Class",
            ["ALL", "NORMAL", "GAS_RISING", "GAS_ELEVATED", "ABRUPT_CHANGE",
             "COMBINED_EVENT", "RECOVERING", "ENV_CHANGE"],
            index=0, key="evt_filter_class",
        )
    with f3:
        source_filter = st.selectbox(
            "Source", ["ALL", "HARDWARE", "SIMULATION"],
            index=0, key="evt_filter_source",
        )
    with f4:
        search_query = st.text_input(
            "Search", placeholder="Search explanation, event ID…",
            key="evt_search_query",
        )
    with f5:
        st.write("")
        if st.button("🗑️ Clear", help="Clear event history for this session"):
            event_manager.clear_events()
            st.rerun()

    filtered = event_manager.get_filtered_events(
        severity=sev_filter,
        incident_class=class_filter,
        source=source_filter,
        search_query=search_query,
    )

    df = event_manager.to_dataframe(filtered)

    if df.empty:
        st.info("No events recorded yet for the active filters.")
    else:
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Event ID":         st.column_config.TextColumn("ID",          width="small"),
                "Timestamp":        st.column_config.TextColumn("Timestamp",   width="medium"),
                "Incident Class":   st.column_config.TextColumn("Class",       width="medium"),
                "Risk Score":       st.column_config.TextColumn("Risk",        width="small"),
                "Persist Risk":     st.column_config.TextColumn("Persist",     width="small"),
                "Severity":         st.column_config.TextColumn("Severity",    width="small"),
                "Temperature (°C)": st.column_config.TextColumn("Temp",        width="small"),
                "Humidity (% RH)":  st.column_config.TextColumn("Humidity",    width="small"),
                "MQ5 ADC":          st.column_config.TextColumn("MQ5 ADC",     width="small"),
                "Explanation":      st.column_config.TextColumn("Explanation", width="large"),
                "Source":           st.column_config.TextColumn("Source",      width="small"),
            },
        )

        csv = event_manager.export_csv(filtered)
        st.download_button(
            label="📥 Export CSV",
            data=csv,
            file_name=f"slg_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )
