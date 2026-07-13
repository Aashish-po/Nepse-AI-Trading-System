from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


DEFAULT_CSV_DIR = ROOT / "nepse_data" / "data"
DEFAULT_OUTPUT_DIR = ROOT / "exports"
MARKET_EVENTS: list[dict[str, Any]] = []


@dataclass(frozen=True)
class MarketTrendResult:
    frame: pd.DataFrame
    figure: go.Figure
    html_path: Path
    png_path: Path


def _load_rows(csv_dir: Path | str = DEFAULT_CSV_DIR) -> list[dict[str, Any]]:
    from app.services.csv_ingestion import _READERS, _pick, _valid_ohlcv

    base = Path(csv_dir)
    rows: list[dict[str, Any]] = []
    for source in ("sharesansar", "merolagani"):
        source_dir = base / source
        if not source_dir.is_dir():
            continue
        for path in sorted(source_dir.glob("*.csv")):
            try:
                file_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            parsed = _READERS[source](path, file_date)
            if not parsed:
                continue
            rows.extend(parsed)

    rows = [row for row in rows if _valid_ohlcv(row)]
    merged: dict[tuple[str, date], dict[str, Any]] = {}
    for row in rows:
        key = (row["symbol"], row["date"])
        merged[key] = row if key not in merged else _pick(merged[key], row)
    return list(merged.values())


def build_market_trend_frame(csv_dir: Path | str = DEFAULT_CSV_DIR) -> pd.DataFrame:
    rows = _load_rows(csv_dir)
    if not rows:
        return pd.DataFrame(columns=["date", "close", "volume", "sma_5", "ema_5", "sma_20"])

    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["date", "symbol"]).reset_index(drop=True)

    index_frame = (
        frame.groupby("date", as_index=False)
        .agg(close=("close", "mean"), volume=("volume", "sum"), symbol_count=("symbol", "nunique"))
        .sort_values("date")
        .reset_index(drop=True)
    )
    if index_frame.empty:
        return index_frame

    index_frame["index_close"] = index_frame["close"] / index_frame["close"].iloc[0] * 100.0
    returns = index_frame["index_close"].pct_change().fillna(0.0)
    rolling_mean = returns.rolling(5, min_periods=2).mean()
    rolling_std = returns.rolling(5, min_periods=2).std(ddof=0).replace(0, np.nan)
    z_scores = ((returns - rolling_mean) / rolling_std).replace([np.inf, -np.inf], np.nan)
    clipped = returns.copy()
    mask = z_scores.abs() > 5
    if mask.any():
        clipped.loc[mask] = rolling_mean.loc[mask]
        adjusted = (1.0 + clipped).cumprod()
        adjusted = adjusted / adjusted.iloc[0] * 100.0
        index_frame["index_close"] = adjusted

    index_frame["sma_5"] = index_frame["index_close"].rolling(5, min_periods=1).mean()
    index_frame["ema_5"] = index_frame["index_close"].ewm(span=5, adjust=False).mean()
    if len(index_frame) >= 20:
        index_frame["sma_20"] = index_frame["index_close"].rolling(20, min_periods=20).mean()
    else:
        index_frame["sma_20"] = np.nan

    return index_frame


def build_market_trend_figure(frame: pd.DataFrame) -> go.Figure:
    if frame.empty:
        fig = go.Figure()
        fig.update_layout(title="NEPSE Overall Index - no data available")
        return fig

    start = frame["date"].min().date().isoformat()
    end = frame["date"].max().date().isoformat()
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Scatter(
            x=frame["date"],
            y=frame["index_close"],
            mode="lines",
            name="NEPSE composite (rebased 100)",
            line=dict(width=2.5, color="#0f766e"),
            hovertemplate="%{x|%Y-%m-%d}<br>Index: %{y:.2f}<extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Bar(
            x=frame["date"],
            y=frame["volume"],
            name="Aggregate volume",
            marker_color="#94a3b8",
            opacity=0.45,
            hovertemplate="%{x|%Y-%m-%d}<br>Volume: %{y:,.0f}<extra></extra>",
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=frame["date"],
            y=frame["sma_5"],
            mode="lines",
            name="5-day SMA",
            line=dict(width=1.5, color="#f59e0b"),
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=frame["date"],
            y=frame["ema_5"],
            mode="lines",
            name="5-day EMA",
            line=dict(width=1.5, dash="dash", color="#7c3aed"),
        ),
        secondary_y=False,
    )
    if frame["sma_20"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=frame["date"],
                y=frame["sma_20"],
                mode="lines",
                name="20-day SMA",
                line=dict(width=1.5, dash="dot", color="#dc2626"),
            ),
            secondary_y=False,
        )

    for event in MARKET_EVENTS:
        event_date = pd.to_datetime(event["date"])
        fig.add_vline(x=event_date, line_width=1, line_dash="dot", line_color="#475569")
        fig.add_annotation(
            x=event_date,
            y=1.02,
            yref="paper",
            text=event["label"],
            showarrow=False,
            font=dict(size=10, color="#334155"),
            xanchor="left",
        )

    fig.update_layout(
        title=f"NEPSE Overall Index — {start} to {end}",
        template="plotly_white",
        height=820,
        width=1400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        margin=dict(l=60, r=50, t=90, b=60),
        hovermode="x unified",
        xaxis=dict(title="Date", rangeslider=dict(visible=False)),
        yaxis=dict(title="Synthetic index (rebased 100)"),
        yaxis2=dict(title="Volume", overlaying="y", side="right"),
        annotations=[
            dict(
                text="Synthetic equal-weighted composite from @nepse_data; year-over-year N/A (<=1 month)",
                x=0,
                y=1.11,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=11, color="#475569"),
            ),
            dict(
                text="Source: @nepse_data (ShareSansar / Merolagani)",
                x=0,
                y=-0.16,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=10, color="#64748b"),
            ),
        ],
    )
    fig.update_yaxes(automargin=True)
    return fig


