# NEPSE AI Trading Dashboard - Feature Guide

## Overview

The NEPSE AI Trading Dashboard is a professional Streamlit application designed for interactive market analysis, strategy management, and backtest execution. It provides a comprehensive interface for quantitative traders and AI researchers.

---

## 📊 Feature 1: Market Overview

### Purpose

Monitor real-time market conditions, data quality metrics, and signal distribution across all tracked symbols.

### Components

#### 1.1 Key Metrics Row

```
┌────────────────────┬────────────────────┬──────────────────┬─────────────────┐
│  NSE Index         │  Tracked Symbols   │  Total Volume    │  Active Signals │
│  Value: 2,450.50   │  117               │  ₹4.2B          │  18             │
│  Δ +1.2%           │  Δ +2              │  Δ +15.8%        │  Δ +3           │
└────────────────────┴────────────────────┴──────────────────┴─────────────────┘
```

**Data Source**: `GET /market/overview`

**Metrics Explained**:

- **NSE Index**: Nepal Stock Exchange composite index with daily change
- **Tracked Symbols**: Total number of stocks in the system with new additions today
- **Total Volume**: Aggregate trading volume across all symbols with % change
- **Active Signals**: Number of active trading signals (BUY/SELL) today

---

#### 1.2 Data Quality Dashboard

```
┌──────────────────────────┬──────────────────────┬──────────────────┐
│  Completeness: 97.3%     │  Validation: 99.2%   │  Trust Score: 0.89│
│  Expected data received  │  Data passes checks  │  Overall quality  │
└──────────────────────────┴──────────────────────┴──────────────────┘
```

**Data Source**: `POST /data-quality/reports/daily`

**Metrics Explained**:

- **Completeness Score**: % of expected price records received from data sources
  - Target: >95% (missing data increases backtest risk)
  - Action: <90% → Check data provider status

- **Validation Pass Rate**: % of data passing validation rules
  - Checks: Non-negative prices, reasonable spreads, timestamp ordering
  - Target: >98%
  - Action: <95% → Investigate anomalies

- **Average Trust Score**: Mean trust score across all symbols
  - Range: 0.0 (untrusted) to 1.0 (fully trusted)
  - Target: >0.85
  - Used: Automatically weights signals by trust

---

#### 1.3 Quality by Symbol (Table View)

Shows per-symbol breakdown:

```
Symbol │ Records │ Completeness │ Trust Score │ Status
-------|---------|--------------|-------------|----------
NABIL  │ 1,247   │ 98.5%        │ 0.92       │ SAFE
SBI    │ 892     │ 94.2%        │ 0.78       │ CAUTION
EIC    │ 1,156   │ 99.1%        │ 0.88       │ SAFE
```

**Sortable by**: Completeness, Trust Score (descending = best)

**Action buttons**:

- Click symbol → Detailed quality report
- Status indicator → Color-coded (🟢 Safe, 🟡 Caution, 🔴 Unsafe)

---

#### 1.4 Per-Symbol Trust Score Lookup

Interactive lookup for historical quality:

**Inputs**:

- Symbol: e.g., "NABIL"
- Date: ISO format (YYYY-MM-DD)

**Output**:

```
Trust Score: 0.92/1.0    Status: 🟢 SAFE    Safe?: ✅ Yes

Quality Components:
├─ Price completeness:  96%
├─ Timestamp validity:  100%
├─ Spread reasonableness: 94%
└─ Volume consistency: 98%
```

**Use case**: Verify data quality before backtesting on specific dates

---

## 🎯 Feature 2: Strategies

### Purpose

Browse, manage, and compare trading strategies with their configurations and backtesting history.

### Components

#### 2.1 Strategy Browser

Dropdown selector with strategy details:

```
Select Strategy: [NABIL SMA Crossover (v1.2.3) ▼]
```

---

#### 2.2 Strategy Information Cards

4-column metric display:

```
┌──────────────┬──────────────┬─────────────────┬─────────────────┐
│ Strategy ID  │ Version      │ Created At      │ Status          │
│ 42           │ v1.2.3       │ 2024-01-15      │ ACTIVE          │
└──────────────┴──────────────┴─────────────────┴─────────────────┘
```

**Details**:

- **Strategy ID**: Unique identifier (used in backtests)
- **Version**: Semantic versioning (major.minor.patch)
- **Created At**: ISO timestamp of strategy creation
- **Status**: ACTIVE, PAUSED, ARCHIVED

---

#### 2.3 Configuration View

