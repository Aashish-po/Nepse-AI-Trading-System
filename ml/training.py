"""Model training and registration."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
from sklearn.linear_model import LogisticRegression
from sqlalchemy.orm import Session

# Ensure backend is on path for app.* imports
_backend_dir = Path(__file__).parent.parent / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from backend.app.models.model_registry import ModelRegistry  # noqa: E402
from ml.dataset import DatasetBundle  # noqa: E402

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


@dataclass
class TrainingResult:
    model_path: str
    model_version: str
    metrics: dict[str, Any]
    params: dict[str, Any]


class ModelTrainer:
    def __init__(
        self,
        session: Session,
        model_version: str = "v1.0.0",
        model_dir: Path | None = None,
    ) -> None:
        self._session = session
        self._model_version = model_version
        self._model_dir = model_dir or MODELS_DIR
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._model: LogisticRegression | None = None

    def train_logistic(self, bundle: DatasetBundle, model_name: str = "logistic") -> TrainingResult:
        X_train = bundle.X_train
        y_train = bundle.y_train
        X_val = bundle.X_val
        y_val = bundle.y_val

        params: dict[str, Any] = {}
        model = LogisticRegression(max_iter=1000)
        model.fit(X_train, y_train)
        self._model = model

        metrics: dict[str, Any] = {
            "train_accuracy": float(model.score(X_train, y_train)),
            "val_accuracy": float(model.score(X_val, y_val)),
            "train_samples": int(X_train.shape[0]),
            "val_samples": int(X_val.shape[0]),
            "feature_dim": int(X_train.shape[1]),
        }

        version_tag = f"v{self._model_version}"
        filename = f"{model_name}_{version_tag}.joblib"
        model_path = self._model_dir / filename
        joblib.dump(model, model_path)

        registry = ModelRegistry(
            name=model_name,
            version=version_tag,
            feature_version=bundle.feature_version,
            params=params,
            model_artifact_path=str(model_path),
            metrics=metrics,
        )
        self._session.add(registry)
        self._session.commit()

        logger.info("Trained %s %s on %d samples", model_name, version_tag, X_train.shape[0])
        return TrainingResult(
            model_path=str(model_path),
            model_version=version_tag,
            metrics=metrics,
            params=params,
        )

    def get_trained_model(self) -> LogisticRegression:
        if self._model is None:
            raise ValueError("No model has been trained yet")
        return self._model

    def get_model_version(self) -> str:
        return self._model_version

    def get_model_dir(self) -> Path:
        return self._model_dir

    def get_model_registry_entry(self, model_name: str) -> ModelRegistry | None:
        version_tag = f"v{self._model_version}"
        return (
            self._session.query(ModelRegistry)
            .filter_by(name=model_name, version=version_tag)
            .first()
        )

    def get_all_model_registry_entries(self, model_name: str) -> list[ModelRegistry]:
        return (
            self._session.query(ModelRegistry)
            .filter_by(name=model_name)
            .order_by(ModelRegistry.created_at.desc())
            .all()
        )

    def get_latest_model_registry_entry(self, model_name: str) -> ModelRegistry | None:
        entries = self.get_all_model_registry_entries(model_name)
        if entries:
            return entries[0]
        return None

    def get_model_metrics(self, model_name: str) -> dict[str, Any]:
        entry = self.get_latest_model_registry_entry(model_name)
        if entry is None:
            raise ValueError(f"No registry entry found for model {model_name}")
        return entry.metrics

    def get_model_params(self, model_name: str) -> dict[str, Any]:
        entry = self.get_latest_model_registry_entry(model_name)
        if entry is None:
            raise ValueError(f"No registry entry found for model {model_name}")
        return entry.params

    def get_model_artifact_path(self, model_name: str) -> str:
        entry = self.get_latest_model_registry_entry(model_name)
        if entry is None:
            raise ValueError(f"No registry entry found for model {model_name}")
        return entry.model_artifact_path

    def get_model_registry_info(self, model_name: str) -> dict[str, Any]:
        entry = self.get_latest_model_registry_entry(model_name)
        if entry is None:
            raise ValueError(f"No registry entry found for model {model_name}")
        return {
            "name": entry.name,
            "version": entry.version,
            "feature_version": entry.feature_version,
            "params": entry.params,
            "metrics": entry.metrics,
            "model_artifact_path": entry.model_artifact_path,
            "created_at": entry.created_at.isoformat(),
        }

    def get_all_model_registry_info(self, model_name: str) -> list[dict[str, Any]]:
        entries = self.get_all_model_registry_entries(model_name)
        return [
            {
                "name": entry.name,
                "version": entry.version,
                "feature_version": entry.feature_version,
                "params": entry.params,
                "metrics": entry.metrics,
                "model_artifact_path": entry.model_artifact_path,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in entries
        ]

    def get_model_registry_entry_by_version(
        self, model_name: str, version: str
    ) -> ModelRegistry | None:
        version_tag = f"v{version}"
        return (
            self._session.query(ModelRegistry)
            .filter_by(name=model_name, version=version_tag)
            .first()
        )
