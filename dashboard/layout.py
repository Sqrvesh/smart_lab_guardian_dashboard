"""
Dashboard layout styling, industrial dark theme CSS, and header components
for Smart Lab Guardian.
"""

import streamlit as st
from datetime import datetime
from typing import Dict, Any, Optional

INDUSTRIAL_DARK_CSS = """
<style>
/* Main app background & base text */
.stApp {
    background-color: #0b0f19;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}

/* Card containers */
.slg-card {
    background: linear-gradient(145deg, #131b2e 0%, #172036 100%);
    border: 1px solid #23314f;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
    /* Uniform fixed height + flex column so all three sensor cards are identical and aligned */
    height: 154px;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    overflow: hidden;
}

.slg-card-header {
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    margin-bottom: 6px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
}

.slg-card-value {
    font-size: 1.85rem;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: -0.02em;
    flex-shrink: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.slg-card-unit {
    font-size: 1.0rem;
    font-weight: 500;
    color: #64748b;
    margin-left: 4px;
}

.slg-card-footer {
    font-size: 0.75rem;
    color: #64748b;
    margin-top: auto;
    display: flex;
    justify-content: space-between;
    flex-shrink: 0;
}

/* Status hero card */
.slg-hero-card {
    background: #111827;
    border-radius: 12px;
    padding: 22px;
    margin-bottom: 20px;
    border-left: 6px solid #10b981;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
}

.slg-hero-title {
    font-size: 1.0rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #94a3b8;
    margin-bottom: 4px;
}

.slg-hero-class {
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin-bottom: 4px;
}

/* Badges */
.slg-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.slg-badge-low {
    background-color: rgba(16, 185, 129, 0.2);
    color: #10b981;
    border: 1px solid #10b981;
}

.slg-badge-medium {
    background-color: rgba(245, 158, 11, 0.2);
    color: #f59e0b;
    border: 1px solid #f59e0b;
}

.slg-badge-high {
    background-color: rgba(249, 115, 22, 0.2);
    color: #f97316;
    border: 1px solid #f97316;
}

.slg-badge-critical {
    background-color: rgba(239, 68, 68, 0.2);
    color: #ef4444;
    border: 1px solid #ef4444;
}

.slg-badge-stale {
    background-color: rgba(100, 116, 139, 0.2);
    color: #94a3b8;
    border: 1px solid #64748b;
}

/* Simulation alert banner */
.slg-sim-banner {
    background: linear-gradient(90deg, #78350f 0%, #92400e 100%);
    border: 1px solid #f59e0b;
    color: #fef3c7;
    padding: 12px 20px;
    border-radius: 8px;
    margin-bottom: 16px;
    font-weight: 600;
    font-size: 0.95rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

/* Stale data warning banner */
.slg-stale-banner {
    background: linear-gradient(90deg, #451a03 0%, #78350f 100%);
    border: 1px solid #ea580c;
    color: #ffedd5;
    padding: 10px 16px;
    border-radius: 8px;
    margin-bottom: 16px;
    font-size: 0.9rem;
    font-weight: 600;
}

/* Connection stats chip */
.slg-stat-chip {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 0.8rem;
    color: #cbd5e1;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}
</style>
"""


def apply_theme():
    """Injects custom CSS into the Streamlit app."""
    st.markdown(INDUSTRIAL_DARK_CSS, unsafe_allow_html=True)


def render_header(
    active_mode: str,
    connection_state: str,
    selected_port: Optional[str],
    baudrate: int,
    messages_count: int,
    malformed_count: int,
    connection_errors: int,
    last_msg_time: Optional[datetime],
    is_stale: bool = False,
):
    """Renders the top branding header, mode badge, and connection telemetry bar."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    col_title, col_telemetry = st.columns([3, 2])

    with col_title:
        st.markdown(
            """
            <div style="display: flex; align-items: baseline; gap: 12px;">
                <h2 style="margin: 0; padding: 0; font-weight: 800; color: #f8fafc; letter-spacing: -0.02em;">
                    🛡️ SMART LAB GUARDIAN
                </h2>
            </div>
            <div style="font-size: 0.82rem; color: #94a3b8; margin-top: 4px; margin-bottom: 6px;">
                Context-Aware Multi-Sensor Incident Detection &amp; Explainable Risk Prioritization System
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_telemetry:
        mode_color = "#3b82f6" if active_mode == "LIVE HARDWARE" else "#f59e0b"
        mode_bg = "rgba(59, 130, 246, 0.15)" if active_mode == "LIVE HARDWARE" else "rgba(245, 158, 11, 0.15)"
        
        # State color
        state_colors = {
            "CONNECTED": ("#10b981", "rgba(16, 185, 129, 0.15)"),
            "CONNECTING": ("#f59e0b", "rgba(245, 158, 11, 0.15)"),
            "DISCONNECTED": ("#94a3b8", "rgba(148, 163, 184, 0.15)"),
            "ERROR": ("#ef4444", "rgba(239, 68, 68, 0.15)"),
        }
        st_color, st_bg = state_colors.get(connection_state, ("#94a3b8", "rgba(148, 163, 184, 0.15)"))

        st.markdown(
            f"""
            <div style="display: flex; justify-content: flex-end; align-items: center; gap: 10px; flex-wrap: wrap;">
                <span class="slg-badge" style="background: {mode_bg}; color: {mode_color}; border: 1px solid {mode_color};">
                    MODE: {active_mode}
                </span>
                <span class="slg-badge" style="background: {st_bg}; color: {st_color}; border: 1px solid {st_color};">
                    SERIAL: {connection_state}
                </span>
                <span style="font-size: 0.8rem; font-family: monospace; color: #64748b;">
                    🕒 {now_str}
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Padding after the title, description, and header controls
    st.markdown('<div style="margin-bottom: 22px;"></div>', unsafe_allow_html=True)


    # Stale hardware data alert (only in live mode)
    if is_stale and active_mode == "LIVE HARDWARE":
        st.markdown(
            """
            <div class="slg-stale-banner">
                ⚠️ <strong>WARNING: HARDWARE TELEMETRY IS STALE</strong> — No valid sensor packets received within timeout. Displayed readings reflect last known cached values and must not be treated as live measurements.
            </div>
            """,
            unsafe_allow_html=True,
        )

