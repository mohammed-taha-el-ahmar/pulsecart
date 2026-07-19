"""Recommender API: /summary, /recommendations/{user_id}, /recent/{user_id}."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from pulsecart.config import Settings
from pulsecart.recommender_api.app import create_app
from pulsecart.schemas import (
    EnrichedEvent,
    Recommendation,
    SessionFeatures,
    UserFeatures,
)


def _enriched(user_id: str, event_id: str, trace_id: str) -> EnrichedEvent:
    return EnrichedEvent(
        event_id=event_id,
        trace_id=trace_id,
        event_type="product_view",
        user_id=user_id,
        session_id="S-1",
        timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        product_id="P0007",
        category="electronics",
        user_features=UserFeatures(user_id=user_id),
        session_features=SessionFeatures(session_id="S-1"),
        recommendations=[
            Recommendation(product_id="P0007", score=0.9, rank=1),
            Recommendation(product_id="P0008", score=0.7, rank=2),
        ],
        scorer_latency_ms=4.2,
        model_version="test-v1",
    )


class TestRecommenderAPI:
    def _client(self, warehouse) -> TestClient:
        return TestClient(create_app(settings=Settings(mode="local"), warehouse=warehouse))

    def test_health(self, warehouse):
        r = self._client(warehouse).get("/health")
        assert r.status_code == 200

    def test_recommendations_for_missing_user_is_404(self, warehouse):
        r = self._client(warehouse).get("/recommendations/UNOBODY")
        assert r.status_code == 404

    def test_recommendations_returns_top_k(self, warehouse):
        warehouse.insert(_enriched("U0001", "e1", "trace-42"))
        r = self._client(warehouse).get("/recommendations/U0001")
        assert r.status_code == 200
        body = r.json()
        assert body["user_id"] == "U0001"
        assert body["trace_id"] == "trace-42"
        assert body["model_version"] == "test-v1"
        assert len(body["recommendations"]) == 2

    def test_recent_paginates(self, warehouse):
        for i in range(5):
            warehouse.insert(_enriched("U0001", f"e{i}", f"t{i}"))
        r = self._client(warehouse).get("/recent/U0001?limit=3")
        assert len(r.json()["events"]) == 3

    def test_summary_reflects_inserts(self, warehouse):
        warehouse.insert(_enriched("U0001", "e1", "t1"))
        warehouse.insert(_enriched("U0002", "e2", "t2"))
        summary = self._client(warehouse).get("/summary").json()
        assert summary["n_events"] == 2
        assert summary["n_users"] == 2
