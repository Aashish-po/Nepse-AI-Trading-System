# NEPSE AI Trading Research Platform

Private research and decision-support platform for NEPSE market data, quantitative research, AI/ML, realistic backtesting, risk-aware portfolio analysis, and signal exploration.

This project is research-only. It does not provide financial advice, guarantee profit, or execute live trades.

## What This Platform Does

```text
Data Sources → Ingestion → Validation → Database → Feature Engineering
  → Quant Research → AI Models → Signal Fusion → Risk Engine
  → Portfolio Optimization → Backtesting / Evaluation → Dashboard / API / Alerts
```

| Layer | Purpose |
|---|---|
| Data Platform | Market data, corporate actions, news, economic indicators |
| Quant Research | Technical analysis, statistical models, factor models, regime detection |
| AI / ML | LSTM forecasting, sentiment (XLM-R), RL (PPO/DQN/HRL), GNNs, ensembles |
| Signal Fusion | Combines model outputs into unified trade signals with confidence scoring |
| Risk Engine | Position sizing, exposure limits, drawdown protection, daily loss limits |
| Portfolio | Mean-variance, risk parity, sector-constrained optimization |
| Evaluation | Backtesting, walk-forward, Monte Carlo, stress testing, benchmarking |
| Explainability | SHAP, feature importance, signal attribution, trade explanations |
| MLOps | MLflow tracking, model registry, auto-retraining, drift monitoring |
| Infrastructure | FastAPI, PostgreSQL/TimescaleDB, Redis, Docker, Kubernetes |
| UI | Streamlit dashboard, research workbench, Telegram / email / webhook alerts |

## MVP Stack

- Backend: Python, FastAPI
- Database: PostgreSQL, with TimescaleDB when available
- Cache/jobs: Redis
- ML tracking: MLflow
- Dashboard: Streamlit
- Research notebooks: Jupyter
- Infrastructure: Docker Compose first, Kubernetes later
- Testing: pytest

## Implementation Roadmap

| Phase | Focus Area | Key Deliverables |
|---|---|---|
| 0 | Foundation | Project structure, env config, CI, health endpoint |
| 1 | Data Ingestion | Scrapers/API clients, raw landing, validation rules |
| 2 | Database | PostgreSQL schema, indexes, TimescaleDB setup |
| 3 | Feature Engineering | Technical indicators, feature store, feature validation |
| 4 | Authentication | User auth, RBAC, JWT handling |
| 5 | Backtesting Engine | Historical simulation, metrics, scenario testing |
| 6 | LSTM & ML Models | Forecasting, training pipeline, model registry |
| 7 | Sentiment & NLP | XLM-R pipeline, news ingestion, sentiment scoring |
| 8 | Reinforcement Learning | PPO / DQN environments, reward functions, HRL |
| 9 | Graph Neural Networks | Graph construction, relationship modeling, GCN |
| 10 | Signal Fusion | Multi-model weighting, confidence calibration, attribution |
| 11 | Risk Engine | Position sizing, exposure limits, drawdown protection |
| 12 | Portfolio Optimization | Mean-variance, risk parity, rebalancing |
| 13 | Explainability | SHAP integration, feature importance, audit logging |
| 14 | Meta-Learning & MLOps | Auto-retraining, model selection, hyperparameter evolution |
| 15 | Dashboard & Alerts | Market overview, signal explorer, portfolio analytics |
| 16 | Production Deployment | Docker / Kubernetes, CI/CD, monitoring, backups |

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
        market.py             # Market data endpoints
        data_quality.py       # Data quality endpoints
        features.py           # Feature generation endpoints
    core/
      config.py               # Application configuration
      logging.py              # Logging configuration
    models/                   # SQLAlchemy ORM models
    schemas/                  # Pydantic schemas
    services/                 # Business logic layer
    db/                       # Database session + Alembic migrations
  tests/                      # pytest test suite
```

## API Endpoints (Current)

| Method | Endpoint | Description |
|---|---|---|
| GET | /health | Health check endpoint |
| POST | /auth/register | Register a new user |
| POST | /auth/login | Login and receive access token |
| GET | /market/prices | List price data (optional symbol filter) |
| POST | /market/ingest | Ingest market price data for a stock |
| POST | /market/ingest/batch | Batch ingest market price data |
| POST | /features/generate | Compute features for a single symbol/date |
| POST | /features/generate-batch | Compute features for a date range |
| POST | /features/generate-multi | Compute features across multiple symbols |
| GET | /data-quality/trust/{symbol}/{date} | Get trust score for symbol/date |
| GET | /data-quality/safe/{symbol}/{date} | Check if data is safe to use |
| GET | /data-quality/summary/{symbol} | Get symbol quality summary |
| POST | /data-quality/reports/daily | Generate daily data quality report |
| GET | /data-quality/alerts | Get data quality alerts |
| POST | /data-quality/alerts/{alert_id}/acknowledge | Acknowledge an alert |

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

## Research Boundary

The MVP is intentionally limited to ingestion, data quality, features, realistic backtesting, strategy research, dashboards, and advisory outputs. Live trading, broker execution, and autonomous financial advice are out of scope.
