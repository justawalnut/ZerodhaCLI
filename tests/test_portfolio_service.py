import asyncio

from zerodhacli.core.models import Product
from zerodhacli.services.portfolio import PortfolioService


class StubClient:
    async def get(self, path, params=None):
        assert path == "/portfolio/positions"
        return {
            "data": {
                "day": [
                    {
                        "tradingsymbol": "INFY",
                        "exchange": "NSE",
                        "product": "MIS",
                        "quantity": 1,
                        "average_price": 1500.0,
                        "pnl": 10.0,
                        "last_price": 1510.0,
                    }
                ],
                "net": [
                    {
                        "tradingsymbol": "INFY",
                        "exchange": "NSE",
                        "product": "MIS",
                        "quantity": 1,
                        "average_price": 1500.0,
                        "pnl": 10.0,
                        "last_price": 1510.0,
                    },
                    {
                        "tradingsymbol": "GAIL",
                        "exchange": "NSE",
                        "product": "CNC",
                        "quantity": 2,
                        "average_price": 125.0,
                        "pnl": 6.0,
                        "last_price": 128.0,
                    },
                ],
            }
        }


async def _positions():
    service = PortfolioService(StubClient())  # type: ignore[arg-type]
    return await service.positions()


def test_positions_deduplicate_day_and_net_entries():
    positions = asyncio.run(_positions())
    assert len(positions) == 2

    mapping = {f"{p.exchange}:{p.tradingsymbol}": p for p in positions}
    assert mapping["NSE:INFY"].product is Product.MIS
    assert mapping["NSE:GAIL"].quantity == 2
