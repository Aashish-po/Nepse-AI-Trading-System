"""Optional lightweight MLflow tracking helpers."""

from __future__ import annotations

import csv
import json
import logging
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from numbers import Real
from pathlib import Path
from typing import Any

try:
    import mlflow
except Exception as exc:  # pragma: no cover - exercised when mlflow is absent
    mlflow = None  # type: ignore[assignment]
    _IMPORT_ERROR: Exception | None = exc
else:
    _IMPORT_ERROR = None

from app.core.config import settings

logger = logging.getLogger(__name__)

BACKTEST_EXPERIMENT = "phase_2b_baseline"
MODEL_EXPERIMENT = "phase_3_models"

DEFAULT_HIGHER_IS_BETTER = {
    "accuracy",
    "annualized_return",
    "expectancy",
    "f1",
    "f1_macro",
    "f1_micro",
    "f1_weighted",
    "precision",
    "profit_factor",
    "recall",
    "sharpe",
    "sharpe_ratio",
    "total_return",
    "train_accuracy",
    "val_accuracy",
    "win_rate",
}
DEFAULT_LOWER_IS_BETTER = {
    "max_drawdown",
    "rmse",
    "mae",
}

BACKTEST_METRIC_NAMES = (
    "total_return",
    "annualized_return",
    "max_drawdown",
    "sharpe_ratio",
    "win_rate",
    "profit_factor",
    "expectancy",
    "total_trades",
)


@dataclass(frozen=True)
class MLflowRunResult:
    enabled: bool
    experiment_name: str
    run_id: str | None = None
    status: str = "disabled"
    error: str | None = None


@dataclass(frozen=True)
class PromotionGateResult:
    promotable: bool
    benchmark: dict[str, bool] = field(default_factory=dict)
    baselines: dict[str, dict[str, bool]] = field(default_factory=dict)
    metrics: dict[str, bool] = field(default_factory=dict)


