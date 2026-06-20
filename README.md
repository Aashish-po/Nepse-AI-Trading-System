<div align="center">

# 📈 NEPSE AI Trading Research Platform

**An advisory-only quantitative research platform for the Nepal Stock Exchange (NEPSE) — combining data-quality assurance, technical analysis, realistic backtesting, and explainable ML signal fusion.**

[![CI](https://github.com/Aashish-po/Nepse-AI-Trading-System/actions/workflows/ci.yml/badge.svg)](https://github.com/Aashish-po/Nepse-AI-Trading-System/actions/workflows/ci.yml)
[![Docker Publish](https://github.com/Aashish-po/Nepse-AI-Trading-System/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Aashish-po/Nepse-AI-Trading-System/actions/workflows/docker-publish.yml)
[![Dependencies](https://img.shields.io/librariesio/github/Aashish-po/Nepse-AI-Trading-System)](https://github.com/Aashish-po/Nepse-AI-Trading-System/network/dependencies)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Version](https://img.shields.io/badge/version-1.0%20(MVP)-success.svg)](#-implementation-roadmap)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey.svg)](#-license)

</div>

> [!IMPORTANT]
> **This project is research-only.** It does **not** provide financial advice, guarantee profit, or execute live trades. All outputs are advisory and require human review. There is no live broker execution and no autonomous trading.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running with Docker](#running-with-docker)
- [Usage](#-usage)
- [API Reference](#-api-reference)
- [Project Structure](#-project-structure)
- [Implementation Roadmap](#-implementation-roadmap)
- [Testing & Quality](#-testing--quality)
- [Contributing](#-contributing)
- [Research Boundary](#-research-boundary)
- [License](#-license)
- [Maintainer](#-maintainer)

---

## 🔍 Overview

The **NEPSE AI Trading Research Platform** is a comprehensive quantitative research system built specifically for the Nepal Stock Exchange. It delivers an end-to-end workflow — from raw market-data ingestion through strategy development, realistic backtesting, and advisory signal generation — designed for individual traders, finance students, and small quant teams.

NEPSE is a small, illiquid market where data quality and execution assumptions are critical. This platform addresses that by enforcing **trust-score data-quality gates**, modelling **realistic transaction costs**, and making every signal **explainable**.

### MVP Success Targets

These are research/evaluation gates — **not** guarantees of trading profit.

| Metric | Target |
| --- | --- |
| Sharpe Ratio | > 1.2 |
| Maximum Drawdown | < 20% |
| Win Rate | > 55% |
| Data Trust (90% of symbols) | ≥ 0.7 |
| Feature Freshness | < 24h |

---

## ✨ Key Features

- **Multi-source data ingestion** — ShareSansar, MeroLagani scraper with manual CSV fallbacks.
- **Data-quality gating** — automated trust scoring (completeness, consistency, freshness, volume, cross-source) with `NORMAL` / `DEGRADED` / `SAFE_MODE` system states.
- **Realistic backtesting** — fees (0.5%), slippage (5 bps), liquidity filters, partial fills, execution delay, stop-loss / take-profit / trailing-stop exits, and benchmark comparison.
- **Explainable signal fusion** — combines technical, ML, and sentiment signals with calibrated confidence and feature attribution (SHAP).
- **Machine learning suite** — baseline models (logistic / random forest / XGBoost), LSTM forecasting, XLM-R sentiment, and experimental RL/GNN research modules (PPO, DQN, GNN, meta-learning).
- **MLOps & governance** — model registry, drift monitoring, automated retraining, and human-approval promotion gates.
- **12-page Streamlit dashboard** + a notebook-driven research workflow and a full REST API with auto-generated Swagger docs.

---

## 🏗 Architecture

```text
Data Sources → Ingestion → Validation → Database → Feature Engineering
  → Data Quality → Trust Scoring → Backtesting → Dashboard / API / Alerts
```

The system is organized into three layers:

1. **User interfaces** — Streamlit dashboard, Jupyter notebooks, and the FastAPI REST API.
2. **Backend services** — ingestion, data quality, feature engineering, backtesting, signal fusion, risk management, ML training/inference, and MLflow tracking.
3. **Data & storage** — PostgreSQL (optionally TimescaleDB), Redis cache/queue, and disk artifacts for models, datasets, and backtest results.

> See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system design and data model.

---

## 🧰 Tech Stack

| Layer | Technologies |
| --- | --- |
| **Backend & API** | Python 3.12, FastAPI, Uvicorn, Pydantic v2 |
| **Database & ORM** | PostgreSQL 13+ (TimescaleDB optional), SQLAlchemy 2.0, Alembic |
| **Cache & Queue** | Redis |
| **ML & Tracking** | scikit-learn, XGBoost, PyTorch (LSTM/RL), MLflow, NumPy/Pandas |
| **Dashboard & Research** | Streamlit, Jupyter, Plotly |
| **DevOps** | Docker & Docker Compose, GitHub Actions, Kubernetes (`infra/k8s/`) |
| **Quality** | pytest, ruff, mypy |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.12**
- **PostgreSQL 13+** and **Redis** (or use [Docker Compose](#running-with-docker), which provisions both)
- **Git**

### Installation

<details open>
<summary><strong>Windows (PowerShell)</strong></summary>

```powershell
# 1. Clone the repository
git clone https://github.com/Aashish-po/Nepse-AI-Trading-System.git
cd "Nepse-AI-Trading-System"

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
python -m pip install -U pip
pip install -r requirements-dev.txt

# 4. Create your environment file
copy .env.example .env
```

</details>

<details>
<summary><strong>macOS / Linux (bash)</strong></summary>

```bash
# 1. Clone the repository
git clone https://github.com/Aashish-po/Nepse-AI-Trading-System.git
cd Nepse-AI-Trading-System

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
python -m pip install -U pip
pip install -r requirements-dev.txt

# 4. Create your environment file
cp .env.example .env
```

</details>

### Configuration

Copy `.env.example` to `.env` and fill in the required values. Key variables:

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET_KEY` | Secret for JWT auth (min. 32 chars) |
| `SHARESANSAR_API_URL` | Primary data source endpoint |
| `MLFLOW_TRACKING_URI` | MLflow tracking server URI |

> [!WARNING]
> Never commit your `.env` file or any secrets. See [`Documents/7_Security.md`](Documents/7_Security.md) for the full secrets-management policy.

### Running with Docker

The fastest way to bring up the full stack (PostgreSQL, Redis, API, dashboard, MLflow):

```bash
docker compose -f infra/docker-compose.yml up --build
```

---

## 📖 Usage

### Run the API

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --app-dir .
```

- Health check: <http://127.0.0.1:8000/health>
- Interactive Swagger UI: <http://127.0.0.1:8000/docs>

### Run the Dashboard

```bash
pip install -r dashboard/requirements-dashboard.txt
streamlit run dashboard/app.py
```

The dashboard runs at <http://localhost:8501> with 12 pages: Market Overview, Strategies, Backtesting, Signals, Features, Data Sources, Alerts, System Status, ML Models, Analytics, MLOps, and Explainability.

### Seed Symbol Data

```bash
python scripts/seed_symbols.py
```

Populates the database with NEPSE stock symbols for initial testing.

### Database Migrations

```bash
alembic upgrade head                              # apply latest schema
alembic revision --autogenerate -m "description"  # create a new migration
alembic downgrade -1                              # roll back one revision
```

### Research Notebooks

The platform supports a notebook-driven research cycle:

```text
1. Idea → 2. Notebook Experiment → 3. Backtest → 4. Strategy Integration → 5. Dashboard/Report
```

Start with [`research/notebooks/`](research/notebooks/) (`01_idea_to_backtest.ipynb`, `02_backtest_and_export.ipynb`, `03_integrate_bundle.ipynb`). All experimental results must be validated through the tested backtesting pipeline before integration.

---

## 🔌 API Reference

The REST API exposes auth, market data, features, data quality, strategies/backtests, signals, ML, portfolio, explainability, governance, MLOps, and analytics routes. Full interactive docs are available at `/docs` when the API is running.

<details>
<summary><strong>View full endpoint table</strong></summary>

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/health` | Health check (status, environment, version, scope) |
| GET | `/health/live` | Liveness probe (process up) |
| GET | `/health/ready` | Readiness probe (database reachable) |
| GET | `/metrics` | Prometheus metrics (request counts, latency histogram) |
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login and receive access token |
| GET | `/market/prices` | List price data with optional symbol filter |
| POST | `/market/ingest` | Ingest a single price record for a stock |
| POST | `/market/ingest/batch` | Batch ingest OHLCV data for a date range |
| POST | `/features/generate` | Compute features for a single symbol/date |
| POST | `/features/generate-batch` | Compute features for a date range (single symbol) |
| POST | `/features/generate-multi` | Compute features across multiple symbols |
| GET | `/data-quality/trust/{symbol}/{date}` | Get trust score and quality details |
| GET | `/data-quality/safe/{symbol}/{date}` | Check if data is safe to use (trust >= 0.7) |
| GET | `/data-quality/summary/{symbol}` | Symbol quality summary (avg trust, unsafe days, issues) |
| POST | `/data-quality/reports/daily` | Generate daily data quality report |
| GET | `/data-quality/alerts` | List data quality alerts |
| POST | `/data-quality/alerts/{alert_id}/acknowledge` | Acknowledge an alert |
| GET | `/data-quality/trends/{symbol}` | Trust score trend over 30 days |
| GET | `/data-quality/freshness/{symbol}/{date}` | Check data freshness (last update vs expected) |
| GET | `/data-quality/system-mode` | Get system mode (NORMAL / DEGRADED / SAFE_MODE) |
| GET | `/data-quality/cross-validate/{symbol}/{date}` | Cross-validate price across active data sources |
| GET | `/data-quality/source-accuracy/{source_id}` | Accuracy score for a data source |
| GET | `/data-quality/weighted-price/{symbol}/{date}` | Source-weighted average price |
| GET | `/data-quality/source-drift/{source_id}` | Detect drift in a data source's record volume |
| GET | `/data-quality/mode-history` | System mode history |
| POST | `/data-quality/sources/recover-blacklisted` | Attempt to recover blacklisted sources |
| POST | `/data-quality/trust/apply-decay` | Apply time-based decay to old trust scores |
| POST | `/strategies/` | Create a new strategy |
| GET | `/strategies/` | List all strategies |
| GET | `/strategies/{strategy_id}` | Get strategy details |
| POST | `/strategies/backtests` | Run backtest for a strategy |
| GET | `/strategies/backtests/{backtest_id}` | Get backtest results |
| POST | `/strategies/benchmarks/compare` | Compare strategy vs buy-and-hold / NEPSE |
| POST | `/ml/train` | Train an ML model |
| GET | `/ml/models` | List trained models |
| GET | `/ml/predict/{symbol}` | Get model prediction for a symbol |
| POST | `/portfolio/account` | Create/reset a portfolio account |
| GET | `/portfolio/account/snapshot` | Portfolio snapshot (equity, cash, positions) |
| POST | `/portfolio/optimize` | Optimize allocation (equal / risk-parity / mean-variance) |
| GET | `/explain/models/{model_id}/importance` | Global feature importance (SHAP + fallbacks) |
| POST | `/explain/models/{model_id}/predict` | Local attribution + trade explanation |
| GET | `/governance/models` | List models by governance state |
| POST | `/governance/models/{model_id}/submit` | Submit a model for approval |
| POST | `/governance/models/{model_id}/approve` | Approve a model |
| POST | `/governance/models/{model_id}/production` | Mark an approved model production-ready |
| GET | `/mlops/champion` | Select best model by metric |
| GET | `/mlops/rank` | Rank registered models by metric |
| GET | `/mlops/models/{model_id}/retrain-assessment` | Assess whether a model needs retraining |
| POST | `/mlops/retrain` | Trigger a retraining run |
| POST | `/mlops/evolve` | Evolutionary hyperparameter search |
| GET | `/analytics/market-overview` | Market overview with top gainers/losers |
| GET | `/analytics/signals` | Signal explorer with filters and summary |
| POST | `/analytics/portfolio` | Portfolio analytics from an equity curve |
| POST | `/alerts/evaluate` | Evaluate rule-based alerts |

</details>

---

## 📂 Project Structure

<details>
<summary><strong>View directory tree</strong></summary>

```text
.
├── .github/workflows/        # CI (ci.yml), image publish (docker-publish.yml), Pages
├── AGENTS.md                 # Common dev commands
├── pyproject.toml            # Project + ruff/mypy config
├── requirements.txt          # Runtime dependencies
├── requirements-dev.txt      # Dev/test dependencies
├── alembic.ini               # Alembic config
├── pytest.ini                # pytest config
│
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI application entry point
│   │   ├── core/             # config, logging, security, dependencies
│   │   ├── api/routes/       # auth, health, market, features, data_quality, strategies,
│   │   │                     #   signals, ml, lstm, portfolio, explainability, mlops, analytics
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response contracts
│   │   ├── services/         # Business logic (ingestion, backtest, signal_fusion, ...)
│   │   └── db/migrations/    # Alembic revisions 0001 … 0011
│   └── tests/                # pytest suite (incl. phase gates)
│
├── ml/                       # ML / research modules (training, lstm, sentiment, ppo, dqn, gnn, ...)
├── strategies/               # Strategy definitions and experiments
├── backtesting/              # Backtesting helpers
├── features/                 # Feature helpers
├── data/                     # Data loaders, ingestion, validation
├── scripts/                  # seed_symbols.py, smoke_test.py, backup_db.sh
│
├── dashboard/                # Streamlit dashboard (single app, 12 pages)
├── research/notebooks/       # Idea → backtest → integrate notebook workflow
├── docs/                     # Reference specs (ARCHITECTURE, PHASES, SUCCESS_METRICS, ...)
├── infra/                    # docker-compose.yml, docker/, k8s/
└── models/                   # Trained model artifacts *.joblib (gitignored)
```

</details>

---

## 🗺 Implementation Roadmap

All 15 phases (0–14) are implemented in code and covered by tests. Phase numbering matches the phase-gated test suite (e.g. `test_phase8_gate.py`, `test_phase10_integration.py`, `test_phase14_experimental.py`).

| Phase | Focus Area | Key Deliverables |
| --- | --- | --- |
| 0 | Foundation | Project structure, env config, CI, `/health` endpoint |
| 1 | Backend & Database | FastAPI skeleton, SQLAlchemy ORM, Alembic migrations, JWT auth/RBAC, symbol seeding |
| 2 | Data Ingestion & Quality | Ingestion service, validation rules, trust scoring, data-quality gate, alerting |
| 3 | Feature Engineering | Technical indicators (RSI/SMA/EMA/MACD/ATR), returns/volatility, point-in-time feature store |
| 4 | Data Quality & Reliability | Trust model, daily reports, quality alerts, system modes (NORMAL/DEGRADED/SAFE_MODE) |
| 5 | Strategy & Backtesting | Strategy registry, realistic backtesting, benchmark comparison |
| 6 | Research Workflow & Dashboard | Streamlit dashboard, notebook workflow, export validation |
| 7 | Baseline ML | Logistic regression, random forest, XGBoost, walk-forward training, promotion gates |
| 8 | LSTM & Sentiment | LSTM next-day forecasting, XLM-R/lexicon sentiment, NEPSE market calendar |
| 9 | Signal Fusion & Risk | Signal fusion engine, risk manager, position sizing (advisory; `enforced: false`) |
| 10 | Portfolio Optimization | In-memory account simulation, allocation methods (equal/risk-parity/mean-variance) |
| 11 | Explainability (SHAP) | Feature importance, local attribution, trade explanations, model governance |
| 12 | MLOps / Monitoring / Retraining | Model selection, auto-retraining, hyperparameter evolution, drift monitoring |
| 13 | Production Hardening & Deployment | Docker images, Kubernetes manifests, CI/CD, Prometheus monitoring, DB backups |
| 14 | Experimental AI | PPO, DQN, GNN, ensembles, meta-learning (experimental research only) |

> Phase 14 RL/GNN modules are experimental research code. Live broker execution and autonomous trading remain **out of scope**.

---

## ✅ Testing & Quality

```bash
# Run the full test suite
python -m pytest backend/tests/ -v

# Lint
python -m ruff check backend/

# Type check
mypy backend/ --ignore-missing-imports --explicit-package-bases
```

The CI pipeline ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs ruff, the full pytest suite, import smoke tests, and mypy on every push and pull request to `main` and `develop`.

---

## 🤝 Contributing

Contributions are welcome! To get started:

1. **Fork** the repository and create a feature branch from `main` (e.g. `git checkout -b feature/your-feature`).
2. **Set up** your environment (see [Installation](#installation)).
3. **Make your changes**, following the existing code style.
4. **Validate locally** before pushing:

   ```bash
   python -m ruff check backend/
   python -m pytest backend/tests/ -v
   ```

5. **Commit** with a clear message and **open a pull request** against `main`, describing the change and linking any related issues.

Please ensure all tests pass and lint is clean — CI must be green before a PR can be merged. Common development commands are documented in [`AGENTS.md`](AGENTS.md).

---

## 🛡 Research Boundary

This platform is intentionally limited to **ingestion, data quality, features, realistic backtesting, strategy research, dashboards, and advisory outputs**. The following are explicitly out of scope:

- ❌ Live broker execution or order placement
- ❌ Autonomous / automated trading
- ❌ Financial advice or guaranteed returns
- ❌ Options, derivatives, or forex (equities only)

All advisory outputs require human review. See [`docs/RISK_DISCLAIMER.md`](docs/RISK_DISCLAIMER.md) for the full disclaimer.

---

## 📜 License

This project is currently **proprietary — all rights reserved**. No license for reuse, redistribution, or modification is granted unless a `LICENSE` file is added to the repository. For usage or collaboration inquiries, please contact the maintainer.

---

## 👤 Maintainer

**Aashish Paudel**

- GitHub: [@Aashish-po](https://github.com/Aashish-po)
- Repository: [Nepse-AI-Trading-System](https://github.com/Aashish-po/Nepse-AI-Trading-System)

> Built for the NEPSE quantitative-research community. ⭐ Star the repo if you find it useful!
