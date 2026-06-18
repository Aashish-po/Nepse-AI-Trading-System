
# NEPSE AI Trading Research Platform

Private research and decision-support platform for NEPSE market data, quantitative research, data quality assurance, realistic backtesting, and signal exploration.

**This project is research-only. It does not provide financial advice, guarantee profit, or execute live trades.**

## Overview

A comprehensive quantitative research platform designed specifically for the Nepal Stock Exchange (NEPSE) market. The platform provides end-to-end workflows from raw market data ingestion through strategy development, backtesting, and advisory signal generation.

## Architecture

```text
Data Sources → Ingestion → Validation → Database → Feature Engineering
  → Data Quality → Trust Scoring → Backtesting → Dashboard / API / Alerts
```

## MVP Success Targets

| Metric | Target |
|--------|--------|
| Sharpe Ratio | > 1.2 |
| Maximum Drawdown | < 20% |
| Win Rate | > 55% |

All outputs are advisory-only and require human review.

## MVP Stack

- Backend: Python, FastAPI
- Database: PostgreSQL, with TimescaleDB when available
- Cache/jobs: Redis
- ML tracking: MLflow
- Dashboard: Streamlit
- Research notebooks: Jupyter
- Infrastructure: Docker Compose first, Kubernetes later
- Testing: pytest
- Linting: ruff

## Implementation Roadmap

All 15 phases (0–14) are implemented in code and covered by tests. The phase
numbering below matches `Documents/6_IMPLEMENTATION_PLAN.md` and the phase-gated
test suite (e.g. `test_phase8_gate.py`, `test_phase10_integration.py`,
`test_phase14_experimental.py`).

| Phase | Focus Area             | Key Deliverables                                           |
| ----- | ---------------------- | ---------------------------------------------------------- |
| 0     | Foundation             | Project structure, env config, CI, `/health` endpoint      |
| 1     | Backend & Database     | FastAPI skeleton, SQLAlchemy ORM, Alembic migrations, JWT auth/RBAC, symbol seeding |
| 2     | Data Ingestion & Quality | Ingestion service, validation rules, ingestion logs, trust scoring, data-quality gate, alerting |
| 3     | Feature Engineering    | Technical indicators (RSI/SMA/EMA/MACD/ATR), returns/volatility, feature store, point-in-time safety |
| 4     | Data Quality & Reliability | Trust model, daily reports, quality alerts, system modes (NORMAL/DEGRADED/SAFE_MODE) |
| 5     | Strategy & Backtesting | Strategy registry, realistic backtesting (fees/slippage/liquidity/partial fills), benchmark comparison |
| 6     | Research Workflow & Dashboard | Streamlit dashboard, notebook workflow, export validation, analytics & alerts pages |
| 7     | Baseline ML            | Logistic regression, random forest, XGBoost, walk-forward training, promotion gates, model registry API |
| 8     | LSTM & Sentiment       | LSTM next-day return forecasting, XLM-R/lexicon sentiment, NEPSE market calendar |
| 9     | Signal Fusion & Risk   | Signal fusion engine, risk manager, position sizing, provider quota tracking (advisory; `enforced: false`) |
| 10    | Portfolio Optimization | In-memory account simulation, allocation methods (equal weight, risk parity, mean-variance, constraints) |
| 11    | Explainability (SHAP)  | Feature importance, local attribution, trade explanations, model governance/approval workflow |
| 12    | MLOps / Monitoring / Retraining | Model selection, auto-retraining policy, hyperparameter evolution, drift monitoring |
| 13    | Production Hardening & Deployment | Multi-stage Docker images, Compose, Kubernetes manifests, CI/CD, Prometheus monitoring, DB backups |
| 14    | Experimental AI        | PPO, DQN, GNN, ensembles, meta-learning (experimental research modules, not live trading) |

The Phase 14 RL/GNN modules are experimental research code. Live broker execution
and autonomous trading remain out of scope (deferred) until data-quality and
backtesting reliability are proven in production research use.

## Current Project Structure

