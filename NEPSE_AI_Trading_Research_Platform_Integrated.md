# NEPSE AI Trading Research Platform

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Purpose, Scope, and Intended Use](#2-purpose-scope-and-intended-use)
3. [System Overview](#3-system-overview)
4. [Reference Architecture](#4-reference-architecture)
5. [Core Platform Layers](#5-core-platform-layers)
6. [Backend Architecture](#6-backend-architecture)
7. [Database Design](#7-database-design)
8. [Data Platform and Ingestion Pipeline](#8-data-platform-and-ingestion-pipeline)
9. [Feature Engineering](#9-feature-engineering)
10. [Quantitative Research Layer](#10-quantitative-research-layer)
11. [AI and Machine Learning Layer](#11-ai-and-machine-learning-layer)
12. [Signal Fusion Engine](#12-signal-fusion-engine)
13. [Risk Engine](#13-risk-engine)
14. [Portfolio Optimization](#14-portfolio-optimization)
15. [Backtesting and Evaluation](#15-backtesting-and-evaluation)
16. [Explainable AI Layer](#16-explainable-ai-layer)
17. [Meta-Learning and MLOps](#17-meta-learning-and-mlops)
18. [API and Service Design](#18-api-and-service-design)
19. [Dashboard, Alerts, and User Interfaces](#19-dashboard-alerts-and-user-interfaces)
20. [Infrastructure and Deployment](#20-infrastructure-and-deployment)
21. [CI/CD Pipeline](#21-cicd-pipeline)
22. [Monitoring and Observability](#22-monitoring-and-observability)
23. [Security, Governance, and Compliance](#23-security-governance-and-compliance)
24. [Infrastructure Sizing and Budget Estimates](#24-infrastructure-sizing-and-budget-estimates)
25. [Implementation Roadmap](#25-implementation-roadmap)
26. [Production Readiness Checklist](#26-production-readiness-checklist)
27. [Risk Disclaimer](#27-risk-disclaimer)
28. [Final Summary](#28-final-summary)

---

## 1. Executive Summary

The **NEPSE AI Trading Research Platform** is a private, production-grade quantitative research and AI-assisted trading decision-support system designed for the Nepal Stock Exchange. It combines market data engineering, statistical research, machine learning, reinforcement learning, graph analytics, portfolio optimization, explainability, MLOps, and production infrastructure into a unified platform.

The system is intended for:

- Quantitative research and strategy development
- AI-based market signal generation
- Portfolio construction and risk-aware allocation
- Backtesting and walk-forward validation
- Model monitoring, retraining, and governance
- Research dashboards, alerts, and API-driven workflows

This platform does **not** guarantee trading profits. It is designed as a research, experimentation, and decision-support environment that requires rigorous validation before any real-world use.

---

## 2. Purpose, Scope, and Intended Use

### 2.1 Purpose

The purpose of this document is to consolidate the complete architecture, software design, implementation guidance, infrastructure plan, and production-readiness criteria for the NEPSE AI Trading Research Platform into a single cohesive specification.

### 2.2 Scope

This document covers:

- End-to-end system architecture
- Backend and service structure
- Database schema
- Data ingestion and feature engineering
- Quantitative research modules
- AI models including LSTM, XLM-R, PPO, DQN, HRL, GNN, and ensembles
- Signal fusion and risk management
- Portfolio optimization
- Backtesting and performance evaluation
- Explainability and SHAP-based attribution
- MLflow-based experiment tracking and model registry
- Docker, Kubernetes, CI/CD, monitoring, and deployment
- Production checklist and implementation roadmap

### 2.3 Intended Use

The platform should be used for:

- Research-oriented trading strategy development
- Historical simulation and evaluation
- Portfolio analytics
- Model comparison and experiment tracking
- Decision support through dashboards and alerts

It should **not** be treated as a fully autonomous financial advisor or profit-guaranteeing trading engine.

---

## 3. System Overview

At a high level, the platform follows the lifecycle below:

```text
Data Sources
  ↓
Data Ingestion and Validation
  ↓
PostgreSQL / TimescaleDB Storage
  ↓
Feature Engineering and Feature Store
  ↓
Quantitative Research and AI Models
  ↓
Signal Fusion Engine
  ↓
Risk Engine
  ↓
Portfolio Optimization
  ↓
Backtesting, Evaluation, and Explainability
  ↓
MLOps, Monitoring, Dashboard, Alerts, and APIs
```

The design emphasizes modularity, traceability, reproducibility, and safe research workflows.

---

## 4. Reference Architecture

### 4.1 High-Level Architecture

```text
NEPSE AI Trading Research Platform
│
├── Data Platform
│   ├── NEPSE Market Data APIs / Scrapers
│   ├── OHLCV Market Data
│   ├── Corporate Actions
│   ├── Financial Statements
│   ├── News and Social Data
│   ├── Economic Indicators
│   └── Feature Store
│
├── Quant Research Layer
│   ├── Technical Analysis
│   ├── Statistical Models
│   ├── Factor Models
│   ├── Regime Detection
│   ├── Correlation Analysis
│   └── Event Studies
│
├── AI Model Layer
│   ├── LSTM Forecasting
│   ├── XLM-R Sentiment Model
│   ├── PPO Trading Agent
│   ├── DQN Trading Agent
│   ├── Hierarchical Reinforcement Learning
│   ├── Graph Neural Networks
│   ├── Meta-Learning Engine
│   └── Ensemble Models
│
├── Decision Layer
│   ├── Signal Fusion Engine
│   ├── Risk Engine
│   └── Portfolio Optimization Engine
│
├── Evaluation Layer
│   ├── Backtesting
│   ├── Walk-Forward Testing
│   ├── Monte Carlo Testing
│   ├── Stress Testing
│   └── Benchmark Comparison
│
├── Explainability Layer
│   ├── SHAP
│   ├── Feature Importance
│   ├── Signal Attribution
│   └── Trade Explanation Engine
│
├── MLOps Layer
│   ├── MLflow
│   ├── Model Registry
│   ├── Auto Retraining
│   ├── Monitoring
│   └── Experiment Tracking
│
├── Infrastructure Layer
│   ├── FastAPI
│   ├── PostgreSQL / TimescaleDB
│   ├── Redis
│   ├── Docker
│   ├── Kubernetes
│   └── GPU Training Cluster
│
└── User Layer
    ├── Dashboard
    ├── Research Workbench
    ├── Alerts
    ├── Reports
    └── API
```

### 4.2 Component Interaction View

```text
User / Researcher
  ↓
Dashboard / Research Workbench
  ↓
FastAPI Gateway
  ↓
Service Layer
  ├── Authentication Service
  ├── Market Data Service
  ├── Feature Service
  ├── Signal Service
  ├── Portfolio Service
  ├── Backtest Service
  ├── ML Service
  └── Monitoring Service
  ↓
Persistence and Compute Layer
  ├── PostgreSQL / TimescaleDB
  ├── Redis Cache
  ├── MLflow Tracking Server
  ├── Model Registry
  └── GPU Workers
```

---

## 5. Core Platform Layers

### 5.1 Data Platform

Responsible for acquiring, validating, storing, and serving raw and processed data.

**Key datasets:**

- OHLCV market data
- Corporate actions
- Financial statements
- News and social media data
- Macroeconomic indicators
- Engineered features

### 5.2 Quant Research Layer

Provides classical quantitative research tools and statistical foundations for strategy design.

**Modules:**

- Technical analysis indicators
- ARIMA, VAR, and statistical forecasting models
- Value and momentum factor models
- Bull/bear regime detection
- Cross-stock correlation and co-movement studies
- Event studies around dividends, earnings, and market announcements

### 5.3 AI Layer

Provides predictive, classification, reinforcement learning, and graph-based intelligence.

**Model families:**

- LSTM for time-series forecasting
- XLM-R for multilingual sentiment analysis
- PPO and DQN for trading policy learning
- Hierarchical RL for allocation and execution separation
- GNNs for sector, correlation, and co-movement graphs
- Ensemble and meta-learning models

### 5.4 Portfolio and Risk Layer

Responsible for translating model outputs into risk-aware portfolio decisions.

**Components:**

- Position sizing
- Exposure control
- Drawdown protection
- Daily loss limits
- Portfolio optimization
- Performance analytics

### 5.5 Evaluation Layer

Ensures that signals and strategies are validated before deployment.

**Methods:**

- Backtesting
- Walk-forward testing
- Monte Carlo simulation
- Stress testing
- Benchmark comparison

### 5.6 Explainability Layer

Provides visibility into model and signal behavior.

**Outputs:**

- SHAP explanations
- Feature importance
- Signal attribution
- Trade explanation summaries

### 5.7 MLOps Layer

Manages model lifecycle, reproducibility, monitoring, retraining, and deployment.

**Capabilities:**

- Experiment tracking
- Model registry
- Model versioning
- Auto retraining
- Drift monitoring
- Deployment governance

---

## 6. Backend Architecture

### 6.1 Recommended Repository Structure

```text
backend/
├── app/
│   └── main.py
├── api/
│   ├── routes/
│   ├── dependencies/
│   └── schemas/
├── core/
│   ├── config.py
│   ├── security.py
│   └── logging.py
├── data/
│   ├── ingestion/
│   ├── validation/
│   └── loaders/
├── features/
├── ml/
│   ├── lstm/
│   ├── sentiment/
│   └── ensembles/
├── rl/
│   ├── ppo/
│   ├── dqn/
│   └── hierarchical/
├── gnn/
├── xai/
├── meta/
├── risk/
├── portfolio/
├── alerts/
├── backtesting/
├── mlops/
├── monitoring/
├── services/
├── repositories/
├── models/
└── tests/
```

### 6.2 Service Responsibilities

| Service | Responsibility |
|---|---|
| Authentication Service | User authentication, JWT handling, and RBAC enforcement |
| Market Data Service | Ingestion, retrieval, validation, and normalization of market data |
| Feature Service | Feature computation, storage, and retrieval |
| Signal Service | Signal generation, fusion, confidence scoring, and explanation linking |
| Portfolio Service | Portfolio allocation, exposure tracking, and risk-aware optimization |
| Backtest Service | Historical simulation, metrics generation, and scenario testing |
| ML Service | Model training, inference, registration, and lifecycle integration |
| Monitoring Service | Metrics, model drift, infrastructure health, and alerting |

---

## 7. Database Design

The platform should use **PostgreSQL** for relational data and **TimescaleDB** for time-series workloads where available.

### 7.1 Core Tables

#### `users`

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'researcher',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `stocks`

```sql
CREATE TABLE stocks (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) UNIQUE NOT NULL,
    company_name TEXT,
    sector TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `prices`

```sql
CREATE TABLE prices (
    id BIGSERIAL PRIMARY KEY,
    stock_id INT REFERENCES stocks(id),
    symbol VARCHAR(20) NOT NULL,
    trade_date DATE NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, trade_date)
);
```

#### `signals`

```sql
CREATE TABLE signals (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    signal VARCHAR(20) NOT NULL,
    confidence FLOAT,
    source_model TEXT,
    explanation JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### `models`

```sql
CREATE TABLE models (
    id UUID PRIMARY KEY,
    model_name TEXT NOT NULL,
    version TEXT NOT NULL,
    model_type TEXT,
    metrics JSONB,
    registry_uri TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 7.2 Recommended Additional Tables

#### `features`

```sql
CREATE TABLE features (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    feature_date DATE NOT NULL,
    features JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, feature_date)
);
```

#### `backtest_runs`

```sql
CREATE TABLE backtest_runs (
    id UUID PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    config JSONB NOT NULL,
    metrics JSONB,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT
);
```

#### `portfolio_snapshots`

```sql
CREATE TABLE portfolio_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    positions JSONB NOT NULL,
    total_value NUMERIC,
    cash NUMERIC,
    exposure FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 8. Data Platform and Ingestion Pipeline

### 8.1 Data Sources

The platform supports ingestion from:

- NEPSE market data sources
- Broker or vendor data feeds
- Corporate announcement sources
- Company financial disclosures
- News portals and social media sources
- Macroeconomic data providers

### 8.2 Ingestion Flow

```text
Scraper / API Client
  ↓
Raw Landing Zone
  ↓
ETL and Normalization
  ↓
Data Validation
  ↓
PostgreSQL / TimescaleDB
  ↓
Feature Store
```

### 8.3 Data Validation Rules

Validation should include:

- Missing value checks
- Duplicate symbol/date checks
- OHLC consistency checks: `low <= open/close <= high`
- Volume sanity checks
- Corporate action adjustments
- Outlier detection
- Schema validation

---

## 9. Feature Engineering

### 9.1 Core Market Features

```python
df["returns"] = df["close"].pct_change()
df["sma20"] = df["close"].rolling(20).mean()
df["ema20"] = df["close"].ewm(span=20).mean()
```

### 9.2 Technical Indicators

- RSI
- MACD
- SMA / EMA
- ATR
- Bollinger Bands
- OBV
- VWAP
- Volatility measures
- Momentum indicators
- Volume acceleration

### 9.3 Feature Store Requirements

The feature store should support:

- Point-in-time correctness
- Feature versioning
- Batch feature generation
- Training/inference feature consistency
- Metadata tracking
- Reproducible feature pipelines

---

## 10. Quantitative Research Layer

### 10.1 Technical Analysis

Technical analysis modules compute trend, momentum, volatility, and volume-derived indicators for downstream models and strategies.

### 10.2 Statistical Models

Recommended baseline models:

- ARIMA
- VAR
- Linear regression
- Logistic classification models
- Volatility models

### 10.3 Factor Models

Initial factors:

- Value
- Momentum
- Volatility
- Quality
- Liquidity
- Sector-relative strength

### 10.4 Regime Detection

Regime classification should identify:

- Bull market regime
- Bear market regime
- Sideways regime
- High-volatility regime
- Low-liquidity regime

### 10.5 Event Studies

Event study modules should evaluate abnormal returns and volatility around:

- Earnings announcements
- Dividend declarations
- Bonus/right share announcements
- Regulatory announcements
- Macro events

---

## 11. AI and Machine Learning Layer

### 11.1 LSTM Forecasting Pipeline

LSTM models forecast price, return, volatility, or directional movement from time-series windows.

#### Example PyTorch Model

```python
class LSTMModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(20, 128, batch_first=True)
        self.fc = nn.Linear(128, 1)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1])
```

#### Training Flow

1. Load OHLCV and engineered features
2. Scale features
3. Create rolling windows
4. Split train/validation/test datasets
5. Train model
6. Evaluate using RMSE, MAE, MAPE, and directional accuracy
7. Register model in MLflow

### 11.2 XLM-R Sentiment Pipeline

XLM-R is used for multilingual sentiment inference on news and text data.

```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

tokenizer = AutoTokenizer.from_pretrained("xlm-roberta-base")
model = AutoModelForSequenceClassification.from_pretrained("xlm-roberta-base")
```

Pipeline:

```text
News / Social Text
  ↓
Cleaning
  ↓
Tokenization
  ↓
XLM-R Inference
  ↓
Sentiment Score
  ↓
Confidence Score
```

Example output:

```json
{
  "sentiment": "bullish",
  "score": 0.87
}
```

### 11.3 PPO Trading Agent

PPO is used to learn trading policies under a simulated environment.

```python
from stable_baselines3 import PPO

model = PPO("MlpPolicy", env, verbose=1)
model.learn(total_timesteps=100000)
```

Reward function:

```python
reward = profit - drawdown_penalty + sharpe_bonus
```

Actions:

- BUY
- SELL
- HOLD

### 11.4 DQN Trading Agent

DQN is suitable for discrete action spaces.

```python
from stable_baselines3 import DQN

model = DQN("MlpPolicy", env)
model.learn(total_timesteps=100000)
```

### 11.5 Hierarchical Reinforcement Learning

Hierarchical RL separates high-level allocation decisions from low-level trade execution.

```python
class HighLevelAgent:
    pass

class LowLevelAgent:
    pass
```

High-level responsibilities:

- Market allocation
- Exposure management
- Sector allocation

Low-level responsibilities:

- Entry timing
- Exit timing
- Trade execution rules

### 11.6 Graph Neural Networks

GNNs model relationships between listed companies.

Graph edges may represent:

- Sector similarity
- Historical correlation
- Co-movement
- Supply-chain relationships where available

```python
from torch_geometric.nn import GCNConv

class GCN(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = GCNConv(32, 64)
        self.conv2 = GCNConv(64, 32)
```

Training objectives:

- Relationship prediction
- Sector influence modeling
- Signal propagation across correlated securities

### 11.7 Ensemble Models

Ensemble models combine multiple weak or specialized signals into a stronger aggregate decision.

Recommended ensemble methods:

- Weighted average ensemble
- Stacking
- Voting classifier
- Model confidence weighting
- Regime-aware model selection

---

## 12. Signal Fusion Engine

The Signal Fusion Engine combines model outputs into a single trade signal and confidence score.

### 12.1 Inputs

- LSTM forecast
- Sentiment score
- PPO policy output
- DQN policy output
- GNN relationship signal
- Market regime classification
- Risk state

### 12.2 Weighted Fusion

```python
score = (
    lstm * 0.30 +
    sentiment * 0.20 +
    rl * 0.30 +
    gnn * 0.20
)
```

### 12.3 Signal Mapping

| Score Range | Signal | Interpretation |
|---:|---|---|
| `>= 0.70` | BUY | Strong positive model consensus |
| `0.55 to 0.69` | WEAK_BUY | Moderate positive signal |
| `0.45 to 0.54` | HOLD | No strong directional edge |
| `0.30 to 0.44` | WEAK_SELL | Moderate negative signal |
| `< 0.30` | SELL | Strong negative model consensus |

### 12.4 Fusion Requirements

The fusion engine should support:

- Configurable model weights
- Regime-aware weighting
- Confidence calibration
- Model availability fallback
- Signal attribution
- Audit logging

---

## 13. Risk Engine

The Risk Engine prevents model outputs from directly becoming unsafe trades.

### 13.1 Core Rules

```python
MAX_RISK_PER_TRADE = 0.02
```

Recommended checks:

- Maximum risk per trade
- Maximum portfolio exposure
- Sector exposure limits
- Daily loss limits
- Maximum drawdown threshold
- Liquidity constraints
- Signal confidence threshold

### 13.2 Position Sizing

The default risk model uses a 2% rule:

```text
Position Size = Account Equity × 2% / Trade Risk
```

### 13.3 Drawdown Protection

If portfolio drawdown breaches configured thresholds, the system should:

1. Reduce new position sizes
2. Disable low-confidence signals
3. Trigger alerts
4. Require manual review before resuming aggressive allocation

---

## 14. Portfolio Optimization

Portfolio optimization converts approved signals into target allocations.

### 14.1 Supported Methods

- Mean-variance optimization
- Maximum Sharpe optimization
- Risk parity
- Equal risk contribution
- Sector-constrained allocation
- Regime-aware allocation

### 14.2 Example Methods

```python
weights = optimizer.max_sharpe()
weights = optimizer.risk_parity()
```

### 14.3 Portfolio Outputs

The portfolio engine should produce:

- Target weights
- Current vs target allocation
- Rebalancing instructions
- Exposure by sector
- Risk contribution by asset
- Expected volatility and drawdown estimates

---

## 15. Backtesting and Evaluation

### 15.1 Backtesting Flow

```text
Historical Data
  ↓
Feature Generation
  ↓
Strategy / Model Signal
  ↓
Execution Simulation
  ↓
Risk and Portfolio Rules
  ↓
Metrics and Reports
```

### 15.2 Evaluation Methods

- Backtesting
- Walk-forward testing
- Monte Carlo simulation
- Stress testing
- Benchmark comparison

### 15.3 Metrics

- CAGR
- Sharpe Ratio
- Sortino Ratio
- Maximum Drawdown
- Win Rate
- Profit Factor
- Volatility
- RMSE
- MAE
- MAPE
- Directional Accuracy

### 15.4 Benchmarking

Strategies should be compared against:

- NEPSE index benchmarks
- Sector benchmarks
- Buy-and-hold strategies
- Equal-weight portfolios
- Cash baseline

---

## 16. Explainable AI Layer

Explainability is required for research trust, debugging, and governance.

### 16.1 SHAP Integration

```python
import shap

explainer = shap.Explainer(model)
values = explainer(X)
```

### 16.2 Example Explanation Output

```text
RSI contribution:       +0.18
MACD contribution:      +0.11
Sentiment contribution: +0.07
```

### 16.3 Dashboard Requirements

The dashboard should expose:

- Feature contribution charts
- Model confidence
- Signal attribution
- Historical explanation drift
- Trade explanation summaries

---

## 17. Meta-Learning and MLOps

### 17.1 Meta-Learning Loop

```text
Train
  ↓
Evaluate
  ↓
Select
  ↓
Deploy
  ↓
Monitor
  ↓
Retrain
  ↓
Repeat
```

### 17.2 Meta-Learning Controller

```python
def meta_cycle():
    models = generate_models()
    best = evaluate_and_select(models)
    deploy(best)
```

Capabilities:

- Auto retraining
- Auto model selection
- Hyperparameter evolution
- Regime-specific model selection
- Performance degradation detection

### 17.3 MLflow Integration

```python
import mlflow

with mlflow.start_run():
    mlflow.log_param("epochs", 50)
    mlflow.log_metric("rmse", 0.12)
```

MLflow should track:

- Parameters
- Metrics
- Artifacts
- Model versions
- Training datasets
- Evaluation results

---

## 18. API and Service Design

### 18.1 FastAPI Application

```python
from fastapi import FastAPI

app = FastAPI(title="NEPSE AI Trading Research Platform")

@app.get("/health")
def health():
    return {"status": "ok"}
```

### 18.2 Example Endpoints

```python
@app.get("/signals")
def signals():
    return {"signals": []}

@app.post("/backtest")
def run_backtest(config: dict):
    return {"result": "success"}
```

### 18.3 Recommended API Domains

| Domain | Example Endpoints |
|---|---|
| Health | `GET /health` |
| Auth | `POST /auth/login`, `POST /auth/refresh` |
| Market Data | `GET /market/prices`, `POST /market/ingest` |
| Features | `GET /features/{symbol}` |
| Signals | `GET /signals`, `GET /signals/{symbol}` |
| Portfolio | `GET /portfolio`, `POST /portfolio/rebalance` |
| Backtesting | `POST /backtests`, `GET /backtests/{id}` |
| Models | `GET /models`, `POST /models/train` |
| Monitoring | `GET /metrics`, `GET /drift` |

---

## 19. Dashboard, Alerts, and User Interfaces

### 19.1 Dashboard

Recommended implementations:

- Streamlit for rapid research dashboards
- React for production-grade user interfaces

Dashboard modules:

- Market overview
- Signal explorer
- Portfolio analytics
- Backtest reports
- Model performance
- SHAP explanations
- Infrastructure health

### 19.2 Research Workbench

The research workbench should allow researchers to:

- Run experiments
- Compare model versions
- Inspect features
- Launch backtests
- Review explainability outputs
- Export reports

### 19.3 Alerts

Supported alert channels:

- Telegram
- Email
- Dashboard notifications
- Webhook integrations

Alert types:

- New high-confidence signal
- Drawdown breach
- Model drift detected
- Data pipeline failure
- API latency threshold breach
- GPU utilization anomaly

---

## 20. Infrastructure and Deployment

### 20.1 Docker Compose

```yaml
version: "3.9"

services:
  api:
    build: ./backend
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis

  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: nepse_ai
      POSTGRES_USER: nepse
      POSTGRES_PASSWORD: change_me
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7

  mlflow:
    image: ghcr.io/mlflow/mlflow
    ports:
      - "5000:5000"

volumes:
  postgres_data:
```

### 20.2 Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nepse-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nepse-api
  template:
    metadata:
      labels:
        app: nepse-api
    spec:
      containers:
        - name: api
          image: nepse-ai/api:latest
          ports:
            - containerPort: 8000
```

### 20.3 Kubernetes Components

- API Deployment
- Service
- Ingress
- Horizontal Pod Autoscaler
- PostgreSQL deployment or managed database
- Redis cache
- MLflow service
- Dashboard deployment
- GPU worker pods

---

## 21. CI/CD Pipeline

### 21.1 GitHub Actions Example

```yaml
name: CI

on:
  push:
    branches:
      - main

jobs:
  build-test-deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Lint
        run: echo "Run linting"

      - name: Test
        run: echo "Run tests"

      - name: Build Docker Image
        run: echo "Build image"

      - name: Deploy
        run: echo "Deploy application"
```

### 21.2 CI/CD Stages

1. Lint
2. Unit tests
3. Integration tests
4. Security scan
5. Build Docker images
6. Push images to registry
7. Deploy to staging
8. Run smoke tests
9. Deploy to production

---

## 22. Monitoring and Observability

### 22.1 Prometheus Metrics

Metrics to capture:

- API latency
- Request count
- Error rate
- GPU utilization
- CPU and memory usage
- Data ingestion success/failure
- Model drift
- Signal distribution
- Backtest job status

Example:

```python
REQUEST_COUNT.inc()
```

### 22.2 Grafana Dashboards

Recommended dashboards:

- API performance
- Infrastructure health
- GPU utilization
- Data pipeline status
- Model performance
- Model drift
- Trading strategy performance
- Portfolio risk metrics

### 22.3 Logging

Logs should be structured and include:

- Request ID
- User ID where applicable
- Service name
- Timestamp
- Severity
- Model version
- Strategy ID
- Error trace

---

## 23. Security, Governance, and Compliance

### 23.1 Authentication and Authorization

Recommended controls:

- JWT authentication
- Role-based access control
- Strong password hashing
- Token expiry and refresh flow
- Principle of least privilege

### 23.2 Data Security

Controls:

- Encrypted credentials
- Secrets management
- Database backups
- Network isolation
- Audit logs
- Access reviews

### 23.3 Model Governance

Each production model should include:

- Version ID
- Training dataset reference
- Evaluation metrics
- Approval status
- Explainability report
- Deployment timestamp
- Rollback path

---

## 24. Infrastructure Sizing and Budget Estimates

### 24.1 Sizing Options

| Tier | CPU | RAM | GPU | Recommended Use |
|---|---:|---:|---|---|
| Student Prototype | 4–6 cores | 16 GB | Optional | Learning, proof of concept |
| Starter | 8 cores | 32 GB | RTX 4060 | Small-scale research |
| Research | 16 cores | 64 GB | RTX 4070 / RTX 4090 | Model training and experimentation |
| Production | 32+ cores | 64–256 GB | Multiple GPUs | Production-grade research platform |
| Enterprise | 64+ cores | 256 GB | 4× A100 or equivalent | Institutional-scale training and serving |

### 24.2 Budget Estimates

| Tier | Estimated Cost |
|---|---:|
| Student Prototype | USD 0–50/month |
| Starter Workstation | USD 1,500–2,500 one-time |
| Research Server | USD 4,000–8,000 one-time or USD 100–300/month cloud |
| Institutional Scale | USD 1,000+/month cloud |
| Enterprise Cluster | USD 50,000+ one-time or equivalent managed cloud cost |

---

## 25. Implementation Roadmap

### 25.1 Sprint Plan

| Sprint | Focus Area | Key Deliverables |
|---:|---|---|
| 1 | Data Ingestion | Scrapers/API clients, raw data landing, validation rules |
| 2 | Database | PostgreSQL schema, indexes, migrations, TimescaleDB setup |
| 3 | Indicators | Technical indicators, feature store, feature validation |
| 4 | LSTM | Forecasting model, training pipeline, evaluation metrics |
| 5 | Dashboard | Market overview, signal viewer, basic analytics |
| 6 | Sentiment | XLM-R pipeline, news ingestion, sentiment scoring |
| 7 | Reinforcement Learning | PPO and DQN environments, reward functions, simulations |
| 8 | GNN | Graph construction, relationship modeling, GCN prototype |
| 9 | Explainability | SHAP integration, signal attribution, dashboard explanations |
| 10 | Meta-Learning | Auto retraining, model selection, hyperparameter evolution |
| 11 | MLOps | MLflow tracking, model registry, deployment workflows |
| 12 | Production Deployment | Docker/Kubernetes, monitoring, backups, production checklist |

### 25.2 End-to-End Implementation Flow

```text
Collect Data
  ↓
Store Data
  ↓
Create Features
  ↓
Train Models
  ↓
Generate Signals
  ↓
Apply Risk Filters
  ↓
Execute Portfolio Logic
  ↓
Backtest
  ↓
Deploy Best Model
  ↓
Monitor and Retrain
```

---

## 26. Production Readiness Checklist

### 26.1 Data

- [ ] Data validation implemented
- [ ] Duplicate detection implemented
- [ ] Corporate action handling implemented
- [ ] Missing data policy defined
- [ ] Feature store supports point-in-time correctness

### 26.2 Models

- [ ] Model versioning enabled
- [ ] MLflow tracking enabled
- [ ] Evaluation metrics logged
- [ ] Explainability generated
- [ ] Model drift monitoring configured
- [ ] Rollback strategy defined

### 26.3 Backend and APIs

- [ ] Health endpoint available
- [ ] API input validation implemented
- [ ] Error handling standardized
- [ ] Service-level tests implemented
- [ ] API documentation generated

### 26.4 Security

- [ ] JWT authentication implemented
- [ ] RBAC implemented
- [ ] Secrets management configured
- [ ] Security audit completed
- [ ] Audit logging enabled

### 26.5 Infrastructure

- [ ] Docker Compose working
- [ ] Kubernetes manifests prepared
- [ ] Database backup strategy implemented
- [ ] Disaster recovery plan documented
- [ ] Monitoring dashboards configured
- [ ] Alert thresholds configured

### 26.6 Testing

- [ ] Unit tests implemented
- [ ] Integration tests implemented
- [ ] Backtesting validation completed
- [ ] Load testing completed
- [ ] Smoke tests included in CI/CD

---

## 27. Risk Disclaimer

This platform is designed for research and decision support only. It does not guarantee profits, prevent losses, or replace independent financial judgment. Trading and investing involve substantial risk, including the possible loss of capital. All models, signals, and strategies must be validated through robust testing, stress testing, and ongoing monitoring before any practical use.

---

## 28. Final Summary

The NEPSE AI Trading Research Platform is a full-stack, production-oriented blueprint for building a private quantitative research and AI-assisted trading system. It integrates:

- A robust data platform
- Quantitative research modules
- Multi-model AI and reinforcement learning
- Graph neural networks
- Signal fusion
- Risk-aware portfolio logic
- Backtesting and evaluation
- Explainability
- MLflow-based MLOps
- Docker/Kubernetes deployment
- Monitoring, governance, and production-readiness controls

When implemented carefully, the platform can serve as a powerful research environment for NEPSE-focused market analysis, strategy development, and AI-assisted decision support.
