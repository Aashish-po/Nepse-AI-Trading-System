"""Dataset building and walk-forward validation for ML training."""

# ruff: noqa: E402
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

# MUST be at the very top before any other imports
_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"

if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

# Now safe to import everything else
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from app.models.feature import Features
from app.models.price import Price
from app.models.stock import Stock
from sqlalchemy import select
from sqlalchemy.orm import Session

from ml.feature_vector import build_feature_vector
from ml.labeling import LabelConfig, create_labels

logger = logging.getLogger(__name__)
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"


@dataclass
class DatasetBundle:
    X_train: NDArray[np.float64]
    X_val: NDArray[np.float64]
    X_test: NDArray[np.float64]
    y_train: NDArray[np.floating]
    y_val: NDArray[np.floating]
    y_test: NDArray[np.floating]

    train_dates: list[str]
    val_dates: list[str]
    test_dates: list[str]
    feature_version: str
    symbol: str
    prices_train: NDArray[np.float64] | None = None
    prices_val: NDArray[np.float64] | None = None
    prices_test: NDArray[np.float64] | None = None
    returns_train: NDArray[np.floating] | None = None
    returns_val: NDArray[np.floating] | None = None
    returns_test: NDArray[np.floating] | None = None

    # Allow dict-style access used in some tests: bundle['X_train']
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


@dataclass
class WalkForwardWindow:
    bundle: DatasetBundle
    window_index: int
    total_windows: int


