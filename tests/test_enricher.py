"""Enricher tier: session assembly, feature lookup, scorer contract, Lambda decode."""

from __future__ import annotations

import base64
import json

from pulsecart.enricher.handler import Enricher, _decode_record
from pulsecart.enricher.session_state import SessionStateStore
from pulsecart.fakes.fake_dynamodb import FakeDynamoTable
from pulsecart.fakes.fake_scorer import ScriptedFakeScorer
from pulsecart.schemas import ClickEvent, ProductFeatures


class TestSessionState:
    def test_events_in_session_grows(self, click_batch):
        store = SessionStateStore()
        for e in click_batch[:-1]:
            store.observe(e)
        features = store.features_for(click_batch[-1], product_lookup={})
        assert features.events_in_session == 3

    def test_cart_value_sums_only_add_to_cart(self, click_batch):
        store = SessionStateStore()
        for e in click_batch[:-1]:
            store.observe(e)
        products = {"P0007": ProductFeatures(product_id="P0007", category="e", price=25.0)}
        features = store.features_for(click_batch[-1], product_lookup=products)
        assert features.cart_value == 25.0
        assert features.last_category == "electronics"


class TestEnricher:
    def test_enrich_returns_top_k_recommendations(self, enricher: Enricher, sample_click):
        result = enricher.enrich(sample_click)
        assert 0 < len(result.recommendations) <= enricher.settings.scorer_top_k
        assert all(r.rank == i + 1 for i, r in enumerate(result.recommendations))

    def test_trace_id_propagates(self, enricher: Enricher, sample_click):
        result = enricher.enrich(sample_click)
        assert result.trace_id == sample_click.trace_id
        # Scorer must have been called with the same trace_id
        assert isinstance(enricher.scorer, ScriptedFakeScorer)
        assert enricher.scorer.last_request.trace_id == sample_click.trace_id

    def test_scorer_is_called_exactly_once_per_event(self, enricher: Enricher, click_batch):
        for e in click_batch:
            enricher.enrich(e)
        assert isinstance(enricher.scorer, ScriptedFakeScorer)
        assert enricher.scorer.call_count == len(click_batch)

    def test_cold_start_user_gets_default_features(self, enricher: Enricher):
        cold_user = ClickEvent(event_type="page_view", user_id="U9999", session_id="S-new")
        result = enricher.enrich(cold_user)
        assert result.user_features.lifetime_orders == 0
        assert result.user_features.tenure_days == 0

    def test_known_user_features_are_used(self, enricher: Enricher, user_table: FakeDynamoTable):
        user_table.put_item(
            {
                "user_id": "U0001",
                "tenure_days": 500,
                "lifetime_orders": 12,
                "avg_order_value": 89.5,
                "category_affinity": {"electronics": 0.9},
                "ttl": 9_999_999_999,
            }
        )
        evt = ClickEvent(
            event_type="product_view", user_id="U0001", session_id="S-1", product_id="P0007"
        )
        result = enricher.enrich(evt)
        assert result.user_features.lifetime_orders == 12
        assert result.user_features.avg_order_value == 89.5

    def test_session_features_grow_with_multiple_events(self, enricher: Enricher, click_batch):
        results = [enricher.enrich(e) for e in click_batch]
        assert results[0].session_features.events_in_session == 1
        assert results[-1].session_features.events_in_session == 3

    def test_enriched_event_serialises_and_deserialises(self, enricher: Enricher, sample_click):
        result = enricher.enrich(sample_click)
        raw = result.model_dump_json()
        # Should be pure JSON round-trippable — the shape landing in Redshift.
        parsed = json.loads(raw)
        assert parsed["trace_id"] == sample_click.trace_id
        assert isinstance(parsed["recommendations"], list)


class TestLambdaDecode:
    def test_decodes_base64_kinesis_data(self):
        payload = {
            "event_type": "page_view",
            "user_id": "U1",
            "session_id": "S1",
        }
        b64 = base64.b64encode(json.dumps(payload).encode()).decode()
        record = {"kinesis": {"data": b64, "partitionKey": "S1", "sequenceNumber": "1"}}
        evt = _decode_record(record)
        assert evt.user_id == "U1"

    def test_decodes_raw_bytes_from_fake_stream(self):
        # The FakeKinesisStream stores raw bytes, no base64. Both paths must work.
        payload = {"event_type": "page_view", "user_id": "U2", "session_id": "S2"}
        record = {
            "kinesis": {
                "data": json.dumps(payload).encode(),
                "partitionKey": "S2",
                "sequenceNumber": "1",
            }
        }
        evt = _decode_record(record)
        assert evt.user_id == "U2"
