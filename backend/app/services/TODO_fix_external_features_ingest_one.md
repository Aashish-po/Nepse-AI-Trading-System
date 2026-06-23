# TODO: Fix mypy/pylance error in external_features.py (_ingest_one)

- [x] Inspect `GlobalMarketFeatureBuilder` in `backend/app/services/external_features.py` and identify missing `_ingest_one` method.
- [ ] Implement `_ingest_one` in `GlobalMarketFeatureBuilder` by delegating to `MarketIngestionService` logic (fetch via provider client + upsert into `ExternalPrice`).
- [x] Run `pytest backend/tests/test_external_market.py` to confirm the attribute error is resolved.
- [ ] Run a quick smoke test (optional) for external ingestion endpoint if present.
