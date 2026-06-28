from __future__ import annotations

import pandas as pd
import streamlit as st
from common import (
    load_data_sources,
    render_table,
)


def page_data_sources():
    """Data source management and monitoring."""  # type: ignore[annotation-unchecked]

    st.header("📡 Data Sources")

    sources = load_data_sources()
    render_table(
        pd.DataFrame(sources),
        key="data_sources",
        name="data_sources",
        height=300,
        empty_msg="No data source history available.",
    )
