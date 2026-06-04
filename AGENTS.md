# Agent Commands

## Lint & Type Check

```bash
python -m ruff check backend/
```

## Tests

```bash
python -m pytest backend/tests/ -v
```

## Run Server

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --app-dir .
```

## Run Seed Script

```bash
python scripts/seed_symbols.py
```

## Alembic Migrations

```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
alembic downgrade -1
```
