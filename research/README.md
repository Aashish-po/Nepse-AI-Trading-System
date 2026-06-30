# Research

Research notebooks and experimental workflows for strategy development.

## Structure

```
research/
├── notebooks/
│   ├── README.md
│   ├── 01_idea_to_backtest.ipynb
│   ├── 02_backtest_and_export.ipynb
│   └── 03_integrate_bundle.ipynb
└── README.md
```

## Workflow

1. **Idea**: Define hypothesis in `01_idea_to_backtest.ipynb`
2. **Experiment**: Execute backtest via API
3. **Export**: Download artifacts in `02_backtest_and_export.ipynb`
4. **Integrate**: Package for production in `03_integrate_bundle.ipynb`

## Outputs

All experimental results are exported to `/exports/`:

- `backtest_report_<id>.json` - Full backtest results
- `equity_curve_<id>.csv` - Time series equity data
- `trades_<id>.csv` - Trade history
- `equity_curve_<id>.png` - Chart visualization

## Prerequisites

- Backend API running (`uvicorn backend.app.main:app`)
- `API_BASE` environment variable set
- Python 3.12 with Jupyter installed
