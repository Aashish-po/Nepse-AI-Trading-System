# DataQualityGate Invariant Specification

## 1. Invariant Statement

No feature, strategy, model, signal, backtest, or trading decision module in this system may compute, persist, or emit any output without first passing through the `DataQualityGate` for the relevant symbol and date.

This is a mandatory, non-bypassable security boundary.

---

## 2. Scope

| Covered Module Type | Examples |
|---|---|
| Feature computation | Any function or class that derives indicators, ratios, or transforms from price data |
| Strategy evaluation | Any module that generates signals, weights, or allocations |
| Model inference | Any ML or rule-based model that consumes market data to produce predictions |
| Backtest execution | Any simulation that processes historical dates for a symbol |
| Signal emission | Any endpoint or worker that publishes tradeable output |

---

## 3. Enforcement Mechanisms

### 3.1 Architectural Gate (Mandatory Entry Point)

All entry points into covered modules MUST route through `DataQualityGate`:

- `DataQualityGate.assert_safe_for_features(symbol, date_str)` — blocks feature computation
- `DataQualityGate.assert_safe_for_backtest(symbol, date_str)` — excludes backtest dates
- `DataQualityGate.get_feature_weight(symbol, date_str, base_weight)` — optional soft-mode weight adjustment

### 3.2 Hard Gate Failure State

When `assert_safe_for_features` or `assert_safe_for_backtest` is called and the underlying `DataQualityService.evaluate_symbol_date()` returns `status == "unsafe"`:

- The gate MUST raise `DataQualityGateError`
- The calling module MUST NOT proceed with computation
- The calling module MUST NOT persist partial results for that symbol/date
- The error MUST propagate to the caller for logging and observability

### 3.3 Soft Mode (Warning Zone)

When `status == "warning"` (trust score 0.70–0.84):

- `get_feature_weight()` MUST return `base_weight * 0.5`
- Computation is NOT blocked, but output MUST be weighted accordingly
- This allows downstream strategies to apply reduced conviction

### 3.4 Excellent Zone

When `status == "excellent"` (trust score ≥ 0.85):

- `get_feature_weight()` MUST return `base_weight`
- Full computation proceeds with no penalty

---

## 4. Validation Protocols

### 4.1 Trust Score Computation

The `DataQualityService._compute_trust_score()` method is the sole authority for computing trust scores. It evaluates:

- Completeness (missing OHLCV fields)
- Volume anomaly (rolling 20-day baseline, 3σ or relative threshold)
- Missing dates (gap detection)
- Holiday status (via `HolidayCalendar`)
- Rejected records (from ingestion logs)

Base score: 1.0
Penalties are subtracted and clamped to `[0.0, 1.0]`.

### 4.2 Status Classification

| Trust Score | Status | Meaning |
|---|---|---|
| ≥ 0.85 | `excellent` | Full trust |
| 0.70 – 0.84 | `warning` | Reduced weight |
| < 0.70 | `unsafe` | Hard block |

### 4.3 Idempotency

`DataQualityGate.check()` MUST be idempotent for the same symbol/date within a single session. Repeated calls MUST return the same `QualityGateResult` without side effects, except for `HolidayCalendar` backfill of `is_trading_day`.

---

## 5. Prohibited Patterns

The following patterns are FORBIDDEN in production code:

1. **Direct trust_score read without gate**: Reading `DataTrust.trust_score` directly from the database to make computation decisions without calling `DataQualityGate.check()`.
2. **Bypass via inline evaluation**: Calling `DataQualityService.evaluate_symbol_date()` directly in feature/strategy/model code without wrapping it in `DataQualityGate`.
3. **Soft-pedaling unsafe**: Treating `unsafe` status as `warning` or `excellent` to avoid blocking computation.
4. **Silent failure suppression**: Catching `DataQualityGateError` and continuing computation without explicit handling.
5. **Dry-run quality injection**: Triggering quality evaluation during dry-run ingestion (quality checks only apply to persisted data).

---

## 6. Failure States

| Failure | Behavior |
|---|---|
| `DataQualityGateError` raised | Computation halted; error logged with symbol, date, trust_score, and status |
| `DataQualityService` unavailable | Gate MUST fail closed — treat as `unsafe` and block computation |
| Missing symbol or price data | Gate returns `unsafe` with reason `stock_not_found` or `no_price_data` |
| Database connection loss | Gate MUST raise `DataQualityGateError`; caller MUST NOT proceed |

---

## 7. Compliance Verification

### 7.1 Static Analysis

All Python files in `backend/app/services/` MUST be audited for:

- Direct imports of `DataQualityService` (allowed only in `data_quality_gate.py` and tests)
- Calls to `evaluate_symbol_date` outside of `DataQualityGate` (forbidden)
- Feature computation functions that do not call `assert_safe_for_features` (forbidden)

### 7.2 Runtime Verification

Every `compute_features`, `run_backtest`, and equivalent entry point MUST:

1. Call the gate FIRST
2. Proceed ONLY if no exception is raised
3. Log the gate result (symbol, date, trust_score, status) for observability

### 7.3 Test Coverage

Test suites MUST include:

- Hard gate blocks `unsafe` data
- Soft mode applies 0.5 weight for `warning`
- Excellent mode applies full weight
- Backtest excludes `unsafe` dates
- Feature generation raises on `unsafe`

---

## 8. Dry-Run Integrity

- Dry-run ingestion (`IngestionService.run(dry_run=True)`) MUST NOT trigger `DataQualityService.evaluate_symbol_date()`
- Quality checks apply only to persisted data
- Dry-run results MAY include validation results (bad row counts) but MUST NOT include trust scores or quality status
- This prevents false-positive gate failures on data that has not been committed

---

## 9. Versioning

This specification applies to all code in `backend/app/services/` and `backend/app/api/routes/` as of the current HEAD. Any new service or route that computes features, strategies, models, signals, or backtests MUST comply before merge.

---

## 10. Authority

`DataQualityGate` is the sole authority for data quality enforcement. No other component may override, bypass, or shadow its decisions.
