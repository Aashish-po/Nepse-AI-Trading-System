# Scripts

Utility scripts for database management, testing, and data operations.

## Scripts

| Script | Purpose |
|--------|---------|
| `seed_symbols.py` | Populate database with NEPSE stock symbols |
| `smoke_test.py` | Quick verification of API endpoints |
| `backup_db.sh` | PostgreSQL backup script with retention |

## Usage

```bash
# Seed initial data
python scripts/seed_symbols.py

# Run smoke tests
python scripts/smoke_test.py

# Database backup (requires DATABASE_URL in .env)
bash scripts/backup_db.sh

# With custom backup directory and retention
bash scripts/backup_db.sh /backups 30
```

## Smoke Test

Verifies:

- Health endpoints (`/health`, `/health/live`, `/health/ready`)
- Market data endpoints (`/market/prices`)
- Strategy endpoints (`/strategies/`)
- Basic API response structure
