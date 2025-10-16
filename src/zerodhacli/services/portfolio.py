"""Portfolio state helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from ..core.models import Position, Product
from .kite_client import KiteRESTClient


@dataclass(slots=True)
class PortfolioService:
    """Fetches and caches positions/holdings."""

    client: KiteRESTClient

    async def positions(self) -> List[Position]:
        data = await self.client.get("/portfolio/positions")
        buckets = data.get("data", {}) if isinstance(data, dict) else {}

        net_entries = []
        day_entries = []
        other_entries: List[Any] = []

        if isinstance(buckets, dict):
            net_entries = buckets.get("net") or []
            day_entries = buckets.get("day") or []
            for key, entries in buckets.items():
                if key in {"net", "day"}:
                    continue
                other_entries.append(entries)

        positions: Dict[Tuple[str, str, Product], Position] = {}

        def _safe_int(value: Any) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        def _safe_float(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        def _parse_product(value: Any) -> Product:
            if isinstance(value, Product):
                return value
            if isinstance(value, str):
                try:
                    return Product(value)
                except ValueError:
                    return Product.MIS
            return Product.MIS

        def _upsert_position(entry: dict) -> None:
            product = _parse_product(entry.get("product", Product.MIS.value))
            key = (entry.get("exchange", ""), entry.get("tradingsymbol", ""), product)

            quantity = _safe_int(entry.get("quantity", 0))
            average_price = _safe_float(entry.get("average_price", 0.0))
            pnl = _safe_float(entry.get("pnl", 0.0))
            last_price_value = entry.get("last_price")
            last_price = _safe_float(last_price_value) if last_price_value is not None else None

            position = Position(
                tradingsymbol=entry.get("tradingsymbol", ""),
                exchange=entry.get("exchange", ""),
                product=product,
                quantity=quantity,
                average_price=average_price,
                pnl=pnl,
                last_price=last_price,
            )

            existing = positions.get(key)
            if existing is None:
                positions[key] = position
                return

            if existing.quantity == 0 and quantity != 0:
                positions[key] = position
                return

            if existing.last_price is None and last_price is not None:
                existing.last_price = last_price

            if existing.pnl == 0.0 and pnl != 0.0:
                existing.pnl = pnl

        for entry in net_entries:
            if entry:
                _upsert_position(entry)

        for entries in other_entries:
            for entry in entries or []:
                if entry:
                    _upsert_position(entry)

        for entry in day_entries:
            if not entry:
                continue

            product = _parse_product(entry.get("product", Product.MIS.value))
            key = (entry.get("exchange", ""), entry.get("tradingsymbol", ""), product)

            day_quantity = _safe_int(entry.get("quantity", 0))
            day_average_price = _safe_float(entry.get("average_price", 0.0))
            day_pnl = _safe_float(entry.get("pnl", 0.0))
            last_price_value = entry.get("last_price")
            last_price = _safe_float(last_price_value) if last_price_value is not None else None

            position = positions.get(key)
            if position is None:
                position = Position(
                    tradingsymbol=entry.get("tradingsymbol", ""),
                    exchange=entry.get("exchange", ""),
                    product=product,
                    quantity=day_quantity,
                    average_price=day_average_price,
                    pnl=day_pnl,
                    last_price=last_price,
                )
                positions[key] = position
            else:
                if position.last_price is None and last_price is not None:
                    position.last_price = last_price

            position.day_quantity = day_quantity
            position.day_average_price = day_average_price
            position.day_pnl = day_pnl

        return list(positions.values())

    async def index_by_symbol(self) -> Dict[str, Position]:
        return {f"{p.exchange}:{p.tradingsymbol}": p for p in await self.positions()}
