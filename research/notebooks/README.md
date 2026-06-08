# Research Notebooks

Use this folder for exploratory workflows:

1. Idea
2. Notebook experiment
3. Backtest
4. Strategy integration
5. Dashboard/report export

## Notebooks in Phase 6

### 01) `01_idea_to_backtest.ipynb`

- Create the **backtest request payload** (`strategy_id` + `config`).

### 02) `02_backtest_and_export.ipynb`

- Calls `POST /strategies/backtests`
- Exports:
  - `exports/backtest_report_<id>.json`
  - `exports/equity_curve_<id>.csv`
  - `exports/trades_<id>.csv`

### 03) `03_integrate_bundle.ipynb`

- Builds an **integration bundle** JSON file from exported artifacts.

## Notes

- Notebook outputs should not be treated as production evidence until reproduced through the tested backtesting pipeline.
- If your backend base URL differs, update `API_BASE` in notebook 02 (and optionally notebook 01).
