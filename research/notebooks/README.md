# Research Notebooks

Use this folder for exploratory workflows.

## Quick start

1. Start the backend:

   ```bash
   uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --app-dir .
   ```

2. Set `API_BASE` to the running backend before opening a notebook:

   ```bash
   export API_BASE=http://127.0.0.1:8000
   ```

   Windows CMD variant:

   ```cmd
   set API_BASE=http://127.0.0.1:8000
   ```

   PowerShell variant:

   ```powershell
    $env:API_BASE="http://127.0.0.1:8000"
    ```

3. Open `01_idea_to_backtest.ipynb`, edit the hypothesis and parameters, then run all cells.

4. Run `02_backtest_and_export.ipynb` to execute the backtest and export JSON, CSV, and chart artifacts.

5. Run `03_integrate_bundle.ipynb` to package the exported artifacts for the strategy registry.

## Workflow overview

1. **Idea** → Define hypothesis and parameters
2. **Notebook** → Create backtest request payload
3. **Backtest** → Execute via API and analyze results
4. **Export** → Download artifacts (JSON/CSV/charts)
5. **Integrate** → Package for strategy registry

## Complete Workflow (Phase 6)

### 01) `01_idea_to_backtest.ipynb`

- Defines research hypothesis
- Fetches available strategies
- Builds backtest request payload with config parameters

### 02) `02_backtest_and_export.ipynb`

- Executes `POST /strategies/backtests` with payload
- Exports:
  - `exports/backtest_report_<id>.json` - Full backtest result
  - `exports/equity_curve_<id>.csv` - Equity time series
  - `exports/trades_<id>.csv` - Trade history
  - `exports/equity_curve_<id>.png` - Chart image
  - `exports/config_<id>.json` - Reproducible config

### 03) `03_integrate_bundle.ipynb`

- Creates integration bundle JSON for strategy registry
- Validates artifact presence
- Documents next integration steps

## Dashboard Access

Run the Streamlit dashboard:

```bash
streamlit run dashboard/app.py
```

Features:

- **Market Overview**: NSE data, symbol counts, volume metrics
- **Data Quality**: Trust scores, validation reports, quality trends
- **Strategies**: List and inspect strategy configurations
- **Backtesting**: Run backtests with configurable parameters
- **Benchmarks**: Compare strategy vs buy-and-hold
- **Exports**: Download JSON bundles, CSV data, chart definitions

## API Endpoints Reference

All notebook and dashboard API calls use `API_BASE` as the backend root URL. The default is:

```text
http://127.0.0.1:8000
```

If the backend runs on a different host or port, update `API_BASE` before running the notebooks.

### Health & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health check |
| `/market/overview` | GET | Market summary data |

### Features

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/features/generate?symbol=NABIL&date_str=2024-01-15` | POST | Generate features for one symbol/date |
| `/features/generate-batch` | POST | Generate features for a date range |
| `/features/generate-multi` | POST | Generate features for multiple symbols |

### Strategies

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/strategies/` | GET | List all strategies |
| `/strategies/{id}` | GET | Get strategy details |
| `/strategies/` | POST | Create new strategy |
| `/strategies/backtests` | POST | Run backtest |

### Data Quality

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/data-quality/trust/{symbol}/{date}` | GET | Per-symbol trust score |
| `/data-quality/reports/daily` | POST | Daily quality report |
| `/data-quality/summary/{symbol}` | GET | Symbol quality summary |

### Signals

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/signals/heatmap/{date}` | GET | Signal distribution heatmap |

## Expected Outputs

### Backtest Result Schema

```json
{
  "backtest_id": "bt_20240101_001",
  "strategy_id": 1,
  "metrics": {
    "total_return": 0.25,
    "sharpe_ratio": 1.8,
    "max_drawdown": -0.15,
    "win_rate": 0.62,
    "profit_factor": 2.1,
    "expectancy": 1250.50,
    "total_trades": 42,
    "winning_trades": 26,
    "equity_curve": [{"date": "2020-01-01", "equity": 1000000}],
    "trades": [{"entry_date": "2020-01-05", "entry_price": 100.0}]
  }
}
```

### Trust Score Response Schema

```json
{
  "symbol": "NABIL",
  "date": "2024-01-15",
  "trust_score": 0.85,
  "status": "SAFE",
  "safe": true,
  "components": {
    "completeness": 0.95,
    "freshness": 1.0,
    "validation": 0.9
  }
}
```

## Manual Smoke Verification

1. **Start Backend:**

   ```bash
   uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
   ```

2. **Run Smoke Tests:**

   ```bash
   python scripts/smoke_test.py
   ```

3. **Run Dashboard:**

   ```bash
   streamlit run dashboard/app.py
   ```

4. **Verify Pages:**
   - Market Overview loads
   - Strategies page shows data
   - Backtesting runs successfully
   - Exports download correctly

## Notes

- Notebook outputs are exploratory only — not production evidence until reproduced through the verified pipeline
- Use `streamlit_option_menu` for navigation in dashboard
- Chart exports available as JSON definitions for further customization
- Currency formatting: Rs.K (thousands), Rs.M (millions), Rs.B (billions)
- Trust score thresholds (per the data-quality gate): `excellent` >= 0.85, `warning` 0.70–0.84, `unsafe` < 0.70
