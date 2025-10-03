"""High-level order orchestration."""

from __future__ import annotations

import asyncio
import itertools
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, List, Optional, Sequence, Tuple
import json

from ..core.config import AppConfig
from ..core.models import OrderRequest, OrderResponse, OrderSummary, OrderType, Position, Product, Variety
from ..core.rate_limit import AsyncRateLimiter
from .kite_client import KiteRESTClient
from .portfolio import PortfolioService


@dataclass(slots=True)
class _DryOrderRecord:
    request: OrderRequest
    created_at: datetime
    status: str = "OPEN"
    average_price: Optional[float] = None


@dataclass(slots=True)
class ExecutionRecord:
    """Captures a single order placement acknowledgement."""

    request: OrderRequest
    response: OrderResponse
    timestamp: datetime


@dataclass(slots=True)
class _SimPosition:
    """Lightweight accumulator for dry-run position state."""

    tradingsymbol: str
    exchange: str
    product: Product
    quantity: int = 0
    average_price: float = 0.0
    mark_price: Optional[float] = None

    def to_position(self) -> Position:
        return Position(
            tradingsymbol=self.tradingsymbol,
            exchange=self.exchange,
            product=self.product,
            quantity=self.quantity,
            average_price=self.average_price,
            pnl=0.0,
            last_price=self.mark_price,
        )


