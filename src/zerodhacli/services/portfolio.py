"""Portfolio state helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..core.models import Position, Product
from .kite_client import KiteRESTClient


@dataclass(slots=True)
class PortfolioService:
    """Fetches and caches positions/holdings."""

    client: KiteRESTClient

    async def positions(self) -> List[Position]:
        data = await self.client.get("/portfolio/positions")
        buckets = data.get("data", {}) if isinstance(data, dict) else {}

        ordered_buckets = []
        if isinstance(buckets, dict):
            if "net" in buckets:
                ordered_buckets.append(buckets["net"])
            if "day" in buckets:
                ordered_buckets.append(buckets["day"])
            for key, entries in buckets.items():
                if key in {"net", "day"}:
                    continue
                ordered_buckets.append(entries)

        positions: Dict[Tuple[str, str, Product], Position] = {}

        for entries in ordered_buckets:
            for entry in entries or []:
                product_value = entry.get("product", Product.MIS.value)
                product = Product(product_value) if isinstance(product_value, str) else product_value
                key = (entry.get("exchange", ""), entry.get("tradingsymbol", ""), product)

                quantity = int(entry.get("quantity", 0))
                average_price = float(entry.get("average_price", 0.0))
                pnl = float(entry.get("pnl", 0.0))
                last_price = entry.get("last_price")
                position = Position(
                    tradingsymbol=entry.get("tradingsymbol", ""),
                    exchange=entry.get("exchange", ""),
                    product=product,
                    quantity=quantity,
                    average_price=average_price,
                    pnl=pnl,
                    last_price=float(last_price) if last_price is not None else None,
                )

                existing = positions.get(key)
                if existing is None:
                    positions[key] = position
                    continue
                if existing.quantity == 0 and quantity != 0:
                    positions[key] = position

        return list(positions.values())

    async def index_by_symbol(self) -> Dict[str, Position]:
        return {f"{p.exchange}:{p.tradingsymbol}": p for p in await self.positions()}
