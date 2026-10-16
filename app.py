"""
Smart Lab Guardian: Main Streamlit Application Entrypoint.
Real-Time Context-Aware Multi-Sensor Incident Detection and Explainable Risk Dashboard.
"""

import time
import os
import sys
from datetime import datetime

# Add project root to sys.path so modules import reliably
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import streamlit as st

from smart_lab_guardian_dashboard.communication.serial_manager import (
    SerialManager,
    SerialConnectionState,
)
from smart_lab_guardian_dashboard.core.state_manager import StateManager
from smart_lab_guardian_dashboard.core.sensor_registry import SensorRegistry
from smart_lab_guardian_dashboard.core.event_manager import EventManager
from smart_lab_guardian_dashboard.core.freshness import FreshnessTracker
from smart_lab_guardian_dashboard.simulation.scenario_engine import ScenarioEngine, EngineState
from smart_lab_guardian_dashboard.dashboard.layout import apply_theme, render_header
from smart_lab_guardian_dashboard.dashboard.status import render_status_panel
from smart_lab_guardian_dashboard.dashboard.components import (
    render_all_sensor_cards,
    render_tinyml_panel,
    render_explainability_panel,
    render_event_timeline,
)
from smart_lab_guardian_dashboard.dashboard.charts import render_realtime_charts


# ---------------------------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Smart Lab Guardian Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply custom dark theme
apply_theme()


# ---------------------------------------------------------------------------
# Session State Initialization (Thread-safe singletons per browser session)
# ---------------------------------------------------------------------------
if "state_manager" not in st.session_state:
    registry = SensorRegistry()
    events = EventManager()
    freshness = FreshnessTracker(default_timeout_seconds=4.0)
    st.session_state.state_manager = StateManager(
        sensor_registry=registry,
        event_manager=events,
        freshness_tracker=freshness,
    )

if "serial_manager" not in st.session_state:
    st.session_state.serial_manager = SerialManager(baudrate=115200)

if "scenario_engine" not in st.session_state:
    st.session_state.scenario_engine = ScenarioEngine(st.session_state.state_manager)

if "selected_port" not in st.session_state:
    st.session_state.selected_port = None

if "active_mode" not in st.session_state:
    st.session_state.active_mode = "SIMULATION"  # default to SIMULATION for safe immediate exploration

if "auto_refresh_enabled" not in st.session_state:
    st.session_state.auto_refresh_enabled = True

if "sim_auto_play" not in st.session_state:
    st.session_state.sim_auto_play = False

if "sim_speed" not in st.session_state:
    st.session_state.sim_speed = 1.0


state_mgr: StateManager = st.session_state.state_manager
serial_mgr: SerialManager = st.session_state.serial_manager
scenario_eng: ScenarioEngine = st.session_state.scenario_engine


