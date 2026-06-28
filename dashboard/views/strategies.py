from __future__ import annotations

import pandas as pd
import streamlit as st
from common import (
    _safe_int,
    _strategy_label,
    _valid_strategies,
    load_strategies,
    render_table,
)


def page_strategies():
    """Strategies overview and management."""  # type: ignore[annotation-unchecked]

    st.header("🎯 Trading Strategies")

    strategies = _valid_strategies(load_strategies())

    if not strategies:
        st.warning("No strategies found. Create one via the API first.")
        return

    strategy_ids = [_safe_int(strategy.get("id"), -1) for strategy in strategies]

    # Strategy selector
    selected_id = st.selectbox(
        "Select Strategy",
        options=strategy_ids,
        format_func=lambda x: next(
            (_strategy_label(s) for s in strategies if _safe_int(s.get("id"), -1) == x),
            "Unknown",
        ),
        key="strategy_selector",
    )

    # Display selected strategy details
    strategy = next((s for s in strategies if _safe_int(s.get("id"), -1) == selected_id), None)
    if strategy:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Strategy ID", strategy.get("id"))
        with col2:
            st.metric("Version", f"v{strategy.get('version', '0.0.0')}")
        with col3:
            st.metric("Created", strategy.get("created_at", "N/A"))
        with col4:
            st.metric("Status", strategy.get("status", "active").upper())

        st.divider()

        # Strategy configuration
        st.subheader("⚙️ Configuration")
        if "config" in strategy:
            st.json(strategy["config"])

        # Backtests history
        st.subheader("📈 Recent Backtests")
        render_table(
            pd.DataFrame(strategy.get("recent_backtests", [])),
            key="strat_backtests",
            name=f"backtests_{strategy.get('id')}",
            empty_msg="No backtests recorded yet.",
        )

        # Parameters
        st.subheader("📊 Strategy Parameters")
        if "parameters" in strategy:
            st.json(strategy["parameters"])
