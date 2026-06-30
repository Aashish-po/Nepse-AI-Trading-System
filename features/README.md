# Features

Technical indicator calculations and feature engineering for NEPSE stocks.

## Indicators

| Category | Indicators |
|----------|----------|
| Trend | SMA, EMA, MACD |
| Momentum | RSI |
| Volatility | ATR, rolling volatility |
| Volume | Volume ratio |
| Price | Daily returns, price range |

## Structure

```
features/
├── indicators.py      # Technical indicator functions
└── __init__.py
```

> Point-in-time feature storage lives in the backend feature service
> (`backend/app/services/feature.py`), not in this package.

## Usage

```python
from features.indicators import compute_rsi, compute_sma

# Calculate features for a symbol
features = {
    "rsi": compute_rsi(prices, period=14),
    "sma_20": compute_sma(prices, period=20),
    "sma_50": compute_sma(prices, period=50),
}
```

## Point-in-Time Store

Features are stored with date stamps to prevent look-ahead bias during backtesting.
