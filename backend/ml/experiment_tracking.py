"""Experiment tracking for ML backtests and strategy iterations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

EXPERIMENTS_DIR = Path(__file__).resolve().parent.parent / "experiments"


@dataclass
class ExperimentRecord:
    experiment_id: str
    strategy_version: str
    model_version: str
    dataset_version: str
    metrics: dict[str, float]
    config: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ExperimentTracker:
    """Lightweight JSON-based experiment tracking."""

    def __init__(self, experiments_dir: Path | None = None) -> None:
        self._experiments_dir = experiments_dir or EXPERIMENTS_DIR
        self._experiments_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        strategy_version: str,
        model_version: str,
        dataset_version: str,
        metrics: dict[str, float],
        config: dict[str, Any] | None = None,
    ) -> str:
        experiment_id = str(uuid4())[:8]
        record = ExperimentRecord(
            experiment_id=experiment_id,
            strategy_version=strategy_version,
            model_version=model_version,
            dataset_version=dataset_version,
            metrics=metrics,
            config=config or {},
        )

        path = self._experiments_dir / f"exp_{experiment_id}.json"
        with open(path, "w") as f:
            json.dump(
                {
                    "experiment_id": record.experiment_id,
                    "strategy_version": record.strategy_version,
                    "model_version": record.model_version,
                    "dataset_version": record.dataset_version,
                    "metrics": record.metrics,
                    "config": record.config,
                    "timestamp": record.timestamp,
                },
                f,
                indent=2,
            )
        logger.info("Logged experiment %s", experiment_id)
        return experiment_id

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        path = self._experiments_dir / f"exp_{experiment_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)

    def list_by_strategy(self, strategy_version: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for p in self._experiments_dir.glob("exp_*.json"):
            with open(p) as f:
                data = json.load(f)
                if data.get("strategy_version") == strategy_version:
                    results.append(data)
        return sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)
