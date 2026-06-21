from __future__ import annotations

import pandas as pd
import streamlit as st
from common import (
    load_data_sources,
)


def page_data_sources():
    """Data source management and monitoring."""  # type: ignore[annotation-unchecked]

    st.header("📡 Data Sources")

    sources = load_data_sources()
    if sources:
        st.dataframe(pd.DataFrame(sources), use_container_width=True, height=300)
    else:
        st.info("No data source history available.")
