"""
UI Components for Smart Lab Guardian:
- Sensor overview cards: Temperature, Humidity, and a unified Gas Response card.
- Collapsible Technical Details panel (raw MQ-5 ADC / mV, firmware dynamics, MLP).
- Explainable risk contribution breakdown chart.
- Filterable incident event timeline with clean evaluation labels and CSV export.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any

try:
    from smart_lab_guardian_dashboard.core.sensor_registry import SensorDefinition, SensorRegistry
    from smart_lab_guardian_dashboard.core.state_manager import LiveSensorState, IncidentState, StateManager
    from smart_lab_guardian_dashboard.core.freshness import FreshnessStatus, FreshnessTracker
    from smart_lab_guardian_dashboard.core.event_manager import EventManager, IncidentEvent
    from smart_lab_guardian_dashboard.core.gas_response import GriTracker, compute_gri, gri_label, gri_color
    from smart_lab_guardian_dashboard.core.evaluation_labels import format_evaluation_label
except ImportError:
    from core.sensor_registry import SensorDefinition, SensorRegistry
    from core.state_manager import LiveSensorState, IncidentState, StateManager
    from core.freshness import FreshnessStatus, FreshnessTracker
    from core.event_manager import EventManager, IncidentEvent
    from core.gas_response import GriTracker, compute_gri, gri_label, gri_color
    from core.evaluation_labels import format_evaluation_label


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
# 1. Unified Gas Response Card
# ---------------------------------------------------------------------------

def render_gas_response_card(
    gas_state: LiveSensorState,
    freshness_tracker: FreshnessTracker,
    gri_tracker: Optional[GriTracker] = None,
) -> None:
    """
    Renders the unified Gas Response card in the primary sensor overview.
    Replaces separate raw ADC and voltage cards with a single human-readable
    metric showing:
    - Gas Response Index (0–100) or Calibrating status.
    - Concise status badge: Low, Elevated, High, or Calibrating.
    - Trend indicator: Rising, Stable, Falling, or Calibrating.
    - Never labeled as ppm, %LEL, or an actual gas concentration.
    """
    mq5_val = gas_state.current_value
    mq5_adc: Optional[int] = int(mq5_val) if isinstance(mq5_val, (int, float)) else None

    # Compute GRI using GriTracker if provided, else standalone formula
    if gri_tracker is not None:
        gri_val, is_calibrated = gri_tracker.compute(mq5_adc)
    elif mq5_adc is not None:
        gri_val = compute_gri(mq5_adc)
        is_calibrated = True
    else:
        gri_val = None
        is_calibrated = False

    # Trend symbol
    trend_raw = gas_state.trend or "STEADY"
    trend_map = {
        "RISING": "↗ Rising",
        "FALLING": "↘ Falling",
        "STEADY": "→ Stable",
    }
    trend_display = trend_map.get(trend_raw, "→ Stable")

    # Freshness
    age = freshness_tracker.get_age_seconds(gas_state.last_updated)
    fresh_badge, fresh_color = freshness_tracker.get_status_badge(gas_state.status, age)

    if not is_calibrated or gri_val is None:
        if gas_state.status in (FreshnessStatus.NO_DATA, FreshnessStatus.NOT_CONFIGURED):
            display_val = "No Data"
            badge_text = "OFFLINE"
            badge_color = "#64748b"
            sub_note = "Awaiting sensor telemetry"
            trend_display = "—"
        else:
            display_val = "Calibrating…"
            badge_text = "CALIBRATING"
            badge_color = "#64748b"
            sub_note = "Establishing clean-air baseline"
            trend_display = "Evaluating"
        accent_color = "#64748b"
    else:
        display_val = f"{gri_val:.0f} / 100"
        lbl = gri_label(gri_val)
        badge_text = lbl.upper()
        badge_color = gri_color(gri_val)
        accent_color = badge_color
        sub_note = f"Status: {lbl} Response (0–100 scale)"

    st.markdown(
        f"""
        <div class="slg-card" style="border-top: 3px solid {accent_color};">
            <div class="slg-card-header">
                <span>🔬 Gas Response</span>
                <span class="slg-badge" style="background: rgba(0,0,0,0.3); color: {badge_color}; border: 1px solid {badge_color}; font-size: 0.7rem;">
                    {badge_text}
                </span>
            </div>
            <div class="slg-card-value">
                {display_val}
            </div>
            <div style="font-size: 0.78rem; color: #94a3b8; margin-top: 6px;">
                {sub_note}
            </div>
            <div class="slg-card-footer">
                <span>Trend: <strong style="color: #cbd5e1;">{trend_display}</strong></span>
                <span style="color: {fresh_color}; font-size: 0.72rem;">{fresh_badge}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 2. Generic and Overview Sensor Cards
