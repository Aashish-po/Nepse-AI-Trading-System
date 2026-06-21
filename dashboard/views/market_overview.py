from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st
from common import (
    _format_currency,
    _safe_dict,
    _safe_float,
    get_daily_quality_report,
    get_trust_score,
    load_market_overview,
)


def page_market_overview():
    """Market overview with data quality metrics."""  # type: ignore[annotation-unchecked]

    st.header("📊 Market Overview")

    # Load market data
    overview = load_market_overview()
    quality_report = get_daily_quality_report()
    overview_data = _safe_dict(overview)
    quality_data = _safe_dict(quality_report)

    # Key metrics row
    if overview_data:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            nse_change = _safe_float(overview_data.get("nse_change", 0))
            st.metric(
                "NSE Index",
                overview_data.get("nse_value", "N/A"),
                delta=f"{nse_change:.2f}%",
                delta_color="inverse",
            )

        with col2:
            st.metric(
                "Tracked Symbols",
                overview_data.get("total_symbols", 0),
                delta=overview_data.get("new_symbols_today", 0),
            )

        with col3:
            vol_change = _safe_float(overview_data.get("volume_change", 0))
            st.metric(
                "Total Volume",
                _format_currency(overview_data.get("total_volume", 0)),
                delta=f"{vol_change:.1f}%",
            )

        with col4:
            st.metric(
                "Active Signals",
                overview_data.get("active_signals", 0),
                delta=overview_data.get("new_signals_today", 0),
                delta_color="off",
            )
    else:
        st.info("Market overview unavailable. Ensure backend is running.")

    st.divider()

    # Data quality report
    st.subheader("🔍 Data Quality Report")

    if quality_data:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Data Completeness",
                f"{quality_data.get('completeness_score', 0):.1%}",
                help="Percentage of expected data points received",
            )

        with col2:
            st.metric(
                "Validation Pass Rate",
                f"{quality_data.get('validation_pass_rate', 0):.1%}",
                help="Percentage of data passing validation checks",
            )

        with col3:
            st.metric(
                "Avg Trust Score",
                f"{quality_data.get('avg_trust_score', 0):.2f}/1.0",
                help="Average data trustworthiness across all symbols",
            )

        # Detailed quality breakdown
        if "quality_by_symbol" in quality_data:
            df_quality = pd.DataFrame(quality_data["quality_by_symbol"])
            if not df_quality.empty:
                st.subheader("Quality by Symbol")
                st.dataframe(df_quality, use_container_width=True, height=300)
    else:
        st.warning("Quality report unavailable.")

    st.divider()

    # Per-symbol trust score lookup
    st.subheader("🎯 Per-Symbol Trust Score")
    col1, col2 = st.columns(2)

    with col1:
        lookup_symbol = st.text_input("Symbol", value="NABIL", key="trust_symbol")

    with col2:
        lookup_date = st.text_input(
            "Date (YYYY-MM-DD)", value=dt.date.today().isoformat(), key="trust_date"
        )

    if st.button("Fetch Trust Score", key="fetch_trust"):
        trust = get_trust_score(lookup_symbol, lookup_date)
        trust_data = _safe_dict(trust)
        if trust_data:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Trust Score", f"{trust_data.get('trust_score', 0):.2f}/1.0")
            with col2:
                status = str(trust_data.get("status", "unknown")).upper()
                color = "🟢" if status == "SAFE" else "🟡" if status == "CAUTION" else "🔴"
                st.metric("Status", f"{color} {status}")
            with col3:
                st.metric("Safe?", "✅ Yes" if trust_data.get("safe") else "❌ No")

            if "components" in trust_data:
                st.caption("**Quality Components:**")
                comp_df = pd.DataFrame([trust_data["components"]])
                st.dataframe(comp_df, use_container_width=True)
        else:
            st.error(
                "Failed to fetch trust score. Check symbol/date and ensure backend is running."
            )
