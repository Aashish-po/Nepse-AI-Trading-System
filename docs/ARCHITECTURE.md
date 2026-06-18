# Architecture

## Scope

The platform is a private NEPSE research system. It supports market data ingestion, data quality checks, feature engineering, strategy research, realistic backtesting, advisory signals, portfolio analysis, explainability, and monitoring.

## High-Level Flow

```text
Data Sources
  -> Ingestion
  -> Data Quality and Reliability
  -> PostgreSQL / TimescaleDB
  -> Feature Engineering
  -> Strategy and Model Research
  -> Realistic Backtesting
  -> Signal Fusion and Risk
  -> Portfolio Simulation
  -> Dashboard, Reports, Monitoring
```

## Default Stack

- FastAPI for backend APIs
- PostgreSQL/TimescaleDB for relational and time-series storage
- Redis for cache and future jobs
- MLflow for experiment tracking and model registry
- Streamlit for MVP dashboard
- Jupyter for research notebooks
- Docker Compose for local infrastructure, Kubernetes manifests for staging
- pytest and ruff for quality gates

## API Layer

The FastAPI app (`backend/app/main.py`) mounts the following routers:

- `auth` — authentication for mutating routes
- `health` — `/health`, `/health/live`, `/health/ready`, plus Prometheus `/metrics`
- `market`, `data_quality`, `features` — market data, trust scores, feature generation
- `signals`, `strategies` — advisory signals and strategy/backtest endpoints
- `portfolio` — portfolio account simulation and optimization (advisory)
- `explainability`, `model_governance` — SHAP attributions and the model approval workflow
- `mlops`, `analytics`, `alerts` — meta-learning/MLOps, analytics, and rule-based alerts
- `lstm` and a conditionally enabled `ml` router for model inference

Supporting services live in `backend/app/services/`; ML/research code lives in `ml/`.

## Runtime Boundaries

- Portfolio account state is held in-memory in the current API.
- Risk-manager outputs are advisory; signal risk enforcement currently reports
  `enforced: false` unless wired to live portfolio sources.
- RL/GNN/PPO/DQN modules under `ml/` are experimental research code, not live trading.
- Local runtime artifacts (trained `models/*.joblib`, `exports/`, caches, `.venv/`)
  are generated and git-ignored — they are not source artifacts.

## Safety Boundary

The platform produces research outputs and advisory recommendations only. No broker integration or live execution is included in the MVP.