```text
.
├── .github/workflows/                       # CI (ci.yml), image publish (docker-publish.yml), Pages
├── .streamlit/                              # Streamlit config (local)
├── .vscode/                                 # VS Code workspace settings
├── AGENTS.md                                # Common dev commands
├── README.md
├── pyproject.toml                           # Project + ruff config
├── uv.lock                                  # uv lockfile
├── requirements.txt
├── requirements-dev.txt
├── alembic.ini
├── pytest.ini
├── .pre-commit-config.yaml
├── Nepse AI Trading System.code-workspace
│
├── backend/
│   ├── __init__.py
│   └── app/
│       ├── main.py                          # FastAPI application entry point
│       ├── core/                            # config.py, logging.py, security.py, dependencies.py
│       ├── api/routes/                       # auth, health, market, features, data_quality,
│       │                                     #   strategies, signals, ml, lstm, lstm_route,
│       │                                     #   portfolio, explainability, mlops, analytics
│       ├── models/                          # SQLAlchemy ORM models (stock, price, feature,
│       │                                     #   data_quality, data_source, strategy, signal,
│       │                                     #   backtest, portfolio_snapshot, dataset,
│       │                                     #   model_registry, trade, user, benchmark,
│       │                                     #   drift_event, telegram, quota, NEPSEINDEX, types)
│       ├── schemas/                         # auth, market, feature, ingestion, strategy,
│       │                                     #   data_quality, signals, portfolio, explainability
│       ├── services/                        # auth, market, ingestion, feature, data_quality,
│       │                                     #   data_quality_gate, backtest, benchmark, strategy,
│       │                                     #   mlflow_tracking, telegram_alerter, signal_backfill,
│       │                                     #   signal_fusion, risk_manager, portfolio_account,
│       │                                     #   portfolio_optimization, model_governance, mlops,
│       │                                     #   monitoring, analytics, alerts, provider_quota,
│       │                                     #   market_calendar
│       ├── db/                              # session.py, base.py
│       └── db/migrations/versions/           # Alembic revisions 0001 … 0011
│
├── ml/                                      # ML / research modules
│   ├── training.py, inference.py, predictions.py, evaluation.py, dataset.py
│   ├── feature_vector.py, labeling.py, drift_monitoring.py, model_io.py
│   ├── risk_manager.py, position_sizing.py, signal_fusion.py, experiment_tracking.py
│   ├── lstm.py, sentiment.py, ensemble.py, explainability.py, meta_learning.py
│   └── ppo.py, dqn.py, gnn.py               # Phase 14 experimental RL/GNN
│
├── strategies/                              # Strategy definitions and experiments
├── backtesting/                             # Backtesting helpers
├── features/                                # Feature helpers
│
├── data/                                    # Data layer
│   ├── loaders/, ingestion/, validation/
│   └── raw/.gitkeep                         # Placeholder for raw input files
│
├── scripts/
│   ├── seed_symbols.py                      # Seed NEPSE symbols into database
│   ├── smoke_test.py                        # Manual smoke verification
│   └── backup_db.sh                         # pg_dump backup + retention
│
├── dashboard/                               # Streamlit dashboard (single app, 12 pages)
│   ├── app.py                               # Main Streamlit application
│   ├── README.md, feature_guide.md
│   ├── requirements-dashboard.txt
│   ├── setup.sh, setup.bat
│   └── .streamlit/config.toml
│
├── docs/                                    # Reference specs
│   ├── ARCHITECTURE.md, PHASES.md, SUCCESS_METRICS.md
│   ├── data_quality_gate_spec.md, RISK_DISCLAIMER.md
│
├── Documents/                               # Methodology / planning docs (git-ignored)
│   ├── 0_INDEX.md, 00_QUICK_REFERENCE.md
│   └── 1_PRD.md … 7_Security.md (incl. 6_IMPLEMENTATION_PLAN.md)
│
├── infra/                                   # Infrastructure / deployment
│   ├── docker-compose.yml, README.md
│   ├── docker/api.Dockerfile, docker/dashboard.Dockerfile
│   └── k8s/                                 # namespace, configmap, api/dashboard deployments, backup-cronjob
│
├── models/                                  # Trained model artifacts *.joblib (gitignored)
│
├── research/notebooks/                      # 01_idea_to_backtest, 02_backtest_and_export,
│   │                                         #   03_integrate_bundle + README.md
│
└── backend/tests/                           # pytest suite (incl. phase gates:
                                             #   test_phase6_validation, test_phase8_gate,
                                             #   test_phase10_integration, test_phase14_experimental)
```