Raw strategy parameters (JSON):

```json
{
  "name": "NABIL SMA Crossover",
  "type": "technical_analysis",
  "lookback_window": 50,
  "fast_sma": 20,
  "slow_sma": 50,
  "entry_condition": "fast_sma > slow_sma",
  "exit_condition": "fast_sma < slow_sma",
  "symbols": ["NABIL", "SBI", "EIC"],
  "enabled": true
}
```

---

#### 2.4 Recent Backtests (Table)

```
Date       │ Backtest ID │ Return │ Sharpe │ Max DD │ Trades
-----------|-------------|--------|--------|--------|--------
2024-01-20 │ bt_001      │ 12.5%  │ 1.84   │ -8.3%  │ 42
2024-01-15 │ bt_002      │ 9.8%   │ 1.62   │ -10.1% │ 38
```

**Sortable by**: Date (newest first), Return (best first)

---

#### 2.5 Strategy Parameters (JSON)

Detailed hyperparameters:

```json
{
  "indicators": {
    "sma_fast": 20,
    "sma_slow": 50,
    "rsi_period": 14,
    "rsi_overbought": 70,
    "rsi_oversold": 30
  },
  "position_sizing": {
    "fixed_size": 10,
    "max_positions": 5,
    "risk_per_trade": 0.02
  },
  "filters": {
    "min_volume": 100000,
    "min_price": 50,
    "max_price_change": 0.10
  }
}
```

---

## 🧪 Feature 3: Backtesting

### Purpose

Execute historical backtests with full performance analysis and benchmark comparison.

### Components

#### 3.1 Configuration Sidebar

**Input Fields**:

- **Initial Capital**: Starting portfolio value (₹)
  - Default: 1,000,000
  - Range: 100,000 → 100,000,000

- **Commission Rate**: Per-transaction cost (decimal)
  - Default: 0.005 (0.5%)
  - Typical range: 0.002 → 0.01
  - Example: Trade ₹100,000 with 0.5% commission = ₹500 fee

- **Slippage**: Execution slippage in basis points
  - Default: 5 bps (0.05%)
  - Accounts for: Bid-ask spread, market impact, partial fills
  - Example: Entry price 100 with 5 bps slippage = 100.05 entry

- **Execution Delay**: Bars to wait before executing signal
  - Default: 1 (execute on next bar)
  - Useful: Avoid lookahead bias, simulate real-world delays
  - Range: 0 → 5

- **Strategy Selection**: Dropdown of available strategies

- **Date Range**: Start and end dates for backtest
  - Min start date: 2015-01-01 (available data)
  - Max end date: Today
  - Min duration: 1 month

- **Benchmark Symbol**: Symbol for buy-and-hold comparison
  - Default: NABIL
  - Should be liquid, widely tracked

---

#### 3.2 Performance Metrics (8 KPIs)

```
┌────────────────────┬───────────────────┬──────────────────┬───────────────────┐
│ Total Return       │ Sharpe Ratio      │ Max Drawdown     │ Win Rate          │
│ 🟢 +25.4%          │ 1.84              │ 🔴 -12.3%        │ 🟢 62.3%          │
│ Total gain/loss    │ Risk-adjusted ret │ Largest decline  │ Winning trades %  │
└────────────────────┴───────────────────┴──────────────────┴───────────────────┘

┌────────────────────┬───────────────────┬──────────────────┬───────────────────┐
│ Profit Factor      │ Expectancy        │ Total Trades     │ Winning Trades    │
│ 2.1x               │ ₹1,250.50         │ 42               │ 26 (61.9%)        │
│ Gross P/L ratio    │ Avg profit/trade  │ Trades executed  │ Number of winners │
└────────────────────┴───────────────────┴──────────────────┴───────────────────┘
```

**Metric Definitions**:

| Metric | Formula | Interpretation | Target |
|--------|---------|----------------|--------|
| **Total Return** | (Final Value - Initial) / Initial | Overall profitability | >0% (positive) |
| **Sharpe Ratio** | (Return - Rf) / Volatility | Risk-adjusted performance | >1.0 (good), >2.0 (excellent) |
| **Max Drawdown** | (Trough - Peak) / Peak | Worst peak-to-trough decline | >-20% (acceptable) |
| **Win Rate** | Winning Trades / Total Trades | % of profitable trades | >50% (positive expectancy) |
| **Profit Factor** | Gross Profit / Gross Loss | Total P/L ratio | >1.5 (good), >2.0 (strong) |
| **Expectancy** | (Win% × Avg Win) - (Loss% × Avg Loss) | Average profit per trade | >₹0 (positive) |
| **Total Trades** | Count of all executed trades | Trade frequency | Depends on strategy |
| **Winning Trades** | Count of profitable trades | Success count | Should correlate with Win Rate |

