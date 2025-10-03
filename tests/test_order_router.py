import asyncio

from zerodhacli.core.config import AppConfig, KiteCredentials
from zerodhacli.core.models import OrderRequest, OrderType, Product
from zerodhacli.services.order_router import OrderRouter
from zerodhacli.services.portfolio import PortfolioService


class MockClient:
    def __init__(self) -> None:
        self.orders_response = {"data": []}
        self._order_counter = 0
        self.last_payload = None
        self.cancelled_paths: list[str] = []

    async def post(self, path, payload):
        self._order_counter += 1
        self.last_payload = payload
        return {
            "status": "success",
            "data": {"order_id": f"MOCK-{self._order_counter}", "payload": payload},
        }

    async def put(self, path, payload):
        self.last_payload = payload
        return {"status": "success", "data": {"order_id": path.rsplit("/", 1)[-1], "payload": payload}}

    async def delete(self, path, params=None, headers=None):
        self.cancelled_paths.append(path)
        return {"status": "success", "data": {"order_id": path.rsplit("/", 1)[-1]}}

    async def get(self, path, params=None):
        return self.orders_response

    async def aclose(self):  # pragma: no cover - compatibility shim
        return None


def _router(client: MockClient | None = None, dry_run: bool = False) -> OrderRouter:
    config = AppConfig(creds=KiteCredentials(), dry_run=dry_run)
    client = client or MockClient()
    portfolio = PortfolioService(client)  # type: ignore[arg-type]
    return OrderRouter(config, client, portfolio)  # type: ignore[arg-type]


def test_place_order_uses_client_response():
    client = MockClient()
    router = _router(client)

    order = OrderRequest(
        tradingsymbol="TEST",
        exchange="NFO",
        transaction_type="BUY",
        quantity=1,
        order_type=OrderType.MARKET,
        product=Product.MIS,
    )

    response = asyncio.run(router.place_order(order))

    assert response.status == "success"
    assert response.order_id == "MOCK-1"
    assert client.last_payload["exchange"] == "NFO"
    assert client.last_payload["order_type"] == OrderType.MARKET.value


def test_filter_and_cancel_orders_against_mock_payload():
    client = MockClient()
    client.orders_response = {
        "data": [
            {
                "order_id": "11",
                "status": "OPEN",
                "tradingsymbol": "TEST",
                "transaction_type": "BUY",
                "exchange": "NFO",
                "quantity": 1,
                "price": 101,
                "order_timestamp": "2024-06-21 10:15:00",
                "variety": "regular",
                "product": "MIS",
            },
            {
                "order_id": "12",
                "status": "OPEN",
                "tradingsymbol": "TEST",
                "transaction_type": "BUY",
                "exchange": "NFO",
                "quantity": 1,
                "price": 102,
                "order_timestamp": "2024-06-21 10:16:00",
                "variety": "regular",
                "product": "MIS",
            },
            {
                "order_id": "13",
                "status": "OPEN",
                "tradingsymbol": "TEST",
                "transaction_type": "SELL",
                "exchange": "NFO",
                "quantity": 1,
                "price": 103,
                "order_timestamp": "2024-06-21 10:17:00",
                "variety": "regular",
                "product": "MIS",
            },
        ]
    }

    router = _router(client)

    latest_buy = asyncio.run(router.filter_orders(side="BUY", count=1, latest=True))
    assert len(latest_buy) == 1
    assert latest_buy[0].order_id == "12"

    responses = asyncio.run(router.cancel_orders([(latest_buy[0].order_id, latest_buy[0].variety)]))
    assert responses[0].status == "success"
    assert client.cancelled_paths[-1] == "/orders/regular/12"


def test_dry_run_generates_fake_ids():
    router = _router(dry_run=True)

    order = OrderRequest(
        tradingsymbol="TEST",
        exchange="NFO",
        transaction_type="BUY",
        quantity=1,
        order_type=OrderType.MARKET,
        product=Product.MIS,
    )

    response = asyncio.run(router.place_order(order))

    assert response.status == "dry-run"
    assert response.order_id.startswith("DRY-")


def test_recent_history_and_sim_positions():
    router = _router(dry_run=True)

    first = OrderRequest(
        tradingsymbol="TEST",
        exchange="NFO",
        transaction_type="BUY",
        quantity=2,
        order_type=OrderType.LIMIT,
        product=Product.MIS,
        price=100.0,
    )
    second = OrderRequest(
        tradingsymbol="TEST",
        exchange="NFO",
        transaction_type="SELL",
        quantity=1,
        order_type=OrderType.LIMIT,
        product=Product.MIS,
        price=105.0,
    )

    asyncio.run(router.place_order(first))
    asyncio.run(router.place_order(second))

    history = asyncio.run(router.recent_history(5))
    assert len(history) == 2
    assert history[-1].request.transaction_type == "SELL"

    positions = router.simulated_positions()
    assert len(positions) == 1
    position = positions[0]
    assert position.quantity == 1
    assert position.tradingsymbol == "TEST"
    assert position.last_price == 105.0


def test_recent_history_fetches_from_client_when_live():
    client = MockClient()
    client.orders_response = {
        "data": [
            {
                "order_id": "21",
                "status": "COMPLETE",
                "transaction_type": "BUY",
                "tradingsymbol": "FOO",
                "exchange": "NSE",
                "quantity": 5,
                "order_type": "LIMIT",
                "price": 101.5,
                "trigger_price": 100.5,
                "variety": "regular",
                "product": "MIS",
                "order_timestamp": "2024-06-21 10:15:00",
                "validity": "DAY",
            }
        ]
    }

    router = _router(client)

    history = asyncio.run(router.recent_history(3))

    assert len(history) == 1
    record = history[0]
    assert record.response.order_id == "21"
    assert record.request.tradingsymbol == "FOO"
    assert record.request.order_type.value == "LIMIT"
    assert record.request.price == 101.5
