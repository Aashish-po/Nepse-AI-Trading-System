"""Model explainability: feature importance, attribution, and trade explanations.

Phase 11. Uses SHAP when available for both global and local (per-prediction)
attributions, and falls back to model-native methods (linear coefficients,
tree ``feature_importances_``, or permutation importance) so the service still
works in environments where SHAP cannot be installed.

All explanations are advisory and intended to help a human researcher understand
*why* a model produced a given output. They do not constitute financial advice.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

from ml.feature_vector import FEATURE_ORDER  # noqa: E402

logger = logging.getLogger(__name__)

try:
    import shap  # type: ignore[import-untyped]

    SHAP_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    shap = None  # type: ignore[assignment]
    SHAP_AVAILABLE = False


@dataclass
class FeatureContribution:
    """A single feature's contribution to an output."""

    feature: str
    value: float
    contribution: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "value": float(self.value),
            "contribution": float(self.contribution),
        }


@dataclass
class GlobalImportance:
    """Global feature importance ranking for a model."""

    method: str
    importances: list[FeatureContribution] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "importances": [c.to_dict() for c in self.importances],
        }


@dataclass
class LocalExplanation:
    """Per-prediction explanation (local attribution)."""

    method: str
    prediction: int
    base_value: float
    contributions: list[FeatureContribution] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "prediction": int(self.prediction),
            "base_value": float(self.base_value),
            "contributions": [c.to_dict() for c in self.contributions],
        }


def _unwrap_estimator(model: Any) -> Any:
    """Return the underlying estimator, unwrapping calibration wrappers."""
    # CalibratedClassifierCV stores fitted sub-estimators in calibrated_classifiers_
    calibrated = getattr(model, "calibrated_classifiers_", None)
    if calibrated:
        inner = getattr(calibrated[0], "estimator", None)
        if inner is not None:
            return inner
    # Only unwrap calibration-style wrappers, never ensembles (whose ``estimator``
    # attribute is an unfitted base template).
    if type(model).__name__ in {"CalibratedClassifierCV", "Pipeline"}:
        inner = getattr(model, "estimator", None) or getattr(model, "base_estimator", None)
        if inner is not None and inner is not model:
            return inner
    return model


def _feature_names(n: int) -> list[str]:
    """Return feature names, padding/truncating to match the model's input dim."""
    if n == len(FEATURE_ORDER):
        return list(FEATURE_ORDER)
    if n < len(FEATURE_ORDER):
        return list(FEATURE_ORDER[:n])
    return list(FEATURE_ORDER) + [f"feature_{i}" for i in range(len(FEATURE_ORDER), n)]


