"""Session-feature assembly.

Accumulates the current session's event history in memory so features like
cart_value, events_in_session, and session_length_seconds can be sent to the
scorer alongside the current event.

In production this would live in ElastiCache or DynamoDB; for the Lambda
demo it's in-process (fine for a batch of Kinesis records handled by one
invocation).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from pulsecart.schemas import ClickEvent, ProductFeatures, SessionFeatures


@dataclass
class SessionStateStore:
    """In-memory session state keyed by session_id."""

    _events: dict[str, list[ClickEvent]] = field(default_factory=lambda: defaultdict(list))

    def observe(self, event: ClickEvent) -> None:
        self._events[event.session_id].append(event)

    def features_for(
        self,
        event: ClickEvent,
        product_lookup: dict[str, ProductFeatures],
    ) -> SessionFeatures:
        history = self._events.get(event.session_id, []) + [event]
        cart_value = 0.0
        last_category: str | None = None
        for e in history:
            if e.category:
                last_category = e.category
            if e.event_type == "add_to_cart" and e.product_id in product_lookup:
                cart_value += product_lookup[e.product_id].price
        session_len = _session_length(history)
        return SessionFeatures(
            session_id=event.session_id,
            session_length_seconds=session_len,
            events_in_session=len(history),
            cart_value=round(cart_value, 2),
            last_category=last_category,
        )


def _session_length(history: list[ClickEvent]) -> int:
    if not history:
        return 0
    times: list[datetime] = [e.timestamp for e in history]
    return int((max(times) - min(times)).total_seconds())
