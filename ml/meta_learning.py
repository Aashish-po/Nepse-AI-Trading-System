"""Meta-learning and MLOps: model selection, auto-retraining, hyperparameter evolution.

Phase 12. Provides three capabilities on top of the Phase 7 training pipeline:

* **Model selection** — rank registered models by a chosen out-of-sample metric
  and pick the best (the "champion").
* **Auto-retraining triggers** — decide whether a model should be retrained based
  on feature drift, performance degradation versus the champion, or staleness.
* **Hyperparameter evolution** — a lightweight evolutionary search over a
  hyperparameter space, mutating the best candidates across generations.

These utilities are pure-Python where possible so they are testable without a
live training run; the heavier retraining is delegated to ``ModelTrainer``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------- selection
@dataclass
class ModelCandidate:
    """A model considered during selection."""

    model_id: str
    name: str
    version: str
    metric_value: float
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "version": self.version,
            "metric_value": self.metric_value,
            "metrics": self.metrics,
        }


def _extract_metric(metrics: dict[str, Any], key: str) -> float | None:
    """Read a metric, tolerating walk-forward aggregates ({"mean": ...})."""
    if not metrics or key not in metrics:
        return None
    value = metrics[key]
    if isinstance(value, dict):
        value = value.get("mean")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class ModelSelector:
    """Select the best model from a set of candidates by a metric."""

    # Metrics where a lower value is better.
    _LOWER_IS_BETTER = {"max_drawdown"}

    def __init__(self, metric: str = "sharpe_ratio") -> None:
        self._metric = metric

    def rank(self, models: list[dict[str, Any]]) -> list[ModelCandidate]:
        """Rank model registry dicts (best first). Skips models lacking the metric."""
        candidates: list[ModelCandidate] = []
        for m in models:
            value = _extract_metric(m.get("metrics") or {}, self._metric)
            if value is None:
                continue
            candidates.append(
                ModelCandidate(
                    model_id=str(m.get("model_id") or m.get("id") or m.get("version")),
                    name=m.get("name", "unknown"),
                    version=m.get("version", ""),
                    metric_value=value,
                    metrics=m.get("metrics") or {},
                )
            )
        reverse = self._metric not in self._LOWER_IS_BETTER
        candidates.sort(key=lambda c: c.metric_value, reverse=reverse)
        return candidates

    def select_best(self, models: list[dict[str, Any]]) -> ModelCandidate | None:
        ranked = self.rank(models)
        return ranked[0] if ranked else None


# ------------------------------------------------------------------ retraining
@dataclass
class RetrainDecision:
    should_retrain: bool
    reasons: list[str] = field(default_factory=list)
    triggers: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_retrain": self.should_retrain,
            "reasons": self.reasons,
            "triggers": self.triggers,
        }


class RetrainPolicy:
    """Decide whether a model needs retraining.

    Triggers:
    * drift — fraction of drifted features exceeds ``max_drift_fraction``.
    * performance — current metric dropped below ``min_metric`` or by more than
      ``max_degradation`` relative to the champion baseline.
    * staleness — model older than ``max_age_days``.
    """

    def __init__(
        self,
        max_drift_fraction: float = 0.3,
        min_metric: float = 0.5,
        max_degradation: float = 0.2,
        max_age_days: int = 90,
        metric: str = "sharpe_ratio",
    ) -> None:
        self._max_drift_fraction = max_drift_fraction
        self._min_metric = min_metric
        self._max_degradation = max_degradation
        self._max_age_days = max_age_days
        self._metric = metric

    def evaluate(
        self,
        drift_results: list[Any] | None = None,
        current_metric: float | None = None,
        baseline_metric: float | None = None,
        model_created_at: datetime | None = None,
        now: datetime | None = None,
    ) -> RetrainDecision:
        reasons: list[str] = []
        triggers: dict[str, Any] = {}

        if drift_results:
            n = len(drift_results)
            drifted = sum(1 for r in drift_results if getattr(r, "is_drift", False))
            fraction = drifted / n if n else 0.0
            triggers["drift_fraction"] = fraction
            if fraction > self._max_drift_fraction:
                reasons.append(
                    f"feature drift {fraction:.0%} exceeds {self._max_drift_fraction:.0%}"
                )

        if current_metric is not None:
            triggers["current_metric"] = current_metric
            if current_metric < self._min_metric:
                reasons.append(
                    f"{self._metric}={current_metric:.3f} below floor {self._min_metric}"
                )
            if baseline_metric is not None and baseline_metric > 0:
                degradation = (baseline_metric - current_metric) / abs(baseline_metric)
                triggers["degradation"] = degradation
                if degradation > self._max_degradation:
                    reasons.append(f"{self._metric} degraded {degradation:.0%} vs baseline")

        if model_created_at is not None:
            current = now or datetime.utcnow()
            # Normalize tz-aware vs naive.
            if model_created_at.tzinfo is not None and current.tzinfo is None:
                model_created_at = model_created_at.replace(tzinfo=None)
            age_days = (current - model_created_at).days
            triggers["age_days"] = age_days
            if age_days > self._max_age_days:
                reasons.append(f"model age {age_days}d exceeds {self._max_age_days}d")

        return RetrainDecision(should_retrain=bool(reasons), reasons=reasons, triggers=triggers)


# ----------------------------------------------------- hyperparameter evolution
@dataclass
class HyperparamSpace:
    """Search space for evolutionary hyperparameter optimization.

    Each entry maps a parameter name to a list of allowed values (categorical) or
    a ``(low, high)`` tuple for continuous/integer ranges.
    """

    params: dict[str, Any]

    def sample(self, rng: np.random.Generator) -> dict[str, Any]:
        chosen: dict[str, Any] = {}
        for name, spec in self.params.items():
            if (
                isinstance(spec, list | tuple)
                and len(spec) == 2
                and all(isinstance(v, int | float) for v in spec)
            ):
                low, high = spec
                if isinstance(low, int) and isinstance(high, int):
                    chosen[name] = int(rng.integers(low, high + 1))
                else:
                    chosen[name] = float(rng.uniform(low, high))
            elif isinstance(spec, list):
                chosen[name] = spec[int(rng.integers(0, len(spec)))]
            else:
                chosen[name] = spec
        return chosen

    def mutate(
        self, genome: dict[str, Any], rng: np.random.Generator, rate: float = 0.3
    ) -> dict[str, Any]:
        mutated = dict(genome)
        for name, spec in self.params.items():
            if rng.random() > rate:
                continue
            if (
                isinstance(spec, list | tuple)
                and len(spec) == 2
                and all(isinstance(v, int | float) for v in spec)
            ):
                low, high = spec
                if isinstance(low, int) and isinstance(high, int):
                    mutated[name] = int(rng.integers(low, high + 1))
                else:
                    mutated[name] = float(rng.uniform(low, high))
            elif isinstance(spec, list):
                mutated[name] = spec[int(rng.integers(0, len(spec)))]
        return mutated


@dataclass
class EvolutionResult:
    best_params: dict[str, Any]
    best_score: float
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "best_params": self.best_params,
            "best_score": self.best_score,
            "history": self.history,
        }


class HyperparameterEvolution:
    """Simple (μ + λ) evolutionary search over a hyperparameter space."""

    def __init__(
        self,
        space: HyperparamSpace,
        population_size: int = 8,
        generations: int = 5,
        elite: int = 2,
        seed: int = 42,
    ) -> None:
        self._space = space
        self._population_size = max(2, population_size)
        self._generations = max(1, generations)
        self._elite = max(1, min(elite, population_size))
        self._rng = np.random.default_rng(seed)

    def evolve(self, fitness: Callable[[dict[str, Any]], float]) -> EvolutionResult:
        """Run evolution. ``fitness`` maps a genome to a score (higher is better)."""
        population = [self._space.sample(self._rng) for _ in range(self._population_size)]
        history: list[dict[str, Any]] = []
        best_params: dict[str, Any] = population[0]
        best_score = -np.inf

        for gen in range(self._generations):
            scored = [(genome, float(fitness(genome))) for genome in population]
            scored.sort(key=lambda gs: gs[1], reverse=True)

            if scored[0][1] > best_score:
                best_score = scored[0][1]
                best_params = dict(scored[0][0])

            history.append(
                {
                    "generation": gen,
                    "best_score": scored[0][1],
                    "mean_score": float(np.mean([s for _, s in scored])),
                }
            )

            elites = [dict(genome) for genome, _ in scored[: self._elite]]
            children: list[dict[str, Any]] = list(elites)
            while len(children) < self._population_size:
                parent = elites[int(self._rng.integers(0, len(elites)))]
                children.append(self._space.mutate(parent, self._rng))
            population = children

        return EvolutionResult(best_params=best_params, best_score=best_score, history=history)
