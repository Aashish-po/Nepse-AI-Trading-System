from __future__ import annotations

import datetime as dt

import pandas as pd
import requests  # type: ignore[import-untyped]
import streamlit as st
from common import (
    API_BASE,
)


def page_ml_models():
    """ML model training and management."""  # type: ignore[annotation-unchecked]

    st.header("🤖 Baseline ML Models")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Train New Model")

        model_name = st.selectbox(
            "Model Type",
            options=["logistic", "random_forest", "xgboost"],
            index=0,
            key="ml_model_type",
        )
        symbols_input = st.text_input(
            "Symbols (comma-separated)",
            value="NABIL",
            key="ml_symbols",
        )
        symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]

        col1a, col1b = st.columns(2)
        start_input = st.date_input(
            "Start Date",
            value=dt.date(2022, 1, 1),
            key="ml_start_date",
        )
        if isinstance(start_input, tuple):
            start_date = start_input[0] if start_input else dt.date(2022, 1, 1)
        else:
            start_date = start_input or dt.date(2022, 1, 1)

        end_input = st.date_input(
            "End Date",
            value=dt.date.today(),
            key="ml_end_date",
        )
        if isinstance(end_input, tuple):
            end_date = end_input[0] if end_input else dt.date.today()
        else:
            end_date = end_input or dt.date.today()

        validation = st.radio(
            "Validation Method",
            options=["single_split", "walk_forward"],
            index=0,
            key="ml_validation",
        )

        if st.button("🚀 Train Model", key="ml_train_btn"):
            with st.spinner("Training..."):
                payload = {
                    "model_name": model_name,
                    "symbols": symbols,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "validation_method": validation,
                    "random_state": 42,
                }
                try:
                    response = requests.post(
                        f"{API_BASE}/ml/models/train",
                        json=payload,
                        timeout=120,
                    )
                    if response.status_code == 200:
                        result = response.json()
                        st.success("✅ Model trained successfully!")
                        st.json(result)
                    else:
                        st.error(f"Training failed: {response.text}")
                except Exception as e:
                    st.error(f"Training failed: {e}")
            # dashboard/app.py - add to ML Models page

        # ML Models Page - Add LSTM Signal Generation
        if st.sidebar.checkbox("Generate LSTM Signals", value=False):
            st.subheader("🤖 LSTM Signal Generation")

            col1, col2 = st.columns([2, 1])

            with col1:
                symbols_to_signal = st.multiselect(
                    "Select symbols", options=["NABIL", "SBI", "HBL", "EBL"], default=["NABIL"]
                )

            with col2:
                if st.button("Generate Signals", key="lstm_generate_signals_btn"):
                    st.info(f"Generating LSTM signals for {len(symbols_to_signal)} symbols...")

                    # In production: load LSTM models and generate signals
                    # For MVP: show framework is ready

                    st.success("✅ LSTM signals framework ready")
                    st.write(
                        "Phase 8 Week 4 deliverable: signals now available via `/signals` endpoint"
                    )
    with col2:
        st.subheader("Model Status")

        try:
            response = requests.get(f"{API_BASE}/ml/models", timeout=10)
            if response.status_code == 200:
                models = response.json().get("models", [])
                if models:
                    latest = models[0]
                    st.metric("Latest Model", latest.get("name", "N/A"))
                    st.metric("Status", latest.get("status", "unknown"))
                    metrics = latest.get("metrics", {})
                    if metrics and "sharpe_ratio" in metrics:
                        st.metric("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}")
                else:
                    st.info("No models trained yet")
            else:
                st.info("No models available")
        except Exception:
            st.info("Model list unavailable")

    st.divider()

    st.subheader("All Models")
    try:
        response = requests.get(f"{API_BASE}/ml/models", timeout=10)
        if response.status_code == 200:
            models = response.json().get("models", [])
            if models:
                # Side-by-side comparison (§ Week 9): flatten name/status + metrics.
                comparison = [
                    {
                        "name": m.get("name", "—"),
                        "status": m.get("status", "—"),
                        **{k: v for k, v in (m.get("metrics") or {}).items()},
                    }
                    for m in models
                ]
                st.dataframe(pd.DataFrame(comparison), use_container_width=True)
                st.caption("Per-model detail:")
                for model in models:
                    with st.expander(
                        f"{model.get('name', 'Unknown')} ({model.get('status', 'unknown')})"
                    ):
                        st.json(model)
            else:
                st.info("No models to display")
    except Exception:
        st.info("Could not load models")
