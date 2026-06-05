"""Feature computation service with vectorized technical indicators and quality enforcement."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import sqlalchemy as sa
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
        features = self._build_features(symbol, date_str)
        self._persist_features(symbol, date_str, features)
        return {
            "symbol": symbol.upper(),
            "date": date_str,
            "feature_version": self._feature_version,
            "features": features,
        }

    def compute_features_batch(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        owns_session = self._session is None
        session = self._get_session()
        try:
            stock = session.scalar(sa.select(Stock).where(Stock.symbol == symbol.upper()))
            if stock is None:
                raise ValueError(f"Stock {symbol} not found")

            query = sa.select(Price).where(Price.stock_id == stock.id)
            if start_date:
                query = query.where(Price.date >= start_date)
            if end_date:
                query = query.where(Price.date <= end_date)
            query = query.order_by(Price.date)

            prices = session.scalars(query).all()
            if not prices:
                raise ValueError(f"No price data found for {symbol}")

            df = self._prices_to_dataframe(prices)
            gate_results = self._batch_quality_check(symbol, df)

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

            features_df = self._compute_all_features(safe_df, symbol)
            inserted_count = self._bulk_persist_features(features_df, stock.id)

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
                session.close()

    def _prices_to_dataframe(self, prices: list[Price]) -> pd.DataFrame:
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
    ) -> list[dict[str, Any]]:
        dates = df["date"].dt.date.astype(str).tolist()
        return [
            {"date": d, "safe": self._gate.evaluate_symbol_date(symbol, d).get("safe", False)}
            for d in dates
        ]

    def _compute_all_features(
        self,
        df: pd.DataFrame,
        symbol: str,
    ) -> pd.DataFrame:
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values

        result = pd.DataFrame({"date": df["date"]})

        result["rsi_14"] = self._compute_rsi(close, period=14)
        result["rsi_21"] = self._compute_rsi(close, period=21)

        macd_result = self._compute_macd(close)
        result["macd"] = macd_result["macd"]
        result["macd_signal"] = macd_result["signal"]
        result["macd_hist"] = macd_result["histogram"]

        atr_result = self._compute_atr(high, low, close, period=14)
        result["atr_14"] = atr_result

        result["sma_20"] = self._compute_sma(close, period=20)
        result["sma_50"] = self._compute_sma(close, period=50)
        result["ema_20"] = self._compute_ema(close, period=20)
        result["ema_50"] = self._compute_ema(close, period=50)

        result["returns"] = self._compute_returns(close)
        result["volatility_20"] = self._compute_rolling_std(result["returns"].values, period=20)

        result["volume_sma_20"] = self._compute_sma(volume, period=20)
        result["volume_ratio"] = self._compute_volume_ratio(volume, result["volume_sma_20"].values)

        result["price_range"] = self._compute_price_range(high, low, close)

        return result

    def _compute_rsi(self, prices: np.ndarray, period: int = 14) -> np.ndarray:
        prices = np.asarray(prices, dtype=np.float64)
        delta = np.diff(prices, prepend=np.nan)

        gains = np.where(delta > 0, delta, 0)
        losses = np.where(delta < 0, -delta, 0)

        avg_gain = pd.Series(gains).rolling(window=period, min_periods=period).mean().values
        avg_loss = pd.Series(losses).rolling(window=period, min_periods=period).mean().values

        rs = np.divide(
            avg_gain,
            avg_loss,
            out=np.zeros_like(avg_gain),
            where=(avg_loss > 0) & (~np.isnan(avg_gain)) & (~np.isnan(avg_loss)),
        )
        rsi = 100 - (100 / (1 + rs))

        rsi = np.where((avg_gain == 0) & (avg_loss == 0), 100.0, rsi)
        rsi = np.where(np.isnan(rsi), np.nan, rsi)

        return rsi

    def _compute_macd(
        self,
        prices: np.ndarray,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> dict[str, np.ndarray]:
        prices = np.asarray(prices, dtype=np.float64)

        ema_fast = self._compute_ema(prices, fast)
        ema_slow = self._compute_ema(prices, slow)

        macd = ema_fast - ema_slow

        macd_signal = pd.Series(macd).rolling(window=signal, min_periods=signal).mean().values
        macd_hist = macd - macd_signal

        return {"macd": macd, "signal": macd_signal, "histogram": macd_hist}

    def _compute_atr(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14,
    ) -> np.ndarray:
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)

        prev_close = np.roll(close, 1)
        prev_close[0] = close[0]

        tr = np.maximum(high - low, np.abs(high - prev_close))
        tr = np.maximum(tr, np.abs(low - prev_close))

        atr = pd.Series(tr).rolling(window=period, min_periods=period).mean().values

        return atr

    def _compute_sma(self, values: np.ndarray, period: int = 20) -> np.ndarray:
        values = np.asarray(values, dtype=np.float64)
        sma = pd.Series(values).rolling(window=period, min_periods=period).mean().values
        return sma

    def _compute_ema(self, values: np.ndarray, period: int = 20) -> np.ndarray:
        values = np.asarray(values, dtype=np.float64)
        ema = pd.Series(values).ewm(span=period, adjust=False, min_periods=period).mean().values
        return ema

    def _compute_returns(self, prices: np.ndarray) -> np.ndarray:
        prices = np.asarray(prices, dtype=np.float64)
        returns = np.diff(prices, prepend=np.nan) / np.roll(prices, 1)
        returns[0] = np.nan
        return returns

    def _compute_rolling_std(self, values: np.ndarray, period: int = 20) -> np.ndarray:
        values = np.asarray(values, dtype=np.float64)
        return pd.Series(values).rolling(window=period, min_periods=period).std().values

    def _compute_volume_ratio(
        self,
        volume: np.ndarray,
        volume_sma: np.ndarray,
    ) -> np.ndarray:
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
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> np.ndarray:
        high = np.asarray(high, dtype=np.float64)
        low = np.asarray(low, dtype=np.float64)
        close = np.asarray(close, dtype=np.float64)

        with np.errstate(divide="ignore", invalid="ignore"):
            range_pct = np.where(
                close > 0,
                (high - low) / close,
                np.nan,
            )
        return range_pct

    def _build_features(self, symbol: str, date_str: str) -> dict[str, float]:
        return {
            "returns": 0.0,
            "volatility": 0.0,
            "volume_ratio": 0.0,
        }

    def _persist_features(
        self,
        symbol: str,
        date_str: str,
        features: dict[str, Any],
    ) -> None:
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

            feature = Feature(
                stock_id=stock.id,
                date=price.date,
                feature_version=self._feature_version,
                values=features,
            )
            session.add(feature)
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
    ) -> int:
        session = self._get_session()
        owns_session = self._session is None
        try:
            features_to_insert = []
            for _, row in features_df.iterrows():
                values = row.drop("date").to_dict()
                clean_values = {k: float(v) if not np.isnan(v) else None for k, v in values.items()}

                features_to_insert.append(
                    Feature(
                        stock_id=stock_id,
                        date=row["date"].date(),
                        feature_version=self._feature_version,
                        values=clean_values,
                    )
                )

            with session.begin_nested():
                for feat in features_to_insert:
                    session.merge(feat)

            session.commit()
            logger.info(
                f"Bulk persisted {len(features_to_insert)} feature rows",
                extra={"stock_id": stock_id, "feature_version": self._feature_version},
            )
            return len(features_to_insert)
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(
                f"Bulk feature persistence failed: {e}",
                extra={"stock_id": stock_id},
            )
            raise
        finally:
            if owns_session:
                session.close()