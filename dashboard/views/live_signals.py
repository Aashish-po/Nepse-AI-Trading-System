from __future__ import annotations

import pandas as pd
import streamlit as st
from common import (
    _safe_list,
    fetch_live_signal_ws,
    load_live_signal_snapshot,
    render_hero,
    render_table,
)

try:
    # Optional websocket dependency; common.fetch_live_signal_ws handles None.
    from websocket import create_connection  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - optional dependency
    create_connection = None  # type: ignore[assignment]


def page_live_signals():
    """Simple live signal snapshot page."""

    render_hero(
        "Live Signals",
        "Polling-based snapshot view backed by the signal router with fast refresh.",
    )

    symbol = st.text_input("Symbol", value="NABIL", key="signals_live_symbol")
    st.caption("Use Refresh Snapshot to pull the latest backend state.")
    if st.button("Refresh Snapshot", key="signals_live_refresh"):
        snapshot = fetch_live_signal_ws(symbol, create_connection) or load_live_signal_snapshot(
            symbol
        )
        if not snapshot:
            st.warning("No live data returned from the backend.")
            return
        st.metric("Snapshot status", str(snapshot.get("status", "unknown")).upper())
        if snapshot.get("status") == "websocket":
            st.success("Connected to the live websocket route.")
            st.json(snapshot.get("subscription", {}))
        else:
            rows = _safe_list(snapshot.get("rows"))
            render_table(
                pd.DataFrame(rows),
                key="live_signals",
                name=f"live_{symbol}",
                height=240,
                empty_msg="No recent signal rows found.",
            )
