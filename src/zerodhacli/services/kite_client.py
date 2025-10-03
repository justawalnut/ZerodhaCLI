"""Thin wrapper around Kite Connect REST endpoints."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from ..core.config import AppConfig, KiteCredentials


class KiteRESTClient:
    """Handles authenticated requests to Kite Connect.

    The implementation keeps things minimal for now; error handling and
    pagination will be layered in alongside live API testing.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._creds: KiteCredentials = config.creds
        self._client = httpx.AsyncClient(base_url=config.root_url, timeout=10.0)
        self._lock = asyncio.Lock()

    async def _headers(self) -> Dict[str, str]:
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self._creds.api_key}:{self._creds.access_token}",
        }

    async def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            headers = await self._headers()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            response = await self._client.post(path, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def put(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with self._lock:
            headers = await self._headers()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            response = await self._client.put(path, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def delete(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        async with self._lock:
            headers = await self._headers()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            response = await self._client.delete(path, data=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        async with self._lock:
            response = await self._client.get(path, params=params, headers=await self._headers())
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
