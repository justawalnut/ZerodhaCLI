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
    assert mapping["NSE:INFY"].day_pnl == 10.0
    assert mapping["NSE:INFY"].day_quantity == 1
    assert mapping["NSE:GAIL"].quantity == 2
    assert mapping["NSE:GAIL"].day_pnl is None


class DayOnlyClient:
    async def get(self, path, params=None):
        assert path == "/portfolio/positions"
        return {
            "data": {
                "day": [
                    {
                        "tradingsymbol": "SBIN",
                        "exchange": "NSE",
                        "product": "MIS",
                        "quantity": 0,
                        "average_price": 600.0,
                        "pnl": 25.0,
                        "last_price": 602.0,
                    }
                ]
            }
        }


def test_positions_include_day_only_entries_with_zero_quantity():
    service = PortfolioService(DayOnlyClient())  # type: ignore[arg-type]
    positions = asyncio.run(service.positions())

    assert len(positions) == 1
    position = positions[0]
    assert position.tradingsymbol == "SBIN"
    assert position.quantity == 0
    assert position.day_pnl == 25.0
    assert position.day_quantity == 0
