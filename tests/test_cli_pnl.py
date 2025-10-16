from types import SimpleNamespace

import pytest

from zerodhacli.cli import app
from zerodhacli.core.models import OrderResponse, OrderType, Position, Product


class StubOrders:
    def __init__(self):
        self.last_request = None

    async def place_order(self, order):
        self.last_request = order
        return OrderResponse(order_id="oid", status="ok")


class StubServices:
    def __init__(self):
        self.orders = StubOrders()
        self.config = SimpleNamespace(
            default_product="MIS",
            autoslice=False,
            market_protection=None,
            dry_run=True,
        )


class StubSession:
    def __init__(self):
        self.services = StubServices()


@pytest.mark.parametrize(
    "tokens,default,expected_tokens,expected_side",
    [
        ([], "SELL", [], "SELL"),
        (["INFY", "1", "200"], "SELL", ["INFY", "1", "200"], "SELL"),
        (["INFY", "1", "200", "buy"], "SELL", ["INFY", "1", "200"], "BUY"),
        (["INFY", "1", "200", "SELL"], "BUY", ["INFY", "1", "200"], "SELL"),
    ],
)
def test_extract_side(tokens, default, expected_tokens, expected_side):
    filtered, side = app._extract_side(tokens, default)
    assert filtered == expected_tokens
    assert side == expected_side


def test_compute_breakdown_uses_day_metrics():
    position = Position(
        tradingsymbol="INFY",
        exchange="NSE",
        product=Product.MIS,
        quantity=5,
        average_price=100.0,
        pnl=0.0,
        last_price=110.0,
        day_quantity=5,
        day_average_price=98.0,
        day_pnl=150.0,
    )
    breakdown = app._compute_position_breakdown(position)
    assert breakdown.mark == pytest.approx(110.0)
    assert breakdown.unrealized == pytest.approx((110.0 - 98.0) * 5)
    assert breakdown.realized == pytest.approx(150.0 - (110.0 - 98.0) * 5)
    assert breakdown.day == pytest.approx(150.0)
    assert breakdown.day_is_approximate is False


def test_compute_breakdown_falls_back_to_net_when_day_missing():
    position = Position(
        tradingsymbol="SBIN",
        exchange="NSE",
        product=Product.CNC,
        quantity=2,
        average_price=200.0,
        pnl=0.0,
        last_price=210.0,
    )
    breakdown = app._compute_position_breakdown(position)
    assert breakdown.unrealized == pytest.approx((210.0 - 200.0) * 2)
    assert breakdown.realized is None
    assert breakdown.day == pytest.approx((210.0 - 200.0) * 2)
    assert breakdown.day_is_approximate is True


def test_compute_breakdown_uses_position_pnl_when_available():
    position = Position(
        tradingsymbol="TCS",
        exchange="NSE",
        product=Product.CNC,
        quantity=3,
        average_price=3200.0,
        pnl=45.0,
        last_price=3215.0,
    )
    breakdown = app._compute_position_breakdown(position)
    assert breakdown.unrealized == pytest.approx((3215.0 - 3200.0) * 3)
    assert breakdown.day == pytest.approx(45.0)
    assert breakdown.day_is_approximate is False


def test_compute_breakdown_treats_closed_day_position_as_realized():
    position = Position(
        tradingsymbol="RELIANCE",
        exchange="NSE",
        product=Product.MIS,
        quantity=0,
        average_price=0.0,
        pnl=0.0,
        last_price=125.0,
        day_quantity=0,
        day_average_price=120.0,
        day_pnl=100.0,
    )
    breakdown = app._compute_position_breakdown(position)
    assert breakdown.unrealized == pytest.approx(0.0)
    assert breakdown.realized == pytest.approx(100.0)
    assert breakdown.day == pytest.approx(100.0)
    assert breakdown.day_is_approximate is False


def test_stop_loss_supports_buy_side():
    session = StubSession()
    dispatcher = app.CommandDispatcher(session)
    dispatcher.do_sl(["INFY", "1", "100", "buy"])
    request = session.services.orders.last_request
    assert request is not None
    assert request.transaction_type == "BUY"
    assert request.order_type in {OrderType.SL, OrderType.SL_M}


def test_take_profit_places_limit_order_with_side():
    session = StubSession()
    dispatcher = app.CommandDispatcher(session)
    dispatcher.do_tp(["INFY", "1", "@250", "buy"])
    request = session.services.orders.last_request
    assert request is not None
    assert request.transaction_type == "BUY"
    assert request.order_type is OrderType.LIMIT
    assert request.price == pytest.approx(250.0)