# ---------------------------------------------------------------------------

def render_sensor_card(
    sensor_def: SensorDefinition,
    sensor_state: LiveSensorState,
    freshness_tracker: FreshnessTracker,
    gri_tracker: Optional[GriTracker] = None,
) -> None:
    """
    Renders an individual sensor card.
    If the sensor is gas-related, renders the unified Gas Response card.
    Otherwise renders standard environmental card (Temperature, Humidity).
    """
    if sensor_def.sensor_type == "gas" or sensor_def.sensor_id in ("gas_mq5", "gas_mq5_mv"):
        render_gas_response_card(sensor_state, freshness_tracker, gri_tracker)
        return

    card_title = sensor_def.display_name
    unit = sensor_def.unit
    val = sensor_state.current_value
    status = sensor_state.status

    # Trend symbol
    trend_icons = {
        "RISING": "↗ Rising",
        "FALLING": "↘ Falling",
        "STEADY": "→ Stable",
    }
    trend_display = trend_icons.get(sensor_state.trend, "→ Stable")

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

    formatted_val = sensor_def.format_value(val)

    sub_note = ""
    if sensor_def.warning_thresholds:
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
    gri_tracker: Optional[GriTracker] = None,
) -> None:
    """
    Renders the primary sensor overview with exactly 3 headline cards:
    1. Ambient Temperature (°C)
    2. Relative Humidity (% RH)
    3. Unified Gas Response (0–100 index, Low/Elevated/High, Trend)

    Separate ADC counts and millivolts are excluded from headline metrics
    and available inside the collapsible Technical Details section.
    """
    col_temp, col_hum, col_gas = st.columns(3)

    # 1. Temperature
    with col_temp:
        temp_def = sensor_registry.get_sensor("temp_ambient")
        temp_state = sensor_states.get(
            "temp_ambient",
            LiveSensorState(sensor_id="temp_ambient", status=FreshnessStatus.NO_DATA),
        )
        if temp_def:
            render_sensor_card(temp_def, temp_state, freshness_tracker, gri_tracker)

    # 2. Humidity
    with col_hum:
        hum_def = sensor_registry.get_sensor("humidity_rel")
        hum_state = sensor_states.get(
            "humidity_rel",
            LiveSensorState(sensor_id="humidity_rel", status=FreshnessStatus.NO_DATA),
        )
        if hum_def:
            render_sensor_card(hum_def, hum_state, freshness_tracker, gri_tracker)

    # 3. Gas Response
    with col_gas:
        gas_state = sensor_states.get(
            "gas_mq5",
            LiveSensorState(sensor_id="gas_mq5", status=FreshnessStatus.NO_DATA),
        )
        render_gas_response_card(gas_state, freshness_tracker, gri_tracker)


# ---------------------------------------------------------------------------
# 3. TinyML Embedded Inference Panel
# ---------------------------------------------------------------------------

