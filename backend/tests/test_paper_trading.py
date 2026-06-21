# backend/tests/test_paper_trading.py

import datetime
from decimal import Decimal

from app.models.price import Price
from app.models.stock import Stock
from app.services.paper_trading import (
    OrderStatus,
    PaperTradingEngine,
)


# --------------------------------------------------------------------- service
def _engine() -> PaperTradingEngine:
    # No slippage/commission by default keeps arithmetic assertions exact; tests
    # that care about costs construct their own engine.
    return PaperTradingEngine(commission_rate=Decimal("0"), slippage_bps=Decimal("0"))


def test_create_account_with_initial_capital():
    engine = _engine()
    account = engine.create_account("Test", Decimal("50000.00"))

    assert account.id == 1
    assert account.cash == Decimal("50000.00")
    assert account.initial_capital == Decimal("50000.00")
    assert account.positions == {}
    assert engine.get_account(1) is account


def test_create_account_rejects_nonpositive_capital():
    engine = _engine()
    try:
        engine.create_account("Bad", Decimal("0"))
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_market_buy_fills_and_updates_position():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))

    order = engine.execute_order(
        account_id=account.id,
        symbol="abc",
        side="BUY",
        quantity=10,
        market_price=Decimal("100.00"),
    )

    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == Decimal("10")
    assert order.fill_price == Decimal("100.00")
    assert account.cash == Decimal("9000.00")  # 10000 - 10*100
    assert "ABC" in account.positions  # symbol normalized to upper
    assert account.positions["ABC"].quantity == Decimal("10")
    assert account.positions["ABC"].average_price == Decimal("100.00")


def test_buy_applies_slippage_and_commission():
    # 5 bps slippage on a buy: 100 -> 100.05; commission 0.5% of notional.
    engine = PaperTradingEngine(commission_rate=Decimal("0.005"), slippage_bps=Decimal("5.0"))
    account = engine.create_account("Test", Decimal("10000.00"))

    order = engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))

    assert order.fill_price is not None
    assert order.fill_price == Decimal("100.00") * (1 + Decimal("5.0") / Decimal("10000"))
    notional = Decimal("10") * order.fill_price
    assert order.commission == notional * Decimal("0.005")
    assert order.slippage_cost == abs(order.fill_price - Decimal("100.00")) * Decimal("10")
    assert account.cash == Decimal("10000.00") - notional - order.commission


def test_buy_insufficient_cash_is_rejected():
    engine = _engine()
    # Can't afford even one share (50 < 100).
    account = engine.create_account("Test", Decimal("50.00"))

    order = engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))

    assert order.status == OrderStatus.REJECTED
    assert account.cash == Decimal("50.00")
    assert "ABC" not in account.positions


def test_buy_partial_fill_when_cash_limited():
    engine = _engine()
    account = engine.create_account("Test", Decimal("550.00"))

    # Wants 10 @ 100 = 1000, can only afford 5.
    order = engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))

    assert order.status == OrderStatus.PARTIAL
    assert order.filled_quantity == Decimal("5")
    assert account.positions["ABC"].quantity == Decimal("5")


def test_average_price_on_add_to_position():
    engine = _engine()
    account = engine.create_account("Test", Decimal("100000.00"))

    engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))
    engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("120.00"))

    pos = account.positions["ABC"]
    assert pos.quantity == Decimal("20")
    assert pos.average_price == Decimal("110.00")  # (1000 + 1200) / 20


def test_sell_reduces_position_and_tracks_realized_pnl():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))
    engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))

    order = engine.execute_order(account.id, "ABC", "SELL", 5, Decimal("120.00"))

    assert order.status == OrderStatus.FILLED
    assert order.realized_pnl == Decimal("100.00")  # (120-100)*5
    assert account.positions["ABC"].quantity == Decimal("5")
    assert account.realized_pnl == Decimal("100.00")
    # cash: 10000 - 1000 (buy) + 600 (sell) = 9600
    assert account.cash == Decimal("9600.00")


def test_sell_entire_position_removes_it():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))
    engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))

    engine.execute_order(account.id, "ABC", "SELL", 10, Decimal("100.00"))

    assert "ABC" not in account.positions


def test_sell_without_position_is_rejected():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))

    order = engine.execute_order(account.id, "ABC", "SELL", 5, Decimal("100.00"))

    assert order.status == OrderStatus.REJECTED


def test_limit_buy_not_marketable_is_pending():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))

    # Market 100 is above the 95 buy limit -> not marketable.
    order = engine.execute_order(
        account.id,
        "ABC",
        "BUY",
        10,
        Decimal("100.00"),
        order_type="LIMIT",
        limit_price=Decimal("95.00"),
    )

    assert order.status == OrderStatus.PENDING
    assert order.filled_quantity == Decimal("0")
    assert account.cash == Decimal("10000.00")


def test_limit_buy_marketable_fills_at_capped_price():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))

    # Market 100 <= 105 limit -> fills, never above limit.
    order = engine.execute_order(
        account.id,
        "ABC",
        "BUY",
        10,
        Decimal("100.00"),
        order_type="LIMIT",
        limit_price=Decimal("105.00"),
    )

    assert order.status == OrderStatus.FILLED
    assert order.fill_price is not None
    assert order.fill_price <= Decimal("105.00")


