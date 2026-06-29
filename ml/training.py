"""ML model training and evaluation."""

# ruff: noqa: E402
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import joblib
import numpy as np
from numpy.typing import NDArray

_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"

if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

# Now safe to import everything else
from typing import TYPE_CHECKING, Any

from app.models.model_registry import ModelRegistry
from app.services.mlflow_tracking import mlflow_tracker
from sklearn.linear_model import LogisticRegression
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from ml.dataset import DatasetBuilder

try:
    from sklearn.ensemble import RandomForestClassifier

    RF_AVAILABLE = True
except ImportError:
    RandomForestClassifier = None  # type: ignore[misc, assignment]
    RF_AVAILABLE = False

try:
    from xgboost import XGBClassifier

    XGB_AVAILABLE = True
except ImportError:
    XGBClassifier = None  # type: ignore[assignment, misc]
    XGB_AVAILABLE = False

import uuid

from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

from ml.dataset import DatasetBundle
from ml.meta_learning import HyperparameterEvolution, HyperparamSpace

# ... rest of ml/training.py continues unchanged ...

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

        try:
            mlflow_tracker.log_model_training(
                model_name=model_name,
                model_version=version_tag,
                feature_version=bundle.feature_version,
                symbol=bundle.symbol,
                split_sizes={
                    "train_size": int(X_train.shape[0]),
                    "val_size": int(X_val.shape[0]),
                    "test_size": int(bundle.X_test.shape[0]),
                },
                metrics=metrics,
                model_path=model_path,
            )
        except Exception as exc:
            logger.warning("MLflow model training logging failed: %s", exc)

        logger.info("Trained %s %s on %d samples", model_name, version_tag, X_train.shape[0])
        return TrainingResult(
            model_path=str(model_path),
            model_version=version_tag,
            metrics=metrics,
            params=params,
        )

    def train_baseline(
        self,
        bundle_or_dataset: DatasetBundle,
        model_name: str = "logistic",
        random_state: int = 42,
    ) -> dict[str, Any]:
        """
        Train a baseline model with deterministic promotion gate.

        Args:
            bundle_or_dataset: Either a DatasetBundle or DatasetBuilder for walk-forward
            model_name: One of "logistic", "random_forest", "xgboost"
            random_state: For reproducibility

        Returns:
            dict with model_id, model, metrics, promotion_status
        """
        if isinstance(bundle_or_dataset, DatasetBundle):
            X, y = bundle_or_dataset.X_train, bundle_or_dataset.y_train
            feature_version = bundle_or_dataset.feature_version
            test_X, test_y = bundle_or_dataset.X_test, bundle_or_dataset.y_test
        else:
            raise ValueError("train_baseline requires a DatasetBundle")

        model = self._create_model(model_name, random_state)

        # Calibrate probabilities when supported, but avoid failing when the dataset
        # is too small / too imbalanced for the requested CV folds.
        calibrated_model = None
        if hasattr(model, "predict_proba"):
            cv_folds = 3
            unique, counts = np.unique(y, return_counts=True)
            # Each fold must contain at least one sample per class.
            if counts.min() < cv_folds:
                # Choose the largest cv that still guarantees >=1 sample per class
                cv_folds = max(2, int(counts.min()))
            # CalibratedClassifierCV requires each class to appear in every fold.
            # If we still can't satisfy that constraint, fall back to uncalibrated.
            if cv_folds >= 2 and counts.min() >= cv_folds:
                calibrated_model = CalibratedClassifierCV(model, cv=cv_folds)

        if calibrated_model is None:
            calibrated_model = model

        calibrated_model.fit(X, y)

        train_metrics = self._evaluate_model(calibrated_model, X, y)
        test_metrics = self._evaluate_model(
            calibrated_model,
            test_X,
            test_y,
            returns=bundle_or_dataset.returns_test,
        )

        # Promotion must be decided on out-of-sample (test) performance. Train metrics are
        # kept separately for diagnostics only — never as the gate's headline numbers.
        metrics = {
            "accuracy": test_metrics["accuracy"],
            "precision": test_metrics["precision"],
            "recall": test_metrics["recall"],
            "f1_weighted": test_metrics["f1_weighted"],
            "roc_auc": test_metrics["roc_auc"],
            "sharpe_ratio": test_metrics.get("sharpe_ratio", 0.0),
            "max_drawdown": test_metrics.get("max_drawdown", 0.0),
            "win_rate": test_metrics.get("win_rate", 0.0),
            "train_accuracy": train_metrics["accuracy"],
            "train_precision": train_metrics["precision"],
            "train_recall": train_metrics["recall"],
            "train_f1_weighted": train_metrics["f1_weighted"],
            "train_roc_auc": train_metrics["roc_auc"],
        }

        promotion_status = self._promotion_gate(metrics)

        model_id = str(uuid.uuid4())[:8]
        model_path = self._model_dir / f"{model_name}_v{model_id}.joblib"
        joblib.dump(calibrated_model, model_path)

        registry = ModelRegistry(
            name=model_name,
            version=f"v{model_id}",
            feature_version=feature_version,
            params={
                "random_state": random_state,
                "model_type": model_name,
                "status": promotion_status,
            },
            model_artifact_path=str(model_path),
            metrics=metrics,
        )
        self._session.add(registry)
        self._session.commit()

        return {
            "model_id": model_id,
            "model": calibrated_model,
            "metrics": metrics,
            "promotion_status": promotion_status,
        }

    def train_walk_forward(
        self,
        builder: DatasetBuilder,
        symbols: list[str],
        start_date: date,
        end_date: date,
        model_name: str = "logistic",
        random_state: int = 42,
        train_size: int = 252,
        test_size: int = 63,
        step: int = 63,
    ) -> dict[str, Any]:
        """
        Train across walk-forward folds with time-series cross-validation.

        Returns aggregated metrics (mean ± std across folds).
        """
        fold_metrics = []
        all_X, all_y, _all_dates, all_returns, _all_prices = builder._build_full_dataset(
            symbols, start_date, end_date
        )
        if all_X.empty:
            return {"error": "No valid folds generated"}

        n = len(all_X)
        # Embargo between train and test so feature windows (lookback=20) and label
        # horizons do not straddle the boundary. Mirrors DatasetBuilder.walk_forward_cv.
        embargo = max(20, 1)
        for start in range(0, n - train_size - embargo - test_size + 1, step):
            train_end = start + train_size
            test_start = train_end + embargo
            test_end = test_start + test_size
            train_X = all_X.iloc[start:train_end].reset_index(drop=True)
            train_y = all_y.iloc[start:train_end].reset_index(drop=True)
            test_X = all_X.iloc[test_start:test_end].reset_index(drop=True)
            test_y = all_y.iloc[test_start:test_end].reset_index(drop=True)
            test_returns = np.array(all_returns[test_start:test_end], dtype=np.float64)

            model = self._create_model(model_name, random_state)
            model.fit(train_X.values, train_y.values)

            fold_metrics.append(
                self._evaluate_model(model, test_X.values, test_y.values, returns=test_returns)
            )

        if not fold_metrics:
            return {"error": "No valid folds generated"}

        aggregated = {}
        for key in fold_metrics[0].keys():
            values = [m[key] for m in fold_metrics]
            aggregated[key] = {
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }

        avg_sharpe = aggregated.get("sharpe_ratio", {}).get("mean", 0)
        promotion_status = "promoted" if avg_sharpe > 1.0 else "rejected"

        model_id = str(uuid.uuid4())[:8]

        # Persist model for walk-forward training
        feature_version = "v4.0.0"
        model = self._create_model(model_name, random_state)
        model.fit(all_X.values, all_y.values)

        model_path = self._model_dir / f"{model_name}_v{model_id}.joblib"
        joblib.dump(model, model_path)

        registry = ModelRegistry(
            name=model_name,
            version=f"v{model_id}",
            feature_version=feature_version,
            params={
                "random_state": random_state,
                "model_type": model_name,
                "status": promotion_status,
                "n_folds": len(fold_metrics),
            },
            model_artifact_path=str(model_path),
            metrics=aggregated,
        )
        self._session.add(registry)
        self._session.commit()

        return {
            "model_id": model_id,
            "model": model,
            "model_name": model_name,
            "metrics": aggregated,
            "promotion_status": promotion_status,
            "n_folds": len(fold_metrics),
        }

    def _create_model(
        self,
        model_name: str,
        random_state: int,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Instantiate an estimator, optionally overriding hyperparameters.

        ``params`` (e.g. from :meth:`train_with_evolution`) override the per-model
        defaults below. Unknown keys are passed straight through to the estimator.
        """
        overrides = params or {}
        if model_name == "logistic":
            kwargs: dict[str, Any] = {
                "random_state": random_state,
                "max_iter": 1000,
                "class_weight": "balanced",
            }
            kwargs.update(overrides)
            return LogisticRegression(**kwargs)
        elif model_name == "random_forest":
            if RandomForestClassifier is None:
                raise ValueError("RandomForestClassifier not available")
            kwargs = {
                "n_estimators": 100,
                "random_state": random_state,
                "class_weight": "balanced",
            }
            kwargs.update(overrides)
            return RandomForestClassifier(**kwargs)
        elif model_name == "xgboost":
            if not XGB_AVAILABLE or XGBClassifier is None:
                raise ValueError("XGBClassifier not available - install xgboost")
            kwargs = {
                "random_state": random_state,
                "eval_metric": "logloss",
                "tree_method": "hist",
            }
            kwargs.update(overrides)
            return XGBClassifier(**kwargs)
        else:
            raise ValueError(f"Unknown model: {model_name}")

    def _default_search_space(self, model_name: str) -> HyperparamSpace:
        """Per-model hyperparameter search space for evolutionary tuning."""
        if model_name == "logistic":
            return HyperparamSpace(
                params={"C": [0.01, 0.1, 1.0, 10.0], "solver": ["lbfgs", "liblinear"]}
            )
        elif model_name == "random_forest":
            return HyperparamSpace(
                params={
                    "n_estimators": [50, 100, 200, 300],
                    "max_depth": [3, 5, 10, 20],
                    "min_samples_leaf": [1, 2, 5],
                }
            )
        elif model_name == "xgboost":
            return HyperparamSpace(
                params={
                    "n_estimators": [50, 100, 200],
                    "max_depth": [3, 5, 7],
                    "learning_rate": (0.01, 0.3),
                    "subsample": (0.6, 1.0),
                }
            )
        else:
            raise ValueError(f"Unknown model: {model_name}")

    def train_with_evolution(
        self,
        bundle: DatasetBundle,
        model_name: str = "random_forest",
        space: HyperparamSpace | None = None,
        population_size: int = 8,
        generations: int = 5,
        seed: int = 42,
        drawdown_penalty: float = 0.5,
    ) -> dict[str, Any]:
        """Evolutionary hyperparameter search, then train + register the winner.

        Fitness is the validation-set Sharpe ratio penalised by max drawdown
        (``sharpe - drawdown_penalty * max_drawdown``), evaluated on the bundle's
        validation split so the test split stays untouched for the promotion gate.

        Returns the same shape as :meth:`train_baseline` plus ``best_params`` and
        ``evolution_history``.
        """
        if bundle.returns_val is None:
            raise ValueError("train_with_evolution requires bundle.returns_val for fitness scoring")

        space = space or self._default_search_space(model_name)

        X_train, y_train = bundle.X_train, bundle.y_train
        X_val, y_val = bundle.X_val, bundle.y_val
        returns_val = np.asarray(bundle.returns_val, dtype=np.float64)

        def fitness(genome: dict[str, Any]) -> float:
            try:
                model = self._create_model(model_name, seed, params=genome)
                model.fit(X_train, y_train)
            except Exception as exc:
                # An invalid genome (e.g. incompatible solver/penalty) should lose,
                # not abort the whole search.
                logger.debug("Genome %s failed to fit: %s", genome, exc)
                return float("-inf")
            metrics = self._evaluate_model(model, X_val, y_val, returns=returns_val)
            return metrics["sharpe_ratio"] - drawdown_penalty * metrics["max_drawdown"]

        evolution = HyperparameterEvolution(
            space,
            population_size=population_size,
            generations=generations,
            seed=seed,
        )
        result = evolution.evolve(fitness)
        best_params = result.best_params

        # Train the final model on train, score it out-of-sample on test for the gate.
        model = self._create_model(model_name, seed, params=best_params)
        model.fit(X_train, y_train)
        test_metrics = self._evaluate_model(
            model, bundle.X_test, bundle.y_test, returns=bundle.returns_test
        )
        metrics = {
            "accuracy": test_metrics["accuracy"],
            "precision": test_metrics["precision"],
            "recall": test_metrics["recall"],
            "f1_weighted": test_metrics["f1_weighted"],
            "roc_auc": test_metrics["roc_auc"],
            "sharpe_ratio": test_metrics.get("sharpe_ratio", 0.0),
            "max_drawdown": test_metrics.get("max_drawdown", 0.0),
            "win_rate": test_metrics.get("win_rate", 0.0),
            "val_fitness": float(result.best_score),
        }

        promotion_status = self._promotion_gate(metrics)

        model_id = str(uuid.uuid4())[:8]
        model_path = self._model_dir / f"{model_name}_v{model_id}.joblib"
        joblib.dump(model, model_path)

        registry = ModelRegistry(
            name=model_name,
            version=f"v{model_id}",
            feature_version=bundle.feature_version,
            params={
                "model_type": model_name,
                "status": promotion_status,
                "tuning": "evolution",
                "best_params": best_params,
                "generations": generations,
                "population_size": population_size,
            },
            model_artifact_path=str(model_path),
            metrics=metrics,
        )
        self._session.add(registry)
        self._session.commit()

        return {
            "model_id": model_id,
            "model": model,
            "metrics": metrics,
            "promotion_status": promotion_status,
            "best_params": best_params,
            "best_score": float(result.best_score),
            "evolution_history": result.history,
        }

    def _evaluate_model(
        self, model, X: Any, y: Any, returns: NDArray[np.floating] | None = None
    ) -> dict[str, float]:
        y_pred = model.predict(X)

        # Prefer calibrated/wrapper probabilities; fall back to the base estimator only
        # when the wrapper itself cannot produce probabilities.
        y_proba = None
        if hasattr(model, "predict_proba"):
            y_proba = model.predict_proba(X)
        else:
            base_model = getattr(model, "base_estimator", None) or getattr(model, "estimator", None)
            if base_model is not None and hasattr(base_model, "predict_proba"):
                y_proba = base_model.predict_proba(X)

        unique_labels = len(np.unique(y))
        if unique_labels >= 2 and y_proba is not None:
            n_classes = y_proba.shape[1]
            if unique_labels == 2 and n_classes == 2:
                roc = float(roc_auc_score(y, y_proba[:, 1]))
            elif unique_labels == 2 and n_classes == 3:
                roc = float(roc_auc_score(y, y_proba[:, 1]))
            else:
                try:
                    roc = float(roc_auc_score(y, y_proba, average="weighted", multi_class="ovr"))
                except ValueError:
                    roc = 0.5
        else:
            roc = 0.5

        trading_metrics = {"sharpe_ratio": 0.0, "max_drawdown": 0.0, "win_rate": 0.0}
        if returns is not None and len(returns) == len(y_pred):
            positions = np.where(y_pred == 1, 1.0, np.where(y_pred == -1, -1.0, 0.0))
            strategy_returns = positions * np.asarray(returns, dtype=np.float64)
            active_trades = positions != 0
            if strategy_returns.size:
                mean = float(np.mean(strategy_returns))
                std = float(np.std(strategy_returns))
                sharpe = mean / std * np.sqrt(252.0) if std > 0 else 0.0
                cumulative = np.cumprod(1.0 + strategy_returns)
                peak = np.maximum.accumulate(cumulative)
                drawdown = (peak - cumulative) / np.where(peak == 0, 1.0, peak)
                trading_metrics = {
                    "sharpe_ratio": float(sharpe),
                    "max_drawdown": float(np.max(drawdown)),
                    "win_rate": float(np.mean(strategy_returns[active_trades] > 0))
                    if np.any(active_trades)
                    else 0.0,
                }

        return {
            "accuracy": float(accuracy_score(y, y_pred)),
            "precision": float(precision_score(y, y_pred, average="weighted", zero_division=0)),
            "recall": float(recall_score(y, y_pred, average="weighted", zero_division=0)),
            "f1_weighted": float(f1_score(y, y_pred, average="weighted", zero_division=0)),
            "roc_auc": float(roc),
            **trading_metrics,
        }

    def _promotion_gate(
        self,
        metrics: dict[str, float],
        baseline_metrics: dict[str, float] | None = None,
    ) -> str:
        """
        Gate: Model must beat buy-and-hold baseline.

        Requirements:
        - Sharpe > baseline_sharpe (or 0.5 if no baseline)
        - Max DD < 0.20
        - Win rate > 0.55
        """
        baseline_sharpe = 0.5  # Default: NEPSE buy-and-hold typical
        if baseline_metrics:
            baseline_sharpe = baseline_metrics.get("sharpe_ratio", 0.5)

        if (
            metrics.get("sharpe_ratio", 0) > baseline_sharpe
            and metrics.get("max_drawdown", 1.0) < 0.20
            and metrics.get("win_rate", 0) > 0.55
        ):
            return "promoted"
        return "rejected"

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
