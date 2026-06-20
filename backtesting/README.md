# Backtesting

Realistic backtesting engine with transaction cost modeling and portfolio simulation.

## Features

- **Transaction costs**: 0.5% commission, 5 bps slippage
- **Liquidity filters**: Minimum volume thresholds
- **Partial fills**: Simulate illiquid market conditions
- **Execution delay**: Model trade timing realistically
- **Exit strategies**: Stop-loss, take-profit, trailing-stop
- **Benchmark comparison**: Strategy vs buy-and-hold

## Structure

```
backtesting/
├── __init__.py        # Backtesting module
├── engine.py          # Core backtesting engine
├── portfolio.py       # Capital simulation
└── metrics.py         # Performance calculations
```

## Usage

```python
from backtesting import run_backtest

# Execute a backtest
result = run_backtest(
    strategy_id=1,
    symbol="NABIL",
    start_date="2023-01-01",
    end_date="2023-12-31",
    initial_capital=1000000
)
```

## Performance Metrics

- Total return, Sharpe ratio
- Max drawdown, win rate
- Profit factor, expectancy
- Trade count, winning trades
