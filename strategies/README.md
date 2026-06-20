# Strategies

Strategy definitions and experimental implementations for NEPSE trading.

## Structure

```
strategies/
├── __init__.py
├── base.py           # Base strategy interface
├── moving_average.py # Moving average crossover
├── rsi_reversion.py  # RSI mean-reversion
└── experimental/     # Research strategies
```

## Strategy Interface

All strategies follow a common interface:

```python
class Strategy(Protocol):
    def generate_signals(self, symbol: str, date: date) -> dict:
        """Return trading signals for given symbol/date."""
        ...

    def get_parameters(self) -> dict:
        """Return strategy configuration."""
        ...
```

## Available Strategies

- **Moving Average Crossover**: Price crosses above/below SMA/EMA
- **RSI Reversion**: Buy when RSI < 30, sell when RSI > 70
- **Experimental**: PPO/DQN strategies (Phase 14, research-only)

## Backtesting

Strategies are tested through the backtesting engine which applies:

- 0.5% transaction fees
- 5 bps slippage
- Liquidity filters
- Partial fill simulation
- Execution delay
