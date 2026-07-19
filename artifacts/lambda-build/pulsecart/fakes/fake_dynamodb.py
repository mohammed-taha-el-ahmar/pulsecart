"""In-memory DynamoDB stand-in with TTL semantics.

Real DynamoDB deletes expired items lazily; here we enforce TTL on every read
so tests can pin behaviour with a fixed clock.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeDynamoTable:
    """Behaves like a single DynamoDB table with a single-attribute partition key + TTL."""

    name: str
    partition_key: str = "id"
    ttl_attribute: str = "ttl"
    _items: dict[str, dict[str, Any]] = field(default_factory=dict)
    _clock: float | None = None  # None ⇒ use real time; tests can pin this.

    def _now(self) -> float:
        return self._clock if self._clock is not None else time.time()

    def put_item(self, item: dict[str, Any]) -> None:
        pk_value = item[self.partition_key]
        self._items[pk_value] = dict(item)

    def get_item(self, key: str) -> dict[str, Any] | None:
        item = self._items.get(key)
        if item is None:
            return None
        ttl = item.get(self.ttl_attribute)
        if ttl is not None and ttl <= self._now():
            del self._items[key]
            return None
        return dict(item)

    def batch_get(self, keys: list[str]) -> dict[str, dict[str, Any]]:
        return {k: v for k in keys if (v := self.get_item(k)) is not None}

    def set_clock(self, epoch_seconds: float) -> None:
        self._clock = epoch_seconds

    def advance_clock(self, seconds: float) -> None:
        self._clock = self._now() + seconds

    def __len__(self) -> int:
        # Realistic count: purge expired first.
        now = self._now()
        expired = [k for k, v in self._items.items() if (v.get(self.ttl_attribute) or 0) <= now]
        for k in expired:
            del self._items[k]
        return len(self._items)
