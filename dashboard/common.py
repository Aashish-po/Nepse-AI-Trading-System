"""Shared configuration, helpers, formatters, and cached API wrappers used by
every dashboard page. Page modules under ``views/`` import from here so that
``app.py`` stays a thin entry point (config + navigation + routing)."""

from __future__ import annotations

import datetime as dt
import html
import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import requests  # type: ignore[import-untyped]
import streamlit as st

API_BASE = st.secrets.get("API_BASE", "http://127.0.0.1:8000")
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Shared Plotly theme (plan §3.2). Registered once and set as the default so every
# go.Figure() across the views inherits it; per-figure update_layout still wins for
# titles/axes. Composed on top of plotly_dark for sane base defaults.
# ponytail: one template here beats editing update_layout in every view module.
_GRID = "rgba(100, 116, 139, 0.2)"  # slate-500 @ 20%
pio.templates["nepse"] = go.layout.Template(
    layout=dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#CBD5E1"),  # --text-secondary
        colorway=["#0EA5E9", "#10B981", "#EF4444", "#F59E0B", "#6366F1"],  # accent→info
        xaxis=dict(gridcolor=_GRID, zerolinecolor=_GRID, linecolor="#334155"),
        yaxis=dict(gridcolor=_GRID, zerolinecolor=_GRID, linecolor="#334155"),
        hoverlabel=dict(
            bgcolor="rgba(15, 23, 42, 0.9)", bordercolor="#0EA5E9", font=dict(color="#F8FAFC")
        ),
    )
)
pio.templates.default = "plotly_dark+nepse"


def auth_headers() -> dict[str, str]:
    """Bearer header for authenticated endpoints, when a token is present."""
    if st.session_state.get("auth_token"):
        return {"Authorization": f"Bearer {st.session_state.auth_token}"}
    return {}