## API Endpoints (Current)

| Method | Endpoint                                     | Description                                                 |
| ------ | -------------------------------------------- | ----------------------------------------------------------- |
| GET    | /health                                      | Health check (status, environment, version, scope)          |
| GET    | /health/live                                 | Liveness probe (process up)                                 |
| GET    | /health/ready                                | Readiness probe (database reachable)                        |
| GET    | /metrics                                     | Prometheus metrics (request counts, latency histogram)      |
| POST   | /auth/register                               | Register a new user                                         |
| POST   | /auth/login                                  | Login and receive access token                              |
| GET    | /market/prices                               | List price data with optional symbol filter                 |
| POST   | /market/ingest                               | Ingest a single price record for a stock                    |
| POST   | /market/ingest/batch                         | Batch ingest OHLCV data for a date range                    |
| POST   | /features/generate                           | Compute features for a single symbol/date                   |
| POST   | /features/generate-batch                     | Compute features for a date range (single symbol)           |
| POST   | /features/generate-multi                     | Compute features across multiple symbols                    |
| GET    | /data-quality/trust/{symbol}/{date}          | Get trust score and quality details                         |
| GET    | /data-quality/safe/{symbol}/{date}           | Check if data is safe to use (trust >= 0.7)                 |
| GET    | /data-quality/summary/{symbol}               | Get symbol quality summary (avg trust, unsafe days, issues) |
| POST   | /data-quality/reports/daily                  | Generate daily data quality report                          |
| GET    | /data-quality/alerts                         | List data quality alerts                                    |
| POST   | /data-quality/alerts/{alert_id}/acknowledge  | Acknowledge an alert                                        |
| GET    | /data-quality/trends/{symbol}                | Get trust score trend over 30 days                          |
| GET    | /data-quality/freshness/{symbol}/{date}      | Check data freshness (last update vs expected)              |
| GET    | /data-quality/system-mode                    | Get system mode (NORMAL / DEGRADED / SAFE_MODE)             |
| GET    | /data-quality/cross-validate/{symbol}/{date} | Cross-validate price across active data sources             |
| GET    | /data-quality/source-accuracy/{source_id}    | Get accuracy score for a data source                        |
| GET    | /data-quality/weighted-price/{symbol}/{date} | Get source-weighted average price                           |
| GET    | /data-quality/source-drift/{source_id}       | Detect drift in a data source's record volume               |
| GET    | /data-quality/mode-history                   | Get system mode history                                     |
| POST   | /data-quality/sources/recover-blacklisted    | Attempt to recover blacklisted sources                      |
| POST   | /data-quality/trust/apply-decay              | Apply time-based decay to old trust scores                  |
| POST   | /strategies/                               | Create a new strategy                                       |
| GET    | /strategies/                               | List all strategies                                         |
| GET    | /strategies/{strategy_id}                   | Get strategy details                                        |
| POST   | /strategies/backtests                      | Run backtest for a strategy                                 |
| GET    | /strategies/backtests/{backtest_id}         | Get backtest results                                        |
| POST   | /strategies/benchmarks/compare             | Compare strategy vs buy-and-hold/NEPSE                    |
| POST   | /ml/train                                  | Train an ML model                                           |
| GET    | /ml/models                                 | List trained models                                         |
| GET    | /ml/predict/{symbol}                       | Get model prediction for a symbol                           |
| POST   | /portfolio/account                         | Create/reset a portfolio account                            |
| GET    | /portfolio/account/snapshot                | Portfolio snapshot (equity, cash, positions)                |
| POST   | /portfolio/optimize                        | Optimize allocation (equal/risk-parity/mean-variance)       |
| GET    | /explain/models/{model_id}/importance      | Global feature importance (SHAP + fallbacks)                |
| POST   | /explain/models/{model_id}/predict         | Local attribution + trade explanation                       |
| GET    | /governance/models                         | List models by governance state                             |
| POST   | /governance/models/{model_id}/submit       | Submit a model for approval                                 |
| POST   | /governance/models/{model_id}/approve      | Approve a model                                             |
| POST   | /governance/models/{model_id}/production   | Mark an approved model production-ready                     |
| GET    | /mlops/champion                             | Select best model by metric                                 |
| GET    | /mlops/rank                                 | Rank registered models by metric                            |
| GET    | /mlops/models/{model_id}/retrain-assessment| Assess whether a model needs retraining                     |
| POST   | /mlops/retrain                             | Trigger a retraining run                                    |
| POST   | /mlops/evolve                              | Evolutionary hyperparameter search                          |
| GET    | /analytics/market-overview                 | Market overview with top gainers/losers                     |
| GET    | /analytics/signals                         | Signal explorer with filters and summary                    |
| POST   | /analytics/portfolio                       | Portfolio analytics from an equity curve                    |
| POST   | /alerts/evaluate                           | Evaluate rule-based alerts                                  |

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements-dev.txt
copy .env.example .env
pytest
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --app-dir .
```

Open `http://127.0.0.1:8000/health` to verify the API.
Open `http://127.0.0.1:8000/docs` for the interactive Swagger UI.

