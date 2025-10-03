"""SQLite-backed shadow index for order metadata."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

from ..core.config import STATE_DB


@dataclass(slots=True)
class OrderMetadata:
    """Metadata captured for each acknowledged order."""

    order_id: str
    role: Optional[str] = None
    group: Optional[str] = None
    strategy_id: Optional[str] = None
    protected: bool = False
    symbol: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def age_seconds(self) -> Optional[float]:
        if self.created_at is None:
            return None
        now = datetime.now(timezone.utc)
        reference = self.created_at if self.created_at.tzinfo else self.created_at.replace(tzinfo=timezone.utc)
        return (now - reference).total_seconds()


class OrderIndex:
    """Persist metadata for orders to enable predicate cancels."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = str(path or STATE_DB)
        self._connection = sqlite3.connect(self._path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
        self._connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS order_index (
                    order_id TEXT PRIMARY KEY,
                    role TEXT,
                    group_id TEXT,
                    strategy_id TEXT,
                    protected INTEGER NOT NULL DEFAULT 0,
                    symbol TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )

    def close(self) -> None:
        self._connection.close()

    def record(
        self,
        order_id: str,
        *,
        role: Optional[str] = None,
        group: Optional[str] = None,
        strategy_id: Optional[str] = None,
        protected: bool = False,
        symbol: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        timestamp = (created_at or datetime.now(timezone.utc)).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO order_index (order_id, role, group_id, strategy_id, protected, symbol, created_at)
                VALUES (:order_id, :role, :group_id, :strategy_id, :protected, :symbol, :created_at)
                ON CONFLICT(order_id) DO UPDATE SET
                    role=excluded.role,
                    group_id=excluded.group_id,
                    strategy_id=excluded.strategy_id,
                    protected=excluded.protected,
                    symbol=excluded.symbol,
                    created_at=excluded.created_at
                """,
                {
                    "order_id": order_id,
                    "role": role,
                    "group_id": group,
                    "strategy_id": strategy_id,
                    "protected": 1 if protected else 0,
                    "symbol": symbol,
                    "created_at": timestamp,
                },
            )

    def bulk_fetch(self, order_ids: Iterable[str]) -> Dict[str, OrderMetadata]:
        ids = list(order_ids)
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        cursor = self._connection.execute(
            f"SELECT * FROM order_index WHERE order_id IN ({placeholders})",
            ids,
        )
        mapping: Dict[str, OrderMetadata] = {}
        for row in cursor.fetchall():
            created_at_raw = row["created_at"]
            created_at = None
            if isinstance(created_at_raw, datetime):
                created_at = created_at_raw
            elif isinstance(created_at_raw, str):
                try:
                    created_at = datetime.fromisoformat(created_at_raw)
                except ValueError:
                    created_at = None
            mapping[row["order_id"]] = OrderMetadata(
                order_id=row["order_id"],
                role=row["role"],
                group=row["group_id"],
                strategy_id=row["strategy_id"],
                protected=bool(row["protected"]),
                symbol=row["symbol"],
                created_at=created_at,
            )
        return mapping

    def purge(self, order_ids: Iterable[str]) -> None:
        ids = list(order_ids)
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self._connection:
            self._connection.execute(
                f"DELETE FROM order_index WHERE order_id IN ({placeholders})",
                ids,
            )


__all__ = ["OrderIndex", "OrderMetadata"]
