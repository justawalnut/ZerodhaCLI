"""Portfolio state helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from ..core.models import Position, Product
from .kite_client import KiteRESTClient


@dataclass(slots=True)
class PortfolioService:
    """Fetches and caches positions/holdings."""

    client: KiteRESTClient

    async def positions(self) -> List[Position]:
        data = await self.client.get("/portfolio/positions")
        result: List[Position] = []
        for entries in data.get("data", {}).values():
            for entry in entries:
                product_value = entry.get("product", Product.MIS.value)
                result.append(
                    Position(
                        tradingsymbol=entry["tradingsymbol"],
                        exchange=entry["exchange"],
                        product=Product(product_value) if isinstance(product_value, str) else product_value,
                        quantity=int(entry["quantity"]),
                        average_price=float(entry["average_price"]),
                        pnl=float(entry.get("pnl", 0.0)),
                    )
                )
        return result

    async def index_by_symbol(self) -> Dict[str, Position]:
        return {f"{p.exchange}:{p.tradingsymbol}": p for p in await self.positions()}
