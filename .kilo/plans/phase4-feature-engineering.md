# Phase 4: Feature Engineering Implementation Plan

## Overview

Enhance the existing Feature Engineering module with trust-aware scaling, event-based overrides, and correlation-aware adjustments while implementing the missing `get_features` retrieval method and renaming `compute_features_batch` to `compute_bulk`.

## Current State Analysis

### Already Implemented

- `Feature` model with `feature_version`, `trust_score`, `trust_version`, and JSONB `values` column
- `FeatureService` with `compute_features`, `compute_features_batch`, `compute_features_multi_stock`
- Technical indicators: RSI (14, 21), MACD, ATR (14), SMA (20, 50), EMA (20, 50), Returns, Volatility (20), Volume Ratio, Price Range
- `DataQualityGate` with `assert_safe_for_features`, `get_feature_weight`, integration with trust scores
- `DataQualityService` with `calculate_weighted_price`, `get_active_event_overrides`, `detect_source_correlations`

### Gaps to Address

1. **Trust-Aware Scaling**: Features not scaled by trust_score and feature_weight
2. **Event-Based Overrides**: No sensitivity multiplier application to features
3. **Correlation-Aware Adjustment**: No confidence penalty for high source correlation
4. **Missing `get_features` method**: No retrieval API for persisted features
5. **Method naming**: `compute_features_batch` should be `compute_bulk` per spec
6. **Enhanced pipeline**: Integrate weighted price into the computation flow
7. **Test coverage**: Missing tests for advanced intelligence features

## Implementation Tasks

### Task 1: Create Indicator Functions Module (`features/indicators.py`)

Extract mathematical indicator functions into a standalone module for:

- `compute_rsi(prices, period=14)` - with zero average loss edge case handling
- `compute_sma(values, period=20)` - Simple Moving Average
- `compute_ema(values, period=20)` - Exponential Moving Average
- `compute_macd(prices, fast=12, slow=26, signal=9)` - MACD with histogram
- `compute_atr(high, low, close, period=14)` - Average True Range
- `compute_volatility(returns, period=20)` - Rolling standard deviation
- `compute_returns(prices)` - Periodic returns
- `compute_volume_ratio(volume, volume_sma)` - Volume normalization

### Task 2: Enhance FeatureService with Trust & Event Integration

Update `backend/app/services/feature.py`:

**A. Add `_apply_trust_scaling` method:**

```python
def _apply_trust_scaling(self, features: dict, trust_score: float, feature_weight: float) -> dict[str, float]:
    # Scale normalized indicators (RSI, volatility) by trust_score * feature_weight
    # Returns confidence-weighted feature values
```

**B. Add `_apply_event_overrides` method:**

```python
def _apply_event_overrides(self, symbol: str, date_str: str) -> float:
    # Fetch active event overrides via DataQualityService.get_active_event_overrides()
    # Return cumulative sensitivity multiplier (product of all active overrides)
```

**C. Add `_apply_correlation_penalty` method:**

```python
def _apply_correlation_penalty(self, trust_score: float) -> float:
    # Check SourceCorrelation for high correlation (> 0.8)
    # Apply confidence penalty (reduce trust_score by 0.1 if correlation detected)
```

**D. Add `get_features` method:**

```python
def get_features(self, symbol: str, date_str: str, feature_version: str | None = None) -> dict[str, Any]:
    # Retrieve features from Feature store with optional version filter
```

**E. Add `compute_bulk` alias:**

```python
def compute_bulk(self, symbol: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    # Delegate to compute_features_batch for backward compatibility
```

### Task 3: Update Pipeline Orchestration

Modify `_compute_all_features` to integrate:

1. Fetch weighted price via `DataQualityService.calculate_weighted_price` for multi-source consensus
2. Apply trust-weighted scaling to normalized indicators
3. Apply event-based sensitivity multipliers
4. Apply correlation-aware confidence adjustments

### Task 4: Enhance Persistence with Trust Version

Update `_persist_single_feature` and `_bulk_persist_features` to:

- Include `trust_version` from DataTrust records
- Support immutable versioning (merge with version conflict detection)

### Task 5: Implement Comprehensive Test Suite

Add to `backend/tests/test_feature.py`:

- `test_trust_aware_scaling_rsi()` - RSI scaled by trust_score
- `test_trust_aware_scaling_volatility()` - Volatility scaled by feature_weight
- `test_event_override_applied_to_features()` - Sensitivity multiplier affects output
- `test_correlation_penalty_applied()` - High correlation reduces confidence
- `test_safe_mode_blocks_feature_generation()` - SAFE_MODE prevents computation
- `test_feature_consistency_across_versions()` - Version immutability maintained
- `test_compute_bulk_returns_expected_format()` - New method naming
- `test_get_features_retrieves_persisted()` - Retrieval method works
- `test_insufficient_data_handling()` - Edge cases for small samples

### Task 6: Update Schemas

Add to `backend/app/schemas/feature.py`:

- `FeatureRetrieveRequest` schema
- `FeatureRetrieveResponse` schema

## File Changes Summary

| File | Changes |
|------|---------|
| `features/indicators.py` | **NEW** - Standalone indicator functions |
| `features/__init__.py` | Export indicator functions |
| `backend/app/services/feature.py` | Trust scaling, event overrides, correlation penalty, `get_features`, `compute_bulk` |
| `backend/app/schemas/feature.py` | Retrieval schemas |
| `backend/tests/test_feature.py` | New test cases for advanced features |

## Testing Strategy

### Unit Tests

- RSI bounds: 0-100 validation with constant prices, rising prices, falling prices
- Insufficient data: < period samples return NaN
- Trust-weighted scaling: Mathematical correctness (trust_score *weight* value)
- Event override: Multiplier correctly applied to volatile features
- Correlation penalty: High correlation triggers trust score reduction

### Integration Tests

- SAFE_MODE blocking: System in SAFE_MODE throws DataQualityGateError
- Feature consistency: Multiple versions stored without overwrite
- Weighted price: Multi-source prices correctly aggregated

## Execution Order

1. Create `features/indicators.py` with clean indicator implementations
2. Update `FeatureService` with trust/event/correlation logic
3. Add `get_features` and `compute_bulk` methods
4. Update `_compute_all_features` pipeline
5. Add comprehensive test coverage
6. Run lint and typecheck: `python -m ruff check backend/` and tests

## Configuration Notes

- No new environment variables required
- Uses existing `trust_score_minimum` from config for thresholds
- Event types: EARNINGS, CORPORATE_ACTION, MARKET_PANIC
