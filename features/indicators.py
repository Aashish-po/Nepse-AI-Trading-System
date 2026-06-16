"""Standalone technical indicator functions for feature engineering."""

from __future__ import annotations

from typing import Any

import numpy as np


def compute_rsi(prices: Any, period: int = 14) -> np.ndarray:
    """Compute Relative Strength Index with SMA-based rolling mean.

    Handles the edge case where average loss is zero (constant prices) by returning 100.0.
    """
    prices = np.asarray(prices, dtype=np.float64)
    delta = np.diff(prices, prepend=np.nan)

    gains = np.where(delta > 0, delta, 0)
    losses = np.where(delta < 0, -delta, 0)

    avg_gain = np.asarray(
        __import__("pandas").Series(gains).rolling(window=period, min_periods=period).mean().values
    )
    avg_loss = np.asarray(
        __import__("pandas").Series(losses).rolling(window=period, min_periods=period).mean().values
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


def compute_sma(values: Any, period: int = 20) -> np.ndarray:
    """Compute Simple Moving Average."""
    values = np.asarray(values, dtype=np.float64)
    sma = np.asarray(
        __import__("pandas").Series(values).rolling(window=period, min_periods=period).mean().values
    )
    return sma


def compute_ema(values: Any, period: int = 20) -> np.ndarray:
    """Compute Exponential Moving Average."""
    values = np.asarray(values, dtype=np.float64)
    ema = np.asarray(
        __import__("pandas")
        .Series(values)
        .ewm(span=period, adjust=False, min_periods=period)
        .mean()
        .values
    )
    return ema


def compute_macd(
    prices: Any,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, np.ndarray]:
    """Compute MACD with histogram."""
    prices = np.asarray(prices, dtype=np.float64)

    ema_fast = compute_ema(prices, fast)
    ema_slow = compute_ema(prices, slow)

    macd = ema_fast - ema_slow

    # The MACD signal line is conventionally a 9-period EMA of the MACD line, not an SMA.
    macd_signal = compute_ema(macd, signal)
    macd_hist = np.asarray(macd - macd_signal)

    return {
        "macd": np.asarray(macd),
        "signal": macd_signal,
        "histogram": macd_hist,
    }


def compute_atr(
    high: Any,
    low: Any,
    close: Any,
    period: int = 14,
) -> np.ndarray:
    """Compute Average True Range."""
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    tr = np.maximum(high - low, np.abs(high - prev_close))
    tr = np.maximum(tr, np.abs(low - prev_close))

    atr = np.asarray(
        __import__("pandas").Series(tr).rolling(window=period, min_periods=period).mean().values
    )

    return atr


def compute_returns(prices: Any) -> np.ndarray:
    """Compute periodic returns."""
    prices = np.asarray(prices, dtype=np.float64)
    diff = np.diff(prices, prepend=np.nan)
    prev = np.roll(prices, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.where(prev != 0, diff / prev, np.nan)
    returns[0] = np.nan
    return np.asarray(returns)


def compute_volatility(values: Any, period: int = 20) -> np.ndarray:
    """Compute rolling standard deviation (volatility)."""
    values = np.asarray(values, dtype=np.float64)
    return np.asarray(
        __import__("pandas").Series(values).rolling(window=period, min_periods=period).std().values
    )


def compute_volume_ratio(
    volume: Any,
    volume_sma: Any,
) -> np.ndarray:
    """Compute volume normalization ratio."""
    volume = np.asarray(volume, dtype=np.float64)
    volume_sma = np.asarray(volume_sma, dtype=np.float64)

    ratio = np.divide(
        volume,
        volume_sma,
        out=np.ones_like(volume),
        where=volume_sma > 0,
    )
    return ratio


def compute_price_range(
    high: Any,
    low: Any,
    close: Any,
) -> np.ndarray:
    """Compute price range as percentage of close."""
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
