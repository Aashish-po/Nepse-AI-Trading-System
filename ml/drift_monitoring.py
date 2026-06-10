"""Feature drift monitoring for model validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class DriftResult:
    feature: str
    p_value: float
    drift_score: float
    is_drift: bool


class DriftMonitor:
    """Monitor feature distribution shifts over time."""

    def __init__(self, p_threshold: float = 0.05, psi_threshold: float = 0.2) -> None:
        self._p_threshold = p_threshold
        self._psi_threshold = psi_threshold

    def detect(
        self,
        reference: dict[str, NDArray[np.float64]],
        current: dict[str, NDArray[np.float64]],
    ) -> list[DriftResult]:
        """Detect drift between reference and current feature distributions."""
        results: list[DriftResult] = []
        for name in reference:
            if name not in current:
                continue
            ref_vals = reference[name][~np.isnan(reference[name])]
            cur_vals = current[name][~np.isnan(current[name])]
            if len(ref_vals) < 10 or len(cur_vals) < 10:
                continue

            _, p_value = stats.ks_2samp(ref_vals, cur_vals)  # type: ignore[misc]
            p_value = float(p_value)  # pyright: ignore[reportArgumentType]
            psi = self._compute_psi(ref_vals, cur_vals)

            is_drift = p_value < self._p_threshold or psi > self._psi_threshold
            results.append(
                DriftResult(
                    feature=name,
                    p_value=p_value,
                    drift_score=psi,
                    is_drift=is_drift,
                )
            )
        return results

    def _compute_psi(self, ref: NDArray[np.float64], cur: NDArray[np.float64]) -> float:
        ref_bins = np.percentile(ref, np.linspace(0, 100, 11))
        cur_bins = np.percentile(cur, np.linspace(0, 100, 11))
        all_bins = np.unique(np.concatenate([ref_bins, cur_bins]))

        ref_counts, _ = np.histogram(ref, bins=all_bins)
        cur_counts, _ = np.histogram(cur, bins=all_bins)

        ref_pct = ref_counts / len(ref) + 1e-8
        cur_pct = cur_counts / len(cur) + 1e-8

        psi = np.sum((ref_pct - cur_pct) * np.log(ref_pct / cur_pct))
        return float(psi)


class CorrelationMonitor:
    """Monitor feature correlation changes over time."""

    def __init__(self, threshold: float = 0.8) -> None:
        self._threshold = threshold

    def detect(
        self,
        reference: NDArray[np.float64],
        current: NDArray[np.float64],
    ) -> dict[str, Any]:
        if reference.shape[1] != current.shape[1]:
            return {"error": "shape_mismatch"}

        ref_corr = np.corrcoef(reference.T)
        cur_corr = np.corrcoef(current.T)

        corr_change = np.abs(ref_corr - cur_corr)
        mean_change = float(np.mean(corr_change))
        max_change = float(np.max(corr_change))

        return {
            "mean_correlation_change": mean_change,
            "max_correlation_change": max_change,
            "significant_change": mean_change > self._threshold,
        }


class TrustScoreMonitor:
    """Monitor trust score degradation over time."""

    def __init__(self, threshold: float = 0.5) -> None:
        self._threshold = threshold

    def check(self, scores: list[float]) -> dict[str, Any]:
        if not scores:
            return {"status": "no_data"}

        avg = float(np.mean(scores))
        recent = scores[-30:] if len(scores) >= 30 else scores
        recent_avg = float(np.mean(recent))

        return {
            "overall_avg": avg,
            "recent_avg": recent_avg,
            "degradation": avg - recent_avg,
            "below_threshold": recent_avg < self._threshold,
        }

    def check_trust_score_degradation(self, scores: list[float]) -> dict[str, Any]:
        if not scores:
            return {"status": "no_data"}

        avg_score = float(np.mean(scores))
        recent_scores = scores[-30:] if len(scores) >= 30 else scores
        recent_avg = float(np.mean(recent_scores))

        degradation = avg_score - recent_avg
        below_threshold = recent_avg < self._threshold

        return {
            "overall_avg": avg_score,
            "recent_avg": recent_avg,
            "degradation": degradation,
            "below_threshold": below_threshold,
        }

    def check_correlation_change(
        self, reference: NDArray[np.float64], current: NDArray[np.float64]
    ) -> dict[str, Any]:
        if reference.shape[1] != current.shape[1]:
            return {"error": "shape_mismatch"}

        ref_corr = np.corrcoef(reference.T)
        cur_corr = np.corrcoef(current.T)

        corr_change = np.abs(ref_corr - cur_corr)
        mean_change = float(np.mean(corr_change))
        max_change = float(np.max(corr_change))

        return {
            "mean_correlation_change": mean_change,
            "max_correlation_change": max_change,
            "significant_change": mean_change > self._threshold,
        }

    def check_feature_drift(
        self, reference: dict[str, NDArray[np.float64]], current: dict[str, NDArray[np.float64]]
    ) -> list[DriftResult]:
        drift_monitor = DriftMonitor(p_threshold=self._threshold)
        return drift_monitor.detect(reference, current)
