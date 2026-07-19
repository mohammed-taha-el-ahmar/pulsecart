"""Boundary schemas. Every stage of the pipeline speaks Pydantic on the wire.

The ClickEvent → Enrichment → EnrichedEvent contract is the fixed protocol; the
underlying Kinesis / DynamoDB / SageMaker implementations can be swapped out
(real vs. fake) without touching any producer or consumer code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal["page_view", "product_view", "add_to_cart", "purchase", "search"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex


class ClickEvent(BaseModel):
    """Raw clickstream event as emitted by the producer."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(default_factory=_new_id)
    trace_id: str = Field(default_factory=_new_id)
    event_type: EventType
    user_id: str
    session_id: str
    timestamp: datetime = Field(default_factory=_utcnow)
    product_id: str | None = None
    category: str | None = None
    search_query: str | None = None
    device: str = "desktop"
    referrer: str | None = None


class UserFeatures(BaseModel):
    """User features cached in DynamoDB."""

    user_id: str
    tenure_days: int = 0
    lifetime_orders: int = 0
    avg_order_value: float = 0.0
    category_affinity: dict[str, float] = Field(default_factory=dict)
    last_seen: datetime | None = None


class ProductFeatures(BaseModel):
    """Product features cached in DynamoDB."""

    product_id: str
    category: str
    price: float
    popularity_score: float = 0.0
    avg_rating: float = 0.0
    days_since_launch: int = 0


class SessionFeatures(BaseModel):
    """Features assembled on the stream from the current session's event window."""

    session_id: str
    session_length_seconds: int = 0
    events_in_session: int = 1
    cart_value: float = 0.0
    last_category: str | None = None


class Recommendation(BaseModel):
    """A single ranked product recommendation."""

    product_id: str
    score: float
    rank: int


class ScoreRequest(BaseModel):
    """Sent to the Scorer (SageMaker endpoint or a fake)."""

    trace_id: str
    user_id: str
    session_id: str
    user_features: UserFeatures
    session_features: SessionFeatures
    candidate_products: list[ProductFeatures]
    top_k: int = 5


class ScoreResponse(BaseModel):
    """Returned by the Scorer."""

    trace_id: str
    recommendations: list[Recommendation]
    latency_ms: float
    model_version: str = "v1"


class EnrichedEvent(BaseModel):
    """Output of the enricher: raw event + all context + top-K recommendations.

    This is the row landing in Redshift via streaming ingestion.
    """

    event_id: str
    trace_id: str
    event_type: EventType
    user_id: str
    session_id: str
    timestamp: datetime
    product_id: str | None
    category: str | None
    user_features: UserFeatures
    session_features: SessionFeatures
    recommendations: list[Recommendation]
    scored_at: datetime = Field(default_factory=_utcnow)
    scorer_latency_ms: float
    model_version: str
