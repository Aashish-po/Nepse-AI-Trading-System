from __future__ import annotations

import pandas as pd
import requests  # type: ignore[import-untyped]
import streamlit as st
from common import (
    API_BASE,
    _safe_list,
)


def page_mlops():
    """Model selection, ranking, and retraining assessment."""  # type: ignore[annotation-unchecked]

    st.header("⚙️ MLOps")
    metric = st.selectbox(
        "Selection metric", ["sharpe_ratio", "accuracy", "f1_weighted", "max_drawdown"]
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Champion")
        try:
            res = requests.get(f"{API_BASE}/mlops/champion?metric={metric}", timeout=10)
            if res.status_code == 200:
                champion = res.json().get("champion")
                if champion:
                    st.json(champion)
                else:
                    st.info("No models with this metric yet.")
            else:
                st.warning("Champion selection unavailable.")
        except requests.RequestException as exc:
            st.error(f"Backend error: {exc}")

    with col2:
        st.subheader("Ranking")
        try:
            res = requests.get(f"{API_BASE}/mlops/rank?metric={metric}", timeout=10)
            if res.status_code == 200:
                models = _safe_list(res.json().get("models"))
                if models:
                    st.dataframe(pd.DataFrame(models), use_container_width=True)
                else:
                    st.info("No ranked models.")
            else:
                st.warning("Ranking unavailable.")
        except requests.RequestException as exc:
            st.error(f"Backend error: {exc}")

    st.divider()
    st.subheader("Hyperparameter Evolution (demo)")
    st.caption("Searches toward target values using an evolutionary algorithm.")
    if st.button("Run Evolution Demo"):
        payload = {
            "space": {"x": [0.0, 10.0], "y": [0.0, 10.0]},
            "target": {"x": 5.0, "y": 5.0},
            "population_size": 10,
            "generations": 10,
            "seed": 7,
        }
        try:
            res = requests.post(f"{API_BASE}/mlops/evolve", json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                st.write("Best params:", data["best_params"])
                st.write("Best score:", data["best_score"])
                history = _safe_list(data.get("history"))
                if history:
                    st.line_chart(pd.DataFrame(history).set_index("generation")["best_score"])
            else:
                st.warning("Evolution unavailable.")
        except requests.RequestException as exc:
            st.error(f"Backend error: {exc}")
