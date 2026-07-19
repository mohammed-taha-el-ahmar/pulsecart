"""Warehouse tier: insert / lookup / summary against DuckDB."""

from __future__ import annotations

from datetime import UTC, datetime

from pulsecart.schemas import (
    EnrichedEvent,
    Recommendation,
    SessionFeatures,
    UserFeatures,
)


def _make_enriched(event_id: str, user_id: str, trace_id: str) -> EnrichedEvent:
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
        scorer_latency_ms=3.2,
        model_version="v1",
    )


class TestDuckDBWarehouse:
    def test_insert_and_lookup(self, warehouse):
        warehouse.insert(_make_enriched("e1", "U0001", "trace-1"))
        rows = warehouse.latest_for_user("U0001")
        assert len(rows) == 1
        assert rows[0]["trace_id"] == "trace-1"
        assert rows[0]["recommendations"][0]["product_id"] == "P0007"

    def test_summary_aggregates(self, warehouse):
        warehouse.insert(_make_enriched("e1", "U0001", "t1"))
        warehouse.insert(_make_enriched("e2", "U0001", "t2"))
        warehouse.insert(_make_enriched("e3", "U0002", "t3"))
        summary = warehouse.summary()
        assert summary["n_events"] == 3
        assert summary["n_users"] == 2
        assert summary["avg_latency_ms"] > 0

    def test_upsert_replaces_by_event_id(self, warehouse):
        warehouse.insert(_make_enriched("e1", "U0001", "t1"))
        warehouse.insert(_make_enriched("e1", "U0001", "t2"))
        rows = warehouse.latest_for_user("U0001")
        assert len(rows) == 1
        assert rows[0]["trace_id"] == "t2"
