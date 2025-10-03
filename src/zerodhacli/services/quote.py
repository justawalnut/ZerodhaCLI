"""Quote utilities for retrieving last traded prices."""

from __future__ import annotations

from typing import Dict, Iterable

from ..core.models import Position
from .kite_client import KiteRESTClient


class QuoteService:
    """Fetches latest prices via the Kite REST API."""

    def __init__(self, client: KiteRESTClient) -> None:
        self._client = client

    async def ltp(self, instruments: Iterable[str]) -> Dict[str, float]:
        """Return last traded price for each instrument key ("EXCHANGE:SYMBOL")."""

        keys = list(dict.fromkeys(instruments))
        if not keys:
            return {}
        params = [("i", key) for key in keys]
        payload = await self._client.get("/quote/ltp", params=params)
        data = payload.get("data", {})
        result: Dict[str, float] = {}
        for key in keys:
            item = data.get(key)
            if not item:
                continue
            price = item.get("last_price")
            if price is None:
                continue
            result[key] = float(price)
        return result

    async def enrich_positions(self, positions: Iterable[Position]) -> None:
        """Attach last_price to positions lacking it."""

        missing = [f"{p.exchange}:{p.tradingsymbol}" for p in positions if p.last_price is None]
        mapping = await self.ltp(missing)
        for position in positions:
            key = f"{position.exchange}:{position.tradingsymbol}"
            if position.last_price is None and key in mapping:
                position.last_price = mapping[key]
