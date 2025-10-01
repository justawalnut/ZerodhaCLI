"""Simple cooperative rate limiter scaffolding."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional


@dataclass(slots=True)
class TokenBucket:
    """Token bucket for enforcing request-per-second caps."""

    capacity: int
    refill_rate: float  # tokens per second
    tokens: float
    last_refill: float

    def consume(self, amount: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False


class AsyncRateLimiter:
    """Async-aware limiter supporting multiple windows."""

    def __init__(self, per_second: int, per_minute: Optional[int] = None) -> None:
        self._per_second_bucket = TokenBucket(per_second, per_second, per_second, time.monotonic())
        self._minute_window: Deque[float] = deque()
        self._per_minute = per_minute
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, respecting both caps."""

        while True:
            async with self._lock:
                if self._per_minute is not None:
                    now = time.monotonic()
                    while self._minute_window and now - self._minute_window[0] > 60:
                        self._minute_window.popleft()
                    if len(self._minute_window) >= self._per_minute:
                        wait_time = 60 - (now - self._minute_window[0])
                    else:
                        wait_time = 0
                else:
                    wait_time = 0

                if wait_time == 0 and self._per_second_bucket.consume():
                    if self._per_minute is not None:
                        self._minute_window.append(time.monotonic())
                    return

            await asyncio.sleep(max(wait_time, 0.05))