def render_hero(title: str, subtitle: str) -> None:
    """Render the styled page hero banner (see the ``.hero`` CSS in app.py)."""
    title = html.escape(title)
    subtitle = html.escape(subtitle)
    st.markdown(
        f"""
        <div class="hero">
            <div class="section-label">NEPSE AI Trading System</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_table(
    df: pd.DataFrame,
    key: str,
    *,
    name: str = "data",
    height: int = 400,
    empty_msg: str = "No data.",
) -> None:
    """Searchable, exportable dataframe (plan §3.2 / Phase 3 filtering).

    Column-click sorting is already native to ``st.dataframe``; this adds a
    substring row filter and a CSV download. Reused by the table-heavy views
    (signals, alerts, analytics, data sources, mlops, live signals).
    """
    if df is None or df.empty:
        st.info(empty_msg)
        return
    query = st.text_input("Filter rows", key=f"{key}_filter", placeholder="🔍 Filter…")
    if query:
        mask = df.astype(str).apply(
            lambda row: row.str.contains(query, case=False, regex=False).any(), axis=1
        )
        df = df[mask]
        if df.empty:
            st.info(f'No rows match "{query}".')
            return
    st.dataframe(df, use_container_width=True, height=height)
    st.download_button(
        "📥 CSV", _csv_bytes(df), file_name=f"{name}.csv", mime="text/csv", key=f"{key}_dl"
    )


def ws_url_from_api_base(api_base: str) -> str:
    """Translate an http(s) API base into its ws(s) websocket equivalent."""
    if api_base.startswith("https://"):
        return "wss://" + api_base.removeprefix("https://")
    if api_base.startswith("http://"):
        return "ws://" + api_base.removeprefix("http://")
    return "ws://" + api_base


def load_live_signal_snapshot(symbol: str) -> dict | None:
    """Polling fallback: pull today's heatmap rows for a single symbol."""
    try:
        res = requests.get(f"{API_BASE}/signals/heatmap/{dt.date.today().isoformat()}", timeout=10)
        res.raise_for_status()
        data = res.json()
        rows = data.get("heat_data", []) if isinstance(data, dict) else []
        matches = [
            row for row in rows if isinstance(row, dict) and row.get("symbol") == symbol.upper()
        ]
        if not matches:
            return {"symbol": symbol.upper(), "status": "no_data", "rows": []}
        return {"symbol": symbol.upper(), "status": "ok", "rows": matches}
    except Exception:
        return None


def fetch_live_signal_ws(symbol: str, create_connection) -> dict | None:
    """Best-effort websocket subscribe/unsubscribe round-trip for a symbol."""
    if create_connection is None:
        return None
    ws_url = ws_url_from_api_base(API_BASE).rstrip("/") + "/ws/signals"
    try:
        ws = create_connection(ws_url, timeout=8.0)
        try:
            ws.send(json.dumps({"symbol": symbol.upper()}))
            subscribed = json.loads(ws.recv())
            ws.send(json.dumps({"action": "unsubscribe"}))
            return {"status": "websocket", "symbol": symbol.upper(), "subscription": subscribed}
        finally:
            ws.close()
    except Exception:
        return None


def load_paper_accounts() -> list[dict[str, Any]]:
    """List the caller's paper-trading accounts (empty when unavailable)."""
    headers = auth_headers()
    try:
        res = requests.get(f"{API_BASE}/paper-trading/accounts", headers=headers, timeout=10)
        if res.status_code != 200:
            return []
        data = res.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _parse_returns_matrix(uploaded_file: Any | None, raw_text: str) -> pd.DataFrame:
    """Read a returns matrix from an uploaded CSV or pasted CSV text."""
    if uploaded_file is not None:
        return pd.read_csv(uploaded_file)
    if not raw_text or not raw_text.strip():
        raise ValueError("Provide a CSV file or paste CSV text.")
    return pd.read_csv(io.StringIO(raw_text))


def backend_health() -> dict | None:
    """Check backend /health endpoint."""
    try:
        res = requests.get(f"{API_BASE}/health", timeout=5)
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def require_backend_or_safe_mode() -> bool:
    """Return True if backend reachable; else show safe-mode banner and return False."""
    health = backend_health()
    if not health:
        st.error("Backend unavailable (GET /health failed). Please start backend API.")
        return False
    return True


def _safe_int(value: object, default: int = -1) -> int:
    """Safe int conversion for None/invalid values."""
    try:
        # Explicit runtime checks to keep mypy happy (int(object) is invalid).
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int | float | str):
            return int(value)
        return default
    except (ValueError, TypeError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    """Safe float conversion."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return default


def _safe_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, default=str, indent=2).encode("utf-8")


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def _plotly_json(fig: go.Figure | None) -> dict[str, Any] | None:
    if fig is None:
        return None
    try:
        raw = fig.to_json()
        if not isinstance(raw, str) or not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def _extract_backtest_components(result: object) -> tuple[dict[str, Any], list[Any], list[Any]]:
    metrics = _safe_dict(result.get("metrics")) if isinstance(result, dict) else {}
    return metrics, _safe_list(metrics.get("equity_curve")), _safe_list(metrics.get("trades"))


def _strategy_label(strategy: dict[str, Any]) -> str:
    return f"{strategy.get('name', 'Strategy')} (v{strategy.get('version', '0.0.0')})"


def _valid_strategies(strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        strategy
        for strategy in strategies
        if isinstance(strategy, dict) and _safe_int(strategy.get("id"), -1) != -1
    ]


def _format_currency(value: float) -> str:
    """Format value as currency."""
    if abs(value) >= 1e9:
        return f"Rs.{value / 1e9:.2f}B"
    elif abs(value) >= 1e6:
        return f"Rs.{value / 1e6:.2f}M"
    elif abs(value) >= 1e3:
        return f"Rs.{value / 1e3:.2f}K"
    return f"Rs.{value:.2f}"


def _format_percentage(value: float, decimals: int = 2) -> str:
    """Format percentage with a shape + signed value so meaning survives without color."""
    arrow = "▲" if value >= 0 else "▼"
    return f"{arrow} {value:+.{decimals}f}%"


def load_strategies() -> list[dict]:
    """Load all strategies from backend."""
    try:
        res = requests.get(f"{API_BASE}/strategies/", timeout=5)
        res.raise_for_status()
        payload = res.json()

        if not isinstance(payload, list):
            return []

        return _valid_strategies([item for item in payload if isinstance(item, dict)])
    except Exception:
        return []


def load_market_overview() -> dict | None:
    """Load market overview data."""
    try:
        res = requests.get(f"{API_BASE}/market/overview", timeout=10)
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def get_trust_score(symbol: str, date_str: str) -> dict | None:
    """Get data quality trust score for a symbol/date."""
    try:
        res = requests.get(f"{API_BASE}/data-quality/trust/{symbol}/{date_str}", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception:
        return None


def get_daily_quality_report() -> dict | None:
    """Get comprehensive daily data quality report."""
    try:
        res = requests.post(f"{API_BASE}/data-quality/reports/daily", timeout=60)
        res.raise_for_status()
        return res.json()
    except Exception:
        return None


def run_backtest(payload: dict) -> dict:
    """Execute backtest with given config."""
    headers = {}
    if st.session_state.auth_token:
        headers["Authorization"] = f"Bearer {st.session_state.auth_token}"
    res = requests.post(
        f"{API_BASE}/strategies/backtests", json=payload, headers=headers, timeout=120
    )
    res.raise_for_status()
    return res.json()


def compare_benchmark(payload: dict) -> dict | None:
    """Compare strategy to benchmark."""
    try:
        headers = {}
        if st.session_state.auth_token:
            headers["Authorization"] = f"Bearer {st.session_state.auth_token}"
        res = requests.post(
            f"{API_BASE}/strategies/benchmarks/compare", json=payload, headers=headers, timeout=120
        )
        if res.status_code != 200:
            return None
        return res.json()
    except Exception:
        return None


def load_signals(date_str: str) -> list[dict]:
    """Load signals for a specific date."""
    try:
        res = requests.get(f"{API_BASE}/signals/heatmap/{date_str}", timeout=10)
        res.raise_for_status()
        data = res.json()
        return data.get("heat_data", []) if isinstance(data, dict) else []
    except Exception:
        return []


def load_features(symbol: str, date_str: str | None = None) -> dict | None:
    """Load feature generation status for a symbol."""
    try:
        params = {
            "symbol": symbol.upper(),
            "date_str": date_str or dt.date.today().isoformat(),
        }
        res = requests.post(f"{API_BASE}/features/generate", params=params, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data if isinstance(data, dict) else None
        return None
    except Exception:
        return None


def load_data_sources() -> list[dict]:
    """Load data sources information."""
    try:
        res = requests.get(f"{API_BASE}/data-quality/mode-history", timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data if isinstance(data, list) else []
        return []
    except Exception:
        return []


def load_alerts() -> list[dict]:
    """Load data quality alerts."""
    try:
        res = requests.get(f"{API_BASE}/data-quality/alerts", timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data if isinstance(data, list) else []
        return []
    except Exception:
        return []


def load_health_status() -> dict | None:
    """Load system health."""
    try:
        res = requests.get(f"{API_BASE}/health", timeout=5)
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None
