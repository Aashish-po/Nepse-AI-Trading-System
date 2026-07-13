from __future__ import annotations

from pathlib import Path

from scripts.generate_market_trend_chart import (
    build_market_trend_figure,
    build_market_trend_frame,
    generate_market_trend_chart,
)


def test_market_trend_chart_builds_from_real_csvs(tmp_path: Path) -> None:
    csv_dir = Path(__file__).resolve().parents[2] / "nepse_data" / "data"
    frame = build_market_trend_frame(csv_dir=csv_dir)

    assert not frame.empty
    assert frame["index_close"].isna().sum() == 0

    figure = build_market_trend_figure(frame)
    assert figure is not None

    result = generate_market_trend_chart(csv_dir=csv_dir, output_dir=tmp_path)
    assert result.html_path.exists()
    assert result.png_path.exists()
