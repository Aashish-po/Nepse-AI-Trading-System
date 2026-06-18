"""Tests for Phase 11: explainability and model governance."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from app.models.model_registry import ModelRegistry
from app.services.model_governance import GovernanceError, ModelGovernanceService
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

_WORKSPACE = Path(__file__).resolve().parent.parent.parent
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

from ml.explainability import ExplainabilityService, explain_trade  # noqa: E402
from ml.feature_vector import FEATURE_DIM  # noqa: E402


def _fit_logistic() -> LogisticRegression:
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, FEATURE_DIM))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    model = LogisticRegression(max_iter=500)
    model.fit(X, y)
    return model


def _fit_forest() -> RandomForestClassifier:
    rng = np.random.default_rng(1)
    X = rng.normal(size=(200, FEATURE_DIM))
    y = (X[:, 2] > 0).astype(int)
    model = RandomForestClassifier(n_estimators=20, random_state=0)
    model.fit(X, y)
    return model


class TestGlobalImportance:
    def test_logistic_native_importance(self) -> None:
        model = _fit_logistic()
        service = ExplainabilityService(use_shap=False)
        result = service.global_importance(model, top_k=5)
        assert result.method == "coefficients"
        assert len(result.importances) == 5
        # Sorted by absolute contribution descending.
        contribs = [abs(c.contribution) for c in result.importances]
        assert contribs == sorted(contribs, reverse=True)

    def test_forest_native_importance(self) -> None:
        model = _fit_forest()
        service = ExplainabilityService(use_shap=False)
        result = service.global_importance(model)
        assert result.method == "feature_importances"
        assert len(result.importances) == FEATURE_DIM

    def test_shap_global_importance(self) -> None:
        model = _fit_forest()
        rng = np.random.default_rng(2)
        background = rng.normal(size=(50, FEATURE_DIM))
        service = ExplainabilityService(use_shap=True)
        result = service.global_importance(model, background=background, top_k=5)
        # Either shap worked or it gracefully fell back.
        assert result.method in {"shap", "feature_importances"}
        assert len(result.importances) == 5


class TestLocalExplanation:
    def test_explain_prediction_fallback(self) -> None:
        model = _fit_logistic()
        service = ExplainabilityService(use_shap=False)
        x = np.ones(FEATURE_DIM)
        explanation = service.explain_prediction(model, x, top_k=3)
        assert explanation.prediction in (0, 1)
        assert len(explanation.contributions) == 3
        assert explanation.method == "coefficients"

    def test_explain_trade_summary(self) -> None:
        model = _fit_logistic()
        service = ExplainabilityService(use_shap=False)
        x = np.ones(FEATURE_DIM)
        explanation = service.explain_prediction(model, x, top_k=3)
        trade = explain_trade(
            symbol="NABIL",
            signal_type="ml",
            prediction=explanation.prediction,
            explanation=explanation,
            confidence=0.72,
        )
        assert trade["symbol"] == "NABIL"
        assert "Advisory only" in trade["summary"]
        assert len(trade["drivers"]) == 3


def _seed_model(db_session, status: str = "promoted") -> ModelRegistry:
    entry = ModelRegistry(
        name="logistic",
        version="vabc12345",
        feature_version="v4.0.0",
        params={"status": status, "model_type": "logistic"},
        model_artifact_path="models/logistic_vtest.joblib",
        metrics={"accuracy": 0.6},
    )
    db_session.add(entry)
    db_session.commit()
    return entry


class TestGovernance:
    def test_full_approval_lifecycle(self, db_session) -> None:
        entry = _seed_model(db_session)
        service = ModelGovernanceService(db_session)

        status = service.submit_for_approval(entry.id, notes="please review")
        assert status["governance_status"] == "pending_approval"
        assert status["production_ready"] is False

        status = service.approve(entry.id, reviewer="alice", notes="looks good")
        assert status["governance_status"] == "approved"
        assert status["reviewer"] == "alice"

        status = service.mark_production_ready(entry.id, reviewer="alice")
        assert status["governance_status"] == "production"
        assert status["production_ready"] is True

    def test_cannot_promote_without_approval(self, db_session) -> None:
        entry = _seed_model(db_session)
        service = ModelGovernanceService(db_session)
        with pytest.raises(GovernanceError):
            service.mark_production_ready(entry.id, reviewer="bob")

    def test_reject_blocks_production(self, db_session) -> None:
        entry = _seed_model(db_session)
        service = ModelGovernanceService(db_session)
        service.submit_for_approval(entry.id)
        status = service.reject(entry.id, reviewer="carol", notes="overfit")
        assert status["governance_status"] == "rejected"
        with pytest.raises(GovernanceError):
            service.mark_production_ready(entry.id, reviewer="carol")

    def test_list_by_state(self, db_session) -> None:
        entry = _seed_model(db_session)
        service = ModelGovernanceService(db_session)
        service.submit_for_approval(entry.id)
        pending = service.list_by_state("pending_approval")
        assert len(pending) == 1
        assert service.list_by_state("production") == []

    def test_resolve_by_version(self, db_session) -> None:
        _seed_model(db_session)
        service = ModelGovernanceService(db_session)
        status = service.get_status("vabc12345")
        assert status["version"] == "vabc12345"


class TestExplainabilityRoutes:
    def test_global_importance_endpoint(self, client, db_session) -> None:
        # Train + persist a real model so the artifact exists.
        from ml.training import MODELS_DIR

        model = _fit_logistic()
        import joblib

        path = MODELS_DIR / "logistic_vexpltest.joblib"
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, path)
        entry = ModelRegistry(
            name="logistic",
            version="vexpltest",
            feature_version="v4.0.0",
            params={"status": "promoted"},
            model_artifact_path=str(path),
            metrics={"accuracy": 0.6},
        )
        db_session.add(entry)
        db_session.commit()

        resp = client.get(f"/explain/models/{entry.id}/importance?top_k=5")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["importances"]) == 5
        assert body["method"] in {"coefficients", "shap"}

    def test_governance_endpoint_lifecycle(self, client, db_session) -> None:
        entry = _seed_model(db_session)
        r1 = client.post(f"/governance/models/{entry.id}/submit", json={"notes": "x"})
        assert r1.status_code == 200
        assert r1.json()["governance_status"] == "pending_approval"

        r2 = client.post(f"/governance/models/{entry.id}/approve", json={"reviewer": "alice"})
        assert r2.status_code == 200
        assert r2.json()["governance_status"] == "approved"

        r3 = client.post(f"/governance/models/{entry.id}/production", json={"reviewer": "alice"})
        assert r3.status_code == 200
        assert r3.json()["production_ready"] is True
