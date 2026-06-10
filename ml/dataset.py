"""Dataset builder for supervised ML training."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.orm import Session

# Ensure backend is on path for app.* imports
_backend_dir = Path(__file__).parent.parent / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# Model imports at module level to avoid SQLAlchemy MetaData collision
from backend.app.models.feature import Feature  # noqa: E402
from backend.app.models.price import Price  # noqa: E402
from backend.app.models.stock import Stock  # noqa: E402
from ml.feature_vector import build_feature_vector  # noqa: E402
from ml.labeling import LabelConfig, create_labels  # noqa: E402

logger = logging.getLogger(__name__)
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"


@dataclass
class DatasetBundle:
    X_train: NDArray[np.float64]
    X_val: NDArray[np.float64]
    X_test: NDArray[np.float64]
    y_train: NDArray[np.float64]
    y_val: NDArray[np.float64]
    y_test: NDArray[np.float64]
    train_dates: list[str]
    val_dates: list[str]
    test_dates: list[str]
    feature_version: str
    symbol: str


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
        y, _, valid_mask = create_labels(prices, self._label_config)
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
        y, _, valid_mask = create_labels(prices, self._label_config)
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

    def _query_feature_price_rows(self, symbol: str) -> list[Any]:
        stock = self._session.scalar(select(Stock).where(Stock.symbol == symbol.upper()))
        if stock is None:
            raise ValueError(f"Stock {symbol} not found")

        f = Feature
        p = Price

        stmt = (
            select(f, p)
            .join(p, (f.stock_id == p.stock_id) & (f.date == p.date))
            .where(
                f.stock_id == stock.id,
                f.feature_version == self._feature_version,
                f.confidence.is_not(None),
            )
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
        return list(self._session.scalars(select(Feature.feature_version).distinct()).all())
