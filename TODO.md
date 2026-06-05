# TODO - FeatureService type fixes

- [ ] Update `backend/app/services/feature.py` indicator helper method type hints to accept broader array-like inputs.
- [ ] Ensure each `_compute_*` method casts inputs to `np.ndarray[np.float64]` immediately and return types are consistent (`np.ndarray`).
- [ ] Fix `_persist_single_feature` parameter typing to match produced dict shape (`dict[str, float|None]`).
- [ ] Add explicit `stock is None` guard in `_persist_single_feature` (and keep runtime behavior safe).
- [ ] Run mypy/pyright or `python -m compileall` / unit tests to verify no regressions.
