"""Feature vector adapter for ML pipelines."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

# Ensure both workspace root and backend directory are on path
_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"

if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from app.services.feature import FEATURE_REGISTRY  # noqa: E402

FEATURE_ORDER = list(FEATURE_REGISTRY.keys())
FEATURE_DIM = len(FEATURE_ORDER)


def validate_vector(vector: NDArray[np.float64]) -> NDArray[np.float64]:
    if vector.shape[0] != FEATURE_DIM:
        raise ValueError(
            f"Feature vector length mismatch: expected {FEATURE_DIM}, got {vector.shape[0]}"
        )
    return vector


def fill_missing(vector: NDArray[np.float64], fill_value: float = 0.0) -> NDArray[np.float64]:
    return np.where(np.isnan(vector) | np.isinf(vector), fill_value, vector)


def build_feature_vector(values: dict[str, Any]) -> NDArray[np.float64]:
    vector: list[float] = []
    for name in FEATURE_ORDER:
        value = values.get(name)
        if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
            vector.append(0.0)
        else:
            vector.append(float(value))
    return validate_vector(np.array(vector, dtype=np.float64))