class DatasetBuilder:
    def __init__(
        self,
        session: Session,
        label_config: LabelConfig | None = None,
        feature_version: str | None = None,
        impute: bool = True,
        artifacts_dir: Path | None = None,
    ) -> None:
        self._session = session
        self._label_config = label_config or LabelConfig()
        self._feature_version = feature_version or "v4.0.0"
        self._impute = impute
        self._artifacts_dir = artifacts_dir or ARTIFACTS_DIR

    def walk_forward(
        self,
        symbol: str,
        window_size: float = 0.7,
        step_size: float = 0.2,
        horizon: int | None = None,
    ) -> Iterator[WalkForwardWindow]:
        rows = self._query_feature_price_rows(symbol)
        if not rows:
            raise ValueError(f"No feature/price data available for {symbol}")

        X_list: list[NDArray[np.float64]] = []
        prices_list: list[float] = []
        dates: list[str] = []
        for feature_row, price_row in rows:
            values = feature_row.values or {}
            close_p = price_row.close if price_row is not None else None
            if not values or close_p is None:
                continue
            X_list.append(build_feature_vector(values))
            prices_list.append(float(close_p))
            dates.append(feature_row.date.isoformat())

        if not X_list:
            raise ValueError(f"No valid feature rows for {symbol}")

        X = np.vstack(X_list)
        prices = np.array(prices_list, dtype=np.float64)
        y, returns, valid_mask = create_labels(prices, self._label_config)
        X = X[valid_mask]
        dates = [d for i, d in enumerate(dates) if valid_mask[i]]

        if self._impute:
            X = self._impute_features(X)

        n = len(X)
        window_days = int(n * window_size)
        step_days = int(n * step_size)

        window_index = 0
        for start in range(0, n - window_days - int(n * 0.15), step_days):
            train_end = start + window_days
            val_end = min(train_end + int(window_days * 0.15 / 0.7), n)
            test_end = min(val_end + int(window_days * 0.15 / 0.7), n)

            bundle = DatasetBundle(
                X_train=X[start:train_end],
                X_val=X[train_end:val_end],
                X_test=X[val_end:test_end],
                y_train=y[start:train_end],
                y_val=y[train_end:val_end],
                y_test=y[val_end:test_end],
                train_dates=dates[start:train_end],
                val_dates=dates[train_end:val_end],
                test_dates=dates[val_end:test_end],
                feature_version=self._feature_version,
                symbol=symbol,
                prices_train=prices[start:train_end],
                prices_val=prices[train_end:val_end],
                prices_test=prices[val_end:test_end],
                returns_train=returns[start:train_end],
                returns_val=returns[train_end:val_end],
                returns_test=returns[val_end:test_end],
            )
            total_windows = int((n - window_days) / step_days) + 1
            yield WalkForwardWindow(
                bundle=bundle, window_index=window_index, total_windows=total_windows
            )
            window_index += 1

    def build(self, symbol: str) -> DatasetBundle:
        rows = self._query_feature_price_rows(symbol)
        if not rows:
            raise ValueError(f"No feature/price data available for {symbol}")

        X_list: list[NDArray[np.float64]] = []
        prices_list: list[float] = []
        dates: list[str] = []

        for feature_row, price_row in rows:
            values = feature_row.values or {}
            close_p = price_row.close if price_row is not None else None
            if not values or close_p is None:
                continue
            X_list.append(build_feature_vector(values))
            prices_list.append(float(close_p))
            dates.append(feature_row.date.isoformat())

        if not X_list:
            raise ValueError(f"No valid feature rows for {symbol}")

        X = np.vstack(X_list)
        prices = np.array(prices_list, dtype=np.float64)
        y, returns, valid_mask = create_labels(prices, self._label_config)
        X = X[valid_mask]
        dates = [d for i, d in enumerate(dates) if valid_mask[i]]

        if self._impute:
            X = self._impute_features(X)

        n = len(X)
        train_end = int(n * 0.7)
        val_end = int(n * 0.85)

        return DatasetBundle(
            X_train=X[:train_end],
            X_val=X[train_end:val_end],
            X_test=X[val_end:],
            y_train=y[:train_end],
            y_val=y[train_end:val_end],
            y_test=y[val_end:],
            train_dates=dates[:train_end],
            val_dates=dates[train_end:val_end],
            test_dates=dates[val_end:],
            feature_version=self._feature_version,
            symbol=symbol,
            prices_train=prices[:train_end],
            prices_val=prices[train_end:val_end],
            prices_test=prices[val_end:],
            returns_train=returns[:train_end],
            returns_val=returns[train_end:val_end],
            returns_test=returns[val_end:],
        )

    def build_and_export_parquet(
        self, symbol: str, dataset_name: str | None = None
    ) -> tuple[DatasetBundle, Path]:
        bundle = self.build(symbol)
        name = dataset_name or f"{symbol}_{self._feature_version}"
        path = self._export_parquet(bundle, name)
        return bundle, path

    def _export_parquet(self, bundle: DatasetBundle, name: str) -> Path:
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        path = self._artifacts_dir / f"{name}.parquet"
        table = pa.table(
            {
                "split": (
                    ["train"] * len(bundle.X_train)
                    + ["val"] * len(bundle.X_val)
                    + ["test"] * len(bundle.X_test)
                ),
                "date": bundle.train_dates + bundle.val_dates + bundle.test_dates,
                "label": np.concatenate([bundle.y_train, bundle.y_val, bundle.y_test]).tolist(),
            }
        )
        pq.write_table(table, path)
        logger.info("Exported dataset to %s", path)
        return path

    def _query_feature_price_rows(
        self, symbol: str, start_date: date | None = None, end_date: date | None = None
    ) -> list[Any]:
        stock = self._session.scalar(select(Stock).where(Stock.symbol == symbol.upper()))
        if stock is None:
            raise ValueError(f"Stock {symbol} not found")

        f = Features
        p = Price
        where_conditions = [
            f.stock_id == stock.id,
            f.feature_version == self._feature_version,
            f.confidence.is_not(None),
        ]
        if start_date is not None:
            where_conditions.append(f.date >= start_date)
        if end_date is not None:
            where_conditions.append(f.date <= end_date)

        stmt = (
            select(f, p)
            .join(p, (f.stock_id == p.stock_id) & (f.date == p.date))
            .where(*where_conditions)
            .order_by(f.date.asc())
        )
        return list(self._session.execute(stmt).all())

    def _impute_features(self, X: NDArray[np.float64]) -> NDArray[np.float64]:
        train_medians = np.nanmedian(X, axis=0)
        train_medians = np.where(np.isnan(train_medians), 0.0, train_medians)
        for i in range(X.shape[1]):
            col = X[:, i]
            mask = np.isnan(col) | np.isinf(col)
            col[mask] = train_medians[i]
            X[:, i] = col
        return X

    def get_feature_version(self) -> str:
        return self._feature_version

    def get_label_config(self) -> LabelConfig:
        return self._label_config

    def get_artifacts_dir(self) -> Path:
        return self._artifacts_dir

    def get_impute(self) -> bool:
        return self._impute

    def get_session(self) -> Session:
        return self._session

    def get_dataset_shape(self, symbol: str) -> tuple[int, int]:
        rows = self._query_feature_price_rows(symbol)
        if not rows:
            raise ValueError(f"No feature/price data available for {symbol}")
        return len(rows), len(rows[0][0].values or {})

    def get_available_symbols(self) -> list[str]:
        stocks = self._session.scalars(select(Stock)).all()
        return [s.symbol for s in stocks]

    def get_available_feature_versions(self) -> list[str]:
        return list(self._session.scalars(select(Features.feature_version).distinct()).all())

    def build_supervised(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        lookback: int = 20,
        lookahead: int = 1,
        target_threshold: float = 0.02,
        random_state: int | None = None,
    ) -> tuple[pd.DataFrame, pd.Series]:
        """Build X, y for supervised learning with time-series safe construction."""

        all_X = []
        all_y = []

        for symbol in symbols:
            rows = self._query_feature_price_rows(symbol, start_date, end_date)
            if not rows:
                continue

            prices_list = []
            features_list = []
            dates_list = []
            for feature_row, price_row in rows:
                values = feature_row.values or {}
                close_p = price_row.close if price_row is not None else None
                if not values or close_p is None:
                    continue
                prices_list.append(float(close_p))
                features_list.append(values)
                dates_list.append(feature_row.date)

            if len(prices_list) < lookback + lookahead:
                continue

            prices = np.array(prices_list)
            for i in range(lookback, len(prices) - lookahead):
                X_window = []
                for j in range(i - lookback, i):
                    fv = self._feature_values_to_vector(features_list[j])
                    X_window.extend(fv)
                all_X.append(X_window)

                future_return = (
                    (prices[i + lookahead] - prices[i]) / prices[i] if prices[i] != 0 else 0.0
                )
                if future_return > target_threshold:
                    label = 1
                elif future_return < -target_threshold:
                    label = -1
                else:
                    label = 0
                all_y.append(label)

        if not all_X:
            return pd.DataFrame(), pd.Series(dtype=np.float64)

        return pd.DataFrame(np.array(all_X)), pd.Series(np.array(all_y))

    def _feature_values_to_vector(self, values: dict) -> list[float]:
        return list(build_feature_vector(values))

    def walk_forward_cv(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        train_size: int = 252,
        test_size: int = 63,
        step: int = 63,
        lookahead: int = 1,
        target_threshold: float = 0.02,
    ) -> Iterator[tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, list[str], list[str]]]:
        """Time-series cross-validation: walk forward window."""

        all_X, all_y, all_dates, _all_returns, _all_prices = self._build_full_dataset(
            symbols, start_date, end_date, lookahead, target_threshold
        )

        n = len(all_X)
        if n < train_size + test_size:
            return

        for start in range(0, n - train_size - test_size + 1, step):
            train_end = start + train_size
            test_end = train_end + test_size

            train_X = all_X.iloc[start:train_end].reset_index(drop=True)
            train_y = all_y.iloc[start:train_end].reset_index(drop=True)
            test_X = all_X.iloc[train_end:test_end].reset_index(drop=True)
            test_y = all_y.iloc[train_end:test_end].reset_index(drop=True)
            train_dates = all_dates[start:train_end]
            test_dates = all_dates[train_end:test_end]

            yield train_X, train_y, test_X, test_y, train_dates, test_dates

    def _build_full_dataset(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        lookahead: int = 1,
        target_threshold: float = 0.02,
    ) -> tuple[pd.DataFrame, pd.Series, list[str], list[float], list[float]]:
        all_X = []
        all_y = []
        all_dates = []
        all_returns = []
        all_prices = []

        for symbol in symbols:
            rows = self._query_feature_price_rows(symbol, start_date, end_date)
            if not rows:
                continue

            prices_list = []
            features_list = []
            dates_list = []
            for feature_row, price_row in rows:
                values = feature_row.values or {}
                close_p = price_row.close if price_row is not None else None
                if not values or close_p is None:
                    continue
                prices_list.append(float(close_p))
                features_list.append(values)
                dates_list.append(feature_row.date.isoformat())

            lookback = 20
            if len(prices_list) < lookback + lookahead:
                continue

            for i in range(lookback, len(prices_list) - lookahead):
                X_window = []
                for j in range(i - lookback, i):
                    fv = self._feature_values_to_vector(features_list[j])
                    X_window.extend(fv)
                all_X.append(X_window)

                future_return = (
                    (prices_list[i + lookahead] - prices_list[i]) / prices_list[i]
                    if prices_list[i] != 0
                    else 0.0
                )
                if future_return > target_threshold:
                    label = 1
                elif future_return < -target_threshold:
                    label = -1
                else:
                    label = 0
                all_y.append(label)
                all_returns.append(future_return)
                all_prices.append(prices_list[i])
                all_dates.append(dates_list[i])

        if not all_X:
            return pd.DataFrame(), pd.Series(dtype=np.float64), [], [], []

        return (
            pd.DataFrame(np.array(all_X)),
            pd.Series(np.array(all_y)),
            all_dates,
            all_returns,
            all_prices,
        )
