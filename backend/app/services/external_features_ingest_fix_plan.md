# Plan: Fix `_ingest_one` attribute errors in `external_features.py`

## Information gathered

- `backend/app/services/external_features.py` contains `GlobalMarketFeatureBuilder`.
- `GlobalMarketFeatureBuilder` calls `self._ingest_one(...)` in 3 methods: `ingest_benchmark`, `ingest_benchmark_from_client`, and `ingest_benchmark_from_client_and_session`.
- `external_features.py` currently defines no `_ingest_one` method, causing mypy/pylance errors: "GlobalMarketFeatureBuilder has no attribute _ingest_one".
- `backend/app/services/external_market.py` already implements a fully working ingestion flow including `_ingest_one(...)` and DB upsert logic for `ExternalPrice`.

## Plan

1. Add an internal method `_ingest_one` to `GlobalMarketFeatureBuilder` that delegates ingestion to `MarketIngestionService` (from `external_market.py`).
2. Ensure `_ingest_one`:
   - Fetches OHLCV for one symbol for `today` (using provider-specific client already available).
   - Uses the provided `session` argument.
   - Upserts into `external_prices` / `ExternalPrice` consistently with the rest of the code.
3. Keep method signatures consistent with the existing calls:
   - `_ingest_one(self, session, client, symbol, today) -> dict[str, Any]`.
4. Run tests to confirm the attribute errors are gone:
   - `pytest backend/tests/test_external_market.py` (and optionally full `pytest`).

## Dependent files to edit

- `backend/app/services/external_features.py`

## Followup steps

- Run `pytest backend/tests/test_external_market.py`.
- Optionally run mypy/linters if configured.

## ask_followup_question

- Reply with approval to proceed with implementing `_ingest_one` in `external_features.py` by delegating to `MarketIngestionService`.
