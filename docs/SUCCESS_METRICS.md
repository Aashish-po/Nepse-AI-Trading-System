# MVP Success Metrics

## Research Metrics

- Sharpe ratio target: greater than 1.2
- Maximum drawdown target: less than 20%
- Win rate target: greater than 55%

These targets are research gates, not profit guarantees.

## Data Reliability Metrics

- Daily OHLCV completeness report is available.
- Missing trading days are detected.
- Data trust score is calculated before feature generation.
- Low-trust data is blocked or flagged.

## Backtesting Realism Metrics

- Fees are modeled.
- Slippage is modeled.
- Liquidity filters are modeled.
- Cash tracking and transaction logs are modeled.
- Equity curve is generated for every backtest.

## Engineering Metrics

- API, database, ingestion foundation, features foundation, and dashboard can run locally.
- Lint passes: `python -m ruff check backend/`.
- Test suite passes: `python -m pytest backend/tests/ -v`.
- Health endpoints respond: `/health` returns status `ok`, with `/health/live` and
  `/health/ready` for liveness/readiness and Prometheus metrics at `/metrics`.
- Streamlit dashboard (`dashboard/app.py`) launches and reaches the backend.
- Database migrations apply cleanly (Alembic revisions `0001`–`0011`).
- Data-quality gate enforces hard blocks on unsafe data and soft weighting on warning data.

These engineering metrics gate development quality; the research metrics above are
research gates, not profit guarantees.
