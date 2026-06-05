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
from backend.app.models.feature import Feature
from backend.app.models.price import Price
from backend.app.models.stock import Stock
from backend.app.services.data_quality_gate import DataQualityGate, DataQualityGateError

logger = logging.getLogger(__name__)

FEATURE_VERSION = "v1.0.0"


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

    # ✅ ADD THIS METHOD (fixes your error)
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
                raise DataQualityGateError(
                    f"All dates gated for {symbol}: no safe data to process"
                )

            trust_scores = [r["trust_score"] for r in gate_results if r["safe"]]
            features_df = self._compute_all_features(safe_df)
            inserted_count = self._bulk_persist_features(
                features_df, stock.id, trust_scores, session=sess
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
                results.append({"date": d, "safe": result.safe, "trust_score": result.trust_score})
            except Exception:
                results.append({"date": d, "safe": False, "trust_score": None})
        return results



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

        atr = np.asarray(
            pd.Series(tr).rolling(window=period, min_periods=period).mean().values
        )

        return atr

    def _compute_sma(self, values: npt.ArrayLike, period: int = 20) -> npt.NDArray[np.float64]:
        values = np.asarray(values, dtype=np.float64)
        sma = np.asarray(
            pd.Series(values).rolling(window=period, min_periods=period).mean().values
        )
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
        return np.asarray(
            pd.Series(values).rolling(window=period, min_periods=period).std().values
        )

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

            target_date = pd.to_datetime(date_str)
            feature_row = features_df[features_df["date"] == target_date]
            if feature_row.empty:
                raise ValueError(f"Could not compute features for {date_str}")

            features = feature_row.iloc[0].drop("date").to_dict()
            
            clean_features: dict[str, float | None] = {
                str(k): float(v) if not np.isnan(v) else None
                for k, v in features.items()
            }
      
            trust_score = None
            try:
                gate_result = self._gate.check(symbol, date_str)
                trust_score = gate_result.trust_score if gate_result.safe else None
            except Exception:
                pass

            self._persist_single_feature(symbol, date_str, clean_features, trust_score)

            return {
                "symbol": symbol.upper(),
                "date": date_str,
                "feature_version": self._feature_version,
                "features": clean_features,
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
    ) -> None:
        session = self._get_session()
        owns_session = self._session is None
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                raise ValueError(f"Stock {symbol} not found")
            feature = Feature(
                stock_id=stock.id,
                date=date.fromisoformat(date_str),
                feature_version=self._feature_version,
                trust_score=trust_score,
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

                features_to_insert.append(
                    Feature(
                        stock_id=stock_id,
                        date=row["date"].date(),
                        feature_version=self._feature_version,
                        trust_score=trust,
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