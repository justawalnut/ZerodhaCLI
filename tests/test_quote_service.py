import asyncio

from zerodhacli.core.models import Position, Product
from zerodhacli.services.quote import QuoteService


class StubClient:
    def __init__(self) -> None:
        self.captured_path = None
        self.captured_params = None

    async def get(self, path, params=None):
        self.captured_path = path
        self.captured_params = params
        return {
            "data": {
                "NSE:INFY": {"last_price": 1540.5},
                "NSE:HDFCBANK": {"last_price": 1501.0},
            }
        }


def test_ltp_fetches_each_instrument():
    client = StubClient()
    service = QuoteService(client)  # type: ignore[arg-type]

    result = asyncio.run(service.ltp(["NSE:INFY", "NSE:HDFCBANK", "NSE:INFY"]))

    assert client.captured_path == "/quote/ltp"
    assert client.captured_params == [("i", "NSE:INFY"), ("i", "NSE:HDFCBANK")]
    assert result["NSE:INFY"] == 1540.5
    assert result["NSE:HDFCBANK"] == 1501.0


def test_enrich_positions_updates_missing_prices():
    client = StubClient()
    service = QuoteService(client)  # type: ignore[arg-type]

    position = Position(
        tradingsymbol="INFY",
        exchange="NSE",
        product=Product.MIS,
        quantity=1,
        average_price=1500.0,
        pnl=0.0,
        last_price=None,
    )

    asyncio.run(service.enrich_positions([position]))

    assert position.last_price == 1540.5