def test_limit_sell_not_marketable_is_pending():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))
    engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))

    # Market 100 below the 110 sell limit -> not marketable.
    order = engine.execute_order(
        account.id,
        "ABC",
        "SELL",
        5,
        Decimal("100.00"),
        order_type="LIMIT",
        limit_price=Decimal("110.00"),
    )

    assert order.status == OrderStatus.PENDING
    assert account.positions["ABC"].quantity == Decimal("10")


def test_liquidity_cap_partial_fill_by_volume():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000000.00"))

    # Volume 100, threshold 30% => orders > 30 shares are capped.
    order = engine.execute_order(account.id, "ABC", "BUY", 100, Decimal("10.00"), volume=100)

    assert order.status == OrderStatus.PARTIAL
    assert order.filled_quantity < Decimal("100")
    assert order.filled_quantity > Decimal("0")


def test_mark_to_market_updates_equity_and_curve():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))
    engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))

    equity = engine.mark_to_market(account.id, {"ABC": Decimal("150.00")})

    # cash 9000 + 10 * 150 = 10500
    assert equity == Decimal("10500.00")
    assert account.positions["ABC"].unrealized_pnl == Decimal("500.00")
    assert len(account.equity_curve) == 1
    assert account.equity_curve[0]["equity"] == 10500.0


def test_account_summary_reports_pnl():
    engine = _engine()
    account = engine.create_account("Test", Decimal("10000.00"))
    engine.execute_order(account.id, "ABC", "BUY", 10, Decimal("100.00"))
    engine.mark_to_market(account.id, {"ABC": Decimal("110.00")})

    summary = engine.get_account_summary(account.id)

    assert summary["equity"] == 10100.0
    assert summary["unrealized_pnl"] == 100.0
    assert summary["total_pnl"] == 100.0
    assert abs(summary["total_return_pct"] - 1.0) < 1e-9
    assert summary["open_positions"] == 1


def test_get_trades_returns_recent_first():
    engine = _engine()
    account = engine.create_account("Test", Decimal("100000.00"))
    engine.execute_order(account.id, "ABC", "BUY", 1, Decimal("100.00"))
    engine.execute_order(account.id, "XYZ", "BUY", 1, Decimal("100.00"))

    trades = engine.get_trades(account.id)

    assert len(trades) == 2
    assert trades[0].symbol == "XYZ"  # most recent first


def test_unknown_account_raises():
    engine = _engine()
    for call in (
        lambda: engine.get_account_summary(999),
        lambda: engine.get_trades(999),
        lambda: engine.mark_to_market(999, {}),
        lambda: engine.execute_order(999, "ABC", "BUY", 1, Decimal("10")),
    ):
        try:
            call()
            raised = False
        except KeyError:
            raised = True
        assert raised


# ------------------------------------------------------------------------- API
def test_api_create_account_and_summary(client):
    resp = client.post(
        "/paper-trading/accounts",
        json={"name": "API Acct", "initial_capital": 50000.0},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "API Acct"
    assert body["cash"] == 50000.0
    account_id = body["account_id"]

    summary = client.get(f"/paper-trading/accounts/{account_id}/summary")
    assert summary.status_code == 200
    assert summary.json()["equity"] == 50000.0


def test_api_submit_order_with_explicit_price(client):
    acct = client.post("/paper-trading/accounts", json={"initial_capital": 100000.0}).json()
    account_id = acct["account_id"]

    resp = client.post(
        f"/paper-trading/accounts/{account_id}/orders",
        json={
            "symbol": "NABIL",
            "side": "BUY",
            "quantity": 10,
            "market_price": 500.0,
        },
    )
    assert resp.status_code == 200
    order = resp.json()
    assert order["status"] in ("FILLED", "PARTIAL")
    assert order["symbol"] == "NABIL"

    trades = client.get(f"/paper-trading/accounts/{account_id}/trades")
    assert trades.status_code == 200
    assert len(trades.json()) == 1


def test_api_order_uses_latest_price_from_history(client, db_session):
    stock = Stock(symbol="ADBL", name="ADBL", is_active=True)
    db_session.add(stock)
    db_session.flush()
    db_session.add(
        Price(
            stock_id=stock.id,
            date=datetime.date(2024, 1, 2),
            open=Decimal("200"),
            high=Decimal("210"),
            low=Decimal("195"),
            close=Decimal("205.00"),
            volume=100000,
        )
    )
    db_session.commit()

    account_id = client.post("/paper-trading/accounts", json={"initial_capital": 100000.0}).json()[
        "account_id"
    ]

    resp = client.post(
        f"/paper-trading/accounts/{account_id}/orders",
        json={"symbol": "ADBL", "side": "BUY", "quantity": 5},
    )
    assert resp.status_code == 200
    # API uses the default engine (5 bps slippage): 205 * 1.0005 = 205.1025.
    assert abs(resp.json()["fill_price"] - 205.1025) < 0.01


def test_api_order_missing_price_history_is_400(client):
    account_id = client.post("/paper-trading/accounts", json={"initial_capital": 100000.0}).json()[
        "account_id"
    ]

    resp = client.post(
        f"/paper-trading/accounts/{account_id}/orders",
        json={"symbol": "NOEXIST", "side": "BUY", "quantity": 5},
    )
    assert resp.status_code == 400


def test_api_summary_unknown_account_is_404(client):
    resp = client.get("/paper-trading/accounts/999999/summary")
    assert resp.status_code == 404
