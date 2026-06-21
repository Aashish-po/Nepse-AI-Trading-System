from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from common import (
    _csv_bytes,
    _extract_backtest_components,
    _format_currency,
    _format_percentage,
    _json_bytes,
    _plotly_json,
    _safe_dict,
    _safe_float,
    _safe_int,
    _safe_list,
    _strategy_label,
    _valid_strategies,
    compare_benchmark,
    load_strategies,
    run_backtest,
)


def page_backtesting():
    """Backtest execution and results visualization."""  # type: ignore[annotation-unchecked]

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
