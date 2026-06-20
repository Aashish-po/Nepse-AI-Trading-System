# Backend

FastAPI application with business logic, database models, and REST API routes.

## Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── api/routes/          # REST API endpoints
│   ├── core/              # Config, logging, security
│   ├── models/            # SQLAlchemy ORM models
│   ├── schemas/           # Pydantic request/response contracts
│   ├── services/          # Business logic layer
│   └── db/                # Database session & migrations
└── tests/                 # pytest suite
```

## API Routes

| Category | Routes |
|----------|--------|
| Auth | `/auth/register`, `/auth/login` |
| Health | `/health`, `/health/live`, `/health/ready`, `/metrics` |
| Market | `/market/prices`, `/market/ingest`, `/market/ingest/batch` |
| Features | `/features/generate`, `/features/generate-batch`, `/features/generate-multi` |
| Data Quality | `/data-quality/*` (trust scores, reports, alerts, modes) |
| Strategies | `/strategies/*` (CRUD, backtests, benchmarks) |
| Signals | `/signals/*` (heatmap, evaluation) |
| ML | `/ml/train`, `/ml/models`, `/ml/predict/{symbol}` |
| LSTM | `/lstm/train`, `/lstm/predict` |
| Portfolio | `/portfolio/account`, `/portfolio/optimize` |
| Explainability | `/explain/*` (SHAP feature importance, predictions) |
| MLOps | `/mlops/*` (champion selection, retraining, evolution) |
| Analytics | `/analytics/*` (market overview, signals, portfolio) |
| Alerts | `/alerts/evaluate`, `/alerts/*` |
| Scheduler | `/scheduler/*` (background jobs) |

## Services

- **ingestion.py** - Data ingestion from multiple sources
- **data_quality.py** - Trust scoring and quality validation
- **feature.py** - Technical indicator calculations
- **strategy.py** - Strategy registry and backtesting
- **signal_fusion.py** - Signal combination with confidence scoring
- **risk_manager.py** - Position sizing and risk controls
- **portfolio_optimization.py** - Allocation algorithms
- **model_governance.py** - Model approval workflow
- **mlops.py** - Model selection and retraining orchestration

## Development

```bash
# Run API
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --app-dir .

# Run tests
python -m pytest backend/tests/ -v

# Lint
python -m ruff check backend/

# Type check
mypy backend/ --ignore-missing-imports --explicit-package-bases
```
