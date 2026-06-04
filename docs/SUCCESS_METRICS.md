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
- Test suite passes.
- `/health` endpoint returns status `ok`.

