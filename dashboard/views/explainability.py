from __future__ import annotations

import pandas as pd
import requests  # type: ignore[import-untyped]
import streamlit as st
from common import (
    API_BASE,
    _safe_list,
)


def page_explainability():
    """Feature importance and governance for trained models."""  # type: ignore[annotation-unchecked]

    st.header("🔍 Explainability & Governance")

    model_id = st.text_input("Model ID or version", value="")
    if not model_id:
        st.info("Enter a model ID (see ML Models page) to view explanations.")
        return

    tab_imp, tab_gov = st.tabs(["Feature Importance", "Governance"])

    with tab_imp:
        top_k = st.slider("Top features", 3, 30, 10)
        try:
            res = requests.get(
                f"{API_BASE}/explain/models/{model_id}/importance?top_k={top_k}", timeout=20
            )
            if res.status_code == 200:
                data = res.json()
                st.caption(f"Method: {data.get('method')}")
                importances = _safe_list(data.get("importances"))
                if importances:
                    df = pd.DataFrame(importances)
                    st.bar_chart(df.set_index("feature")["contribution"])
                    st.dataframe(df, use_container_width=True)
            elif res.status_code == 404:
                st.warning("Model not found.")
            else:
                st.warning("Importance unavailable.")
        except requests.RequestException as exc:
            st.error(f"Backend error: {exc}")

    with tab_gov:
        try:
            res = requests.get(f"{API_BASE}/governance/models/{model_id}", timeout=10)
            if res.status_code == 200:
                status = res.json()
                st.metric("Governance Status", status.get("governance_status", "—"))
                st.metric("Production Ready", "Yes" if status.get("production_ready") else "No")
                st.json(status.get("governance", {}))
            elif res.status_code == 404:
                st.warning("Model not found.")
        except requests.RequestException as exc:
            st.error(f"Backend error: {exc}")

        st.divider()
        reviewer = st.text_input("Reviewer", value="researcher")
        notes = st.text_input("Notes", value="")
        c1, c2, c3, c4 = st.columns(4)
        action = None
        if c1.button("Submit"):
            action = ("submit", {"notes": notes})
        if c2.button("Approve"):
            action = ("approve", {"reviewer": reviewer, "notes": notes})
        if c3.button("Reject"):
            action = ("reject", {"reviewer": reviewer, "notes": notes})
        if c4.button("Mark Production"):
            action = ("production", {"reviewer": reviewer, "notes": notes})
        if action:
            verb, payload = action
            try:
                res = requests.post(
                    f"{API_BASE}/governance/models/{model_id}/{verb}", json=payload, timeout=10
                )
                if res.status_code == 200:
                    st.success(f"{verb.title()} succeeded.")
                    st.json(res.json())
                else:
                    st.error(res.json().get("detail", "Action failed."))
            except requests.RequestException as exc:
                st.error(f"Backend error: {exc}")
