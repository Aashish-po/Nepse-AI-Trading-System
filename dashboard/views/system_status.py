from __future__ import annotations

import streamlit as st
from common import (
    load_health_status,
)


def page_system_status():
    """System status and health monitoring."""  # type: ignore[annotation-unchecked]

    st.header("🖥️ System Status")

    health = load_health_status()
    if health:
        st.json(health)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Status", str(health.get("status", "unknown")).upper())
        with col2:
            st.metric("Environment", health.get("environment", "unknown"))
    else:
        st.error("System unavailable.")
