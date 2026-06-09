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

# Ensure workspace root is on path for backend.app imports
_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from ml.dataset import DatasetBundle  # noqa: E402


# Lazy import to avoid circular dependency with SQLAlchemy metadata
def _get_model_registry():
    from backend.app.models.model_registry import ModelRegistry  # noqa: E402

    return ModelRegistry


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

        ModelRegistry = _get_model_registry()
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
