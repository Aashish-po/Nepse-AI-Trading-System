from __future__ import annotations

import datetime as dt

import streamlit as st
from common import (
    load_features,
)


def page_features():
    """Feature generation and analysis."""  # type: ignore[annotation-unchecked]

    st.header("🔧 Features")

    symbol = st.text_input("Symbol", value="NABIL", key="features_symbol")
    date_str = st.text_input(
        "Date (YYYY-MM-DD)", value=dt.date.today().isoformat(), key="features_date"
    )

    if st.button("Generate Features", key="gen_features"):
        with st.spinner("Generating features..."):
            features = load_features(symbol, date_str)
            if features:
                st.json(features)
            else:
                st.warning(
                    "No feature data available. Feature generation endpoint not implemented."
                )
