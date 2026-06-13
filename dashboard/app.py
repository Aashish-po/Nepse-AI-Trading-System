import datetime as dt
import json
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_option_menu import option_menu

# ============================================================================
# PAGE CONFIG & STYLING
# ============================================================================

st.set_page_config(
    page_title="NEPSE AI Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for professional fintech aesthetic
st.markdown(
    """
<style>
    :root {
        --primary: #0F172A;
        --secondary: #1E293B;
        --accent: #0EA5E9;
        --success: #10B981;
        --warning: #F59E0B;
        --danger: #EF4444;
        --text-primary: #F8FAFC;
        --text-secondary: #CBD5E1;
    }
    
    * {
        color: var(--text-primary);
    }
    
    .main {
        background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
        color: var(--text-primary);
    }
    
    .stMetric {
        background: rgba(30, 41, 59, 0.6);
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(100, 116, 139, 0.2);
        backdrop-filter: blur(10px);
    }
    
    .stMetric label {
        font-size: 0.875rem;
        color: var(--text-secondary);
        font-weight: 500;
        letter-spacing: 0.5px;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
        border-bottom: 1px solid rgba(100, 116, 139, 0.2);
    }
    
    .stTabs [aria-selected="true"] {
        border-bottom: 2px solid var(--accent);
    }
    
    [data-testid="stVerticalBlock"] > [style*="flex-direction: column"] > [data-testid="stVerticalBlock"] {
        background: rgba(30, 41, 59, 0.4);
        border: 1px solid rgba(100, 116, 139, 0.15);
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    
    .stDataFrame {
        font-size: 0.875rem;
    }
    
    .stDataFrame tbody tr {
        border-bottom: 1px solid rgba(100, 116, 139, 0.1);
    }
    
    .stat-card {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.8), rgba(30, 41, 59, 0.6));
        border: 1px solid rgba(14, 165, 233, 0.2);
        border-radius: 12px;
        padding: 1.5rem;
        backdrop-filter: blur(20px);
    }
    
    .profit {
        color: var(--success);
    }
    
    .loss {
        color: var(--danger);
    }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================================
# API & CONFIG
# ============================================================================

API_BASE = st.secrets.get("API_BASE", "http://127.0.0.1:8000")

EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# BACKEND AVAILABILITY / HEALTH
# ============================================================================


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


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def _parse_date(s: str) -> str:
    """Validate ISO date format."""
    dt.date.fromisoformat(s)
    return s


def _safe_int(value: object, default: int = -1) -> int:
    """Safe int conversion for None/invalid values."""
    try:
        return int(value)  # type: ignore[arg-type]
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
    """Format percentage with color indicator."""
    color = "🟢" if value >= 0 else "🔴"
    return f"{color} {value:+.{decimals}f}%"


# ============================================================================
# API CALLS (CACHED)
# ============================================================================


@st.cache_data(ttl=60)
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


@st.cache_data(ttl=60)
def load_market_overview() -> dict | None:
    """Load market overview data."""
    try:
        res = requests.get(f"{API_BASE}/market/overview", timeout=10)
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


@st.cache_data(ttl=60)
def get_trust_score(symbol: str, date_str: str) -> dict | None:
    """Get data quality trust score for a symbol/date."""
    try:
        res = requests.get(f"{API_BASE}/data-quality/trust/{symbol}/{date_str}", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception:
        return None


@st.cache_data(ttl=300)
def get_daily_quality_report() -> dict | None:
    """Get comprehensive daily data quality report."""
    try:
        res = requests.post(f"{API_BASE}/data-quality/reports/daily", timeout=60)
        res.raise_for_status()
        return res.json()
    except Exception:
        return None


@st.cache_data(ttl=60)
def get_signal_heatmap(date_str: str) -> dict | None:
    """Get signal distribution heatmap for a date."""
    try:
        res = requests.get(f"{API_BASE}/signals/heatmap/{date_str}", timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception:
        return None


def run_backtest(payload: dict) -> dict:
    """Execute backtest with given config."""
    res = requests.post(f"{API_BASE}/strategies/backtests", json=payload, timeout=120)
    res.raise_for_status()
    return res.json()


def compare_benchmark(payload: dict) -> dict | None:
    """Compare strategy to benchmark."""
    try:
        res = requests.post(f"{API_BASE}/strategies/benchmarks/compare", json=payload, timeout=120)
        if res.status_code != 200:
            return None
        return res.json()
    except Exception:
        return None


# ============================================================================
# PAGE: MARKET OVERVIEW
# ============================================================================


def page_market_overview():
    """Market overview with data quality metrics."""
    st.header("📊 Market Overview")

    # Load market data
    overview = load_market_overview()
    quality_report = get_daily_quality_report()
    overview_data = _safe_dict(overview)
    quality_data = _safe_dict(quality_report)

    # Key metrics row
    if overview_data:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            nse_change = _safe_float(overview_data.get("nse_change", 0))
            st.metric(
                "NSE Index",
                overview_data.get("nse_value", "N/A"),
                delta=f"{nse_change:.2f}%",
                delta_color="inverse",
            )

        with col2:
            st.metric(
                "Tracked Symbols",
                overview_data.get("total_symbols", 0),
                delta=overview_data.get("new_symbols_today", 0),
            )

        with col3:
            vol_change = _safe_float(overview_data.get("volume_change", 0))
            st.metric(
                "Total Volume",
                _format_currency(overview_data.get("total_volume", 0)),
                delta=f"{vol_change:.1f}%",
            )

        with col4:
            st.metric(
                "Active Signals",
                overview_data.get("active_signals", 0),
                delta=overview_data.get("new_signals_today", 0),
                delta_color="off",
            )
    else:
        st.info("Market overview unavailable. Ensure backend is running.")

    st.divider()

    # Data quality report
    st.subheader("🔍 Data Quality Report")

    if quality_data:
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Data Completeness",
                f"{quality_data.get('completeness_score', 0):.1%}",
                help="Percentage of expected data points received",
            )

        with col2:
            st.metric(
                "Validation Pass Rate",
                f"{quality_data.get('validation_pass_rate', 0):.1%}",
                help="Percentage of data passing validation checks",
            )

        with col3:
            st.metric(
                "Avg Trust Score",
                f"{quality_data.get('avg_trust_score', 0):.2f}/1.0",
                help="Average data trustworthiness across all symbols",
            )

        # Detailed quality breakdown
        if "quality_by_symbol" in quality_data:
            df_quality = pd.DataFrame(quality_data["quality_by_symbol"])
            if not df_quality.empty:
                st.subheader("Quality by Symbol")
                st.dataframe(df_quality, use_container_width=True, height=300)
    else:
        st.warning("Quality report unavailable.")

    st.divider()

    # Per-symbol trust score lookup
    st.subheader("🎯 Per-Symbol Trust Score")
    col1, col2 = st.columns(2)

    with col1:
        lookup_symbol = st.text_input("Symbol", value="NABIL", key="trust_symbol")

    with col2:
        lookup_date = st.text_input(
            "Date (YYYY-MM-DD)", value=dt.date.today().isoformat(), key="trust_date"
        )

    if st.button("Fetch Trust Score", key="fetch_trust"):
        trust = get_trust_score(lookup_symbol, lookup_date)
        trust_data = _safe_dict(trust)
        if trust_data:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Trust Score", f"{trust_data.get('trust_score', 0):.2f}/1.0")
            with col2:
                status = str(trust_data.get("status", "unknown")).upper()
                color = "🟢" if status == "SAFE" else "🟡" if status == "CAUTION" else "🔴"
                st.metric("Status", f"{color} {status}")
            with col3:
                st.metric("Safe?", "✅ Yes" if trust_data.get("safe") else "❌ No")

            if "components" in trust_data:
                st.caption("**Quality Components:**")
                comp_df = pd.DataFrame([trust_data["components"]])
                st.dataframe(comp_df, use_container_width=True)
        else:
            st.error(
                "Failed to fetch trust score. Check symbol/date and ensure backend is running."
            )


# ============================================================================
# PAGE: STRATEGIES
# ============================================================================


def page_strategies():
    """Strategies overview and management."""
    st.header("🎯 Trading Strategies")

    strategies = _valid_strategies(load_strategies())

    if not strategies:
        st.warning("No strategies found. Create one via the API first.")
        return

    strategy_ids = [_safe_int(strategy.get("id"), -1) for strategy in strategies]

    # Strategy selector
    selected_id = st.selectbox(
        "Select Strategy",
        options=strategy_ids,
        format_func=lambda x: next(
            (_strategy_label(s) for s in strategies if _safe_int(s.get("id"), -1) == x),
            "Unknown",
        ),
        key="strategy_selector",
    )

    # Display selected strategy details
    strategy = next((s for s in strategies if _safe_int(s.get("id"), -1) == selected_id), None)
    if strategy:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Strategy ID", strategy.get("id"))
        with col2:
            st.metric("Version", f"v{strategy.get('version', '0.0.0')}")
        with col3:
            st.metric("Created", strategy.get("created_at", "N/A"))
        with col4:
            st.metric("Status", strategy.get("status", "active").upper())

        st.divider()

        # Strategy configuration
        st.subheader("⚙️ Configuration")
        if "config" in strategy:
            st.json(strategy["config"])

        # Backtests history
        st.subheader("📈 Recent Backtests")
        if "recent_backtests" in strategy:
            df_backtests = pd.DataFrame(strategy["recent_backtests"])
            st.dataframe(df_backtests, use_container_width=True)
        else:
            st.info("No backtests recorded yet.")

        # Parameters
        st.subheader("📊 Strategy Parameters")
        if "parameters" in strategy:
            st.json(strategy["parameters"])


# ============================================================================
# PAGE: BACKTESTING
# ============================================================================


def page_backtesting():
    """Backtest execution and results visualization."""
    st.header("🧪 Backtest & Analysis")

    strategies = _valid_strategies(load_strategies())

    if not strategies:
        st.warning("No strategies available. Create one first.")
        return

    strategy_ids = [_safe_int(strategy.get("id"), -1) for strategy in strategies]

    # Sidebar configuration
    st.sidebar.header("⚙️ Backtest Config")

    initial_capital = st.sidebar.number_input(
        "Initial Capital (Rs.)", value=1000000, step=100000, help="Starting portfolio value"
    )

    commission = st.sidebar.number_input(
        "Commission Rate",
        value=0.005,
        step=0.0001,
        min_value=0.0,
        help="Transaction cost as decimal (0.005 = 0.5%)",
    )

    slippage = st.sidebar.number_input(
        "Slippage (bps)",
        value=5.0,
        step=1.0,
        min_value=0.0,
        help="Execution slippage in basis points",
    )

    execution_delay = st.sidebar.number_input(
        "Execution Delay (bars)",
        value=1,
        step=1,
        min_value=0,
        help="Bars to delay signal execution",
    )

    # Strategy selection
    selected_id = st.sidebar.selectbox(
        "Select Strategy",
        options=strategy_ids,
        format_func=lambda x: next(
            (_strategy_label(s) for s in strategies if _safe_int(s.get("id"), -1) == x),
            "Unknown",
        ),
        key="backtest_strategy",
    )

    # Date range
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=dt.date(2020, 1, 1), key="backtest_start")
    with col2:
        end_date = st.date_input("End Date", value=dt.date.today(), key="backtest_end")

    # Benchmark settings
    st.sidebar.subheader("📊 Benchmark")
    bench_symbol = st.sidebar.text_input(
        "Benchmark Symbol", value="NABIL", help="Symbol for buy-and-hold comparison"
    )

    # Run backtest
    run_button = st.sidebar.button("🚀 Run Backtest", use_container_width=True)

    if run_button:
        if not strategies:
            st.error("No strategies available.")
            return

        # Prepare payload
        selected_id_int = _safe_int(selected_id, -1)
        if selected_id_int == -1:
            st.error("Invalid strategy selection.")
            return

        start_date_str = (
            start_date.isoformat() if isinstance(start_date, dt.date) else str(start_date)
        )
        end_date_str = end_date.isoformat() if isinstance(end_date, dt.date) else str(end_date)

        selected_strategy = next(
            (
                strategy
                for strategy in strategies
                if _safe_int(strategy.get("id"), -1) == selected_id
            ),
            None,
        )
        if not selected_strategy:
            st.error("Selected strategy is unavailable.")
            return

        strategy_config = _safe_dict(selected_strategy.get("config"))

        payload = {
            "strategy_id": selected_id_int,
            "config": {
                "start_date": start_date_str,
                "end_date": end_date_str,
                "initial_capital": float(initial_capital),
                "commission_rate": float(commission),
                "slippage_bps": float(slippage),
                "execution_delay_bars": int(execution_delay),
            },
        }

        # Execute backtest
        with st.spinner("⏳ Running backtest... This may take a moment."):
            try:
                result = run_backtest(payload)
            except Exception as e:
                st.error(f"❌ Backtest failed: {e}")
                return

        # Extract results
        metrics, equity_curve, trades = _extract_backtest_components(result)

        # Performance metrics
        st.subheader("📊 Performance Metrics")
        col1, col2, col3, col4 = st.columns(4)

        total_return = _safe_float(metrics.get("total_return", 0))
        col1.metric(
            "Total Return",
            _format_percentage(total_return * 100),
            help="Total percentage gain/loss",
        )

        sharpe = metrics.get("sharpe_ratio")
        col2.metric(
            "Sharpe Ratio",
            f"{sharpe:.2f}" if sharpe is not None else "N/A",
            help="Risk-adjusted return",
        )

        max_dd = _safe_float(metrics.get("max_drawdown", 0))
        col3.metric(
            "Max Drawdown", _format_percentage(max_dd * 100), help="Largest peak-to-trough decline"
        )

        win_rate = _safe_float(metrics.get("win_rate", 0))
        col4.metric("Win Rate", _format_percentage(win_rate * 100), help="% of winning trades")

        # Secondary metrics
        col5, col6, col7, col8 = st.columns(4)

        profit_factor = _safe_float(metrics.get("profit_factor", 0))
        col5.metric("Profit Factor", f"{profit_factor:.2f}", help="Gross profit / gross loss")

        expectancy = _safe_float(metrics.get("expectancy", 0))
        col6.metric("Expectancy", _format_currency(expectancy), help="Average profit per trade")

        total_trades = _safe_int(metrics.get("total_trades", 0))
        col7.metric("Total Trades", total_trades, help="Number of trades executed")

        num_winners = _safe_int(metrics.get("winning_trades", 0))
        col8.metric(
            "Winning Trades",
            num_winners,
            help=f"{(num_winners/total_trades*100):.1f}% of trades" if total_trades > 0 else "N/A",
        )

        st.divider()

        fig_equity: go.Figure | None = None
        fig_drawdown: go.Figure | None = None
        fig_comparison: go.Figure | None = None
        benchmark_equity_curve: list[Any] = []

        # Equity curve visualization
        st.subheader("📈 Equity Curve")
        if equity_curve:
            df_eq = pd.DataFrame(equity_curve)
            if "date" in df_eq.columns and "equity" in df_eq.columns:
                df_eq["date"] = pd.to_datetime(df_eq["date"])
                df_eq = df_eq.sort_values("date")

                fig_equity = go.Figure()
                fig_equity.add_trace(
                    go.Scatter(
                        x=df_eq["date"],
                        y=df_eq["equity"],
                        fill="tozeroy",
                        name="Equity",
                        line=dict(color="#0EA5E9", width=2),
                        fillcolor="rgba(14, 165, 233, 0.1)",
                    )
                )
                fig_equity.update_layout(
                    title="Portfolio Equity Over Time",
                    xaxis_title="Date",
                    yaxis_title="Equity (Rs.)",
                    hovermode="x unified",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#F8FAFC"),
                )
                st.plotly_chart(fig_equity, use_container_width=True)
        else:
            st.info("No equity curve data available.")

        # Drawdown analysis
        st.subheader("📉 Drawdown Analysis")
        if equity_curve:
            df_eq = pd.DataFrame(equity_curve)
            if "date" in df_eq.columns and "equity" in df_eq.columns:
                df_eq["date"] = pd.to_datetime(df_eq["date"])
                df_eq = df_eq.sort_values("date").set_index("date")

                rolling_max = df_eq["equity"].cummax()
                drawdown_pct = ((df_eq["equity"] - rolling_max) / rolling_max) * 100

                fig_drawdown = go.Figure()
                fig_drawdown.add_trace(
                    go.Scatter(
                        x=df_eq.index,
                        y=drawdown_pct,
                        fill="tozeroy",
                        name="Drawdown",
                        line=dict(color="#EF4444", width=2),
                        fillcolor="rgba(239, 68, 68, 0.1)",
                    )
                )
                fig_drawdown.update_layout(
                    title="Drawdown Over Time",
                    xaxis_title="Date",
                    yaxis_title="Drawdown (%)",
                    hovermode="x unified",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#F8FAFC"),
                )

                st.plotly_chart(fig_drawdown, use_container_width=True)

        st.divider()

        # Trades table
        st.subheader("📋 Trade Details")
        if trades:
            df_trades = pd.DataFrame(trades)
            st.dataframe(df_trades, use_container_width=True, height=400)
        else:
            st.info("No trades executed.")

        st.divider()

        # Benchmark comparison
        st.subheader("⚖️ Benchmark Comparison (Buy & Hold)")
        start_date_str = (
            start_date.isoformat() if isinstance(start_date, dt.date) else str(start_date)
        )
        end_date_str = end_date.isoformat() if isinstance(end_date, dt.date) else str(end_date)

        bench_payload = {
            "benchmark_type": "buy_and_hold",
            "start_date": start_date_str,
            "end_date": end_date_str,
            "symbol": bench_symbol,
        }

        with st.spinner("Fetching benchmark..."):
            try:
                bench = compare_benchmark(bench_payload)
            except Exception as e:
                st.warning(f"Benchmark comparison failed: {e}")
                bench = None

        bench_data = _safe_dict(bench)
        if bench_data:
            col1, col2 = st.columns(2)

            with col1:
                strategy_return = _safe_float(metrics.get("total_return", 0)) * 100
                st.metric(
                    "Strategy Return",
                    _format_percentage(strategy_return),
                    help="Total strategy performance",
                )

            with col2:
                bench_return = _safe_float(bench_data.get("period_return", 0)) * 100
                st.metric(
                    "Buy & Hold Return",
                    _format_percentage(bench_return),
                    help=f"Buy and hold {bench_symbol}",
                )

            # Compare curves
            if bench_data.get("equity_curve"):
                df_strat = pd.DataFrame(equity_curve)
                df_bench = pd.DataFrame(bench_data["equity_curve"])
                benchmark_equity_curve = _safe_list(bench_data.get("equity_curve"))

                if not df_strat.empty and not df_bench.empty:
                    df_strat["date"] = pd.to_datetime(df_strat["date"])
                    df_bench["date"] = pd.to_datetime(df_bench["date"])
                    df_strat = df_strat.sort_values("date")
                    df_bench = df_bench.sort_values("date")

                    fig_comparison = go.Figure()
                    fig_comparison.add_trace(
                        go.Scatter(
                            x=df_strat["date"],
                            y=df_strat["equity"],
                            name="Strategy",
                            line=dict(color="#0EA5E9", width=2),
                        )
                    )
                    fig_comparison.add_trace(
                        go.Scatter(
                            x=df_bench["date"],
                            y=df_bench["equity"],
                            name=f"Buy & Hold {bench_symbol}",
                            line=dict(color="#F59E0B", width=2),
                        )
                    )
                    fig_comparison.update_layout(
                        title="Strategy vs Benchmark",
                        xaxis_title="Date",
                        yaxis_title="Equity (Rs.)",
                        hovermode="x unified",
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#F8FAFC"),
                    )
                    st.plotly_chart(fig_comparison, use_container_width=True)

        st.divider()

        # Export options
        st.subheader("⬇️ Export Results")

        backtest_id = (
            result.get("backtest_id", "unknown") if isinstance(result, dict) else "unknown"
        )
        bundle = {
            "schema_version": "phase6.v1",
            "backtest_id": backtest_id,
            "strategy_id": selected_id_int,
            "strategy_config": strategy_config,
            "config": payload["config"],
            "metrics": metrics,
            "equity_curve": equity_curve,
            "trades": trades,
            "datasets": {
                "equity_curve": equity_curve,
                "trades": trades,
                "benchmark_equity_curve": benchmark_equity_curve,
            },
            "charts": {
                "equity_curve": _plotly_json(fig_equity),
                "drawdown": _plotly_json(fig_drawdown),
                "benchmark_comparison": _plotly_json(fig_comparison),
            },
            "exported_at": dt.datetime.utcnow().isoformat() + "Z",
        }

        st.download_button(
            label="📥 Download Full Bundle",
            data=_json_bytes(bundle),
            file_name=f"backtest_bundle_{backtest_id}.json",
            mime="application/json",
        )
        st.download_button(
            label="📥 Download Report JSON",
            data=_json_bytes(result),
            file_name=f"backtest_report_{backtest_id}.json",
            mime="application/json",
        )
        st.download_button(
            label="📥 Download Strategy Config",
            data=_json_bytes(strategy_config),
            file_name=f"strategy_config_{selected_id_int}.json",
            mime="application/json",
        )
        st.download_button(
            label="📥 Download Datasets JSON",
            data=_json_bytes(bundle["datasets"]),
            file_name=f"backtest_datasets_{backtest_id}.json",
            mime="application/json",
        )
        st.download_button(
            label="📥 Download Charts JSON",
            data=_json_bytes(bundle["charts"]),
            file_name=f"backtest_charts_{backtest_id}.json",
            mime="application/json",
        )

        col1, col2 = st.columns(2)
        with col1:
            if equity_curve:
                df_eq = pd.DataFrame(equity_curve)
                col1.download_button(
                    label="📥 Equity Curve CSV",
                    data=_csv_bytes(df_eq),
                    file_name=f"equity_{backtest_id}.csv",
                    mime="text/csv",
                )
            else:
                st.info("No equity curve data to export.")

        with col2:
            if trades:
                df_tr = pd.DataFrame(trades)
                col2.download_button(
                    label="📥 Trades CSV",
                    data=_csv_bytes(df_tr),
                    file_name=f"trades_{backtest_id}.csv",
                    mime="text/csv",
                )
            else:
                st.info("No trades to export.")

        if equity_curve:
            df_eq = pd.DataFrame(equity_curve)
            st.download_button(
                label="📥 Equity Curve HTML",
                data=df_eq.to_html(index=False, border=0, classes="equity-table").encode("utf-8"),
                file_name=f"equity_{backtest_id}.html",
                mime="text/html",
            )
        else:
            st.info("No equity curve HTML to export.")

        st.success("✅ Backtest completed successfully!")


# ============================================================================
# PAGE: SIGNALS
# ============================================================================


@st.cache_data(ttl=60)
def load_signals(date_str: str) -> list[dict]:
    """Load signals for a specific date."""
    try:
        res = requests.get(f"{API_BASE}/signals/heatmap/{date_str}", timeout=10)
        res.raise_for_status()
        data = res.json()
        return data.get("heat_data", []) if isinstance(data, dict) else []
    except Exception:
        return []


def page_signals():
    """Signal visualization and management."""
    st.header("📈 Signals")

    signals_date = st.text_input(
        "Signals Date (YYYY-MM-DD)", value=dt.date.today().isoformat(), key="signals_date"
    )

    if st.button("Load Signals", key="load_signals"):
        signals = load_signals(signals_date)
        if signals:
            df_signals = pd.DataFrame(signals)
            st.dataframe(df_signals, use_container_width=True, height=400)

            # Signal distribution chart
            if "signal_type" in df_signals.columns:
                signal_counts = df_signals.groupby("signal_type").size()
                fig = go.Figure(data=[go.Bar(x=signal_counts.index, y=signal_counts.values)])
                fig.update_layout(
                    title="Signal Distribution", xaxis_title="Signal Type", yaxis_title="Count"
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No signals found for this date.")


# ============================================================================
# PAGE: FEATURES
# ============================================================================


@st.cache_data(ttl=60)
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


def page_features():
    """Feature generation and analysis."""
    st.header("🔧 Features")

    symbol = st.text_input("Symbol", value="NABIL", key="features_symbol")
    date_str = st.text_input(
        "Date (YYYY-MM-DD)", value=dt.date.today().isoformat(), key="features_date"
    )

    if st.button("Generate Features", key="gen_features"):
        with st.spinner("Generating features..."):
            features = load_features(symbol, date_str)
            if features:
                st.json(features)
            else:
                st.warning(
                    "No feature data available. Feature generation endpoint not implemented."
                )


# ============================================================================
# PAGE: DATA SOURCES
# ============================================================================


@st.cache_data(ttl=60)
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


def page_data_sources():
    """Data source management and monitoring."""
    st.header("📡 Data Sources")

    sources = load_data_sources()
    if sources:
        st.dataframe(pd.DataFrame(sources), use_container_width=True, height=300)
    else:
        st.info("No data source history available.")


# ============================================================================
# PAGE: ALERTS
# ============================================================================


@st.cache_data(ttl=60)
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


def page_alerts():
    """Alert monitoring and acknowledgment."""
    st.header("🔔 Alerts")

    alerts = load_alerts()
    if alerts:
        df_alerts = pd.DataFrame(alerts)
        if "acknowledged" in df_alerts.columns:
            df_alerts["acknowledged"] = df_alerts["acknowledged"].map({True: "Yes", False: "No"})
        st.dataframe(df_alerts, use_container_width=True, height=400)
    else:
        st.info("No alerts found.")


# ============================================================================
# PAGE: SYSTEM STATUS
# ============================================================================


@st.cache_data(ttl=30)
def load_health_status() -> dict | None:
    """Load system health."""
    try:
        res = requests.get(f"{API_BASE}/health", timeout=5)
        res.raise_for_status()
        data = res.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def page_system_status():
    """System status and health monitoring."""
    st.header("🖥️ System Status")

    health = load_health_status()
    if health:
        st.json(health)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Status", str(health.get("status", "unknown")).upper())
        with col2:
            st.metric("Environment", health.get("environment", "unknown"))
    else:
        st.error("System unavailable.")


# ============================================================================
# PAGE: ML MODELS (PHASE 7)
# ============================================================================


def page_ml_models():
    """ML model training and management."""
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
                for model in models:
                    with st.expander(
                        f"{model.get('name', 'Unknown')} ({model.get('status', 'unknown')})"
                    ):
                        st.json(model)
            else:
                st.info("No models to display")
    except Exception:
        st.info("Could not load models")


# ============================================================================
# MAIN APP
# ============================================================================


def main():
    """Main application entry point."""

    # Startup backend check (Phase 6 validation hardening)
    if not require_backend_or_safe_mode():
        st.warning("🛡️ Safe Mode: read-only UI. Backend is required for interactive data.")
        st.stop()

    # Navigation menu
    with st.sidebar:
        st.image(
            "https://images.unsplash.com/photo-1507679799987-c73779587ccf?ixlib=rb-4.0.3&auto=format&fit=crop&w=1470&q=80",
            caption="NEPSE AI Trading System",
        )
        st.divider()

        page = option_menu(
            "Navigation",
            [
                "📊 Market Overview",
                "🎯 Strategies",
                "🧪 Backtesting",
                "📈 Signals",
                "🔧 Features",
                "📡 Data Sources",
                "🔔 Alerts",
                "🖥️ System Status",
                "🤖 ML Models",
            ],
            icons=[
                "graph-up",
                "bullseye",
                "flask",
                "bar-chart",
                "gear",
                "hdd-network",
                "bell",
                "display",
                "robot",
            ],
            menu_icon="list",
            default_index=0,
        )

    # Route pages
    if page == "📊 Market Overview":
        page_market_overview()
    elif page == "🎯 Strategies":
        page_strategies()
    elif page == "🧪 Backtesting":
        page_backtesting()
    elif page == "📈 Signals":
        page_signals()
    elif page == "🔧 Features":
        page_features()
    elif page == "📡 Data Sources":
        page_data_sources()
    elif page == "🔔 Alerts":
        page_alerts()
    elif page == "🖥️ System Status":
        page_system_status()
    elif page == "🤖 ML Models":
        page_ml_models()

    # Footer
    st.divider()
    st.caption(f"NEPSE AI Trading System • {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    st.markdown(
        """
        <style>
            .stApp {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }""",
        unsafe_allow_html=True,
    )

    st.info(
        "This dashboard is a prototype for monitoring and analyzing trading strategies. "
        "All data is sourced from the backend API. Ensure the backend is running for full functionality."
    )

    st.success(
        "Welcome to the NEPSE AI Trading Dashboard! Explore market data, manage strategies, and run backtests with ease."
    )
    st.image(
        "https://images.unsplash.com/photo-1507679799987-c73779587ccf?ixlib=rb-4.0.3&auto=format&fit=crop&w=1470&q=80",
        caption="Visualize your trading performance with our interactive dashboard.",
    )


if __name__ == "__main__":
    main()
