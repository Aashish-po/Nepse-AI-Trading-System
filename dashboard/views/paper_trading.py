from __future__ import annotations

from typing import Any

import pandas as pd
import requests  # type: ignore[import-untyped]
import streamlit as st
from common import (
    API_BASE,
    _format_currency,
    _format_percentage,
    _safe_dict,
    _safe_float,
    _safe_int,
    _safe_list,
    auth_headers,
    load_paper_accounts,
    render_hero,
)


def page_paper_trading():
    """Paper trading: simulated order execution against live prices."""

    render_hero(
        "Paper Trading",
        "Simulated trading with realistic slippage, commissions, and mark-to-market tracking.",
    )

    headers = auth_headers()

    # --- Account creation ---------------------------------------------------
    with st.expander("➕ Create Account", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            acct_name = st.text_input("Account name", value="Paper Account", key="pt_name")
        with col2:
            capital = st.number_input(
                "Initial capital", min_value=1000.0, value=1000000.0, step=1000.0, key="pt_capital"
            )
        if st.button("Create Account", key="pt_create"):
            try:
                res = requests.post(
                    f"{API_BASE}/paper-trading/accounts",
                    json={"name": acct_name, "initial_capital": capital},
                    headers=headers,
                    timeout=10,
                )
                if res.status_code == 200:
                    data = res.json()
                    st.success(f"Created account #{data.get('account_id', 'unknown')}")
                else:
                    st.error(res.json().get("detail", "Failed to create account"))
            except requests.RequestException as exc:
                st.error(f"Backend error: {exc}")

    accounts = load_paper_accounts()
    if not accounts:
        st.info("No paper trading accounts yet. Create one above.")
        return

    labels = {f"#{a['account_id']} · {a['name']}": a["account_id"] for a in accounts}
    selected = st.selectbox("Account", list(labels.keys()), key="pt_select")
    account_id = labels[selected]

    # --- Account summary ----------------------------------------------------
    try:
        summary = requests.get(
            f"{API_BASE}/paper-trading/accounts/{account_id}/summary",
            headers=headers,
            timeout=10,
        ).json()
    except requests.RequestException as exc:
        st.error(f"Backend error: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Equity", _format_currency(_safe_float(summary.get("equity"))))
    c2.metric("Cash", _format_currency(_safe_float(summary.get("cash"))))
    c3.metric(
        "Total P&L",
        _format_currency(_safe_float(summary.get("total_pnl"))),
        delta=_format_percentage(_safe_float(summary.get("total_return_pct"))),
    )
    c4.metric("Open Positions", _safe_int(summary.get("open_positions"), 0))

    curve = _safe_list(summary.get("equity_curve"))
    if curve:
        st.subheader("Equity Curve")
        curve_df = pd.DataFrame(curve)
        if "timestamp" in curve_df.columns:
            curve_df["timestamp"] = pd.to_datetime(curve_df["timestamp"], errors="coerce")
            curve_df = curve_df.dropna(subset=["timestamp"]).set_index("timestamp")
        if "equity" in curve_df.columns and not curve_df.empty:
            st.line_chart(curve_df["equity"])

    # --- Order entry --------------------------------------------------------
    st.subheader("Place Order")
    oc1, oc2, oc3, oc4 = st.columns(4)
    with oc1:
        order_symbol = st.text_input("Symbol", value="NABIL", key="pt_symbol")
    with oc2:
        order_side = st.selectbox("Side", ["BUY", "SELL"], key="pt_side")
    with oc3:
        order_qty = st.number_input("Quantity", min_value=1, value=10, step=1, key="pt_qty")
    with oc4:
        order_type = st.selectbox("Type", ["MARKET", "LIMIT"], key="pt_type")

    pc1, pc2 = st.columns(2)
    with pc1:
        limit_price = st.number_input(
            "Limit price (LIMIT only)", min_value=0.0, value=0.0, step=1.0, key="pt_limit"
        )
    with pc2:
        market_price = st.number_input(
            "Market price (0 = use latest)", min_value=0.0, value=0.0, step=1.0, key="pt_market"
        )

    if st.button("Submit Order", key="pt_submit"):
        payload: dict[str, Any] = {
            "symbol": order_symbol,
            "side": order_side,
            "quantity": order_qty,
            "order_type": order_type,
        }
        if order_type == "LIMIT" and limit_price > 0:
            payload["limit_price"] = limit_price
        if market_price > 0:
            payload["market_price"] = market_price
        try:
            res = requests.post(
                f"{API_BASE}/paper-trading/accounts/{account_id}/orders",
                json=payload,
                headers=headers,
                timeout=15,
            )
            if res.status_code == 200:
                order = res.json()
                st.success(f"Order {order['status']}: {order['message']}")
                st.json(order)
            else:
                st.error(res.json().get("detail", "Order failed"))
        except requests.RequestException as exc:
            st.error(f"Backend error: {exc}")

    # --- Positions ----------------------------------------------------------
    positions = _safe_dict(summary.get("positions"))
    if positions:
        st.subheader("Positions")
        st.dataframe(pd.DataFrame(list(positions.values())), use_container_width=True, height=200)

    # --- Trade history ------------------------------------------------------
    st.subheader("Order History")
    try:
        trades = requests.get(
            f"{API_BASE}/paper-trading/accounts/{account_id}/trades",
            headers=headers,
            timeout=10,
        ).json()
    except requests.RequestException as exc:
        st.error(f"Backend error: {exc}")
        trades = []
    if trades:
        st.dataframe(pd.DataFrame(trades), use_container_width=True, height=300)
    else:
        st.info("No orders yet for this account.")
