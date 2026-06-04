# NEPSE AI Trading Research Platform: Revised Start-to-End Plan

## Summary

Build a research-only NEPSE quant platform in two tracks: a lean MVP focused on data quality, feature engineering, realistic backtesting, and dashboards; then advanced AI, MLOps, and production hardening after baseline strategies prove useful. Delay RL, GNN, and meta-learning until data reliability and backtest realism are strong.

## Phased Roadmap

1. **Phase 0: Foundation**
   - Define research-only scope, risk disclaimer, user roles, and success metrics.
   - Default targets: Sharpe > 1.2, max drawdown < 20%, win rate > 55%, no live trading.
   - Set up FastAPI, PostgreSQL/TimescaleDB, Redis, MLflow, Docker, Streamlit, CI, tests, and docs.

2. **Phase 1: Backend and Database**
   - Create FastAPI skeleton with `/health`, config, logging, auth foundation, and API validation.
   - Implement tables for users, stocks, prices, features, signals, strategies, backtests, portfolio snapshots, transaction logs, models, datasets, and versions.
   - Add migration workflow, symbol/sector seed data, and indexes for symbol/date queries.

3. **Phase 2: Data Ingestion**
   - Build NEPSE OHLCV ingestion with raw landing storage, normalized storage, ingestion logs, and retry handling.
   - Add primary and backup data source support where available.
   - Validate duplicates, missing values, OHLC rules, volume sanity, outliers, and corporate action adjustments.

4. **Phase 3: Data Quality and Reliability**
   - Add exchange holiday calendar, missing trading day detection, completeness score, volume anomaly detection, and trust score per symbol/date.
   - Generate daily data quality reports and alerts.
   - Block feature generation or mark data unsafe when trust score is below threshold.

5. **Phase 4: Feature Engineering**
   - Compute returns, volatility, SMA, EMA, RSI, MACD, ATR, volume indicators, rolling statistics, and basic regime labels.
   - Store point-in-time-safe feature sets with `feature_version`.
   - Track feature drift, feature stability, and feature importance over time.

6. **Phase 5: Strategy and Backtesting MVP**
   - Create first-class `Strategy = rules + signals + risk + portfolio logic`.
   - Add strategy registry, strategy versioning, benchmark pack, and strategy comparison.
   - Implement realistic backtesting with fees, slippage, liquidity filters, minimum volume thresholds, partial fills, execution delay, cash tracking, transaction logs, and equity curve.
   - Benchmarks: buy-and-hold, NEPSE index, and sector index where data is available.

7. **Phase 6: Research Workflow and Dashboard**
   - Add Streamlit dashboard for market overview, features, strategies, backtests, equity curves, benchmarks, and data quality reports.
   - Add Jupyter/notebook workflow for idea → notebook → backtest → integrate.
   - Allow exporting backtest reports, configs, datasets, and charts.

8. **Phase 7: Baseline ML**
   - Start with simple supervised models before deep learning: linear models, logistic regression, tree models, and calibrated classifiers.
   - Log experiments, datasets, features, strategy versions, and metrics in MLflow.
   - Promote only models that beat benchmark and simple strategy baselines.

9. **Phase 8: LSTM and Sentiment**
   - Add LSTM forecasting only after baseline ML is stable.
   - Add XLM-R sentiment pipeline for legal/available news sources.
   - Store predictions and sentiment as versioned model signals with confidence scores.

10. **Phase 9: Signal Fusion, Risk, and Safeguards**

- Fuse technical, strategy, baseline ML, LSTM, sentiment, regime, and risk-state signals.
- Use dynamic weights based on recent model performance, regime, confidence calibration, and validation history.
- Add kill switch, safe mode, data failure fallback, model failure fallback, and HOLD-only mode.

1. **Phase 10: Portfolio and Capital Simulation**

- Implement account simulation with initial capital, cash, positions, transaction logs, fees, slippage, equity curve, and exposure.
- Add equal weight, risk parity, mean-variance, and constraint-aware allocation.
- Keep all portfolio outputs advisory.

1. **Phase 11: Explainability and Governance**

- Add SHAP, feature importance, signal attribution, trade explanations, and model cards.
- Version datasets, features, models, strategies, backtest configs, and portfolio configs.
- Require human approval before any model or strategy is marked production-ready.

1. **Phase 12: Monitoring and MLOps**

- Add MLflow registry, retraining jobs, drift monitoring, feature monitoring, and model comparison reports.
- Add Prometheus/Grafana, structured logs, audit logs, and alert priority levels: Critical, Warning, Info.
- Monitor data pipeline health, model drift, drawdown, API latency, and infrastructure usage.

1. **Phase 13: Production Hardening**

- Add Docker Compose for local/dev and Kubernetes manifests for production.
- Add backup/restore, secrets management, disaster recovery, load tests, smoke tests, and security review.
- Add cost policy: CPU for ingestion/backtests/baseline ML, GPU only for scheduled deep learning/RL experiments, batch training by default.

1. **Phase 14: Experimental AI**

- Add PPO/DQN, GNN, hierarchical RL, ensembles, and meta-learning only after MVP metrics and data reliability are proven.
- Keep experimental models isolated from advisory signals until they pass benchmark, stress, and governance gates.

## Public Interfaces and Contracts

- APIs: `/health`, `/auth/login`, `/market/prices`, `/market/ingest`, `/data-quality/reports`, `/features/{symbol}`, `/strategies`, `/strategies/{id}`, `/backtests`, `/backtests/{id}`, `/signals`, `/portfolio`, `/models`, `/metrics`, `/drift`.
- Core versioned entities: dataset, feature set, strategy, model, backtest config, signal config, portfolio config.
- Core outputs: clean market data, data trust reports, feature sets, strategy results, backtest reports, calibrated signals, risk-filtered recommendations, equity curves, explanations, and monitoring alerts.

## Test Plan

- Unit tests for data validation, trust scoring, indicators, strategies, backtest math, risk rules, signal fusion, and portfolio simulation.
- Integration tests for ingestion → validation → features → strategy → backtest → dashboard/API.
- Backtest realism tests for liquidity limits, slippage, partial fills, execution delay, fees, and cash accounting.
- ML tests for reproducible training, version logging, calibration, prediction loading, and benchmark comparison.
- Safety tests for kill switch, safe mode, failed data source, failed model load, low trust score, and HOLD-only fallback.
- Production checks for Docker startup, migrations, API health, monitoring metrics, backup restore, and alert routing.

## Assumptions

- The first build target is a 2–3 month MVP: ingestion, database, features, realistic backtesting, strategy registry, and dashboard.
- Advanced AI is optional and delayed until simple models and strategies establish reliable baselines.
- NEPSE data licensing and source reliability must be verified before production use.
- Streamlit is the first dashboard; React is deferred unless the research UI needs a production-grade frontend.