class ExplainabilityService:
    """Produce global and local explanations for trained classifiers."""

    def __init__(self, use_shap: bool = True) -> None:
        self._use_shap = use_shap and SHAP_AVAILABLE

    # ------------------------------------------------------------------ global
    def global_importance(
        self,
        model: Any,
        background: NDArray[np.float64] | None = None,
        top_k: int | None = None,
    ) -> GlobalImportance:
        """Compute global feature importance.

        Preference order: SHAP (mean |value| over background) → native
        coefficients/feature_importances_ → uniform fallback.
        """
        estimator = _unwrap_estimator(model)

        if self._use_shap and background is not None and len(background) > 0:
            try:
                return self._shap_global(model, background, top_k)
            except Exception as exc:  # pragma: no cover - shap edge cases
                logger.warning("SHAP global importance failed, falling back: %s", exc)

        importances = self._native_importance(estimator)
        names = _feature_names(len(importances))
        contribs = [
            FeatureContribution(feature=names[i], value=0.0, contribution=float(importances[i]))
            for i in range(len(importances))
        ]
        contribs.sort(key=lambda c: abs(c.contribution), reverse=True)
        if top_k is not None:
            contribs = contribs[:top_k]
        method = (
            "coefficients"
            if hasattr(estimator, "coef_")
            else (
                "feature_importances" if hasattr(estimator, "feature_importances_") else "uniform"
            )
        )
        return GlobalImportance(method=method, importances=contribs)

    def _native_importance(self, estimator: Any) -> NDArray[np.float64]:
        if hasattr(estimator, "feature_importances_"):
            return np.asarray(estimator.feature_importances_, dtype=np.float64)
        if hasattr(estimator, "coef_"):
            coef = np.asarray(estimator.coef_, dtype=np.float64)
            # Multi-class: aggregate absolute coefficients across classes.
            if coef.ndim > 1:
                return np.mean(np.abs(coef), axis=0)
            return np.abs(coef)
        n = len(FEATURE_ORDER)
        return np.full(n, 1.0 / n, dtype=np.float64)

    def _shap_global(
        self, model: Any, background: NDArray[np.float64], top_k: int | None
    ) -> GlobalImportance:
        values = self._shap_values(model, background)
        mean_abs = np.mean(np.abs(values), axis=0)
        names = _feature_names(len(mean_abs))
        contribs = [
            FeatureContribution(feature=names[i], value=0.0, contribution=float(mean_abs[i]))
            for i in range(len(mean_abs))
        ]
        contribs.sort(key=lambda c: abs(c.contribution), reverse=True)
        if top_k is not None:
            contribs = contribs[:top_k]
        return GlobalImportance(method="shap", importances=contribs)

    # ------------------------------------------------------------------- local
    def explain_prediction(
        self,
        model: Any,
        x: NDArray[np.float64],
        background: NDArray[np.float64] | None = None,
        top_k: int | None = None,
    ) -> LocalExplanation:
        """Explain a single prediction.

        ``x`` is a 1-D feature vector. Returns per-feature contributions.
        """
        x = np.asarray(x, dtype=np.float64).reshape(1, -1)
        prediction = int(model.predict(x)[0])

        if self._use_shap and background is not None and len(background) > 0:
            try:
                return self._shap_local(model, x, background, prediction, top_k)
            except Exception as exc:  # pragma: no cover - shap edge cases
                logger.warning("SHAP local explanation failed, falling back: %s", exc)

        # Fallback: contribution = coefficient * feature value (linear) or
        # feature_importances_ * normalized value (tree).
        estimator = _unwrap_estimator(model)
        names = _feature_names(x.shape[1])
        weights = self._native_importance(estimator)
        if len(weights) != x.shape[1]:
            weights = np.resize(weights, x.shape[1])
        raw = x.flatten() * weights
        base = 0.0
        contribs = [
            FeatureContribution(feature=names[i], value=float(x[0, i]), contribution=float(raw[i]))
            for i in range(x.shape[1])
        ]
        contribs.sort(key=lambda c: abs(c.contribution), reverse=True)
        if top_k is not None:
            contribs = contribs[:top_k]
        method = "coefficients" if hasattr(estimator, "coef_") else "feature_importances"
        return LocalExplanation(
            method=method, prediction=prediction, base_value=base, contributions=contribs
        )

    def _shap_local(
        self,
        model: Any,
        x: NDArray[np.float64],
        background: NDArray[np.float64],
        prediction: int,
        top_k: int | None,
    ) -> LocalExplanation:
        values, base = self._shap_values(model, x, background=background, return_base=True)
        row = values[0]
        names = _feature_names(len(row))
        contribs = [
            FeatureContribution(feature=names[i], value=float(x[0, i]), contribution=float(row[i]))
            for i in range(len(row))
        ]
        contribs.sort(key=lambda c: abs(c.contribution), reverse=True)
        if top_k is not None:
            contribs = contribs[:top_k]
        return LocalExplanation(
            method="shap", prediction=prediction, base_value=float(base), contributions=contribs
        )

    def _shap_values(
        self,
        model: Any,
        data: NDArray[np.float64],
        background: NDArray[np.float64] | None = None,
        return_base: bool = False,
    ) -> Any:
        """Compute SHAP values, selecting the positive class for binary models."""
        bg = background if background is not None else data
        # Cap background size for performance.
        if len(bg) > 100:
            idx = np.linspace(0, len(bg) - 1, 100).astype(int)
            bg = bg[idx]
        # SHAP's type hints are incomplete, so keep Pylance quiet.
        explainer = shap.Explainer(model.predict, bg)  # type: ignore[assignment]
        explanation = explainer(data)
        if isinstance(explanation, list):
            # Multi-output models may return a list of Explanation objects.
            explanation = explanation[-1]
        vals = np.asarray(explanation.values)
        base_vals = np.asarray(explanation.base_values)
        # Multi-output: pick the last column (positive/up class).
        if vals.ndim == 3:
            vals = vals[:, :, -1]
            base_vals = base_vals[:, -1] if base_vals.ndim > 1 else base_vals
        if return_base:
            base = float(np.mean(base_vals)) if np.ndim(base_vals) else float(base_vals)
            return vals, base
        return vals


def explain_trade(
    symbol: str,
    signal_type: str,
    prediction: int,
    explanation: LocalExplanation,
    confidence: float | None = None,
    top_k: int = 3,
) -> dict[str, Any]:
    """Produce a human-readable explanation of a trade/signal decision.

    Returns a structured advisory note summarizing the top drivers behind the
    model's recommendation.
    """
    direction = {1: "BUY", -1: "SELL", 0: "HOLD"}.get(prediction, str(prediction))
    drivers = explanation.contributions[:top_k]

    reasons: list[str] = []
    for c in drivers:
        verb = "supports" if c.contribution >= 0 else "weighs against"
        reasons.append(f"{c.feature} (={c.value:.4g}) {verb} the {direction} call")

    summary = (
        f"{direction} signal for {symbol} ({signal_type}). "
        f"Top drivers: " + "; ".join(reasons) + "."
    )
    if confidence is not None:
        summary += f" Model confidence: {confidence:.1%}."
    summary += " Advisory only — requires human review."

    return {
        "symbol": symbol,
        "signal_type": signal_type,
        "recommendation": direction,
        "confidence": confidence,
        "summary": summary,
        "drivers": [c.to_dict() for c in drivers],
        "method": explanation.method,
    }
