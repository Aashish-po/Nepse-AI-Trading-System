# NEPSE AI Trading Research Platform

Private research and decision-support platform for NEPSE market data, quantitative research, realistic backtesting, risk-aware portfolio analysis, and AI-assisted signal exploration.

This project is research-only. It does not provide financial advice, guarantee profit, or execute live trades.

## Phase 0 Status

Phase 0 establishes the project foundation:

- Product scope and research-only boundary
- MVP success metrics
- Default technical stack
- Initial repository structure
- Foundation documentation
- Environment configuration template
- Minimal FastAPI skeleton and health smoke test

## MVP Stack

- Backend: Python, FastAPI
- Database: PostgreSQL, with TimescaleDB when available
- Cache/jobs: Redis
- ML tracking: MLflow
- Dashboard: Streamlit
- Research notebooks: Jupyter
- Infrastructure: Docker Compose first, Kubernetes later
- Testing: pytest

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements-dev.txt
copy .env.example .env
pytest
uvicorn backend.app.main:app --reload
```

Open `http://127.0.0.1:8000/health` to verify the API.

## Docker

```powershell
docker compose -f infra/docker-compose.yml up --build
```

## Research Boundary

The MVP is intentionally limited to ingestion, data quality, features, realistic backtesting, strategy research, dashboards, and advisory outputs. Live trading, broker execution, and autonomous financial advice are out of scope.

# Nepse-AI-Trading-System