---

#### 3.3 Equity Curve (Interactive Chart)

**Type**: Line chart with fill area (Plotly)

**Features**:

- X-axis: Date (scroll, zoom, hover)
- Y-axis: Portfolio equity value (₹)
- Hover data: Exact equity on each date
- Zoom: Click and drag to zoom into date ranges
- Reset: Double-click to reset zoom

**Interpretation**:

- **Upward trend**: Profitable strategy
- **Flat sections**: Sideways market, no signals
- **Sharp drops**: Losses or drawdowns
- **Smooth curve**: Low volatility, consistent growth

**Export**: Save as PNG via Plotly toolbar

---

#### 3.4 Drawdown Analysis (Interactive Chart)

**Type**: Filled area chart (negative = drawdown)

**Formula**:

```
Drawdown% = (Current Equity - Rolling Peak) / Rolling Peak × 100
```

**Features**:

- Red color indicates drawdown
- Y-axis: Drawdown percentage (negative)
- Shows duration and magnitude of declines
- Hover: Exact drawdown % on each date

**Use case**:

- Identify periods of capital losses
- Assess strategy risk tolerance
- Compare to max drawdown metric

---

#### 3.5 Trades Table

**Columns**:

```
Entry Date │ Entry Price │ Exit Date  │ Exit Price │ Qty │ P&L (₹) │ P&L (%) │ Duration
-----------|------------|------------|-----------|-----|---------|---------|----------
2020-01-05 │ 100.50     │ 2020-01-10 │ 105.75   │ 100 │ +525.00 │ +5.23% │ 5 days
2020-01-15 │ 98.75      │ 2020-01-22 │ 96.25    │ 100 │ -250.00 │ -2.53% │ 7 days
```

**Features**:

- Sortable by any column
- Filterable by date range
- Search by symbol
- Height-scrollable (400px)

**Analysis**:

- Identify best/worst trades
- Find patterns (losing trades on certain days)
- Verify no lookahead bias (entry after signal date)

---

#### 3.6 Benchmark Comparison

**Left side - Strategy metrics**:

```
Strategy Return: 🟢 +25.4%
Sharpe Ratio: 1.84
Max DD: 🔴 -12.3%
```

**Right side - Buy & Hold metrics**:

```
Buy & Hold Return: 🟡 +8.2%
Sharpe Ratio: 0.62
Max DD: 🔴 -15.1%
```

**Overlaid Equity Curves**:

- Blue line: Strategy equity
- Amber line: Buy & Hold equity
- Interactive legend (click to toggle series)
- Hover: Compare values on same date

**Interpretation**:

- Strategy return > Buy & Hold? → Strategy outperforms
- Strategy Sharpe > Buy & Hold? → Better risk-adjusted returns
- Strategy DD > Buy & Hold DD? → Higher drawdown (worse risk)

---

#### 3.7 Export Options

**Option 1: Bundle (JSON)**

```json
{
  "backtest_id": "bt_20240120_001",
  "strategy_id": 42,
  "config": {
    "start_date": "2020-01-01",
    "end_date": "2023-01-01",
    "initial_capital": 1000000,
    ...
  },
  "metrics": { ... },
  "equity_curve": [ ... ],
  "trades": [ ... ],
  "exported_at": "2024-01-20T10:30:00Z"
}
```

**Use case**: Share complete backtest with team/archive

**Option 2: Report (JSON)**

```json
{
  "backtest_id": "bt_20240120_001",
  "metrics": { ... },
  "equity_curve": [ ... ],
  "trades": [ ... ]
}
```

**Use case**: Lightweight backtest results only

**Option 3: Equity Curve (CSV)**

```csv
date,equity
2020-01-01,1000000
2020-01-02,1002500
2020-01-03,1005100
```

**Use case**: Import into Excel, analyze in other tools

**Option 4: Trades (CSV)**

```csv
entry_date,entry_price,exit_date,exit_price,quantity,pnl,pnl_percent
2020-01-05,100.50,2020-01-10,105.75,100,525.00,0.0523
```

**Use case**: Trade journal, detailed analysis

---

## 🔄 Workflow Examples

### Example 1: Evaluate New Strategy

1. **Go to Strategies page**
   - Select strategy from dropdown
   - Review parameters and recent backtests

