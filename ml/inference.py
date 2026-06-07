"""Inference utilities for runtime prediction."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from ml.feature_vector import FEATURE_ORDER, build_feature_vector

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


class Predictor:
    def __init__(
        self,
        model_name: str,
        model_version: str,
        model_dir: Path | None = None,
    ) -> None:
        self._model_name = model_name
        self._model_version = model_version
        self._model_dir = model_dir or MODELS_DIR
        self._model = self._load()

    def predict(self, feature_values: dict[str, Any]) -> dict[str, Any]:
        vector = build_feature_vector(feature_values)
        X = vector.reshape(1, -1)
        prediction = int(self._model.predict(X)[0])
        confidence: float = 0.0
        if hasattr(self._model, "predict_proba"):
            proba = self._model.predict_proba(X)[0]
            confidence = float(np.max(proba))
        return {
            "model_name": self._model_name,
            "model_version": self._model_version,
            "prediction": prediction,
            "confidence": confidence,
            "feature_vector": vector.tolist(),
            "feature_names": FEATURE_ORDER,
        }

    def _load(self) -> Any:
        version_tag = (
            f"v{self._model_version}"
            if not self._model_version.startswith("v")
            else self._model_version
        )
        path = self._model_dir / f"{self._model_name}_{version_tag}.joblib"
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")
        return joblib.load(path)
