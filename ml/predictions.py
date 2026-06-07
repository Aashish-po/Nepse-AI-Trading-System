"""Strategy-model decoupling via predictions interface."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Prediction:
    symbol: str
    date: str
    signal: int
    confidence: float
    direction: int
    strength: float


class ModelAdapter(ABC):
    """Abstract interface for ML models - strategies depend on this, not concrete models."""

    @abstractmethod
    def predict(self, features: dict[str, Any]) -> Prediction:
        """Returns prediction with signal, confidence, direction, strength."""
        ...


class MLModelAdapter(ModelAdapter):
    """Concrete adapter wrapping trained sklearn models."""

    def __init__(self, model_name: str, model_version: str, model_dir: str | None = None) -> None:
        from pathlib import Path

        from ml.inference import Predictor

        self._predictor = Predictor(
            model_name=model_name,
            model_version=model_version,
            model_dir=Path(model_dir) if model_dir else None,
        )
        self._model_name = model_name
        self._model_version = model_version

    def predict(self, features: dict[str, Any]) -> Prediction:
        result = self._predictor.predict(features)
        return Prediction(
            symbol=features.get("symbol", "UNKNOWN"),
            date=features.get("date", ""),
            signal=result["prediction"],
            confidence=result["confidence"],
            direction=result["prediction"],
            strength=result["confidence"],
        )


class StrategySignalGenerator:
    """Strategy uses predictions, not models directly - enables A/B testing."""

    def __init__(self, model_adapter: ModelAdapter) -> None:
        self._model = model_adapter

    def generate(
        self,
        symbol: str,
        date: str,
        features: dict[str, Any],
    ) -> Prediction:
        return self._model.predict(features)
