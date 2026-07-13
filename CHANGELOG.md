# Changelog

## Unreleased

No changes yet.

## v0.1.0 - 2026-07-13

- Fix: Provider seed now creates `DataSource.type='scraper'` instead of legacy `'api'`. This prevents DB constraint failures after the migration that removed `'api'` as an allowed `DataSource.type`. See `docs/MIGRATION_NOTES.md` for details.
