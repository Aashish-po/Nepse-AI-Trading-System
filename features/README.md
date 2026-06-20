# Features

Technical indicator calculations and feature engineering for NEPSE stocks.

## Indicators

| Category | Indicators |
|----------|----------|
| Trend | SMA, EMA, ADX, MACD |
| Momentum | RSI, ROC, Stochastic |
| Volatility | ATR, Bollinger Bands |
| Volume | OBV, Volume MA |
| Returns | Daily returns, volatility |

## Structure

```
features/
├── indicators.py      # Technical indicator functions
├── feature_store.py   # Point-in-time feature storage
├── calculators.py     # Feature calculation utilities
└── __init__.py
```

## Usage

```python
from features.indicators import calculate_rsi, calculate_sma

# Calculate features for a symbol
features = {
    "rsi": calculate_rsi(prices, window=14),
    "sma_20": calculate_sma(prices, window=20),
    "sma_50": calculate_sma(prices, window=50),
}
```

## Point-in-Time Store

Features are stored with date stamps to prevent look-ahead bias during backtesting.
