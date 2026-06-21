from __future__ import annotations

import pandas as pd
import streamlit as st
from common import (
    load_alerts,
)


def page_alerts():
    """Alert monitoring and acknowledgment."""
    st.header("🔔 Alerts")

    alerts = load_alerts()
    if alerts:
        df_alerts = pd.DataFrame(alerts)
        if "acknowledged" in df_alerts.columns:
            df_alerts["acknowledged"] = df_alerts["acknowledged"].map({True: "Yes", False: "No"})
        st.dataframe(df_alerts, use_container_width=True, height=400)
    else:
        st.info("No alerts found.")
