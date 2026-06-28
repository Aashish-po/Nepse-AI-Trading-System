from __future__ import annotations

import pandas as pd
import requests  # type: ignore[import-untyped]
import streamlit as st
from common import (
    API_BASE,
    _format_percentage,
    _safe_list,
    render_table,
)


def page_analytics():
    """Market overview, signal explorer, and portfolio analytics."""  # type: ignore[annotation-unchecked]

    st.header("📉 Analytics")

    tab_market, tab_signals, tab_portfolio, tab_alerts = st.tabs(
        ["Market Overview", "Signal Explorer", "Portfolio Analytics", "Alert Rules"]
    )

    with tab_market:
        top_n = st.slider("Top movers", min_value=3, max_value=20, value=5)
        try:
            res = requests.get(f"{API_BASE}/analytics/market-overview?top_n={top_n}", timeout=10)
            if res.status_code == 200:
                data = res.json()
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Stocks", data.get("total_stocks", 0))
                c2.metric("Active Stocks", data.get("active_stocks", 0))
                c3.metric("Latest Date", data.get("latest_date") or "—")
                col_g, col_l = st.columns(2)
                with col_g:
                    st.subheader("Top Gainers")
                    gainers = _safe_list(data.get("top_gainers"))
                    st.dataframe(
                        pd.DataFrame(gainers), use_container_width=True
                    ) if gainers else st.info("No data.")
                with col_l:
                    st.subheader("Top Losers")
                    losers = _safe_list(data.get("top_losers"))
                    st.dataframe(
                        pd.DataFrame(losers), use_container_width=True
                    ) if losers else st.info("No data.")
            else:
                st.warning("Market overview unavailable.")
        except requests.RequestException as exc:
            st.error(f"Backend error: {exc}")

    with tab_signals:
        col1, col2, col3 = st.columns(3)
        symbol = col1.text_input("Symbol filter", value="", key="an_sym")
        signal_type = col2.text_input("Signal type", value="", key="an_type")
        min_conf = col3.slider("Min confidence", 0.0, 1.0, 0.0, key="an_conf")
        params: dict[str, str | float] = {"min_confidence": min_conf}
        if symbol:
            params["symbol"] = symbol
        if signal_type:
            params["signal_type"] = signal_type
        try:
            res = requests.get(f"{API_BASE}/analytics/signals", params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                st.json(data.get("summary", {}))
                render_table(
                    pd.DataFrame(_safe_list(data.get("signals"))),
                    key="an_signals",
                    name="analytics_signals",
                    height=350,
                    empty_msg="No signals match the filters.",
                )
            else:
                st.warning("Signal explorer unavailable.")
        except requests.RequestException as exc:
            st.error(f"Backend error: {exc}")

    with tab_portfolio:
        st.caption("Enter a comma-separated equity curve to compute analytics.")
        raw = st.text_area("Equity curve", value="100, 102, 101, 105, 108")
        if st.button("Compute Analytics"):
            try:
                curve = [float(x.strip()) for x in raw.split(",") if x.strip()]
                res = requests.post(
                    f"{API_BASE}/analytics/portfolio", json={"equity_curve": curve}, timeout=10
                )
                if res.status_code == 200:
                    data = res.json()
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total Return", _format_percentage(data["total_return"] * 100))
                    c2.metric("Volatility", _format_percentage(data["volatility"] * 100))
                    c3.metric("Sharpe", f"{data['sharpe_ratio']:.2f}")
                    c4.metric("Max Drawdown", _format_percentage(data["max_drawdown"] * 100))
                else:
                    st.warning("Portfolio analytics unavailable.")
            except (ValueError, requests.RequestException) as exc:
                st.error(f"Error: {exc}")

    with tab_alerts:
        st.caption("Evaluate alert rules against current data.")
        symbol = st.text_input("Symbol", value="NABIL", key="alert_sym")
        threshold = st.number_input("Price change threshold (%)", value=5.0)
        if st.button("Evaluate Price Alert"):
            rules = [{"kind": "price_change_pct", "symbol": symbol, "threshold_pct": threshold}]
            try:
                res = requests.post(
                    f"{API_BASE}/alerts/evaluate", json={"rules": rules}, timeout=10
                )
                if res.status_code == 200:
                    data = res.json()
                    st.metric("Alerts Triggered", data.get("count", 0))
                    alerts = _safe_list(data.get("alerts"))
                    if alerts:
                        st.dataframe(pd.DataFrame(alerts), use_container_width=True)
                else:
                    st.warning("Alert evaluation unavailable.")
            except requests.RequestException as exc:
                st.error(f"Backend error: {exc}")