# ---------------------------------------------------------------------------
# Sidebar Controls & Configuration
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div style="padding-bottom: 12px; border-bottom: 1px solid #1e293b; margin-bottom: 14px;">
            <h3 style="margin: 0; color: #f8fafc; font-weight: 700;">⚙️ System Control</h3>
            <span style="font-size: 0.78rem; color: #94a3b8;">Smart Lab Guardian Telemetry Interface</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. Mode Selection
    mode_selection = st.radio(
        "Communication Mode",
        ["SIMULATION", "LIVE HARDWARE"],
        index=0 if st.session_state.active_mode == "SIMULATION" else 1,
        help="Switch between synthetic simulation test suite and physical STM32 USB serial UART",
    )

    if mode_selection != st.session_state.active_mode:
        st.session_state.active_mode = mode_selection
        state_mgr.set_mode(mode_selection)
        st.rerun()

    # -----------------------------------------------------------------------
    # LIVE HARDWARE CONTROLS
    # -----------------------------------------------------------------------
    if st.session_state.active_mode == "LIVE HARDWARE":
        st.markdown("#### 🔌 USB Serial Connection")

        # Discover ports
        available_ports = serial_mgr.list_available_ports()
        port_options = [p["port"] for p in available_ports]

        col_p_sel, col_p_ref = st.columns([3, 1])
        with col_p_sel:
            # If COM7 was previously detected or available in list, select it by default
            default_idx = 0
            if "COM7" in port_options:
                default_idx = port_options.index("COM7")

            selected_p = st.selectbox(
                "Serial Port",
                port_options if port_options else ["No Ports Found"],
                index=default_idx if port_options else 0,
                disabled=serial_mgr.is_connected(),
            )
        with col_p_ref:
            st.write("")  # vertical align
            if st.button("🔄", help="Scan for USB Virtual COM Ports"):
                st.rerun()

        # Port description hint
        if available_ports and selected_p in port_options:
            port_desc = next((p["description"] for p in available_ports if p["port"] == selected_p), "")
            st.caption(f"Hardware: `{port_desc}`")

        baud_choice = st.selectbox(
            "Baud Rate",
            [9600, 19200, 38400, 57600, 115200, 230400],
            index=4,  # default 115200
            disabled=serial_mgr.is_connected(),
        )

        # Connection Buttons
        col_c_btn, col_d_btn = st.columns(2)
        with col_c_btn:
            if not serial_mgr.is_connected():
                if st.button("⚡ Connect", type="primary", use_container_width=True):
                    if selected_p and selected_p != "No Ports Found":
                        success, err = serial_mgr.connect(selected_p, baud_choice)
                        if success:
                            st.session_state.selected_port = selected_p
                            st.toast(f"Connected to {selected_p} @ {baud_choice} baud", icon="✅")
                        else:
                            st.error(f"Connection Failed: {err}")
                        st.rerun()
                    else:
                        st.warning("No COM port selected.")
            else:
                st.button("⚡ Connected", disabled=True, use_container_width=True)

        with col_d_btn:
            if serial_mgr.is_connected():
                if st.button("Disconnect", use_container_width=True):
                    serial_mgr.disconnect()
                    st.toast("Serial connection closed", icon="🔌")
                    st.rerun()
            else:
                st.button("Disconnected", disabled=True, use_container_width=True)

        if serial_mgr.error_message:
            st.error(f"Serial Error: {serial_mgr.error_message}")

        st.info(
            "💡 **Note:** Ensure **PuTTY**, TeraTerm, or Arduino Serial Monitor are **closed** before connecting, or Windows will block access to the COM port."
        )

    # -----------------------------------------------------------------------
    # SIMULATION CONTROLS
    # -----------------------------------------------------------------------
    else:
        st.markdown("#### 🧪 Scenario Simulator Console")

        scenarios_dict = scenario_eng.scenarios
        scenario_options = {s_id: f"{s_id}. {s.name.split(': ')[1] if ':' in s.name else s.name}" for s_id, s in scenarios_dict.items()}

        chosen_scen_id = st.selectbox(
            "Select Test Scenario",
            list(scenario_options.keys()),
            format_func=lambda x: scenario_options[x],
            index=scenario_eng.current_scenario_id - 1,
        )

        if chosen_scen_id != scenario_eng.current_scenario_id:
            scenario_eng.select_scenario(chosen_scen_id)
            st.rerun()

        curr_scen = scenario_eng.get_current_scenario()
        st.caption(f"**Description:** {curr_scen.description}")

        # Simulator Transport Controls
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            if scenario_eng.engine_state != EngineState.RUNNING:
                if st.button("▶️ Play", use_container_width=True):
                    scenario_eng.start()
                    st.session_state.sim_auto_play = True
                    st.rerun()
            else:
                if st.button("⏸️ Pause", use_container_width=True):
                    scenario_eng.pause()
                    st.session_state.sim_auto_play = False
                    st.rerun()

        with col_s2:
            if st.button("⏭️ Step", use_container_width=True):
                scenario_eng.step()
                st.rerun()

        with col_s3:
            if st.button("🔄 Reset", use_container_width=True):
                scenario_eng.reset()
                st.session_state.sim_auto_play = False
                st.rerun()

        # Quick batch test button
        if st.button("⚡ Run Full Scenario Test", use_container_width=True, help="Executes all steps synchronously and displays assertion results"):
            res = scenario_eng.run_all_deterministic()
            if res["all_passed"]:
                st.success("All expected scenario outcomes PASSED! ✅")
            else:
                st.error("Some scenario assertions did not pass.")
            st.rerun()

        # Step Progress Bar
        total_st = curr_scen.total_steps
        curr_st = scenario_eng.current_step
        progress_val = min(1.0, max(0.0, curr_st / max(1, total_st)))
        st.progress(progress_val, text=f"Progress: Step {curr_st} / {total_st}")

        # Expected Outcomes Checklist
        st.markdown("**Expected Outcomes:**")
        eval_res = scenario_eng.evaluate_outcomes()
        for check in eval_res["checks"]:
            mark = "✅" if check["passed"] else "⏳"
            st.markdown(f"<span style='font-size:0.8rem;'>{mark} {check['description']}</span>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # REFRESH & SETTINGS
    # -----------------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### ⚡ Display & Polling")
    auto_refresh = st.checkbox(
        "Auto-Refresh Dashboard (1.0s)",
        value=st.session_state.auto_refresh_enabled,
        help="Automatically updates live telemetry without manual browser refresh",
    )
    st.session_state.auto_refresh_enabled = auto_refresh

    if st.button("🔄 Force Manual Refresh", use_container_width=True):
        st.rerun()


# ---------------------------------------------------------------------------
# Telemetry Ingestion Loop
# ---------------------------------------------------------------------------
# 1. Drain serial hardware queue if connected
if st.session_state.active_mode == "LIVE HARDWARE" and serial_mgr.is_connected():
    new_messages = serial_mgr.get_messages(max_messages=100)
    for msg in new_messages:
        state_mgr.process_message(msg)

# 2. Advance simulation tick if running in auto-play mode
elif st.session_state.active_mode == "SIMULATION" and st.session_state.sim_auto_play:
    if scenario_eng.engine_state == EngineState.RUNNING:
        has_more = scenario_eng.step()
        if not has_more:
            st.session_state.sim_auto_play = False

# 3. Refresh freshness status on all sensors
state_mgr.refresh_freshness()


# ---------------------------------------------------------------------------
# Main Dashboard Layout Rendering
# ---------------------------------------------------------------------------
serial_stats = serial_mgr.get_stats()
is_hw_stale = state_mgr.is_hardware_data_stale()

# 1. Header Bar
render_header(
    active_mode=st.session_state.active_mode,
    connection_state=serial_stats["state"],
    selected_port=serial_stats["port"],
    baudrate=serial_stats["baudrate"],
    messages_count=state_mgr.total_messages_processed,
    malformed_count=state_mgr.malformed_messages_count,
    connection_errors=serial_stats["connection_errors"],
    last_msg_time=state_mgr.last_any_message_timestamp,
    is_stale=is_hw_stale,
)

# 2. Hero Laboratory Status Panel
render_status_panel(
    incident=state_mgr.incident_state,
    is_stale=is_hw_stale if st.session_state.active_mode == "LIVE HARDWARE" else False,
    is_connected=serial_mgr.is_connected() if st.session_state.active_mode == "LIVE HARDWARE" else True,
)

# 3. Live Generic Sensor Cards
render_all_sensor_cards(
    sensor_registry=state_mgr.sensor_registry,
    sensor_states=state_mgr.sensor_states,
    freshness_tracker=state_mgr.freshness_tracker,
)

# 4. Interactive Plotly Real-Time Charts
render_realtime_charts(
    state_manager=state_mgr,
    sensor_registry=state_mgr.sensor_registry,
)

# 5. TinyML Embedded Inference Panel
render_tinyml_panel(
    incident=state_mgr.incident_state,
    latest_features=state_mgr.latest_features,
    features_timestamp=state_mgr.features_timestamp,
    is_stale=is_hw_stale if st.session_state.active_mode == "LIVE HARDWARE" else False,
)

# 6. Explainable Risk Assessment Breakdown
render_explainability_panel(
    incident=state_mgr.incident_state,
)

# 7. Incident & Event Timeline
render_event_timeline(
    event_manager=state_mgr.event_manager,
)

# 8. Diagnostic & Raw Protocol Log (Collapsible)
with st.expander("🛠️ Raw Protocol & Diagnostic Stream Inspector", expanded=False):
    st.markdown(
        """
        <div style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 8px;">
            Inspect recent raw lines emitted by firmware over UART. Diagnostic startup banners and self-test lines are quarantined from sensor history here.
        </div>
        """,
        unsafe_allow_html=True,
    )
    raw_logs = list(reversed(state_mgr.raw_message_log))[:25]
    if not raw_logs:
        st.write("No raw lines received yet.")
    else:
        for entry in raw_logs:
            ts = entry["timestamp"].strftime("%H:%M:%S.%f")[:-3]
            m_type = entry["type"]
            raw_text = entry["raw"]
            valid = entry["valid"]
            badge_col = "#10b981" if valid else "#ef4444"
            st.markdown(
                f"<div style='font-family: monospace; font-size: 0.78rem; padding: 2px 0;'><span style='color: #64748b;'>[{ts}]</span> <strong style='color: {badge_col};'>[{m_type}]</strong> {raw_text}</div>",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Auto-Refresh Loop Trigger
# ---------------------------------------------------------------------------
# If auto-refresh is active and either hardware serial is connected or simulation auto-play is running
if st.session_state.auto_refresh_enabled:
    if (st.session_state.active_mode == "LIVE HARDWARE" and serial_mgr.is_connected()) or \
       (st.session_state.active_mode == "SIMULATION" and st.session_state.sim_auto_play):
        time.sleep(1.0 / max(0.2, st.session_state.sim_speed))
        st.rerun()