class MLflowTrackingService:
    def __init__(
        self,
        tracking_uri: str | None = None,
        enabled: bool | None = None,
        experiment_prefix: str | None = None,
    ) -> None:
        self._tracking_uri = tracking_uri
        self._enabled = enabled
        self._experiment_prefix = experiment_prefix

    def is_available(self) -> bool:
        enabled = settings.mlflow_enabled if self._enabled is None else self._enabled
        return bool(enabled) and mlflow is not None

    def evaluate_promotion_gate(
        self,
        candidate_metrics: Mapping[str, Any],
        benchmark_metrics: Mapping[str, Any] | None = None,
        baseline_metrics: Mapping[str, Mapping[str, Any]] | None = None,
        higher_is_better: Iterable[str] | None = None,
        lower_is_better: Iterable[str] | None = None,
        required_metrics: Iterable[str] | None = None,
    ) -> PromotionGateResult:
        return evaluate_promotion_gate(
            candidate_metrics=candidate_metrics,
            benchmark_metrics=benchmark_metrics,
            baseline_metrics=baseline_metrics,
            higher_is_better=higher_is_better,
            lower_is_better=lower_is_better,
            required_metrics=required_metrics,
        )

    def log_backtest(
        self,
        *,
        experiment_name: str = BACKTEST_EXPERIMENT,
        backtest_id: int,
        strategy_id: int,
        strategy_name: str,
        strategy_version: str,
        config: Mapping[str, Any],
        metrics: Mapping[str, Any],
        strategy_config: Mapping[str, Any] | None = None,
        symbol_count: int | None = None,
    ) -> MLflowRunResult:
        if not self.is_available():
            reason = "MLflow is not installed" if mlflow is None else "MLflow is disabled"
            return self._disabled_result(experiment_name, reason)

        try:
            self._configure_mlflow()
            resolved_experiment_name = self._resolve_experiment_name(experiment_name)
            experiment_id = self._get_or_create_experiment(resolved_experiment_name)

            params = self._backtest_params(
                backtest_id=backtest_id,
                strategy_id=strategy_id,
                strategy_name=strategy_name,
                strategy_version=strategy_version,
                config=config,
                strategy_config=strategy_config or {},
                symbol_count=symbol_count,
            )
            metric_values = self._metric_values(metrics, BACKTEST_METRIC_NAMES)

            with mlflow.start_run(
                experiment_id=experiment_id,
                run_name=f"backtest_{backtest_id}",
            ) as run:
                mlflow.log_params(params)
                mlflow.log_metrics(metric_values)
                self._log_backtest_artifacts(
                    backtest_id=backtest_id,
                    config=config,
                    strategy_config=strategy_config or {},
                    metrics=metrics,
                    equity_curve=metrics.get("equity_curve"),
                    trades=metrics.get("trades"),
                )
                run_id = run.info.run_id

            return MLflowRunResult(
                enabled=True,
                experiment_name=resolved_experiment_name,
                run_id=run_id,
                status="logged",
            )
        except Exception as exc:
            logger.warning("MLflow backtest logging failed: %s", exc)
            return MLflowRunResult(
                enabled=True,
                experiment_name=self._resolve_experiment_name(experiment_name),
                status="failed",
                error=str(exc),
            )

    def log_model_training(
        self,
        *,
        experiment_name: str = MODEL_EXPERIMENT,
        model_name: str,
        model_version: str,
        feature_version: str,
        symbol: str,
        split_sizes: Mapping[str, int],
        metrics: Mapping[str, Any],
        params: Mapping[str, Any] | None = None,
        model_path: str | Path,
    ) -> MLflowRunResult:
        if not self.is_available():
            reason = "MLflow is not installed" if mlflow is None else "MLflow is disabled"
            return self._disabled_result(experiment_name, reason)

        try:
            self._configure_mlflow()
            resolved_experiment_name = self._resolve_experiment_name(experiment_name)
            experiment_id = self._get_or_create_experiment(resolved_experiment_name)

            training_params = {
                "model_name": model_name,
                "model_version": model_version,
                "feature_version": feature_version,
                "symbol": symbol,
                "model_artifact_path": str(model_path),
                **{str(key): int(value) for key, value in split_sizes.items()},
            }
            if params:
                training_params.update(
                    {str(key): _coerce_param(value) for key, value in params.items()}
                )

            with mlflow.start_run(
                experiment_id=experiment_id,
                run_name=f"{model_name}_{model_version}",
            ) as run:
                mlflow.log_params(training_params)
                mlflow.log_metrics(self._metric_values(metrics))
                mlflow.log_artifact(str(model_path), artifact_path="model")
                run_id = run.info.run_id

            return MLflowRunResult(
                enabled=True,
                experiment_name=resolved_experiment_name,
                run_id=run_id,
                status="logged",
            )
        except Exception as exc:
            logger.warning("MLflow model training logging failed: %s", exc)
            return MLflowRunResult(
                enabled=True,
                experiment_name=self._resolve_experiment_name(experiment_name),
                status="failed",
                error=str(exc),
            )

    def _configure_mlflow(self) -> None:
        if mlflow is None:
            raise RuntimeError(_IMPORT_ERROR or "MLflow is not installed")
        tracking_uri = self._tracking_uri or settings.mlflow_tracking_uri
        mlflow.set_tracking_uri(tracking_uri)

    def _get_or_create_experiment(self, experiment_name: str) -> str:
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is not None:
            return experiment.experiment_id
        return mlflow.create_experiment(experiment_name)

    def _resolve_experiment_name(self, experiment_name: str) -> str:
        prefix = (
            self._experiment_prefix
            if self._experiment_prefix is not None
            else settings.mlflow_experiment_prefix
        ).strip()
        if not prefix:
            return experiment_name
        return f"{prefix}/{experiment_name}"

    def _disabled_result(self, experiment_name: str, reason: str) -> MLflowRunResult:
        return MLflowRunResult(
            enabled=False,
            experiment_name=self._resolve_experiment_name(experiment_name),
            status="disabled",
            error=reason,
        )

    def _backtest_params(
        self,
        *,
        backtest_id: int,
        strategy_id: int,
        strategy_name: str,
        strategy_version: str,
        config: Mapping[str, Any],
        strategy_config: Mapping[str, Any],
        symbol_count: int | None,
    ) -> dict[str, str]:
        entry_rules = strategy_config.get("entry_rules", []) or []
        exit_rules = strategy_config.get("exit_rules", []) or []
        risk_rules = strategy_config.get("risk_rules", []) or []
        symbols = config.get("symbols") or strategy_config.get("symbols", []) or []
        resolved_symbol_count = symbol_count if symbol_count is not None else len(symbols)
        commission = config.get("commission", config.get("commission_rate"))

        params: dict[str, Any] = {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "strategy_version": strategy_version,
            "backtest_id": backtest_id,
            "start_date": config.get("start_date", ""),
            "end_date": config.get("end_date", ""),
            "capital": config.get("initial_capital", config.get("capital")),
            "commission": commission,
            "commission_rate": config.get("commission_rate"),
            "slippage_bps": config.get("slippage_bps"),
            "symbol_count": resolved_symbol_count,
            "entry_rule_count": len(entry_rules),
            "exit_rule_count": len(exit_rules),
            "risk_rule_count": len(risk_rules),
        }
        return {
            key: _coerce_param(value) for key, value in params.items() if value not in (None, "")
        }

    def _log_backtest_artifacts(
        self,
        *,
        backtest_id: int,
        config: Mapping[str, Any],
        strategy_config: Mapping[str, Any],
        metrics: Mapping[str, Any],
        equity_curve: Any,
        trades: Any,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix=f"mlflow_backtest_{backtest_id}_") as tmp_dir:
            artifact_dir = Path(tmp_dir)
            _write_json(artifact_dir / "metrics.json", _json_safe(metrics))
            _write_json(
                artifact_dir / "config.json",
                {
                    "backtest_config": _json_safe(config),
                    "strategy_config": _json_safe(strategy_config),
                },
            )
            if equity_curve:
                _write_csv(artifact_dir / "equity_curve.csv", equity_curve)
            if trades:
                _write_csv(artifact_dir / "trades.csv", trades)
            mlflow.log_artifacts(str(artifact_dir), artifact_path="backtest")

    def _metric_values(
        self,
        metrics: Mapping[str, Any],
        selected_metrics: Iterable[str] | None = None,
    ) -> dict[str, float]:
        metric_names = (
            list(selected_metrics) if selected_metrics is not None else list(metrics.keys())
        )
        values: dict[str, float] = {}
        for name in metric_names:
            value = _to_float(metrics.get(name))
            if value is not None:
                values[name] = value
        return values


