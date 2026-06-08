import datetime as dt
import json

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Nepse AI Trading Dashboard", layout="wide")

try:
    API_BASE = st.secrets["API_BASE"]
except Exception:
    API_BASE = "http://localhost:8000"

st.title("📈 Nepse AI Trading System")
st.caption("Phase 6: Research Dashboard (overview → backtest → export)")


def _parse_date(s: str) -> str:
    # Keep backend contract: YYYY-MM-DD strings.
    dt.date.fromisoformat(s)
    return s


@st.cache_data(ttl=60)
def load_strategies() -> list[dict]:
    try:
        res = requests.get(f"{API_BASE}/strategies/", timeout=5)
        res.raise_for_status()
        return res.json()
    except Exception:
        st.error("⚠️ Backend not running or failed to connect")
        return []


@st.cache_data(ttl=60)
def get_trust_score(symbol: str, date_str: str) -> dict | None:
    try:
        res = requests.get(f"{API_BASE}/data-quality/trust/{symbol}/{date_str}", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_daily_quality_report() -> dict | None:
    # Currently unused in this lightweight Phase-6 UI, but kept for later.
    try:
        res = requests.post(f"{API_BASE}/data-quality/reports/daily", timeout=60)
        res.raise_for_status()
        return res.json()
    except Exception:
        return None


def run_backtest(payload: dict) -> dict:
    res = requests.post(f"{API_BASE}/strategies/backtests", json=payload, timeout=120)
    res.raise_for_status()
    return res.json()


def compare_benchmark(payload: dict) -> dict | None:
    res = requests.post(f"{API_BASE}/strategies/benchmarks/compare", json=payload, timeout=120)
    if res.status_code != 200:
        return None
    return res.json()


strategies = load_strategies()

st.header("Market overview & Data quality")
qa_col1, qa_col2, qa_col3 = st.columns(3)
with qa_col1:
    quality_symbol = st.text_input("Symbol", value="NABIL", key="quality_symbol")
with qa_col2:
    quality_date = st.text_input("Date (YYYY-MM-DD)", value="2023-01-01", key="quality_date")
with qa_col3:
    _ = st.slider(
        "Unsafe threshold",
        0.0,
        1.0,
        0.7,
        0.05,
        key="quality_threshold",
        disabled=True,
        help="Dashboard uses backend default safety threshold.",
    )

trust = get_trust_score(quality_symbol, quality_date)
if trust is None:
    st.info("Fetch failed. Start the backend API and refresh.")
else:
    st.write(
        {
            "trust_score": trust.get("trust_score"),
            "status": trust.get("status"),
            "safe": trust.get("safe"),
        }
    )
    st.caption("Components: " + str(trust.get("components", {})))

st.divider()

st.header("Backtest & Export")

if not strategies:
    st.warning(
        "No strategies found from backend. Create one via the API/UI, then refresh this dashboard."
    )
    st.stop()

st.sidebar.header("⚙️ Backtest Config")

initial_capital = st.sidebar.number_input("Initial Capital", value=1000000, step=100000)
commission = st.sidebar.number_input("Commission Rate", value=0.005, step=0.001)
slippage = st.sidebar.number_input("Slippage (bps)", value=5.0, step=1.0)
execution_delay = st.sidebar.number_input("Execution Delay (bars)", value=1, step=1, min_value=0)

selected_strategy = st.sidebar.selectbox(
    "Select Strategy",
    options=[s["id"] for s in strategies],
    format_func=lambda x: next(
        (f"{s['name']} (v{s['version']})" for s in strategies if s["id"] == x),
        "Unknown strategy",
    ),
)

bench_symbol = st.sidebar.text_input("Symbol (for benchmark compare)", value="NABIL")
start_date = st.sidebar.text_input("Start Date (YYYY-MM-DD)", value="2020-01-01")
end_date = st.sidebar.text_input("End Date (YYYY-MM-DD)", value="2023-01-01")

run_button = st.sidebar.button("🚀 Run Backtest")

if run_button:
    payload = {
        "strategy_id": int(selected_strategy),
        "config": {
            "start_date": _parse_date(start_date),
            "end_date": _parse_date(end_date),
            "initial_capital": float(initial_capital),
            "commission_rate": float(commission),
            "slippage_bps": float(slippage),
            "execution_delay_bars": int(execution_delay),
        },
    }

    with st.spinner("Running backtest..."):
        result = run_backtest(payload)

    metrics = result.get("metrics", {})
    equity_curve = metrics.get("equity_curve", [])
    trades = metrics.get("trades", [])

    st.subheader("📊 Performance Metrics")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Return", f"{metrics.get('total_return', 0):.2%}")
    sharpe = metrics.get("sharpe_ratio")
    col2.metric("Sharpe Ratio", f"{sharpe:.2f}" if sharpe is not None else "N/A")
    col3.metric("Max Drawdown", f"{metrics.get('max_drawdown', 0):.2%}")
    col4.metric("Win Rate", f"{metrics.get('win_rate', 0):.2%}")

    col5, col6 = st.columns(2)
    col5.metric("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
    col6.metric("Expectancy", f"{metrics.get('expectancy', 0):.2f}")

    st.subheader("📈 Equity Curve")
    if equity_curve:
        df_eq = pd.DataFrame(equity_curve)
        df_eq["date"] = pd.to_datetime(df_eq["date"])
        df_eq = df_eq.sort_values("date").set_index("date")
        st.line_chart(df_eq["equity"])

        st.subheader("📉 Drawdown")
        rolling_max = df_eq["equity"].cummax()
        drawdown = (df_eq["equity"] - rolling_max) / rolling_max
        st.line_chart(drawdown)
    else:
        st.info("No equity curve data returned.")

    st.subheader("📋 Trades")
    if trades:
        df_trades = pd.DataFrame(trades)
        st.dataframe(df_trades, use_container_width=True)
    else:
        st.info("No trades returned.")

    st.subheader("⚖️ Benchmark Comparison")
    bench_payload = {
        "benchmark_type": "buy_and_hold",
        "start_date": _parse_date(start_date),
        "end_date": _parse_date(end_date),
        "symbol": bench_symbol,
    }

    bench = compare_benchmark(bench_payload)
    if bench:
        period_return = bench.get("period_return")
        if period_return is not None:
            st.metric("Buy & Hold Period Return", f"{period_return:.2%}")

        equity_curve_b = bench.get("equity_curve")
        if equity_curve_b:
            df_b = pd.DataFrame(equity_curve_b)
            if "date" in df_b.columns and "equity" in df_b.columns:
                df_b["date"] = pd.to_datetime(df_b["date"])
                df_b = df_b.sort_values("date").set_index("date")
                st.line_chart(df_b["equity"], height=250)

    st.success("✅ Backtest completed successfully!")

    st.subheader("⬇️ Export backtest report")
    export_format = st.selectbox("Export format", ["JSON", "CSV"], key="export_format")

    if export_format == "JSON":
        json_bytes = json.dumps(result, default=str, indent=2).encode("utf-8")
        st.download_button(
            label="Download backtest report (JSON)",
            data=json_bytes,
            file_name=f"backtest_report_{result.get('backtest_id','unknown')}.json",
            mime="application/json",
        )
    else:
        equity_curve = result.get("metrics", {}).get("equity_curve", [])
        trades = result.get("metrics", {}).get("trades", [])

        df_eq = pd.DataFrame(equity_curve)
        df_tr = pd.DataFrame(trades)

        eq_csv = df_eq.to_csv(index=False).encode("utf-8")
        tr_csv = df_tr.to_csv(index=False).encode("utf-8")

        eq_col, tr_col = st.columns(2)
        with eq_col:
            st.download_button(
                label="Download equity curve (CSV)",
                data=eq_csv,
                file_name=f"equity_curve_{result.get('backtest_id','unknown')}.csv",
                mime="text/csv",
            )
        with tr_col:
            st.download_button(
                label="Download trades (CSV)",
                data=tr_csv,
                file_name=f"trades_{result.get('backtest_id','unknown')}.csv",
                mime="text/csv",
            )
