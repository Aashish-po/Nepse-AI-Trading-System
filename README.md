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

## Project Structure

```text
backend/
  app/
    main.py           # FastAPI application entry point
    api/
      routes/
        health.py     # Health check endpoint
        auth.py       # Authentication endpoints
        market.py     # Market data endpoints
    core/
      config.py       # Application configuration
      logging.py      # Logging configuration
    models/
      stock.py        # Stock ORM model
      price.py        # Price ORM model
      ...             # Other models (signal, strategy, trade, etc.)
    schemas/
      market.py       # Pydantic schemas for market data
    services/
      market.py       # Market data business logic
    db/
      session.py      # Database session management
      migrations/     # Alembic migrations
  tests/
    test_health.py
    test_auth.py
    test_market.py
    conftest.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check endpoint |
| POST | /ingest | Ingest market price data for a stock |
| GET | /market/prices | List price data (optional symbol filter) |

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

## Docker

```powershell
docker compose -f infra/docker-compose.yml up --build
```

## Research Boundary

The MVP is intentionally limited to ingestion, data quality, features, realistic backtesting, strategy research, dashboards, and advisory outputs. Live trading, broker execution, and autonomous financial advice are out of scope.
