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
- Docker Compose for local infrastructure
- pytest and ruff for quality gates

## Safety Boundary

The platform produces research outputs and advisory recommendations only. No broker integration or live execution is included in the MVP.
