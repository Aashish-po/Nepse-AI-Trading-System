# NEPSE AI Trading Dashboard

A professional-grade Streamlit dashboard for the NEPSE AI Trading System with market overview, strategy management, backtesting, and data quality monitoring.

## 🎯 Features

### 📊 Market Overview

- **Real-time market metrics**: NSE index, trading volume, active signals
- **Data quality dashboard**: Completeness, validation pass rate, trust scores
- **Per-symbol analysis**: Detailed trust scores and quality components
- **Comprehensive reports**: Daily quality reports with symbol-by-symbol breakdown

### 🎯 Strategies

- **Strategy browser**: View all configured trading strategies
- **Detailed configuration**: Parameters, versions, creation timestamps
- **Backtest history**: Recent backtest results per strategy
- **Status tracking**: Active/inactive strategy status

### 🧪 Backtesting

- **Flexible configuration**:
  - Initial capital, commission, slippage, execution delay
  - Custom date ranges
  - Multiple strategy selection
  - Benchmark symbol specification
  
- **Performance metrics**:
  - Total return, Sharpe ratio, max drawdown, win rate
  - Profit factor, expectancy, trade counts
  
- **Visualizations**:
  - Interactive equity curve (Plotly)
  - Drawdown analysis over time
  - Strategy vs. benchmark comparison
  - Hover data with detailed metrics
  
- **Trade analysis**:
  - Complete trade table with entry/exit details
  - Entry/exit prices, P&L, duration
  - Sortable and filterable
  
- **Export options**:
  - Full backtest bundle (JSON)
  - Report snapshot (JSON)
  - Equity curve (CSV)
  - Trades ledger (CSV)

## 📦 Installation

### Prerequisites

- Python 3.10+
- NEPSE AI Trading System backend running
- pip or conda

### Setup

```bash
# Clone repository (if not already done)
cd nepse-ai-trading-system/dashboard

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install streamlit \
            streamlit-option-menu \
            pandas \
            plotly \
            altair \
            requests

# Or install from requirements.txt (if available)
pip install -r requirements.txt
```

### Configuration

Create a `.streamlit/secrets.toml` file in the dashboard directory:

```toml
# .streamlit/secrets.toml
API_BASE = "http://localhost:8000"  # Backend API URL
```

Or set the environment variable:

```bash
export API_BASE="http://localhost:8000"
```

## 🚀 Running the Dashboard

```bash
# Start the backend first
cd ../backend
python -m uvicorn app.main:app --reload

# In another terminal, start the dashboard
cd ../dashboard
streamlit run dashboard_complete.py
```

The dashboard will be available at `http://localhost:8501`

## 🎨 Design & UX

### Aesthetic Direction

**Professional fintech** with a focus on clarity and data-driven decision-making:

