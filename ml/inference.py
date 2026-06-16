"""Inference utilities for runtime prediction."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from ml.feature_vector import FEATURE_ORDER, build_feature_vector
from ml.model_io import safe_load_model

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

    @classmethod
    def load_model_by_id(cls, model_id: str, model_dir: Path | None = None) -> Predictor:
        """Load a model by its registry ID."""
        import sqlalchemy
        from app.db.session import get_db
        from app.models.model_registry import ModelRegistry

        session = None
        try:
            session = next(get_db())
            left = ModelRegistry.name == model_id[:8]
            # Use SQL OR instead of Python boolean
            entry = (
                session.query(ModelRegistry)
                .filter(sqlalchemy.or_(left, ModelRegistry.name.like(f"%{model_id}%")))
                .first()
            )
            if entry is None:
                entry = (
                    session.query(ModelRegistry)
                    .filter(ModelRegistry.params.contains({"model_id": model_id}))
                    .first()
                )
        finally:
            if session is not None:
                session.close()

        if entry is None:
            raise ValueError(f"Model {model_id} not found in registry")

        model_path = Path(entry.model_artifact_path)
        # Registry-sourced path: must live under the trusted models directory.
        _ = safe_load_model(model_path)
        return cls(model_name=entry.name, model_version=entry.version, model_dir=model_path.parent)

    def _load(self) -> Any:
        version_tag = (
            f"v{self._model_version}"
            if not self._model_version.startswith("v")
            else self._model_version
        )
        path = self._model_dir / f"{self._model_name}_{version_tag}.joblib"
        return safe_load_model(path, allowed_dir=self._model_dir)
