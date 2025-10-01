"""Service container for dependency wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..core.config import AppConfig
from .kite_client import KiteRESTClient
from .order_router import OrderRouter
from .portfolio import PortfolioService
from .gtt_manager import GTTManager
from .ticker import TickerService


@dataclass(slots=True)
class ServiceContainer:
    """Aggregates all runtime services for the CLI."""

    config: AppConfig
    client: KiteRESTClient
    orders: OrderRouter
    portfolio: PortfolioService
    gtt: GTTManager
    ticker: TickerService

    @classmethod
    def build(cls, config: Optional[AppConfig] = None) -> "ServiceContainer":
        cfg = config or AppConfig.load()
        client = KiteRESTClient(cfg)
        portfolio = PortfolioService(client)
        orders = OrderRouter(cfg, client, portfolio)
        gtt = GTTManager(client)
        ticker = TickerService(cfg, client)
        return cls(config=cfg, client=client, orders=orders, portfolio=portfolio, gtt=gtt, ticker=ticker)

    async def bootstrap(self) -> None:
        """Start background services required for interactive usage."""

        if self.config.dry_run:
            return
        if not (self.config.creds.api_key and self.config.creds.access_token):
            return
        await self.ticker.connect()

    async def aclose(self) -> None:
        """Close any underlying resources."""

        await self.client.aclose()
        await self.ticker.aclose()
