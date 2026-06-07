"""Feature computation service with vectorized technical indicators and quality enforcement."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import sqlalchemy as sa
from numpy.typing import NDArray
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.data_quality import DataTrust
from backend.app.models.feature import Feature
from backend.app.models.price import Price
from backend.app.models.stock import Stock
from backend.app.services.data_quality import DataQualityService
from backend.app.services.data_quality_gate import DataQualityGate, DataQualityGateError

logger = logging.getLogger(__name__)

FEATURE_VERSION = "v4.0.0"

STANDARD_EVENT_TYPES = frozenset(
    {
        "volatility_spike",
        "macro_news",
        "earnings",
        "corporate_action",
        "market_halt",
        "dividend",
        "ipo",
        "regulatory",
        "index_rebalance",
        "derivatives_expiry",
    }
)

EVENT_TYPE_ALIASES: dict[str, str] = {
    "volatility": "volatility_spike",
    "high_volatility": "volatility_spike",
    "high-volatility": "volatility_spike",
    "vol_spike": "volatility_spike",
    "macro": "macro_news",
    "macroeconomic": "macro_news",
    "economic_news": "macro_news",
    "earnings_report": "earnings",
    "corp_action": "corporate_action",
    "dividend_declaration": "dividend",
    "reg": "regulatory",
    "regulation": "regulatory",
    "derivatives": "derivatives_expiry",
    "f&o_expiry": "derivatives_expiry",
    "index": "index_rebalance",
}

FEATURE_REGISTRY: dict[str, dict[str, Any]] = {
    "rsi_14": {"group": "momentum", "base_weight": 1.0},
    "rsi_21": {"group": "momentum", "base_weight": 1.0},
    "macd": {"group": "trend", "base_weight": 0.9},
    "macd_signal": {"group": "trend", "base_weight": 0.8},
    "macd_hist": {"group": "trend", "base_weight": 0.7},
    "atr_14": {"group": "volatility", "base_weight": 0.8},
    "sma_20": {"group": "trend", "base_weight": 0.9},
    "sma_50": {"group": "trend", "base_weight": 0.9},
    "ema_20": {"group": "trend", "base_weight": 0.9},
    "ema_50": {"group": "trend", "base_weight": 0.9},
    "returns": {"group": "momentum", "base_weight": 0.8},
    "volatility_20": {"group": "volatility", "base_weight": 0.8},
    "volume_sma_20": {"group": "volume", "base_weight": 0.7},
    "volume_ratio": {"group": "volume", "base_weight": 0.7},
    "price_range": {"group": "volatility", "base_weight": 0.8},
}


class FeatureService:
    def __init__(
        self,
        gate: DataQualityGate | None = None,
        session: Session | None = None,
        feature_version: str = FEATURE_VERSION,
    ) -> None:
        self._gate = gate or DataQualityGate()
        self._session = session
        self._feature_version = feature_version

    def _to_array(self, series: pd.Series) -> NDArray[np.float64]:
        """Convert pandas Series to clean NumPy float64 array."""
        return series.to_numpy(dtype=np.float64, copy=False)

    def _get_session(self) -> Session:
        if self._session is not None:
            return self._session
        return SessionLocal()

    def compute_features(
        self,
        symbol: str,
        date_str: str,
    ) -> dict[str, Any]:
        self._gate.assert_safe_for_features(symbol, date_str)
        return self._compute_single_features(symbol, date_str)

    def compute_features_batch(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        return self._compute_features_batch_for_stock(symbol, start_date, end_date)

    def compute_bulk(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        return self.compute_features_batch(symbol, start_date, end_date)

    def compute_features_multi_stock(
        self,
        symbols: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        owns_session = self._session is None
        session = self._get_session()
        total_processed = 0
        total_gated = 0
        total_inserted = 0
        errors: list[dict[str, str]] = []

        try:
            for symbol in symbols:
                try:
                    result = self._compute_features_batch_for_stock(
                        symbol, start_date, end_date, session=session
                    )
                    total_processed += result["processed_dates"]
                    total_gated += result["gated_dates"]
                    total_inserted += result["inserted_rows"]
                except Exception as e:
                    errors.append({"symbol": symbol, "error": str(e)})
                    logger.error(
                        f"Feature batch failed for {symbol}: {e}",
                        extra={"symbol": symbol},
                    )

            return {
                "feature_version": self._feature_version,
                "symbols_requested": len(symbols),
                "symbols_succeeded": len(symbols) - len(errors),
                "total_processed_dates": total_processed,
                "total_gated_dates": total_gated,
                "total_inserted_rows": total_inserted,
                "errors": errors,
            }
        finally:
            if owns_session:
                session.close()

    def _compute_features_batch_for_stock(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        session: Session | None = None,
    ) -> dict[str, Any]:
        owns_session = session is None and self._session is None
        sess = session or self._get_session()
        try:
            stock = sess.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                raise ValueError(f"Stock {symbol} not found")

            query = sa.select(Price).where(Price.stock_id == stock.id)
            if start_date:
                query = query.where(Price.date >= start_date)
            if end_date:
                query = query.where(Price.date <= end_date)
            query = query.order_by(Price.date)

            prices = sess.scalars(query).all()
            if not prices:
                raise ValueError(f"No price data found for {symbol}")

            df = self._prices_to_dataframe(prices)
            gate_results = self._batch_quality_check(symbol, df, sess)

            safe_mask = np.array([r["safe"] for r in gate_results])
            unsafe_dates = [r["date"] for r in gate_results if not r["safe"]]

            if len(unsafe_dates) > 0:
                logger.warning(
                    f"Feature generation: {len(unsafe_dates)} dates gated unsafe for {symbol}",
                    extra={"unsafe_dates": unsafe_dates[:5], "symbol": symbol},
                )

            safe_df = df.iloc[safe_mask].copy()
            if safe_df.empty:
                raise DataQualityGateError(f"All dates gated for {symbol}: no safe data to process")

            trust_scores = [r["trust_score"] for r in gate_results if r["safe"]]
            feature_weights = [r["feature_weight"] for r in gate_results if r["safe"]]
            trust_versions = [r["trust_version"] for r in gate_results if r["safe"]]
            features_df = self._compute_all_features(safe_df)

            feature_corr_penalties = self._compute_feature_correlations(features_df)

            confidences: list[float | None] = []
            confidence_adjustments_list: list[dict[str, Any] | None] = []
            event_types_list: list[dict[str, Any] | None] = []
            correlation_penalties_per_row: list[float | None] = []

            for i, (_, row) in enumerate(features_df.iterrows()):
                if i < len(trust_scores):
                    date_str = row["date"].strftime("%Y-%m-%d")
                    event_result = self._apply_event_overrides(symbol, date_str, sess)
                    event_multiplier = event_result["multiplier"]
                    event_types = event_result["event_types"]

                    trust_score = trust_scores[i]
                    feature_weight = feature_weights[i]

                    adjusted_trust = (
                        trust_score * event_multiplier if trust_score is not None else None
                    )

                    raw_features = {str(k): v for k, v in row.drop("date").items()}
                    row_corr_penalties: dict[str, float] = {}

                    for feat_name, feat_val in raw_features.items():
                        corr_pen = feature_corr_penalties.get(feat_name, 1.0)
                        row_corr_penalties[feat_name] = corr_pen
                        if feat_val is not None and not (
                            isinstance(feat_val, float) and np.isnan(feat_val)
                        ):
                            raw_features[feat_name] = feat_val * corr_pen

                    scaled_features, confidence = self._apply_trust_scaling(
                        raw_features, adjusted_trust, feature_weight
                    )
                    confidences.append(confidence)
                    for k, v in scaled_features.items():
                        features_df.iat[i, features_df.columns.get_loc(k)] = v  # type: ignore[index]

                    if trust_score is not None and feature_weight > 0 and event_multiplier < 1.0:
                        event_types_list.append(
                            {
                                "event_types": event_types,
                                "event_multiplier": event_multiplier,
                                "original_trust": trust_score,
                                "adjusted_trust": adjusted_trust,
                            }
                        )
                    elif len(event_types) > 0:
                        event_types_list.append(
                            {
                                "event_types": event_types,
                                "event_multiplier": event_multiplier,
                                "original_trust": trust_score,
                                "adjusted_trust": adjusted_trust,
                            }
                        )
                    else:
                        event_types_list.append(None)

                    avg_corr_penalty = (
                        float(np.mean(list(row_corr_penalties.values())))
                        if row_corr_penalties
                        else 1.0
                    )
                    correlation_penalties_per_row.append(avg_corr_penalty)

                    if confidence is not None:
                        trust_factor = (
                            adjusted_trust * feature_weight if adjusted_trust is not None else 0.0
                        )
                        confidence_adjustments_list.append(
                            {
                                "raw_confidence": 1.0,
                                "event_multiplier": round(event_multiplier, 4),
                                "correlation_multiplier": round(avg_corr_penalty, 4),
                                "trust_multiplier": round(trust_factor, 4),
                                "final_confidence": round(confidence, 4),
                                "deltas": {
                                    "event": round(event_multiplier - 1.0, 4),
                                    "correlation": round(avg_corr_penalty - 1.0, 4),
                                    "trust_scale": round(trust_factor - 1.0, 4),
                                },
                            }
                        )
                    else:
                        confidence_adjustments_list.append(None)

            inserted_count = self._bulk_persist_features(
                features_df,
                stock.id,
                trust_scores,
                trust_versions,
                feature_weights,
                confidences,
                event_types_list,
                correlation_penalties_per_row,
                confidence_adjustments_list,
                session=sess,
            )

            return {
                "symbol": symbol.upper(),
                "feature_version": self._feature_version,
                "total_dates": len(df),
                "gated_dates": len(unsafe_dates),
                "processed_dates": len(safe_df),
                "inserted_rows": inserted_count,
                "features_computed": list(features_df.columns),
            }
        finally:
            if owns_session:
                sess.close()

    def _prices_to_dataframe(self, prices: Sequence[Price]) -> pd.DataFrame:
        data = [
            {
                "date": p.date.isoformat(),
                "open": float(p.open) if p.open is not None else np.nan,
                "high": float(p.high) if p.high is not None else np.nan,
                "low": float(p.low) if p.low is not None else np.nan,
                "close": float(p.close) if p.close is not None else np.nan,
                "volume": float(p.volume) if p.volume is not None else np.nan,
            }
            for p in prices
        ]
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True)

    def _batch_quality_check(
        self,
        symbol: str,
        df: pd.DataFrame,
        session: Session | None = None,
    ) -> list[dict[str, Any]]:
        gate = self._gate if session is None else DataQualityGate(session=session)
        dates = df["date"].dt.date.astype(str).tolist()
        results = []
        for d in dates:
            try:
                result = gate.check(symbol, d)
                trust_version = self._get_trust_version_for_date(symbol, d, session)
                results.append(
                    {
                        "date": d,
                        "safe": result.safe,
                        "trust_score": result.trust_score,
                        "trust_version": trust_version,
                        "feature_weight": gate.get_feature_weight(symbol, d),
                    }
                )
            except Exception:
                results.append(
                    {
                        "date": d,
                        "safe": False,
                        "trust_score": None,
                        "trust_version": None,
                        "feature_weight": 0.0,
                    }
                )
        return results

    def _get_trust_version_for_date(
        self, symbol: str, date_str: str, session: Session | None = None
    ) -> str:
        sess = session or self._get_session()
        owns_session = session is None and self._session is None
        try:
            stock = sess.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return "v1"
            trust_record = sess.scalar(
                sa.select(DataTrust).where(
                    DataTrust.stock_id == stock.id,
                    DataTrust.date == date.fromisoformat(date_str),
                )
            )
            return trust_record.trust_version if trust_record else "v1"
        finally:
            if owns_session:
                sess.close()

    def _apply_trust_scaling(
        self,
        features: dict[str, Any],
        trust_score: float | None,
        feature_weight: float,
    ) -> tuple[dict[str, float | None], float | None]:
        confidence = None
        if trust_score is None or feature_weight <= 0:
            return {k: None for k in features.keys()}, confidence

        confidence = max(0.0, min(1.0, trust_score * feature_weight))
        scaled: dict[str, float | None] = {}
        for k, v in features.items():
            if v is None or np.isnan(v) if isinstance(v, float) else False:
                scaled[k] = None
            elif k in ("rsi_14", "rsi_21"):
                scaled[k] = (v / 100.0) * confidence
            elif k in ("volatility_20",):
                scaled[k] = v * confidence
            else:
                scaled[k] = v
        return scaled, confidence

    def _apply_event_overrides(
        self, symbol: str, date_str: str, session: Session | None = None
    ) -> dict[str, Any]:
        sess = session or self._get_session()
        owns_session = session is None and self._session is None
        try:
            dq = DataQualityService(session=sess)
            overrides = dq.get_active_event_overrides(date_str, symbol)
            multiplier = 1.0
            event_types: list[str] = []
            for o in overrides:
                multiplier *= o["sensitivity_multiplier"]
                event_types.append(self._normalize_event_type(o.get("event_type", "")))
            return {
                "multiplier": max(0.0, min(1.0, multiplier)),
                "event_types": event_types,
            }
        finally:
            if owns_session:
                sess.close()

    def _normalize_event_type(self, raw: str) -> str:
        normalized = EVENT_TYPE_ALIASES.get(raw.lower(), raw.lower())
        if normalized in STANDARD_EVENT_TYPES:
            return normalized
        logger.warning("Unrecognized event type '%s', defaulting to 'macro_news'", raw)
        return "macro_news"

    def _correlation_penalty_func(self, max_corr: float) -> float:
        alpha = 0.22
        penalty = 1.0 - alpha * max_corr ** 2
        return max(0.5, penalty)

    def _compute_feature_correlations(self, features_df: pd.DataFrame) -> dict[str, float]:
        feature_columns = [c for c in features_df.columns if c != "date" and c != "day_index"]
        if len(feature_columns) < 2:
            return {col: 1.0 for col in feature_columns}

        corr_matrix = features_df[feature_columns].corr(method="pearson").abs()
        penalties: dict[str, float] = {}
        for col in feature_columns:
            others = [c for c in feature_columns if c != col]
            if others:
                max_corr = float(corr_matrix[others].loc[col].max())  # type: ignore[arg-type]
                if np.isnan(max_corr):
                    max_corr = 0.0
            else:
                max_corr = 0.0
            penalties[col] = self._correlation_penalty_func(max_corr)
        return penalties

    def _compute_all_features(self, df: pd.DataFrame) -> pd.DataFrame:
        close = self._to_array(df["close"])
        high = self._to_array(df["high"])
        low = self._to_array(df["low"])
        volume = self._to_array(df["volume"])

        result = pd.DataFrame({"date": df["date"]})

        result["rsi_14"] = self._compute_rsi(close, period=14)
        result["rsi_21"] = self._compute_rsi(close, period=21)

        macd_result = self._compute_macd(close)
        result["macd"] = macd_result["macd"]
        result["macd_signal"] = macd_result["signal"]
        result["macd_hist"] = macd_result["histogram"]

        result["atr_14"] = self._compute_atr(high, low, close, period=14)

        result["sma_20"] = self._compute_sma(close, period=20)
        result["sma_50"] = self._compute_sma(close, period=50)
        result["ema_20"] = self._compute_ema(close, period=20)
        result["ema_50"] = self._compute_ema(close, period=50)

        returns = self._compute_returns(close)
        result["returns"] = returns
        result["volatility_20"] = self._compute_rolling_std(returns, period=20)

        volume_sma_20 = self._compute_sma(volume, period=20)
        result["volume_sma_20"] = volume_sma_20
        result["volume_ratio"] = self._compute_volume_ratio(volume, volume_sma_20)

        result["price_range"] = self._compute_price_range(high, low, close)

        return result

    def _compute_rsi(self, prices: npt.ArrayLike, period: int = 14) -> npt.NDArray[np.float64]:
        prices = np.asarray(prices, dtype=np.float64)
        delta = np.diff(prices, prepend=np.nan)

        gains = np.where(delta > 0, delta, 0)
        losses = np.where(delta < 0, -delta, 0)

        avg_gain = np.asarray(
            pd.Series(gains).rolling(window=period, min_periods=period).mean().values
        )
        avg_loss = np.asarray(
            pd.Series(losses).rolling(window=period, min_periods=period).mean().values
        )

        with np.errstate(divide="ignore", invalid="ignore"):
            rs = np.where(
                avg_loss > 0,
                avg_gain / avg_loss,
                np.where(avg_gain > 0, np.inf, np.nan),
            )

        rsi = np.where(rs != np.inf, 100 - (100 / (1 + rs)), 100.0)
        rsi = np.clip(rsi, 0, 100)

        return np.asarray(rsi)

    def _compute_macd(
        self,
        prices: npt.ArrayLike,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> dict[str, npt.NDArray[np.float64]]:
        prices = np.asarray(prices, dtype=np.float64)

        ema_fast = self._compute_ema(prices, fast)
        ema_slow = self._compute_ema(prices, slow)

        macd = ema_fast - ema_slow

        macd_signal = np.asarray(
            pd.Series(macd).rolling(window=signal, min_periods=signal).mean().values
        )
        macd_hist = np.asarray(ema_fast - ema_slow - macd_signal)

        return {
            "macd": np.asarray(macd),
            "signal": macd_signal,
            "histogram": macd_hist,
        }

    def _compute_atr(
        self,
        high: npt.ArrayLike,
        low: npt.ArrayLike,
        close: npt.ArrayLike,
        period: int = 14,
    ) -> npt.NDArray[np.float64]:
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)

        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]

        tr = np.maximum(high - low, np.abs(high - prev_close))
        tr = np.maximum(tr, np.abs(low - prev_close))

        atr = np.asarray(pd.Series(tr).rolling(window=period, min_periods=period).mean().values)

        return atr

    def _compute_sma(self, values: npt.ArrayLike, period: int = 20) -> npt.NDArray[np.float64]:
        values = np.asarray(values, dtype=np.float64)
        sma = np.asarray(pd.Series(values).rolling(window=period, min_periods=period).mean().values)
        return sma

    def _compute_ema(self, values: npt.ArrayLike, period: int = 20) -> npt.NDArray[np.float64]:
        values = np.asarray(values, dtype=np.float64)
        ema = np.asarray(
            pd.Series(values).ewm(span=period, adjust=False, min_periods=period).mean().values
        )
        return ema

    def _compute_returns(self, prices: npt.ArrayLike) -> npt.NDArray[np.float64]:
        prices = np.asarray(prices, dtype=np.float64)
        returns = np.diff(prices, prepend=np.nan) / np.roll(prices, 1)
        returns[0] = np.nan
        return np.asarray(returns)

    def _compute_rolling_std(
        self, values: npt.ArrayLike, period: int = 20
    ) -> npt.NDArray[np.float64]:
        values = np.asarray(values, dtype=np.float64)
        return np.asarray(pd.Series(values).rolling(window=period, min_periods=period).std().values)

    def _compute_volume_ratio(
        self,
        volume: npt.ArrayLike,
        volume_sma: npt.ArrayLike,
    ) -> npt.NDArray[np.float64]:
        volume = np.asarray(volume, dtype=np.float64)
        volume_sma = np.asarray(volume_sma, dtype=np.float64)

        ratio = np.divide(
            volume,
            volume_sma,
            out=np.ones_like(volume),
            where=volume_sma > 0,
        )
        return ratio

    def _compute_price_range(
        self,
        high: npt.ArrayLike,
        low: npt.ArrayLike,
        close: npt.ArrayLike,
    ) -> npt.NDArray[np.float64]:
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            range_pct = np.where(
                close > 0,
                (high - low) / close,
                np.nan,
            )
        return np.asarray(range_pct)

    def _compute_single_features(self, symbol: str, date_str: str) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                raise ValueError(f"Stock {symbol} not found")

            price = session.scalar(
                sa.select(Price).where(
                    Price.stock_id == stock.id,
                    Price.date == date.fromisoformat(date_str),
                )
            )
            if price is None:
                raise ValueError(f"No price data for {symbol} on {date_str}")

            prices = session.scalars(
                sa.select(Price)
                .where(Price.stock_id == stock.id)
                .order_by(Price.date.desc())
                .limit(60)
            ).all()

            df = self._prices_to_dataframe(prices)
            if df.empty:
                raise ValueError(f"Could not build dataframe for {date_str}")

            features_df = self._compute_all_features(df)
            feature_corr_penalties = self._compute_feature_correlations(features_df)

            target_date = pd.to_datetime(date_str)
            feature_row = features_df[features_df["date"] == target_date]
            if feature_row.empty:
                raise ValueError(f"Could not compute features for {date_str}")

            trust_score = None
            trust_version = "v1"
            feature_weight = 1.0
            confidence = None
            event_multiplier = 1.0
            event_types: list[str] = []

            try:
                gate = DataQualityGate(session=session)
                gate_result = gate.check(symbol, date_str)
                trust_score = gate_result.trust_score if gate_result.safe else None
                trust_version = self._get_trust_version_for_date(symbol, date_str, session)
                feature_weight = gate.get_feature_weight(symbol, date_str)
            except Exception:
                pass

            event_result = self._apply_event_overrides(symbol, date_str, session)
            event_multiplier = event_result["multiplier"]
            event_types = event_result["event_types"]

            adjusted_trust = trust_score * event_multiplier if trust_score is not None else None

            features = feature_row.iloc[0].drop("date").to_dict()
            row_corr_penalties: dict[str, float] = {}
            for feat_name, feat_val in features.items():
                corr_pen = feature_corr_penalties.get(str(feat_name), 1.0)
                row_corr_penalties[str(feat_name)] = corr_pen
                if not np.isnan(feat_val):
                    features[feat_name] = feat_val * corr_pen

            clean_features: dict[str, float | None] = {
                str(k): float(v) if not np.isnan(v) else None for k, v in features.items()
            }

            scaled_features, confidence = self._apply_trust_scaling(
                clean_features, adjusted_trust, feature_weight
            )

            avg_corr_penalty = (
                float(np.mean(list(row_corr_penalties.values()))) if row_corr_penalties else 1.0
            )

            confidence_adjustments = None
            if confidence is not None:
                trust_factor = adjusted_trust * feature_weight if adjusted_trust is not None else 0.0
                confidence_adjustments = {
                    "raw_confidence": 1.0,
                    "event_multiplier": round(event_multiplier, 4),
                    "correlation_multiplier": round(avg_corr_penalty, 4),
                    "trust_multiplier": round(trust_factor, 4),
                    "final_confidence": round(confidence, 4),
                    "deltas": {
                        "event": round(event_multiplier - 1.0, 4),
                        "correlation": round(avg_corr_penalty - 1.0, 4),
                        "trust_scale": round(trust_factor - 1.0, 4),
                    },
                }

            event_info_for_persist = None
            if event_types:
                event_info_for_persist = {
                    "event_types": event_types,
                    "event_multiplier": event_multiplier,
                    "original_trust": trust_score,
                    "adjusted_trust": adjusted_trust,
                }

            self._persist_single_feature(
                symbol,
                date_str,
                scaled_features,
                trust_score,
                trust_version,
                feature_weight,
                avg_corr_penalty,
                confidence,
                event_info_for_persist,
                confidence_adjustments,
            )

            return {
                "symbol": symbol.upper(),
                "date": date_str,
                "feature_version": self._feature_version,
                "features": scaled_features,
            }
        finally:
            if owns_session:
                session.close()

    def _persist_single_feature(
        self,
        symbol: str,
        date_str: str,
        features: dict[str, Any],
        trust_score: float | None = None,
        trust_version: str | None = None,
        feature_weight: float | None = None,
        correlation_penalty: float = 1.0,
        confidence: float | None = None,
        event_info: dict[str, Any] | None = None,
        confidence_adjustments: dict[str, Any] | None = None,
    ) -> None:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                raise ValueError(f"Stock {symbol} not found")

            if trust_version is None:
                trust_version = self._get_trust_version_for_date(symbol, date_str, session)
            if feature_weight is None:
                gate = self._gate if session is None else DataQualityGate(session=session)
                feature_weight = gate.get_feature_weight(symbol, date_str)

            if confidence is None and trust_score is not None and feature_weight > 0:
                confidence = max(0.0, min(1.0, trust_score * feature_weight))

            has_event_override = bool(event_info is not None and event_info.get("event_types"))

            features_meta = {
                "trust_score": trust_score,
                "feature_weight": feature_weight,
                "confidence_raw": confidence,
                "correlation_penalty": correlation_penalty,
                "event_override": {
                    "active": has_event_override,
                    "event_types": event_info.get("event_types") if event_info else [],
                    "event_multiplier": event_info.get("event_multiplier") if event_info else 1.0,
                    "original_trust": event_info.get("original_trust") if event_info else None,
                    "adjusted_trust": event_info.get("adjusted_trust") if event_info else None,
                },
                "confidence_adjustments": confidence_adjustments,
                "version": self._feature_version,
                "scaled_by_trust": trust_score is not None,
                "event_adjusted": has_event_override,
                "correlation_penalized": correlation_penalty < 1.0,
            }

            feature = Feature(
                stock_id=stock.id,
                date=date.fromisoformat(date_str),
                feature_version=self._feature_version,
                trust_score=trust_score,
                trust_version=trust_version,
                confidence=confidence,
                features_meta=features_meta,
                values=features,
            )
            session.merge(feature)
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            if owns_session:
                session.close()

    def _bulk_persist_features(
        self,
        features_df: pd.DataFrame,
        stock_id: int,
        trust_scores: list[float] | None = None,
        trust_versions: list[str] | None = None,
        feature_weights: list[float] | None = None,
        confidences: list[float | None] | None = None,
        event_infos: list[dict[str, Any] | None] | None = None,
        correlation_penalties: list[float | None] | None = None,
        confidence_adjustments_list: list[dict[str, Any] | None] | None = None,
        session: Session | None = None,
    ) -> int:
        sess = session or self._get_session()
        owns_session = session is None and self._session is None
        try:
            features_to_insert = []
            for idx, (_, row) in enumerate(features_df.iterrows()):
                values = row.drop("date").to_dict()
                clean_values = {k: float(v) if not np.isnan(v) else None for k, v in values.items()}

                trust = trust_scores[idx] if trust_scores and idx < len(trust_scores) else None
                trust_ver = (
                    trust_versions[idx] if trust_versions and idx < len(trust_versions) else None
                )
                weight = (
                    feature_weights[idx] if feature_weights and idx < len(feature_weights) else None
                )
                confidence = confidences[idx] if confidences and idx < len(confidences) else None
                event_info = (
                    event_infos[idx]
                    if event_infos and idx < len(event_infos) and event_infos[idx]
                    else None
                )
                corr_pen = (
                    correlation_penalties[idx]
                    if correlation_penalties and idx < len(correlation_penalties)
                    else 1.0
                )
                adj = (
                    confidence_adjustments_list[idx]
                    if confidence_adjustments_list
                    and idx < len(confidence_adjustments_list)
                    and confidence_adjustments_list[idx]
                    else None
                )

                has_event_override = bool(event_info is not None and event_info.get("event_types"))

                features_meta = {
                    "trust_score": trust,
                    "feature_weight": weight,
                    "confidence_raw": confidence,
                    "correlation_penalty": corr_pen,
                    "event_override": {
                        "active": has_event_override,
                        "event_types": event_info.get("event_types") if event_info else [],
                        "event_multiplier": event_info.get("event_multiplier") if event_info else 1.0,
                        "original_trust": event_info.get("original_trust") if event_info else None,
                        "adjusted_trust": event_info.get("adjusted_trust") if event_info else None,
                    },
                    "confidence_adjustments": adj,
                    "version": self._feature_version,
                    "scaled_by_trust": trust is not None,
                    "event_adjusted": has_event_override,
                    "correlation_penalized": corr_pen is not None and corr_pen < 1.0,
                }

                features_to_insert.append(
                    Feature(
                        stock_id=stock_id,
                        date=row["date"].date(),
                        feature_version=self._feature_version,
                        trust_score=trust,
                        trust_version=trust_ver,
                        confidence=confidence,
                        features_meta=features_meta,
                        values=clean_values,
                    )
                )

            with sess.begin_nested():
                for feat in features_to_insert:
                    sess.merge(feat)

            sess.commit()
            logger.info(
                f"Bulk persisted {len(features_to_insert)} feature rows",
                extra={"stock_id": stock_id, "feature_version": self._feature_version},
            )
            return len(features_to_insert)
        except SQLAlchemyError as e:
            sess.rollback()
            logger.error(
                f"Bulk feature persistence failed: {e}",
                extra={"stock_id": stock_id},
            )
            raise
        finally:
            if owns_session:
                sess.close()

    def get_features(
        self,
        symbol: str,
        date_str: str,
        feature_version: str | None = None,
    ) -> dict[str, Any] | None:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return None

            query = sa.select(Feature).where(
                Feature.stock_id == stock.id,
                Feature.date == date.fromisoformat(date_str),
            )
            if feature_version:
                query = query.where(Feature.feature_version == feature_version)

            feature = session.scalar(query)
            if feature is None:
                return None

            return {
                "symbol": symbol.upper(),
                "date": date_str,
                "feature_version": feature.feature_version,
                "trust_score": feature.trust_score,
                "trust_version": feature.trust_version,
                "confidence": feature.confidence,
                "features_meta": feature.features_meta,
                "features": feature.values,
            }
        finally:
            if owns_session:
                session.close()

    def get_features_list(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        feature_version: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                return {"features": [], "total": 0, "limit": limit, "offset": offset}

            query = (
                sa.select(Feature)
                .where(Feature.stock_id == stock.id)
                .order_by(Feature.date.desc())
                .limit(limit)
                .offset(offset)
            )
            if start_date:
                query = query.where(Feature.date >= start_date)
            if end_date:
                query = query.where(Feature.date <= end_date)
            if feature_version:
                query = query.where(Feature.feature_version == feature_version)

            features = session.scalars(query).all()
            total_query = (
                sa.select(sa.func.count()).select_from(Feature).where(Feature.stock_id == stock.id)
            )
            if start_date:
                total_query = total_query.where(Feature.date >= start_date)
            if end_date:
                total_query = total_query.where(Feature.date <= end_date)
            if feature_version:
                total_query = total_query.where(Feature.feature_version == feature_version)
            total = session.scalar(total_query) or 0

            results = [
                {
                    "date": f.date.isoformat(),
                    "feature_version": f.feature_version,
                    "trust_score": f.trust_score,
                    "trust_version": f.trust_version,
                    "confidence": f.confidence,
                    "features_meta": f.features_meta,
                    "features": f.values,
                }
                for f in features
            ]

            return {
                "symbol": symbol.upper(),
                "features": results,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        finally:
            if owns_session:
                session.close()