- **Dark theme**: Deep slate backgrounds (#0F172A, #1E293B)
- **Accent color**: Bright cyan (#0EA5E9) for primary actions
- **Semantic colors**: Green for gains, red for losses, amber for warnings
- **Typography**: Clean, metric-focused with proper hierarchy
- **Glass morphism**: Subtle backdrop blur on cards for depth

### Component Library

- **Metric cards**: Summary stats with delta indicators
- **Interactive charts**: Plotly for hover data and zooming
- **Data tables**: Streamlit DataFrames with proper formatting
- **Input controls**: Sidebar configuration with clear labels

## 📋 Page Structure

### Page 1: Market Overview

```
Header: 📊 Market Overview
├─ Key Metrics (4 columns)
│  ├─ NSE Index
│  ├─ Tracked Symbols
│  ├─ Total Volume
│  └─ Active Signals
├─ Data Quality Report (3 metrics)
│  ├─ Completeness Score
│  ├─ Validation Pass Rate
│  └─ Average Trust Score
├─ Quality by Symbol (table)
└─ Per-Symbol Trust Score (lookup)
   ├─ Trust Score
   ├─ Status (Safe/Caution/Unsafe)
   └─ Quality Components
```

### Page 2: Strategies

```
Header: 🎯 Trading Strategies
├─ Strategy Selector (dropdown)
├─ Strategy Overview (4 metrics)
│  ├─ Strategy ID
│  ├─ Version
│  ├─ Created At
│  └─ Status
├─ Configuration (JSON view)
├─ Recent Backtests (table)
└─ Parameters (JSON view)
```

### Page 3: Backtesting

```
Header: 🧪 Backtest & Analysis
├─ Configuration Sidebar
│  ├─ Initial Capital
│  ├─ Commission Rate
│  ├─ Slippage
│  ├─ Execution Delay
│  ├─ Strategy Selection
│  ├─ Date Range
│  └─ Benchmark Symbol
├─ Performance Metrics (8 KPIs)
├─ Equity Curve Chart (Plotly)
├─ Drawdown Analysis Chart (Plotly)
├─ Trades Table (detailed)
├─ Benchmark Comparison
│  ├─ Strategy vs Buy&Hold metrics
│  └─ Overlaid equity curves
└─ Export Options (JSON/CSV)
```

## 🔧 API Integration

The dashboard expects the backend to provide these endpoints:

### Market Data

- `GET /market/overview` → Market metrics and status
- `GET /data-quality/trust/{symbol}/{date}` → Per-symbol trust score
- `POST /data-quality/reports/daily` → Comprehensive quality report
- `GET /signals/heatmap/{date}` → Signal distribution

### Strategies

- `GET /strategies/` → List all strategies
- `POST /strategies/backtests` → Execute backtest
- `POST /strategies/benchmarks/compare` → Compare to benchmark

### Response Schemas

**Backtest Result:**

```json
{
  "backtest_id": "bt_20240101_001",
  "metrics": {
    "total_return": 0.25,
    "sharpe_ratio": 1.8,
    "max_drawdown": -0.15,
    "win_rate": 0.62,
    "profit_factor": 2.1,
    "expectancy": 1250.50,
    "total_trades": 42,
    "winning_trades": 26,
    "equity_curve": [
      {"date": "2020-01-01", "equity": 1000000},
      ...
    ],
    "trades": [
      {
        "entry_date": "2020-01-05",
        "entry_price": 100.00,
        "exit_date": "2020-01-10",
        "exit_price": 105.00,
        "quantity": 100,
        "pnl": 500.00,
        "pnl_percent": 0.05,
        ...
      },
      ...
    ]
  }
}
```

## 📊 Key Functions

### Data Processing

- `_safe_int()` → Graceful int conversion
- `_safe_float()` → Graceful float conversion
- `_format_currency()` → Format large numbers (₹K, ₹M, ₹B)
- `_format_percentage()` → Add color indicators (+/-)

### API Wrappers

- `load_strategies()` → Get all strategies (cached 60s)
- `load_market_overview()` → Get market data (cached 60s)
- `get_trust_score()` → Per-symbol quality (cached 60s)
- `run_backtest()` → Execute backtest (not cached)
- `compare_benchmark()` → Benchmark comparison (not cached)

## 🎯 Caching Strategy

- **Market data**: 60 second TTL (updated frequently)
- **Strategies**: 60 second TTL (configuration rarely changes)
- **Backtest results**: Not cached (always fresh execution)
- **Benchmark data**: Not cached (computed on demand)

Use `st.cache_data.clear()` to force refresh if needed.

## 🐛 Troubleshooting

### Backend Connection Failed

```
⚠️ Backend not running or failed to connect (GET /strategies/).
```

**Solution**: Start the backend before the dashboard:

```bash
python -m uvicorn app.main:app --reload
```

### API_BASE Not Set

```
Using default http://localhost:8000
```

**Solution**: Set in `.streamlit/secrets.toml` or environment:

```bash
export API_BASE="http://your-server:8000"
```

### Slow Backtest Execution

- Reduce date range
- Check backend logs for query bottlenecks
- Verify database indexes on `trades`, `signals` tables

### Chart Not Rendering

- Ensure `equity_curve` and `trades` have required columns
- Verify date format (ISO 8601: YYYY-MM-DD)
- Check browser console for Plotly errors

## 📈 Performance Tips

1. **Query optimization**: Backend should index on `symbol` and `date`
2. **Caching**: Market overview cached 60s to reduce API calls
3. **Lazy loading**: Charts render after backtest completion
4. **Pagination**: Trade tables can be filtered/searched
5. **Incremental**: Equity curves streamed if >10k points

## 🔐 Security Considerations

- **Secrets management**: Use `.streamlit/secrets.toml` (never commit)
- **API validation**: All inputs validated before sending
- **CORS**: Configure backend to allow dashboard origin
- **Rate limiting**: Backend should limit backtest requests
- **Authentication**: Implement if exposing publicly (future)

## 📝 Future Enhancements

- [ ] Real-time signal alerts (WebSocket)
- [ ] Strategy optimization interface
- [ ] Portfolio analysis across multiple strategies
- [ ] Risk metrics dashboard (VaR, Sortino, etc.)
- [ ] ML model explainability
- [ ] Multi-user authentication
- [ ] Dark/light mode toggle
- [ ] Custom indicator builder

## 📞 Support

For issues or questions:

1. Check backend logs: `uvicorn` output
2. Check dashboard logs: Browser console (F12)
3. Verify API endpoints: `curl http://localhost:8000/strategies/`
4. Review error messages in Streamlit UI

## 📄 License

Part of NEPSE AI Trading System

