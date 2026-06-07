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

| Phase | Focus Area             | Key Deliverables                                           |
| ----- | ---------------------- | ---------------------------------------------------------- |
| 0     | Foundation             | Project structure, env config, CI, health endpoint         |
| 1     | Data Ingestion         | Scrapers/API clients, raw landing, validation rules        |
| 2     | Database               | PostgreSQL schema, indexes, TimescaleDB setup              |
| 3     | Feature Engineering    | Technical indicators, feature store, feature validation    |
| 4     | Authentication         | User auth, RBAC, JWT handling                              |
| 5     | Backtesting Engine     | Historical simulation, metrics, scenario testing           |
| 6     | LSTM & ML Models       | Forecasting, training pipeline, model registry             |
| 7     | Sentiment & NLP        | XLM-R pipeline, news ingestion, sentiment scoring          |
| 8     | Reinforcement Learning | PPO / DQN environments, reward functions, HRL              |
| 9     | Graph Neural Networks  | Graph construction, relationship modeling, GCN             |
| 10    | Signal Fusion          | Multi-model weighting, confidence calibration, attribution |
| 11    | Risk Engine            | Position sizing, exposure limits, drawdown protection      |
| 12    | Portfolio Optimization | Mean-variance, risk parity, rebalancing                    |
| 13    | Explainability         | SHAP integration, feature importance, audit logging        |
| 14    | Meta-Learning & MLOps  | Auto-retraining, model selection, hyperparameter evolution |
| 15    | Dashboard & Alerts     | Market overview, signal explorer, portfolio analytics      |
| 16    | Production Deployment  | Docker / Kubernetes, CI/CD, monitoring, backups            |

Advanced AI (ensemble models, meta-learning), high-frequency workflows, and Kubernetes-scale orchestration are deferred until the MVP proves data quality and backtesting reliability.

## Current Project Structure

```text
backend/
  app/
    main.py                   # FastAPI application entry point
    api/
      routes/
        auth.py               # Authentication endpoints (register / login)
        health.py             # Health check endpoint
        market.py             # Market data endpoints (prices, ingest, batch ingest)
        data_quality.py       # Data quality endpoints (trust, safety, alerts, reports)
        features.py           # Feature generation endpoints (single, batch, multi-stock)
    core/
      config.py               # Application configuration
      logging.py              # Logging configuration
    models/                   # SQLAlchemy ORM models
      stock.py                # Stock / symbol metadata
      price.py                # Price data
      feature.py              # Computed features
      data_quality.py         # Trust scores, alerts, reports, holiday calendar, events
      data_source.py          # Data sources and ingestion logs
      strategy.py             # Strategy registry
      signal.py               # Trade signals
      backtest.py             # Backtest results
      portfolio_snapshot.py   # Portfolio snapshots
      dataset.py              # Datasets
      model_registry.py       # ML models
      trade.py                # Trade logs
      user.py                 # Users and RBAC
    schemas/                  # Pydantic schemas
    services/                 # Business logic layer
      feature.py              # Feature computation (RSI, MACD, EMA, ATR, returns, etc.)
      data_quality.py         # Trust scoring, system mode, source accuracy, drift detection
      data_quality_gate.py    # Data quality gating for features and backtesting
      backtest.py             # Backtest execution with data quality enforcement
      benchmark.py            # Benchmark comparison, alpha/beta calculation
      ingestion.py            # Data ingestion service
      market.py               # Market data service
      auth.py                 # Authentication service
    db/                       # Database session + Alembic migrations
  tests/                      # pytest test suite
```

## API Endpoints (Current)

| Method | Endpoint                                     | Description                                                 |
| ------ | -------------------------------------------- | ----------------------------------------------------------- |
| GET    | /health                                      | Health check (status, environment, version, scope)          |
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

**Phase 0-5 Complete**: Foundation, database, data quality, features, and backtesting engine are implemented.

### Completed Features

- Realistic backtesting with fees, slippage, liquidity filters, partial fills
- Strategy registry with versioned configurations
- Multi-condition strategy logic (AND/OR operators)
- Stop loss, take profit, and trailing stop exits
- Data quality gating for backtest safety
- Technical indicators (RSI, SMA, EMA, MACD, ATR, returns)
- Transaction cost and fill rate modeling
- Portfolio-level constraints (max positions, cash reserves)

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