def generate_market_trend_chart(
    csv_dir: Path | str = DEFAULT_CSV_DIR,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
) -> MarketTrendResult:
    frame = build_market_trend_frame(csv_dir)
    fig = build_market_trend_figure(frame)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    html_path = output_path / "market_trend_chart.html"
    png_path = output_path / "market_trend_chart.png"

    fig.write_html(str(html_path), include_plotlyjs="cdn")
    try:
        fig.write_image(str(png_path), width=1400, height=800, scale=2)
    except Exception:
        _write_png_fallback(frame, png_path)
    return MarketTrendResult(frame=frame, figure=fig, html_path=html_path, png_path=png_path)


def _write_png_fallback(frame: pd.DataFrame, png_path: Path) -> None:
    from PIL import Image, ImageDraw

    width, height = 1400, 800
    image = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(image)

    title = "NEPSE Overall Index"
    subtitle = "Plotly image export fallback (PNG still generated)"
    draw.text((40, 30), title, fill=(15, 23, 42))
    draw.text((40, 60), subtitle, fill=(71, 85, 105))

    if frame.empty:
        draw.text((40, 110), "No data available.", fill=(100, 116, 139))
        image.save(png_path)
        return

    left, top, right, bottom = 80, 160, 1320, 680
    draw.rectangle((left, top, right, bottom), outline=(148, 163, 184), width=2)

    series = frame["index_close"].astype(float)
    volume = frame["volume"].astype(float)
    min_val, max_val = float(series.min()), float(series.max())
    span = max(max_val - min_val, 1.0)

    points: list[tuple[float, float]] = []
    for idx, value in enumerate(series):
        x = left + (right - left) * (idx / max(len(series) - 1, 1))
        y = bottom - ((float(value) - min_val) / span) * (bottom - top - 30) - 15
        points.append((x, y))
    if len(points) > 1:
        draw.line(points, fill=(15, 118, 110), width=4)

    max_volume = max(float(volume.max()), 1.0)
    bar_base = 720
    bar_top = 700
    bar_width = max((right - left) / max(len(volume), 1), 1)
    for idx, value in enumerate(volume):
        x0 = left + idx * bar_width
        x1 = x0 + max(bar_width - 2, 1)
        y1 = bar_base
        y0 = bar_base - ((float(value) / max_volume) * (bar_base - bar_top))
        draw.rectangle((x0, y0, x1, y1), fill=(148, 163, 184))

    summary = (
        f"start={series.iloc[0]:.2f}  end={series.iloc[-1]:.2f}  "
        f"rows={len(frame)}  avg_volume={volume.mean():.0f}"
    )
    draw.text((40, 740), summary, fill=(51, 65, 85))
    image.save(png_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the NEPSE market trend chart")
    parser.add_argument("--csv-dir", default=str(DEFAULT_CSV_DIR))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)

    result = generate_market_trend_chart(csv_dir=args.csv_dir, output_dir=args.output_dir)
    if result.frame.empty:
        print("No market data found; wrote empty chart shell.")
        return 0

    period_return = result.frame["index_close"].iloc[-1] / result.frame["index_close"].iloc[0] - 1.0
    print(
        "Generated market trend chart:"
        f" start={result.frame['index_close'].iloc[0]:.2f}"
        f" end={result.frame['index_close'].iloc[-1]:.2f}"
        f" return={period_return:.2%}"
        f" avg_volume={result.frame['volume'].mean():.0f}"
        f" rows={len(result.frame)}"
    )
    print(f"HTML: {result.html_path}")
    print(f"PNG: {result.png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