## Database Migrations

```powershell
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic downgrade -1
```

## Lint & Type Check

```powershell
python -m ruff check backend/
```

## Seed Symbol Data

```powershell
python scripts/seed_symbols.py
```

This populates the database with NEPSE stock symbols for initial testing.

## Research Boundary

The MVP is intentionally limited to ingestion, data quality, features, realistic backtesting, strategy research, dashboards, and advisory outputs. Live trading, broker execution, and autonomous financial advice are out of scope.

## Research Workflow

The platform supports a notebook-driven research cycle:

```
1. Idea → 2. Notebook Experiment → 3. Backtest → 4. Strategy Integration → 5. Dashboard/Report
```

Use `research/notebooks/` for exploratory analysis. All experimental results must be validated through the tested backtesting pipeline before integration.

## Current Phase Status

**Phase 0-14 Implementation Complete**: Foundation, backend & database, data ingestion & quality, features, data-quality reliability, strategy & backtesting, and the research workflow/dashboard (Phases 0-6); baseline ML (Phase 7); LSTM forecasting, multilingual XLM-R/lexicon sentiment, and the NEPSE market calendar (Phase 8); signal fusion with risk management (Phase 9, advisory — `enforced: false`); portfolio optimization (Phase 10, in-memory account state); explainability (SHAP) with model governance (Phase 11); MLOps — meta-learning, retraining policy, drift monitoring (Phase 12); production hardening & deployment with Docker/Kubernetes, CI/CD, monitoring, and backups (Phase 13); and experimental AI — PPO/DQN/GNN, ensembles, meta-learning (Phase 14, experimental research only) are implemented.

**Validation**: The full test suite passes (`python -m pytest backend/tests/ -v`), including phase gates `test_phase6_validation.py`, `test_phase8_gate.py`, `test_phase10_integration.py`, and `test_phase14_experimental.py`. Lint is clean (`python -m ruff check backend/`).

### Completed Features

- Realistic backtesting with fees, slippage, liquidity filters, partial fills
- Strategy registry with versioned configurations
- Multi-condition strategy logic (AND/OR operators)
- Stop loss, take profit, and trailing stop exits
- Data quality gating for backtest safety
- Technical indicators (RSI, SMA, EMA, MACD, ATR, returns)
- Transaction cost and fill rate modeling
- Portfolio-level constraints (max positions, cash reserves)
- Dashboard with 12 pages (Market Overview, Strategies, Backtesting, Signals, Features, Data Sources, Alerts, System Status, ML Models, Analytics, MLOps, Explainability)
- Export workflow (JSON/CSV backtest reports, equity curves, trade logs)
- Safe mode integration (data-quality gating across features and backtests)

### Backtesting Realism

The backtesting engine includes:

- **Fees**: Configurable commission rates (default 0.5%)
- **Slippage**: Basis points slippage model (default 5.0 bps)
- **Liquidity**: Minimum volume thresholds and partial fill simulation
- **Execution Delay**: Configurable bar delay for order execution
- **Cash Tracking**: Real-time cash and position accounting
- **Equity Curves**: Full portfolio equity history for every backtest
- **Trailing Stop**: Dynamic stop loss that tracks price peaks

### Safety Controls

- **Safe Mode**: Blocks low-trust data from feature generation and backtesting
- **Kill Switch**: Emergency stop for advisory signals
- **Trust Scores**: Automated data quality scoring with decay adjustment
- **Data Quality Alerts**: Real-time monitoring of data integrity
  