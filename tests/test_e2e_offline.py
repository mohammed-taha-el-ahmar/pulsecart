"""End-to-end offline integration test.

Exercises the full producer → enricher → warehouse → API path without any AWS
credentials. This is the "offline-first CI" contract the DEMO.md coverage
matrix claims — if this test passes, the whole pipeline works in a laptop or
GitHub Actions runner.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pulsecart.config import Settings
from pulsecart.enricher.handler import Enricher, build_local_enricher
from pulsecart.fakes.fake_dynamodb import FakeDynamoTable
from pulsecart.fakes.fake_scorer import ScriptedFakeScorer
from pulsecart.producer.simulator import generate_events
from pulsecart.recommender_api.app import create_app
from pulsecart.warehouse.warehouse import DuckDBWarehouse


def test_full_pipeline_end_to_end(tmp_path):
    # -- Arrange: fake infra
    settings = Settings(mode="local", duckdb_path=str(tmp_path / "e2e.duckdb"))
    user_table = FakeDynamoTable("users", partition_key="user_id")
    product_table = FakeDynamoTable("products", partition_key="product_id")
    for i in range(1, 21):
        product_table.put_item(
            {
                "product_id": f"P{i:04d}",
                "category": "electronics",
                "price": 10.0 + i,
                "popularity_score": 1.0 - i * 0.03,
                "avg_rating": 4.0,
                "days_since_launch": 30 + i,
                "ttl": 9_999_999_999,
            }
        )
    scorer = ScriptedFakeScorer()
    enricher: Enricher = build_local_enricher(settings, scorer, user_table, product_table)
    warehouse = DuckDBWarehouse(settings.duckdb_path)

    # -- Act: run a small synthetic clickstream through the enricher
    trace_ids_seen: set[str] = set()
    n_events = 0
    for event in generate_events(n_sessions=5, seed=99):
        trace_ids_seen.add(event.trace_id)
        enriched = enricher.enrich(event)
        warehouse.insert(enriched)
        n_events += 1

    # -- Assert: (a) everything landed, (b) trace_ids match, (c) API surfaces recs
    assert n_events > 0
    assert scorer.call_count == n_events
    summary = warehouse.summary()
    assert summary["n_events"] == n_events
    assert summary["n_sessions"] == 5

    # Any user with events should be queryable via the API
    a_user_row = warehouse._con.execute(
        "SELECT user_id, trace_id FROM raw.enriched_events LIMIT 1"
    ).fetchone()
    assert a_user_row is not None
    user_id, trace_id_from_wh = a_user_row
    assert trace_id_from_wh in trace_ids_seen  # traceability preserved

    client = TestClient(create_app(settings=settings, warehouse=warehouse))
    r = client.get(f"/recommendations/{user_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == user_id
    assert len(body["recommendations"]) > 0
    # And the trace_id on the API response walks back to a real click event
    assert body["trace_id"] in trace_ids_seen