class OrderRouter:
    """Places and manages orders while respecting config and rate limits."""

    def __init__(self, config: AppConfig, client: KiteRESTClient, portfolio: PortfolioService) -> None:
        self._config = config
        self._client = client
        self._portfolio = portfolio
        self._rate_limiter = AsyncRateLimiter(per_second=10, per_minute=200)
        self._dry_orders: dict[str, _DryOrderRecord] = {}
        self._history: list[ExecutionRecord] = []
        self._sim_positions: dict[str, _SimPosition] = {}

    async def _throttle(self) -> None:
        if not self._config.dry_run:
            await self._rate_limiter.acquire()

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        """Place a new order via Kite REST."""

        await self._throttle()
        if self._config.dry_run:
            order_id = f"DRY-{uuid.uuid4().hex[:12]}"
            record = _DryOrderRecord(request=order, created_at=datetime.utcnow())
            self._dry_orders[order_id] = record
            response = OrderResponse(order_id=order_id, status="dry-run")
            self._record_execution(order, response)
            self._update_sim_position(order)
            return response
        payload = self._serialize(asdict(order))
        data = await self._client.post("/orders/regular", payload)
        response = OrderResponse(order_id=data.get("data", {}).get("order_id", ""), status=data.get("status", ""))
        self._record_execution(order, response)
        return response

    async def modify_order(self, order_id: str, updates: dict) -> OrderResponse:
        await self._throttle()
        if self._config.dry_run:
            record = self._dry_orders.get(order_id)
            if record is None:
                raise ValueError(f"Order {order_id} not found in dry-run book")
            for key, value in updates.items():
                if hasattr(record.request, key):
                    setattr(record.request, key, value)
            return OrderResponse(order_id=order_id, status="dry-run")
        data = await self._client.put(f"/orders/regular/{order_id}", self._serialize(updates))
        return OrderResponse(order_id=order_id, status=data.get("status", ""))

    async def cancel_orders(self, order_ids: Iterable[str]) -> List[OrderResponse]:
        responses: List[OrderResponse] = []
        for order_id in order_ids:
            await self._throttle()
            if self._config.dry_run:
                if order_id in self._dry_orders:
                    self._dry_orders[order_id].status = "CANCELLED"
                    del self._dry_orders[order_id]
                responses.append(OrderResponse(order_id=order_id, status="dry-run"))
                continue
            data = await self._client.delete(f"/orders/regular/{order_id}")
            responses.append(OrderResponse(order_id=order_id, status=data.get("status", "")))
        return responses

    def recent_history(self, limit: int = 10) -> List[ExecutionRecord]:
        """Return the most recent execution records captured locally."""

        if limit <= 0:
            return []
        return list(self._history[-limit:])

    def simulated_positions(self) -> List[Position]:
        """Project current positions using dry-run executions."""

        return [snapshot.to_position() for snapshot in self._sim_positions.values()]

    async def close_position(self, position: Position, side: Optional[str] = None) -> OrderResponse:
        """Flatten the provided position."""

        quantity = abs(position.quantity)
        if quantity == 0:
            raise ValueError("Position already flat")
        direction = side.upper() if side else ("BUY" if position.quantity < 0 else "SELL")
        order = OrderRequest(
            tradingsymbol=position.tradingsymbol,
            exchange=position.exchange,
            transaction_type=direction,
            quantity=quantity,
            order_type=OrderType.MARKET,
            product=position.product,
            market_protection=self._config.market_protection,
            autoslice=self._config.autoslice or None,
        )
        return await self.place_order(order)

    async def scale_order(self, template: OrderRequest, count: int, start_price: float, end_price: float) -> List[OrderResponse]:
        """Dispatch ladder of limit orders between price bounds."""

        if count <= 0:
            return []
        step = (end_price - start_price) / max(count - 1, 1)
        responses: List[OrderResponse] = []
        for index in range(count):
            price = round(start_price + step * index, 2)
            ladder_payload = {**asdict(template), "price": price}
            ladder_order = OrderRequest(**ladder_payload)
            responses.append(await self.place_order(ladder_order))
            await asyncio.sleep(0.2)  # coarse pacing; refine with ticker feedback
        return responses

    async def chase_order(
        self,
        order: OrderRequest,
        order_id_hint: Optional[str] = None,
        *,
        max_moves: int = 20,
        tick_size: float = 0.05,
        target_price: Optional[float] = None,
        interval: float = 0.5,
    ) -> OrderResponse:
        """Start a chase loop adjusting limit price towards a target."""

        if order.order_type != OrderType.LIMIT:
            raise ValueError("Chase requires an initial LIMIT order")
        if order.price is None:
            raise ValueError("Chase requires a starting limit price")

        response = await self.place_order(order)
        order_id = order_id_hint or response.order_id
        if self._config.dry_run:
            return response

        current_price = order.price
        side = order.transaction_type.upper()
        for _ in itertools.islice(range(max_moves), max_moves):
            if target_price is not None:
                if side == "BUY" and current_price >= target_price:
                    break
                if side == "SELL" and current_price <= target_price:
                    break
            new_price = current_price + tick_size if side == "BUY" else current_price - tick_size
            if target_price is not None:
                if side == "BUY":
                    new_price = min(new_price, target_price)
                else:
                    new_price = max(new_price, target_price)
            await self.modify_order(order_id, {"price": round(new_price, 2)})
            current_price = new_price
            await asyncio.sleep(interval)
        return response

    async def swarm(self, orders: Sequence[OrderRequest], delay: float = 0.1) -> List[OrderResponse]:
        responses: List[OrderResponse] = []
        for order in orders:
            responses.append(await self.place_order(order))
            await asyncio.sleep(delay)
        return responses

    async def list_open_orders(self) -> List[OrderSummary]:
        """Return currently open orders for filtering/cancellation."""

        if self._config.dry_run:
            summaries: List[OrderSummary] = []
            for order_id, record in self._dry_orders.items():
                summaries.append(
                    OrderSummary(
                        order_id=order_id,
                        status=record.status,
                        tradingsymbol=record.request.tradingsymbol,
                        transaction_type=record.request.transaction_type,
                        exchange=record.request.exchange,
                        quantity=record.request.quantity,
                        price=record.request.price,
                        average_price=record.average_price,
                        order_timestamp=record.created_at,
                        variety=record.request.variety,
                        product=record.request.product,
                    )
                )
            return summaries

        payload = await self._client.get("/orders")
        summaries = []
        for entry in payload.get("data", []):
            if entry.get("status") not in {"OPEN", "TRIGGER PENDING"}:
                continue
            variety_raw = entry.get("variety", Variety.REGULAR.value)
            product_raw = entry.get("product", Product.MIS.value)
            summaries.append(
                OrderSummary(
                    order_id=entry["order_id"],
                    status=entry["status"],
                    tradingsymbol=entry["tradingsymbol"],
                    transaction_type=entry["transaction_type"],
                    exchange=entry["exchange"],
                    quantity=int(entry["quantity"]),
                    price=float(entry["price"]) if entry.get("price") else None,
                    average_price=float(entry["average_price"]) if entry.get("average_price") else None,
                    order_timestamp=self._parse_timestamp(entry.get("order_timestamp")),
                    variety=Variety(variety_raw) if isinstance(variety_raw, str) else variety_raw,
                    product=Product(product_raw) if isinstance(product_raw, str) else product_raw,
                )
            )
        return summaries

    async def filter_orders(
        self,
        *,
        side: Optional[str] = None,
        count: Optional[int] = None,
        latest: bool = False,
    ) -> List[OrderSummary]:
        """Filter open orders by side and recency."""

        if count is not None and count <= 0:
            return []
        orders = await self.list_open_orders()
        if side:
            orders = [o for o in orders if o.transaction_type.upper() == side.upper()]
        orders.sort(key=lambda item: item.order_timestamp)
        if latest:
            orders = list(reversed(orders))
        if count is not None:
            orders = orders[:count]
        if latest:
            orders = list(reversed(orders))
        return orders

    @staticmethod
    def _parse_timestamp(raw: Optional[str]) -> datetime:
        if not raw:
            return datetime.utcnow()
        try:
            if raw.endswith("Z"):
                raw = raw[:-1]
            return datetime.fromisoformat(raw)
        except ValueError:
            for layout in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    return datetime.strptime(raw, layout)
                except ValueError:
                    continue
        return datetime.utcnow()

    def _record_execution(self, order: OrderRequest, response: OrderResponse) -> None:
        entry = ExecutionRecord(request=order, response=response, timestamp=datetime.utcnow())
        self._history.append(entry)
        if len(self._history) > 500:
            self._history.pop(0)

    def _update_sim_position(self, order: OrderRequest) -> None:
        key = f"{order.exchange}:{order.tradingsymbol}"
        current = self._sim_positions.get(
            key,
            _SimPosition(tradingsymbol=order.tradingsymbol, exchange=order.exchange, product=order.product),
        )

        price = order.price
        side = order.transaction_type.upper()
        qty = order.quantity

        new_qty, new_avg = self._apply_trade(current.quantity, current.average_price, side, qty, price)

        if new_qty == 0:
            if key in self._sim_positions:
                del self._sim_positions[key]
            return

        current.quantity = new_qty
        if price is not None or current.average_price == 0.0:
            current.average_price = new_avg
        if price is not None:
            current.mark_price = price
        current.product = order.product
        self._sim_positions[key] = current

    @staticmethod
    def _apply_trade(
        current_qty: int,
        current_avg: float,
        side: str,
        qty: int,
        price: Optional[float],
    ) -> Tuple[int, float]:
        """Update a running position based on a simulated fill."""

        if qty <= 0:
            return current_qty, current_avg

        trade_sign = 1 if side == "BUY" else -1
        trade_value = price if price is not None else current_avg
        new_qty = current_qty + trade_sign * qty

        if current_qty == 0:
            return new_qty, trade_value

        if (current_qty > 0 and trade_sign > 0) or (current_qty < 0 and trade_sign < 0):
            # Increasing exposure in the same direction -> weighted average
            if trade_value == 0.0:
                return new_qty, current_avg
            weighted = (abs(current_qty) * current_avg) + (qty * trade_value)
            return new_qty, weighted / abs(new_qty)

        # Reducing existing exposure or reversing direction
        if abs(qty) < abs(current_qty):
            return new_qty, current_avg
        if abs(qty) == abs(current_qty):
            return 0, 0.0
        # Reversal: leftover position adopts the trade price
        remainder = abs(qty) - abs(current_qty)
        residual_qty = trade_sign * remainder
        return residual_qty, trade_value

    @staticmethod
    def _serialize(payload: dict[str, Any]) -> dict[str, Any]:
        wire: dict[str, Any] = {}
        for key, value in payload.items():
            if value is None:
                continue
            wire[key] = OrderRouter._to_wire(value)
        return wire

    @staticmethod
    def _to_wire(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, dict):
            return json.dumps({k: OrderRouter._to_wire(v) for k, v in value.items() if v is not None})
        if isinstance(value, list):
            return json.dumps([OrderRouter._to_wire(item) for item in value])
        return value
