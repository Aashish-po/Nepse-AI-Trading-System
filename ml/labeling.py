"""Label generation for supervised learning."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


class LabelMode(str, Enum):
    classification = "classification"
    regression = "regression"


@dataclass
class LabelConfig:
    horizon: int = 5
    up_threshold: float = 0.02
    down_threshold: float = -0.02
    mode: LabelMode = LabelMode.classification


def create_labels(
    prices: NDArray[np.floating],
    config: LabelConfig | None = None,
) -> tuple[NDArray[np.floating], NDArray[np.floating], NDArray[np.bool_]]:
    if config is None:
        config = LabelConfig()
    returns = _future_returns(prices, config.horizon)
    if config.mode == LabelMode.classification:
        labels = _classify(returns, config.up_threshold, config.down_threshold)
    else:
        labels = returns
    valid = ~np.isnan(labels) & ~np.isnan(returns)
    return labels[valid], returns[valid], valid


def _future_returns(prices: NDArray[np.floating], horizon: int) -> NDArray[np.floating]:
    future_prices = np.roll(prices, -horizon)
    future_prices[-horizon:] = np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        ret = (future_prices - prices) / np.where(prices != 0, prices, np.nan)
    ret[-horizon:] = np.nan
    return ret


def _classify(
    returns: NDArray[np.floating], up_threshold: float, down_threshold: float
) -> NDArray[np.floating]:
    labels = np.where(
        returns >= up_threshold,
        1.0,
        np.where(returns <= down_threshold, -1.0, 0.0),
    )
    labels[np.isnan(returns)] = np.nan
    return labels
