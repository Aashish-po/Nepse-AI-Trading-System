from __future__ import annotations

import pandas as pd
import requests  # type: ignore[import-untyped]
import streamlit as st
from common import (
    API_BASE,
    auth_headers,
    load_alerts,
    render_table,
)


def _acknowledge(alert_ids: list[int]) -> tuple[int, int]:
    """POST acknowledge for each id; return (succeeded, total)."""
    headers = auth_headers()
    ok = 0
    for aid in alert_ids:
        try:
            res = requests.post(
                f"{API_BASE}/data-quality/alerts/{aid}/acknowledge", headers=headers, timeout=10
            )
            if res.status_code == 200 and res.json().get("acknowledged"):
                ok += 1
        except requests.RequestException:
            pass
    return ok, len(alert_ids)


def page_alerts():
    """Alert monitoring and acknowledgment."""
    st.header("🔔 Alerts")

    alerts = load_alerts()
    if not alerts:
        st.info("No alerts found.")
        return

    # Bulk acknowledge (§ Week 9) — only unacknowledged alerts that carry an id.
    unacked = [a for a in alerts if a.get("id") is not None and not a.get("acknowledged")]
    if unacked:
        if not st.session_state.get("auth_token"):
            st.caption("🔐 Log in (sidebar) to acknowledge alerts.")
        else:

            def _label(a: dict) -> str:
                return f"#{a['id']} · {a.get('severity', '?')} · {a.get('symbol', '')}"

            options = {_label(a): a["id"] for a in unacked}
            picked = st.multiselect("Select alerts to acknowledge", list(options), key="ack_pick")
            c1, c2 = st.columns([1, 1])
            if c1.button("Acknowledge selected", disabled=not picked, key="ack_sel"):
                ok, total = _acknowledge([options[label] for label in picked])
                st.success(f"Acknowledged {ok}/{total}.")
                st.rerun()
            if c2.button(f"Acknowledge all ({len(unacked)})", key="ack_all"):
                ok, total = _acknowledge([a["id"] for a in unacked])
                st.success(f"Acknowledged {ok}/{total}.")
                st.rerun()

    df_alerts = pd.DataFrame(alerts)
    if "acknowledged" in df_alerts.columns:
        df_alerts["acknowledged"] = df_alerts["acknowledged"].map({True: "Yes", False: "No"})

    # Severity filter (Phase 3 / §3.x alert management) — only when the column exists.
    if "severity" in df_alerts.columns:
        severity = df_alerts["severity"].astype("string")
        levels = sorted(severity.dropna().unique())
        chosen = st.multiselect("Severity", levels, default=levels, key="alert_severity")
        df_alerts = df_alerts[severity.isna() | severity.isin(chosen)]
    render_table(df_alerts, key="alerts", name="alerts")
