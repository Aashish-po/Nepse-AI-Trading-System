Migration notes — DataSource `type` deprecation
===============================================

Summary
-------

This repository recently removed the legacy `DataSource.type='api'` value and introduced a stricter DB check constraint that only allows `('scraper','csv')`.

What changed
------------

- Alembic migration: `backend/app/db/migrations/versions/0015_remove_legacy_api_data_source_type.py` converts existing `'api'` rows to `'csv'` and updates the constraint.
- Provider seed logic: `backend/app/services/external/providers.py` now seeds provider `DataSource` rows with `type='scraper'` (was `'api'`).

Why
---

The legacy `'api'` stub was used in early development but is being deprecated in favor of explicit CSV/scraper ingestion from the `nepse_data` scrapers.

Developer actions
-----------------

- If you run the application against an existing database, apply the migration:

```bash
alembic -c backend/alembic.ini upgrade head
```

- If you run tests locally, the test suite already expects the seed behaviour to use `scraper`/`csv` types; no further test edits are required.

Notes for reviewers
------------------

- The provider seed change is intentionally minimal: it only changes the `type` of seeded rows so that DB constraints are satisfied and the runtime does not fail during startup or in tests.
- If you prefer `csv` as the canonical seeded type instead of `scraper`, we can update the seeding to use `csv` consistently and adjust docs accordingly.
