"""Deterministic synthetic clickstream generator.

Used both by the local demo (Docker Compose) to feed the pipeline with
realistic-looking traffic, and by the e2e test to assert a full run end-to-end.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from pulsecart.schemas import ClickEvent, EventType

_CATEGORIES = ["electronics", "apparel", "home", "beauty", "sports"]
_DEVICES = ["desktop", "mobile", "tablet"]
_EVENT_WEIGHTS: dict[EventType, float] = {
    "page_view": 0.35,
    "product_view": 0.35,
    "search": 0.15,
    "add_to_cart": 0.10,
    "purchase": 0.05,
}


def _weighted_choice(weights: dict[str, float], rng: random.Random) -> str:
    keys = list(weights.keys())
    values = list(weights.values())
    return rng.choices(keys, weights=values, k=1)[0]


def _make_event(
    *,
    user_id: str,
    session_id: str,
    ts: datetime,
    rng: random.Random,
) -> ClickEvent:
    event_type = _weighted_choice(dict(_EVENT_WEIGHTS), rng)  # type: ignore[arg-type]
    category = rng.choice(_CATEGORIES)
    product_id = f"P{rng.randint(1, 200):04d}" if event_type != "search" else None
    return ClickEvent(
        event_type=event_type,  # type: ignore[arg-type]
        user_id=user_id,
        session_id=session_id,
        timestamp=ts,
        product_id=product_id,
        category=category if event_type != "search" else None,
        search_query=f"{category} deals" if event_type == "search" else None,
        device=rng.choice(_DEVICES),
        referrer=rng.choice([None, "google", "email", "instagram"]),
    )


def generate_events(
    *,
    n_sessions: int = 20,
    events_per_session_range: tuple[int, int] = (3, 12),
    seed: int = 42,
    start_ts: datetime | None = None,
) -> Iterator[ClickEvent]:
    """Yield ClickEvents grouped into synthetic sessions."""
    rng = random.Random(seed)
    ts = start_ts or datetime.now(UTC)
    for s in range(n_sessions):
        user_id = f"U{rng.randint(1, 500):04d}"
        session_id = f"S{s:04d}-{user_id}"
        n_events = rng.randint(*events_per_session_range)
        for _ in range(n_events):
            ts = ts + timedelta(seconds=rng.randint(1, 90))
            yield _make_event(user_id=user_id, session_id=session_id, ts=ts, rng=rng)
