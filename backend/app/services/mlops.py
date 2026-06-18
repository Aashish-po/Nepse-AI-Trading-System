"""MLOps orchestration service (Phase 12).

Bridges the meta-learning utilities (``ml/meta_learning.py``) with the persisted
model registry: champion selection across registered models, retraining-need
assessment, and triggering an actual retrain via ``ModelTrainer``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from app.models.model_registry import ModelRegistry
from sqlalchemy.orm import Session

_workspace_root = Path(__file__).parent.parent.parent.parent
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

logger = logging.getLogger(__name__)


class MLOpsService:
    """Coordinate model selection and retraining over the registry."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _registry_dicts(self, name: str | None = None) -> list[dict[str, Any]]:
        query = self._session.query(ModelRegistry)
        if name:
            query = query.filter(ModelRegistry.name == name)
        entries = query.order_by(ModelRegistry.created_at.desc()).all()
        return [
            {
                "id": e.id,
                "model_id": (e.params or {}).get("model_id") or e.version,
                "name": e.name,
                "version": e.version,
                "metrics": e.metrics or {},
                "params": e.params or {},
                "created_at": e.created_at,
            }
            for e in entries
        ]

    def select_champion(
        self, name: str | None = None, metric: str = "sharpe_ratio"
    ) -> dict[str, Any] | None:
        """Pick the best registered model by ``metric``."""
        from ml.meta_learning import ModelSelector

        selector = ModelSelector(metric=metric)
        best = selector.select_best(self._registry_dicts(name))
        return best.to_dict() if best else None

    def rank_models(
        self, name: str | None = None, metric: str = "sharpe_ratio"
    ) -> list[dict[str, Any]]:
        from ml.meta_learning import ModelSelector

        selector = ModelSelector(metric=metric)
        return [c.to_dict() for c in selector.rank(self._registry_dicts(name))]

    def assess_retraining(
        self,
        model_ref: str | int,
        metric: str = "sharpe_ratio",
        drift_results: list[Any] | None = None,
        **policy_kwargs: Any,
    ) -> dict[str, Any]:
        """Evaluate whether the referenced model should be retrained."""
        from ml.meta_learning import RetrainPolicy, _extract_metric

        entry = self._resolve(model_ref)
        champion = self.select_champion(name=entry.name, metric=metric)
        baseline = champion["metric_value"] if champion else None
        current = _extract_metric(entry.metrics or {}, metric)

        policy = RetrainPolicy(metric=metric, **policy_kwargs)
        decision = policy.evaluate(
            drift_results=drift_results,
            current_metric=current,
            baseline_metric=baseline,
            model_created_at=entry.created_at,
        )
        result = decision.to_dict()
        result["model_version"] = entry.version
        result["champion"] = champion
        return result

    def retrain(
        self, symbols: list[str], model_name: str = "logistic", random_state: int = 42
    ) -> dict[str, Any]:
        """Trigger a fresh baseline training run for the given symbols."""
        from ml.dataset import DatasetBuilder
        from ml.training import ModelTrainer

        builder = DatasetBuilder(session=self._session, feature_version="v4.0.0")
        bundle = builder.build(symbols[0])
        trainer = ModelTrainer(session=self._session)
        result = trainer.train_baseline(bundle, model_name=model_name, random_state=random_state)
        return {
            "model_id": result.get("model_id"),
            "promotion_status": result.get("promotion_status"),
            "metrics": result.get("metrics"),
        }

    def _resolve(self, model_ref: str | int) -> ModelRegistry:
        import sqlalchemy as sa

        ref = str(model_ref)
        query = self._session.query(ModelRegistry)
        entry = None
        if ref.isdigit():
            entry = query.filter(ModelRegistry.id == int(ref)).first()
        if entry is None:
            entry = query.filter(
                sa.or_(
                    ModelRegistry.version == ref,
                    ModelRegistry.version == f"v{ref}",
                    ModelRegistry.version.contains(ref),
                )
            ).first()
        if entry is None:
            raise ValueError(f"Model not found: {model_ref}")
        return entry

    def retrain_lstm_online(
        self,
        symbol: str,
        promoter_threshold: float = 0.02,
        lookback_days: int = 252,
    ) -> dict[str, Any]:
        """
        Online LSTM retraining: daily model refresh with walk-forward validation.

        This implements the "online learning" pattern:
        1. Retrain LSTM on last 252 days of data
        2. Walk-forward validate on next 20 days
        3. If new model beats old by >2% Sharpe → promote
        4. Else → keep old model

        Args:
            symbol: Stock symbol to retrain for
            promoter_threshold: Minimum Sharpe improvement to promote (default 2%)
            lookback_days: Days of history to train on (default 252 trading days)

        Returns:
            Dict with retrain_status, new_metrics, promoted flag
        """
        from datetime import date, timedelta

        from ml.dataset import DatasetBuilder
        from ml.lstm import LSTMTrainer

        # Get date range
        end_date = date.today()
        start_date = end_date - timedelta(days=int(lookback_days * 1.5))  # Extra for walk-forward

        # Build dataset
        builder = DatasetBuilder(session=self._session, feature_version="v4.0.0")

        try:
            all_X, all_y, all_dates, all_returns, _ = builder._build_full_dataset(
                [symbol], start_date, end_date
            )
        except Exception as e:
            logger.warning(f"Failed to build dataset for {symbol}: {e}")
            return {"status": "failed", "error": str(e)}

        if all_X is None or len(all_X) < 100:
            return {"status": "skipped", "reason": "Insufficient data"}

        # Split for walk-forward validation
        train_n = min(lookback_days, len(all_X) - 40)
        train_X, train_y = all_X.iloc[:train_n].to_numpy(), all_y.iloc[:train_n].to_numpy()
        val_X, val_y = (
            all_X.iloc[train_n : train_n + 20].to_numpy(),
            all_y.iloc[train_n : train_n + 20].to_numpy(),
        )

        # Train new LSTM
        trainer = LSTMTrainer(device="cpu", random_state=42)
        result = trainer.train_lstm(
            X_train=train_X,
            y_train=train_y,
            X_val=val_X,
            y_val=val_y,
            epochs=50,
            batch_size=32,
            patience=5,
            model_path=f"models/lstm_{symbol}_online.pt",
        )

        # Compare with existing model if any
        old_sharpe = 0.0
        try:
            old_model = (
                self._session.query(ModelRegistry)
                .filter(
                    ModelRegistry.name == f"lstm_{symbol}",
                )
                .order_by(ModelRegistry.created_at.desc())
                .first()
            )
            if old_model and old_model.metrics:
                old_sharpe = old_model.metrics.get("sharpe_ratio", 0.0)
        except Exception:
            pass

        # Calculate Sharpe from validation accuracy as proxy
        new_sharpe = 0.0
        if result.get("metrics"):
            val_acc = result.get("metrics", {}).get("val_acc", 0.0)
            # Use accuracy as proxy for Sharpe (rough approximation)
            new_sharpe = float(val_acc * 2.0) - 1.0  # Map 0.5 acc -> 0 sharpe

        sharpe_improvement = new_sharpe - old_sharpe

        # Register new model
        import uuid

        model_id = str(uuid.uuid4())[:8]

        registry = ModelRegistry(
            name=f"lstm_{symbol}",
            version=f"v{model_id}",
            feature_version="v4.0.0",
            params={
                "random_state": 42,
                "model_type": "lstm",
                "status": "promoted" if sharpe_improvement > promoter_threshold else "candidate",
                "retrain_type": "online",
            },
            model_artifact_path=result.get("path", ""),
            metrics={
                "sharpe_ratio": new_sharpe,
                "best_val_loss": result.get("metrics", {}).get("best_val_loss", 0.0),
                "val_acc": result.get("metrics", {}).get("val_acc", 0.0),
            },
        )
        self._session.add(registry)
        self._session.commit()

        return {
            "status": "completed",
            "model_id": model_id,
            "old_sharpe": old_sharpe,
            "new_sharpe": new_sharpe,
            "sharpe_improvement": sharpe_improvement,
            "promoted": sharpe_improvement > promoter_threshold,
        }