2. **Go to Backtesting page**
   - Configure: 1M initial capital, 0.5% commission
   - Select strategy from dropdown
   - Set date range: Last 2 years
   - Click "🚀 Run Backtest"

3. **Review results**
   - Check Sharpe ratio (target >1.5)
   - Look at max drawdown (target <-20%)
   - Verify win rate >50%
   - Review trade table for patterns

4. **Compare to benchmark**
   - Check if strategy outperforms buy & hold
   - Compare risk metrics (Sharpe, drawdown)

5. **Export**
   - Download bundle (JSON) for archive
   - Download trades (CSV) for trade journal analysis

---

### Example 2: Debug Strategy Losses

1. **Run backtest**
   - Use minimal date range (3-6 months)
   - Set execution delay = 0 (check for lookahead)
   - Use low commission (verify losses aren't slippage)

2. **Analyze equity curve**
   - Identify dates of sharp declines
   - Check corresponding drawdown chart

3. **Review trades**
   - Filter trades around decline dates
   - Sort by P&L (worst first)
   - Look for patterns:
     - Specific symbols losing more?
     - Certain day-of-week patterns?
     - Event-driven losses?

4. **Check data quality**
   - Go to Market Overview
   - Look up trust scores for symbols on loss dates
   - Verify prices reasonable (no data gaps)

5. **Adjust and re-test**
   - Modify strategy (tighter stops, better exits)
   - Run backtest again
   - Compare metrics to original

---

### Example 3: Monitor Daily Signals

1. **Check Market Overview**
   - View "Active Signals" metric
   - See daily signal counts
   - Monitor data quality trends

2. **Lookup trust score**
   - Pick symbol with upcoming signal
   - Check today's trust score
   - Verify status is SAFE

3. **Run quick backtest**
   - Test signal-generating strategy on recent data
   - Verify it captures expected signals
   - Check win rate on last 3 months

---

## 🚀 Tips & Best Practices

### Backtesting

- **Use realistic costs**: Commission 0.3-0.5%, slippage 5-10 bps
- **Test multiple date ranges**: Bull markets, crashes, sideways
- **Check walk-forward**: Does strategy perform in unseen data?
- **Avoid overfitting**: Don't optimize on full dataset

### Strategy Evaluation

- **Sharpe ratio >1.5**: Good risk-adjusted performance
- **Win rate >55%**: Positive expectancy
- **Profit factor >1.8**: Gross profit much larger than losses
- **Max drawdown <-25%**: Acceptable account drawdown

### Data Quality

- **Trust score >0.80**: Reliable for trading
- **Completeness >95%**: Enough data for signals
- **Validation >98%**: Data anomalies rare
- **Check before large backtests**: Avoid garbage in, garbage out

### Performance Optimization

- **Reduce date range**: Faster execution
- **Use smaller initial capital**: Doesn't affect % returns
- **Cache results**: Export and reuse for comparison
- **Check backend logs**: Debug slow queries

---

## 📞 FAQ

**Q: Why is my backtest taking >2 minutes?**
A: Large date ranges (5+ years) or complex strategies take longer. Try:

- Reduce date range to 2 years
- Check backend database indexes
- Monitor backend CPU usage

**Q: Equity curve is flat. Did the strategy make no trades?**
A: Possible causes:

- No signals generated (check technical indicators)
- Signals filtered out (minimum volume, price range)
- Date range has no matching data
- Strategy parameters too strict

**Q: Max drawdown seems too high. Is data wrong?**
A: Verify:

- Look up trust score for period (go to Market Overview)
- Check trades table for that period
- Compare prices to external source (NSE website)
- Try shorter date range with higher data trust

**Q: Can I export and share results?**
A: Yes! Download bundle (JSON) contains everything. Share via email or Slack.

**Q: How accurate are backtests?**
A: Assumptions made:

- Next-day execution at open price
- Perfect fill at entry price
- No liquidity constraints
- No position size limits
- No slippage on market impact

Real trading will differ due to market conditions, liquidity, timing.

---

## 🔮 Future Features

- [ ] Real-time signal alerts (Telegram integration)
- [ ] Multi-strategy portfolio analysis
- [ ] Risk metrics: VaR, Sortino ratio, Calmar ratio
- [ ] Monte Carlo simulations
- [ ] Walk-forward analysis
- [ ] Parameter optimization interface
- [ ] Strategy comparison dashboard
- [ ] Dark/light mode toggle
- [ ] Mobile responsive design
