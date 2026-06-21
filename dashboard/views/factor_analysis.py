from __future__ import annotations

import pandas as pd
import streamlit as st
from common import _parse_returns_matrix, render_hero


def page_factor_analysis():
    """Local factor analysis for uploaded return series."""

    render_hero(
        "Factor Analysis",
        "Upload or paste returns data to inspect latent drivers, exposures, and attribution.",
    )

    uploaded = st.file_uploader("CSV returns matrix", type=["csv"], key="factor_upload")
    raw_csv = st.text_area(
        "Or paste CSV",
        value="AAA,BBB,CCC\n0.01,0.02,0.03\n0.02,0.01,0.00\n-0.01,0.03,0.02",
        height=160,
        key="factor_csv",
    )
    n_factors = st.slider("Number of factors", min_value=1, max_value=5, value=2, key="factor_n")

    if st.button("Run Factor Analysis", key="run_factor_analysis"):
        try:
            data = _parse_returns_matrix(uploaded, raw_csv)
            matrix = data.select_dtypes(include=["number"]).to_numpy(dtype=float)
            if matrix.size == 0:
                st.warning("No numeric data found.")
                return

            from app.services.factor_analysis import FactorAnalysisService

            service = FactorAnalysisService()
            result = service.compute_factors(matrix, n_factors=n_factors)

            c1, c2, c3 = st.columns(3)
            c1.metric("Rows", matrix.shape[0])
            c2.metric("Symbols", matrix.shape[1])
            c3.metric("Factors", result.factors.shape[1])

            st.subheader("Explained Variance")
            st.bar_chart(pd.Series(result.explained_variance))

            st.subheader("Loadings")
            symbols = list(data.select_dtypes(include=["number"]).columns)
            exposure = service.factor_exposure(result.loadings, symbols)
            st.dataframe(pd.DataFrame(exposure).T, use_container_width=True)
        except Exception as exc:
            st.error(f"Factor analysis failed: {exc}")
