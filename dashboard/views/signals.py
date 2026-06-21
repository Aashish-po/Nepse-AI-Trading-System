from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import (
    load_signals,
)


def page_signals():
    """Signal visualization and management."""  # type: ignore[annotation-unchecked]

    st.header("📈 Signals")

    signals_date = st.text_input(
        "Signals Date (YYYY-MM-DD)", value=dt.date.today().isoformat(), key="signals_date"
    )

    if st.button("Load Signals", key="load_signals"):
        signals = load_signals(signals_date)
        if signals:
            df_signals = pd.DataFrame(signals)
            st.dataframe(df_signals, use_container_width=True, height=400)

            # Signal distribution chart
            if "signal_type" in df_signals.columns:
                signal_counts = df_signals.groupby("signal_type").size()
                fig = go.Figure(data=[go.Bar(x=signal_counts.index, y=signal_counts.values)])
                fig.update_layout(
                    title="Signal Distribution", xaxis_title="Signal Type", yaxis_title="Count"
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No signals found for this date.")
