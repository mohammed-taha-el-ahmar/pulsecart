"""Contract tests. If these fail, the wire format between stages has drifted."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pulsecart.schemas import (
    ClickEvent,
    EnrichedEvent,
    Recommendation,
    ScoreRequest,
    ScoreResponse,
    SessionFeatures,
    UserFeatures,
)


def test_click_event_defaults_are_populated():
    evt = ClickEvent(event_type="page_view", user_id="U1", session_id="S1")
    assert evt.event_id
    assert evt.trace_id
    assert evt.timestamp.tzinfo is not None


def test_click_event_rejects_unknown_event_type():
    with pytest.raises(ValidationError):
        ClickEvent(event_type="banana", user_id="U1", session_id="S1")  # type: ignore[arg-type]


def test_click_event_roundtrips_through_json():
    evt = ClickEvent(
        event_type="product_view",
        user_id="U1",
        session_id="S1",
        product_id="P0001",
        category="electronics",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    dumped = evt.model_dump_json()
    back = ClickEvent.model_validate_json(dumped)
    assert back == evt


def test_score_request_carries_trace_id():
    req = ScoreRequest(
        trace_id="abc",
        user_id="U1",
        session_id="S1",
        user_features=UserFeatures(user_id="U1"),
        session_features=SessionFeatures(session_id="S1"),
        candidate_products=[],
    )
    assert req.trace_id == "abc"
    assert req.top_k == 5


def test_score_response_recommendations_are_ranked_ints():
    resp = ScoreResponse(
        trace_id="abc",
        recommendations=[
            Recommendation(product_id="P0001", score=0.9, rank=1),
            Recommendation(product_id="P0002", score=0.8, rank=2),
        ],
        latency_ms=1.2,
    )
    assert resp.recommendations[0].rank == 1


def test_enriched_event_is_json_serialisable():
    enriched = EnrichedEvent(
        event_id="e1",
        trace_id="t1",
        event_type="product_view",
        user_id="U1",
        session_id="S1",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        product_id="P0001",
        category="electronics",
        user_features=UserFeatures(user_id="U1"),
        session_features=SessionFeatures(session_id="S1"),
        recommendations=[Recommendation(product_id="P0001", score=0.9, rank=1)],
        scorer_latency_ms=1.0,
        model_version="v1",
    )
    payload = json.loads(enriched.model_dump_json())
    assert payload["trace_id"] == "t1"
    assert payload["recommendations"][0]["product_id"] == "P0001"