def render_tinyml_panel(
    incident: IncidentState,
    latest_features: Optional[Dict[str, float]] = None,
    features_timestamp: Optional[datetime] = None,
    is_stale: bool = False,
) -> None:
    """
    Renders TinyML Embedded Prediction Panel & Firmware Telemetry.
    Uses clean human-readable evaluation labels (e.g., 'Normal').
    """
    st.markdown("### 🧠 TinyML Embedded Prediction & Telemetry")

    col_pred, col_details = st.columns([1, 2])

    with col_pred:
        mlp_class_clean = format_evaluation_label(incident.incident_class)
        conf_str = (
            f"{incident.mlp_confidence:.0f}%"
            if getattr(incident, "mlp_confidence", None) is not None
            else "N/A"
        )
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
                    {mlp_class_clean}
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
                Firmware Telemetry &amp; MQ-5 Dynamics
            </div>
            """,
            unsafe_allow_html=True,
        )
        f1, f2, f3 = st.columns(3)
        with f1:
            st.metric(
                "MQ-5 Change",
                f"{incident.mq5_change:.3f}" if getattr(incident, "mq5_change", None) is not None else "—",
                help="Normalized rate of change between consecutive MQ-5 readings",
            )
            st.metric(
                "Persistent Risk",
                f"{incident.persist_risk:.0f}" if getattr(incident, "persist_risk", None) is not None else "—",
                help="Persistent risk score incorporating multi-window trend",
            )
        with f2:
            st.metric(
                "Abrupt Change",
                "Yes" if getattr(incident, "mq5_abrupt", None) else "No",
                help="Flagged when a sudden deviation is detected in sensor window",
            )
            rec = getattr(incident, "recovery", None)
            st.metric(
                "Recovery Window",
                f"{rec}" if rec is not None else "—",
                help="Number of consecutive recovery windows observed",
            )
        with f3:
            st.metric(
                "MQ-5 Variability",
                f"{incident.mq5_variability:.3f}" if getattr(incident, "mq5_variability", None) is not None else "—",
                help="Variance of recent MQ-5 readings within the active window",
            )
            st.metric("Severity", incident.severity)


# ---------------------------------------------------------------------------
# 4. Collapsible Technical Details Panel (Raw ADC, mV, Model Diagnostics)
# ---------------------------------------------------------------------------

def render_mq5_panel(state_manager: StateManager) -> None:
    """
    Renders raw MQ-5 readings (ADC and mV) and firmware diagnostic metrics
    inside a collapsible section. Keeps raw values accessible without
    cluttering headline overview cards.
    """
    latest_risk = getattr(state_manager, "latest_risk", None)
    latest_mlp = getattr(state_manager, "latest_mlp", None)
    gas_state = state_manager.sensor_states.get("gas_mq5")
    gas_mv_state = state_manager.sensor_states.get("gas_mq5_mv")

    mq5_adc = gas_state.current_value if gas_state and gas_state.current_value is not None else None
    mq5_mv = gas_mv_state.current_value if gas_mv_state and gas_mv_state.current_value is not None else None

    with st.expander("🔬 Technical Details & Raw Sensor Diagnostics", expanded=False):
        col_raw, col_metrics, col_mlp = st.columns(3)

        with col_raw:
            st.markdown("**Raw Gas Sensor Readings**")
            st.metric(
                "ADC Count",
                f"{int(mq5_adc)}" if mq5_adc is not None else "—",
                help="Raw 12-bit ADC value (0–4095). Hardware reading for calibration & diagnostics.",
            )
            st.metric(
                "Voltage (mV)",
                f"{int(mq5_mv)}" if mq5_mv is not None else "—",
                help="Estimated analog sensor output voltage in millivolts.",
            )
            st.caption("⚠️ Raw ADC and voltage are uncalibrated hardware readings for diagnostics; NOT ppm.")

        with col_metrics:
            st.markdown("**Firmware Risk Metrics**")
            if latest_risk:
                st.metric(
                    "MQ5 Change",
                    f"{latest_risk.mq5_change:.3f}" if latest_risk.mq5_change is not None else "—",
                )
                st.metric(
                    "Abrupt Deviation",
                    "Yes" if latest_risk.mq5_abrupt else "No",
                )
                st.metric(
                    "Variability",
                    f"{latest_risk.mq5_variability:.3f}" if latest_risk.mq5_variability is not None else "—",
                )
                st.metric(
                    "Recovery Stage",
                    f"{latest_risk.recovery}" if latest_risk.recovery is not None else "—",
                )
            else:
                st.info("Awaiting firmware risk metrics.")

        with col_mlp:
            st.markdown("**Model Output**")
            pred_class = (
                format_evaluation_label(latest_mlp.mlp_class)
                if latest_mlp
                else format_evaluation_label(state_manager.incident_state.incident_class)
            )
            st.metric("Evaluation Label", pred_class)
            if latest_mlp and latest_mlp.confidence is not None:
                st.metric("Confidence", f"{latest_mlp.confidence:.0f}%")
            if latest_mlp and latest_mlp.sample_id is not None:
                st.metric("Sample ID", str(latest_mlp.sample_id))
            st.caption("Firmware evaluates scenario classification on embedded MLP pipeline.")


# ---------------------------------------------------------------------------
# 5. Explainable Risk Breakdown
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
# 6. Event Timeline Table
# ---------------------------------------------------------------------------

def render_event_timeline(event_manager: EventManager) -> None:
    """Filterable, searchable event timeline with CSV export."""
    st.markdown("### 📜 Incident Event Timeline")

    f1, f2, f3, f4, f5 = st.columns([1.5, 2.0, 1.5, 2.5, 1])

    with f1:
        sev_filter = st.selectbox(
            "Severity",
            ["ALL", "LOW", "MEDIUM", "HIGH", "CRITICAL"],
            index=0,
            key="evt_filter_sev",
        )
    with f2:
        class_filter = st.selectbox(
            "Class",
            [
                "ALL",
                "Normal",
                "Sustained Gas Sensor Rise",
                "Abrupt Gas Sensor Change",
                "Combined Environmental Change",
                "Recovering",
            ],
            index=0,
            key="evt_filter_class",
        )
    with f3:
        source_filter = st.selectbox(
            "Source",
            ["ALL", "HARDWARE", "SIMULATION"],
            index=0,
            key="evt_filter_source",
        )
    with f4:
        search_query = st.text_input(
            "Search",
            placeholder="Search explanation, event ID…",
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
                "Gas Response":     st.column_config.TextColumn("Gas Response", width="small"),
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
