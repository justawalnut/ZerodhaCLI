"""GTT orchestration."""

from __future__ import annotations

from typing import Dict, List

from ..core.models import GTTRequest
from .kite_client import KiteRESTClient


class GTTManager:
    """Wraps Kite GTT endpoints."""

    def __init__(self, client: KiteRESTClient) -> None:
        self._client = client

    async def create_gtt(self, payload: GTTRequest) -> Dict[str, str]:
        data = {
            "tradingsymbol": payload.tradingsymbol,
            "exchange": payload.exchange,
            "trigger_values": payload.trigger_values,
            "last_price": payload.last_price,
            "orders": [
                {
                    "price": leg.price,
                    "quantity": leg.quantity,
                    "order_type": leg.order_type.value,
                    "transaction_type": leg.transaction_type,
                }
                for leg in payload.orders
            ],
        }
        return await self._client.post("/gtt/triggers", data)

    async def list_gtts(self) -> List[Dict[str, str]]:
        response = await self._client.get("/gtt/triggers")
        return response.get("data", [])

    async def delete_gtt(self, trigger_id: int) -> Dict[str, str]:
        return await self._client.delete(f"/gtt/triggers/{trigger_id}")
