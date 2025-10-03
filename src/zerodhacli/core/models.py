"""Common domain models for ZerodhaCLI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class Product(str, Enum):
    CNC = "CNC"
    MIS = "MIS"
    NRML = "NRML"
    MTF = "MTF"


class Variety(str, Enum):
    REGULAR = "regular"
    AMO = "amo"
    CO = "co"
    ICEBERG = "iceberg"
    AUCTION = "auction"


class Validity(str, Enum):
    DAY = "DAY"
    IOC = "IOC"
    TTL = "TTL"


@dataclass(slots=True)
class OrderRequest:
    """User-friendly representation of an order request."""

    tradingsymbol: str
    exchange: str
    transaction_type: str
    quantity: int
    order_type: OrderType
    product: Product
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    validity: Validity = Validity.DAY
    variety: Variety = Variety.REGULAR
    disclosed_quantity: int = 0
    tag: Optional[str] = None
    market_protection: Optional[float] = None
    autoslice: Optional[bool] = None
    metadata: Optional[Dict[str, str]] = None


@dataclass(slots=True)
class OrderResponse:
    """Represents an order placement acknowledgement from Kite."""

    order_id: str
    status: str
    request_id: Optional[str] = None
    info: Optional[Dict[str, str]] = None


@dataclass(slots=True)
class OrderSummary:
    """Simplified open-order view used for cancel filtering."""

    order_id: str
    status: str
    tradingsymbol: str
    transaction_type: str
    exchange: str
    quantity: int
    price: Optional[float]
    average_price: Optional[float]
    order_timestamp: datetime
    variety: Variety
    product: Product


@dataclass(slots=True)
class Position:
    """Current position snapshot."""

    tradingsymbol: str
    exchange: str
    product: Product
    quantity: int
    average_price: float
    pnl: float
    last_price: Optional[float] = None


@dataclass(slots=True)
class GTTLeg:
    """Describes one leg of a GTT order."""

    price: float
    quantity: int
    order_type: OrderType
    transaction_type: str


@dataclass(slots=True)
class GTTRequest:
    """Represents a GTT instruction."""

    tradingsymbol: str
    exchange: str
    trigger_values: List[float]
    last_price: Optional[float]
    orders: List[GTTLeg]


@dataclass(slots=True)
class RateLimitBudget:
    """Tracks a per-endpoint rate limit window."""

    capacity: int
    remaining: int
    reset_at: datetime
