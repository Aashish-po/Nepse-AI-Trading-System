# Research Notebooks

Use this folder for exploratory workflows:

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

## Notes

- Notebook outputs are not production evidence until reproduced through verified pipeline
- Use `streamlit_option_menu` for navigation in dashboard
- Chart exports available as JSON definitions for further customization
