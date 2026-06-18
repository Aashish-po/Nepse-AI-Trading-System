"""Tests for Phase 13: dashboard analytics and alerts."""

from __future__ import annotations

import datetime as dt

from app.models.price import Price
from app.models.signal import Signal
from app.models.stock import Stock
from app.services.alerts import AlertEngine
from app.services.analytics import AnalyticsService


def _stock(db_session, symbol: str, sector: str = "Banking") -> Stock:
    stock = Stock(symbol=symbol, name=symbol, sector=sector, is_active=True)
    db_session.add(stock)
    db_session.commit()
    return stock


def _price(db_session, stock_id, date, close, volume=1000) -> None:
    db_session.add(
        Price(
            stock_id=stock_id,
            date=date,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=volume,
        )
    )
    db_session.commit()


def _signal(db_session, stock_id, date, conf, value=1.0, stype="ml", provider="ml") -> None:
    db_session.add(
        Signal(
            stock_id=stock_id,
            date=date,
            signal_type=stype,
            value=value,
            confidence=conf,
            provider=provider,
        )
    )
    db_session.commit()


class TestAnalyticsService:
    def test_market_overview_movers(self, db_session) -> None:
        gainer = _stock(db_session, "GAIN")
        loser = _stock(db_session, "LOSE")
        d1 = dt.date(2024, 1, 1)
        d2 = dt.date(2024, 1, 2)
        _price(db_session, gainer.id, d1, 100.0)
        _price(db_session, gainer.id, d2, 110.0)  # +10%
        _price(db_session, loser.id, d1, 100.0)
        _price(db_session, loser.id, d2, 95.0)  # -5%

        service = AnalyticsService(db_session)
        overview = service.market_overview(top_n=5)
        assert overview["total_stocks"] == 2
        assert overview["active_stocks"] == 2
        assert overview["latest_date"] == "2024-01-02"
        assert overview["top_gainers"][0]["symbol"] == "GAIN"
        assert abs(overview["top_gainers"][0]["change_pct"] - 10.0) < 0.01
        assert overview["top_losers"][0]["symbol"] == "LOSE"

    def test_explore_signals_filters_and_summary(self, db_session) -> None:
        stock = _stock(db_session, "NABIL")
        d = dt.date(2024, 1, 1)
        _signal(db_session, stock.id, d, 0.9, stype="ml", provider="ml")
        _signal(db_session, stock.id, d, 0.4, stype="technical", provider="rules")

        service = AnalyticsService(db_session)
        result = service.explore_signals(min_confidence=0.5)
        assert result["summary"]["count"] == 1
        assert result["signals"][0]["signal_type"] == "ml"
        assert result["summary"]["avg_confidence"] == 0.9

    def test_portfolio_analytics(self, db_session) -> None:
        service = AnalyticsService(db_session)
        curve = [100.0, 102.0, 101.0, 105.0, 108.0]
        result = service.portfolio_analytics(curve)
        assert result["n_periods"] == 5
        assert result["total_return"] > 0
        assert result["max_drawdown"] >= 0

    def test_portfolio_analytics_empty(self, db_session) -> None:
        service = AnalyticsService(db_session)
        result = service.portfolio_analytics([])
        assert result["sharpe_ratio"] == 0.0
        assert result["n_periods"] == 0


class TestAlertEngine:
    def test_price_change_alert(self, db_session) -> None:
        stock = _stock(db_session, "ABC")
        _price(db_session, stock.id, dt.date(2024, 1, 1), 100.0)
        _price(db_session, stock.id, dt.date(2024, 1, 2), 112.0)  # +12%

        engine = AlertEngine(db_session)
        alerts = engine.evaluate_rules(
            [
                {
                    "name": "big_move",
                    "kind": "price_change_pct",
                    "symbol": "ABC",
                    "threshold_pct": 5.0,
                }
            ]
        )
        assert len(alerts) == 1
        assert alerts[0].symbol == "ABC"
        assert alerts[0].severity == "critical"  # 12% >= 2x threshold

    def test_price_change_below_threshold(self, db_session) -> None:
        stock = _stock(db_session, "QUIET")
        _price(db_session, stock.id, dt.date(2024, 1, 1), 100.0)
        _price(db_session, stock.id, dt.date(2024, 1, 2), 101.0)  # +1%
        engine = AlertEngine(db_session)
        alerts = engine.evaluate_rules(
            [{"kind": "price_change_pct", "symbol": "QUIET", "threshold_pct": 5.0}]
        )
        assert alerts == []

    def test_signal_confidence_alert(self, db_session) -> None:
        stock = _stock(db_session, "XYZ")
        _signal(db_session, stock.id, dt.date.today(), 0.92)
        engine = AlertEngine(db_session)
        alerts = engine.evaluate_rules(
            [{"kind": "signal_confidence", "min_confidence": 0.8, "lookback_days": 30}]
        )
        assert len(alerts) == 1
        assert alerts[0].kind == "signal_confidence"

    def test_volume_spike_alert(self, db_session) -> None:
        stock = _stock(db_session, "VOL")
        base = dt.date(2024, 1, 1)
        for i in range(20):
            _price(db_session, stock.id, base + dt.timedelta(days=i), 100.0, volume=1000)
        _price(db_session, stock.id, base + dt.timedelta(days=20), 100.0, volume=5000)
        engine = AlertEngine(db_session)
        alerts = engine.evaluate_rules(
            [{"kind": "volume_spike", "symbol": "VOL", "multiplier": 3.0, "window": 20}]
        )
        assert len(alerts) == 1
        assert alerts[0].kind == "volume_spike"

    def test_unknown_rule_ignored(self, db_session) -> None:
        engine = AlertEngine(db_session)
        alerts = engine.evaluate_rules([{"kind": "nonsense"}])
        assert alerts == []


class TestAnalyticsRoutes:
    def test_market_overview_endpoint(self, client, db_session) -> None:
        stock = _stock(db_session, "AAA")
        _price(db_session, stock.id, dt.date(2024, 1, 1), 100.0)
        _price(db_session, stock.id, dt.date(2024, 1, 2), 105.0)
        resp = client.get("/analytics/market-overview")
        assert resp.status_code == 200
        assert resp.json()["total_stocks"] == 1

    def test_signals_endpoint(self, client, db_session) -> None:
        stock = _stock(db_session, "BBB")
        _signal(db_session, stock.id, dt.date(2024, 1, 1), 0.85)
        resp = client.get("/analytics/signals?min_confidence=0.5")
        assert resp.status_code == 200
        assert resp.json()["summary"]["count"] == 1

    def test_portfolio_endpoint(self, client) -> None:
        resp = client.post("/analytics/portfolio", json={"equity_curve": [100, 105, 103, 110]})
        assert resp.status_code == 200
        assert resp.json()["n_periods"] == 4

    def test_alerts_evaluate_endpoint(self, client, db_session) -> None:
        stock = _stock(db_session, "CCC")
        _price(db_session, stock.id, dt.date(2024, 1, 1), 100.0)
        _price(db_session, stock.id, dt.date(2024, 1, 2), 120.0)
        resp = client.post(
            "/alerts/evaluate",
            json={"rules": [{"kind": "price_change_pct", "symbol": "CCC", "threshold_pct": 5.0}]},
        )
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