def evaluate_promotion_gate(
    candidate_metrics: Mapping[str, Any],
    benchmark_metrics: Mapping[str, Any] | None = None,
    baseline_metrics: Mapping[str, Mapping[str, Any]] | None = None,
    higher_is_better: Iterable[str] | None = None,
    lower_is_better: Iterable[str] | None = None,
    required_metrics: Iterable[str] | None = None,
) -> PromotionGateResult:
    directions = _metric_directions(higher_is_better, lower_is_better)
    metric_names = list(
        required_metrics
        if required_metrics is not None
        else _metric_names(candidate_metrics, benchmark_metrics, baseline_metrics)
    )

    def compare(reference_metrics: Mapping[str, Any] | None) -> dict[str, bool]:
        if reference_metrics is None:
            return {}
        results: dict[str, bool] = {}
        for metric in metric_names:
            if metric not in candidate_metrics or metric not in reference_metrics:
                results[metric] = False
                continue
            candidate_value = _to_float(candidate_metrics[metric])
            reference_value = _to_float(reference_metrics[metric])
            if candidate_value is None or reference_value is None:
                results[metric] = False
                continue
            direction = directions.get(metric, "higher")
            results[metric] = (
                candidate_value <= reference_value
                if direction == "lower"
                else candidate_value >= reference_value
            )
        return results

    benchmark_results = compare(benchmark_metrics)
    baseline_results = {
        str(name): compare(metrics) for name, metrics in (baseline_metrics or {}).items()
    }

    combined: dict[str, bool] = {}
    for metric in metric_names:
        checks: list[bool] = []
        if benchmark_results:
            checks.append(benchmark_results.get(metric, False))
        checks.extend(baseline.get(metric, False) for baseline in baseline_results.values())
        combined[metric] = all(checks) if checks else True

    return PromotionGateResult(
        promotable=all(combined.values()) if combined else True,
        benchmark=benchmark_results,
        baselines=baseline_results,
        metrics=combined,
    )


def _metric_directions(
    higher_is_better: Iterable[str] | None,
    lower_is_better: Iterable[str] | None,
) -> dict[str, str]:
    directions = {metric: "higher" for metric in DEFAULT_HIGHER_IS_BETTER}
    directions.update({metric: "lower" for metric in DEFAULT_LOWER_IS_BETTER})
    if higher_is_better:
        directions.update({metric: "higher" for metric in higher_is_better})
    if lower_is_better:
        directions.update({metric: "lower" for metric in lower_is_better})
    return directions


def _metric_names(
    candidate_metrics: Mapping[str, Any],
    benchmark_metrics: Mapping[str, Any] | None,
    baseline_metrics: Mapping[str, Mapping[str, Any]] | None,
) -> set[str]:
    names = set(candidate_metrics)
    if benchmark_metrics:
        names.update(benchmark_metrics)
    for metrics in (baseline_metrics or {}).values():
        names.update(metrics)
    return names


def _coerce_param(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | float):
        return str(value)
    return json.dumps(_json_safe(value), sort_keys=True)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, Real):
        result = float(value)
    else:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
    if not math_is_finite(result):
        return None
    return result


def math_is_finite(value: float) -> bool:
    return value == value and value not in (float("inf"), float("-inf"))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows_list = [_json_safe(dict(row)) for row in rows]
    if not rows_list:
        return
    fieldnames = sorted({key for row in rows_list for key in row})
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_list)


mlflow_tracker = MLflowTrackingService()
