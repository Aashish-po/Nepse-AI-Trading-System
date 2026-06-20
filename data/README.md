# Data

Data ingestion, validation, and loading modules for NEPSE market data.

## Structure

```
data/
├── loaders/           # Data source loaders
│   ├── sharesansar.py # ShareSansar API integration
│   └── mero_lagani.py # MeroLagani scraper (fallback)
├── validation/        # Data quality validators
│   ├── completeness.py
│   ├── freshness.py
│   └── consistency.py
├── ingestion/         # Ingestion orchestration
│   └── pipeline.py
└── __init__.py
```

## Data Sources

- **ShareSansar**: Primary API for NEPSE data
- **MeroLagani**: Web scraper fallback for data redundancy
- **Manual CSV**: Local file import capability

## Validation Rules

- **Completeness**: Missing value detection
- **Freshness**: Staleness checks (expected update time)
- **Consistency**: Cross-source price reconciliation
- **Volume**: Trading volume validation

## Trust Scoring

Each symbol/date receives a trust score (0.0-1.0) based on:

- Data completeness (weight: 0.25)
- Freshness (weight: 0.25)
- Cross-source validation (weight: 0.25)
- Volume reasonableness (weight: 0.25)

Safe threshold: ≥ 0.7 (`SAFE_MODE` when < 0.7).
