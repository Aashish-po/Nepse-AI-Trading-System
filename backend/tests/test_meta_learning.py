"""Tests for Phase 12: meta-learning and MLOps."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.models.model_registry import ModelRegistry
from app.services.mlops import MLOpsService

_WORKSPACE = Path(__file__).resolve().parent.parent.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

from ml.meta_learning import (  # noqa: E402
    HyperparameterEvolution,
    HyperparamSpace,
    ModelSelector,
    RetrainPolicy,
)


@dataclass
class _Drift:
    is_drift: bool


class TestModelSelector:
    def test_ranks_by_sharpe_descending(self) -> None:
        models = [
            {"id": 1, "name": "a", "version": "v1", "metrics": {"sharpe_ratio": 0.8}},
            {"id": 2, "name": "b", "version": "v2", "metrics": {"sharpe_ratio": 1.5}},
            {"id": 3, "name": "c", "version": "v3", "metrics": {"sharpe_ratio": 1.1}},
        ]
        selector = ModelSelector(metric="sharpe_ratio")
        best = selector.select_best(models)
        assert best is not None
        assert best.version == "v2"
        assert best.metric_value == 1.5

    def test_lower_is_better_for_drawdown(self) -> None:
        models = [
            {"id": 1, "name": "a", "version": "v1", "metrics": {"max_drawdown": 0.3}},
            {"id": 2, "name": "b", "version": "v2", "metrics": {"max_drawdown": 0.1}},
        ]
        selector = ModelSelector(metric="max_drawdown")
        best = selector.select_best(models)
        assert best is not None
        assert best.version == "v2"

    def test_handles_walk_forward_aggregates(self) -> None:
        models = [
            {"id": 1, "name": "a", "version": "v1", "metrics": {"sharpe_ratio": {"mean": 1.2}}},
        ]
        selector = ModelSelector(metric="sharpe_ratio")
        best = selector.select_best(models)
        assert best is not None
        assert best.metric_value == 1.2

    def test_skips_models_missing_metric(self) -> None:
        models = [
            {"id": 1, "name": "a", "version": "v1", "metrics": {"accuracy": 0.6}},
        ]
        selector = ModelSelector(metric="sharpe_ratio")
        assert selector.select_best(models) is None


class TestRetrainPolicy:
    def test_no_retrain_when_healthy(self) -> None:
        policy = RetrainPolicy()
        decision = policy.evaluate(
            drift_results=[_Drift(False), _Drift(False)],
            current_metric=1.2,
            baseline_metric=1.3,
            model_created_at=datetime.utcnow() - timedelta(days=5),
        )
        assert decision.should_retrain is False
        assert decision.reasons == []

    def test_drift_triggers_retrain(self) -> None:
        policy = RetrainPolicy(max_drift_fraction=0.3)
        decision = policy.evaluate(
            drift_results=[_Drift(True), _Drift(True), _Drift(False)],
        )
        assert decision.should_retrain is True
        assert any("drift" in r for r in decision.reasons)

    def test_low_metric_triggers_retrain(self) -> None:
        policy = RetrainPolicy(min_metric=0.5)
        decision = policy.evaluate(current_metric=0.2)
        assert decision.should_retrain is True

    def test_degradation_triggers_retrain(self) -> None:
        policy = RetrainPolicy(max_degradation=0.2, min_metric=0.0)
        decision = policy.evaluate(current_metric=0.7, baseline_metric=1.0)
        assert decision.should_retrain is True
        assert any("degraded" in r for r in decision.reasons)

    def test_staleness_triggers_retrain(self) -> None:
        policy = RetrainPolicy(max_age_days=30)
        decision = policy.evaluate(model_created_at=datetime.utcnow() - timedelta(days=120))
        assert decision.should_retrain is True
        assert any("age" in r for r in decision.reasons)


class TestHyperparameterEvolution:
    def test_converges_toward_target(self) -> None:
        space = HyperparamSpace(params={"x": (0.0, 10.0), "y": (0.0, 10.0)})
        target = {"x": 5.0, "y": 5.0}

        def fitness(genome: dict) -> float:
            return -((genome["x"] - target["x"]) ** 2 + (genome["y"] - target["y"]) ** 2)

        evo = HyperparameterEvolution(space, population_size=12, generations=15, seed=1)
        result = evo.evolve(fitness)
        # Best should be reasonably close to the target.
        assert abs(result.best_params["x"] - 5.0) < 2.0
        assert abs(result.best_params["y"] - 5.0) < 2.0
        # Score should improve (or hold) across generations.
        scores = [h["best_score"] for h in result.history]
        assert scores[-1] >= scores[0]

    def test_categorical_space(self) -> None:
        space = HyperparamSpace(params={"model": ["logistic", "rf", "xgboost"]})

        def fitness(genome: dict) -> float:
            return 1.0 if genome["model"] == "rf" else 0.0

        evo = HyperparameterEvolution(space, population_size=6, generations=5, seed=3)
        result = evo.evolve(fitness)
        assert result.best_params["model"] == "rf"


def _seed(db_session, version: str, sharpe: float, name: str = "logistic") -> ModelRegistry:
    entry = ModelRegistry(
        name=name,
        version=version,
        feature_version="v4.0.0",
        params={"status": "promoted", "model_id": version.lstrip("v")},
        model_artifact_path=f"models/{name}_{version}.joblib",
        metrics={"sharpe_ratio": sharpe, "max_drawdown": 0.1},
    )
    db_session.add(entry)
    db_session.commit()
    return entry


class TestMLOpsService:
    def test_select_champion(self, db_session) -> None:
        _seed(db_session, "vaaa", 0.9)
        _seed(db_session, "vbbb", 1.7)
        service = MLOpsService(db_session)
        champion = service.select_champion(metric="sharpe_ratio")
        assert champion is not None
        assert champion["version"] == "vbbb"

    def test_assess_retraining_stale_model(self, db_session) -> None:
        entry = _seed(db_session, "vccc", 0.3)
        service = MLOpsService(db_session)
        result = service.assess_retraining("vccc", metric="sharpe_ratio")
        assert result["model_version"] == "vccc"
        # Low sharpe (0.3 < 0.5 floor) should flag retraining.
        assert result["should_retrain"] is True
        assert entry.version == "vccc"


class TestMLOpsRoutes:
    def test_champion_endpoint(self, client, db_session) -> None:
        _seed(db_session, "vd1", 0.5)
        _seed(db_session, "vd2", 2.0)
        resp = client.get("/mlops/champion?metric=sharpe_ratio")
        assert resp.status_code == 200
        assert resp.json()["champion"]["version"] == "vd2"

    def test_rank_endpoint(self, client, db_session) -> None:
        _seed(db_session, "ve1", 0.5)
        _seed(db_session, "ve2", 2.0)
        resp = client.get("/mlops/rank?metric=sharpe_ratio")
        assert resp.status_code == 200
        models = resp.json()["models"]
        assert models[0]["version"] == "ve2"

    def test_evolve_endpoint(self, client) -> None:
        resp = client.post(
            "/mlops/evolve",
            json={
                "space": {"x": [0.0, 10.0], "y": [0.0, 10.0]},
                "target": {"x": 5.0, "y": 5.0},
                "population_size": 10,
                "generations": 10,
                "seed": 7,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "best_params" in body
        assert len(body["history"]) == 10
