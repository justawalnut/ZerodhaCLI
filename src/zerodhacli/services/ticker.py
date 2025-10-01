"""WebSocket ticker management."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Awaitable, Callable, Dict, Optional

import websockets

from ..core.config import AppConfig
from .kite_client import KiteRESTClient


class TickerService:
    """Manages Kite Ticker subscriptions."""

    def __init__(self, config: AppConfig, client: KiteRESTClient) -> None:
        self._config = config
        self._client = client
        self._connection: Optional[websockets.WebSocketClientProtocol] = None
        self._listen_task: Optional[asyncio.Task[None]] = None
        self._callbacks: Dict[str, Callable[[Any], Awaitable[None]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._connection is not None:
            return
        if not (self._config.creds.api_key and self._config.creds.access_token):
            return
        url = "wss://ws.kite.trade/?api_key={api_key}&access_token={token}".format(
            api_key=self._config.creds.api_key,
            token=self._config.creds.access_token,
        )
        self._connection = await websockets.connect(url)
        self._listen_task = asyncio.create_task(self._listener())

    async def _listener(self) -> None:
        assert self._connection is not None
        try:
            async for message in self._connection:
                callbacks = list(self._callbacks.values())
                for callback in callbacks:
                    await callback(message)
        except asyncio.CancelledError:  # pragma: no cover - shutdown path
            pass

    async def subscribe(self, key: str, callback: Callable[[Any], Awaitable[None]]) -> None:
        async with self._lock:
            self._callbacks[key] = callback
        await self.connect()

    async def unsubscribe(self, key: str) -> None:
        async with self._lock:
            self._callbacks.pop(key, None)

    async def aclose(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task
        if self._connection:
            await self._connection.close()
        self._connection = None
        self._listen_task = None
        self._callbacks.clear()
