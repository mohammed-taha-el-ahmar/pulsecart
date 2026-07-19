"""Verify the fakes actually behave like their AWS counterparts on the paths we rely on."""

from __future__ import annotations

from pulsecart.fakes.fake_dynamodb import FakeDynamoTable
from pulsecart.fakes.fake_kinesis import FakeKinesisStream
from pulsecart.fakes.fake_scorer import ScriptedFakeScorer
from pulsecart.schemas import (
    ProductFeatures,
    ScoreRequest,
    SessionFeatures,
    UserFeatures,
)


class TestFakeKinesisStream:
    def test_put_json_preserves_partition_key_ordering(self):
        stream = FakeKinesisStream()
        for i in range(5):
            stream.put_json("pk-A", {"i": i})
        for i in range(3):
            stream.put_json("pk-B", {"i": i})
        events = stream.drain()
        assert len(events) == 8
        # Global sequence numbers are strictly increasing
        seqs = [int(e["kinesis"]["sequenceNumber"]) for e in events]
        assert seqs == sorted(seqs)

    def test_drain_empties_the_stream(self):
        stream = FakeKinesisStream()
        stream.put_json("pk", {"i": 1})
        assert len(stream) == 1
        stream.drain()
        assert len(stream) == 0


class TestFakeDynamoTable:
    def test_ttl_is_enforced_on_read(self):
        table = FakeDynamoTable("t")
        table.set_clock(1_000.0)
        table.put_item({"id": "a", "ttl": 1_100.0})
        assert table.get_item("a") is not None
        table.set_clock(1_101.0)
        assert table.get_item("a") is None

    def test_batch_get_returns_only_live_items(self):
        table = FakeDynamoTable("t")
        table.set_clock(1_000.0)
        table.put_item({"id": "live", "ttl": 2_000.0, "x": 1})
        table.put_item({"id": "expired", "ttl": 500.0, "x": 2})
        got = table.batch_get(["live", "expired", "missing"])
        assert set(got.keys()) == {"live"}


class TestScriptedFakeScorer:
    def _make_req(self, products: list[ProductFeatures]) -> ScoreRequest:
        return ScoreRequest(
            trace_id="t1",
            user_id="U1",
            session_id="S1",
            user_features=UserFeatures(user_id="U1"),
            session_features=SessionFeatures(session_id="S1"),
            candidate_products=products,
            top_k=3,
        )

    def test_ranks_by_popularity_descending(self):
        products = [
            ProductFeatures(product_id="P1", category="c", price=10, popularity_score=0.1),
            ProductFeatures(product_id="P2", category="c", price=10, popularity_score=0.9),
            ProductFeatures(product_id="P3", category="c", price=10, popularity_score=0.5),
        ]
        resp = ScriptedFakeScorer().score(self._make_req(products))
        assert [r.product_id for r in resp.recommendations] == ["P2", "P3", "P1"]
        assert [r.rank for r in resp.recommendations] == [1, 2, 3]

    def test_top_k_truncates(self):
        products = [
            ProductFeatures(
                product_id=f"P{i}", category="c", price=10, popularity_score=1 - i * 0.1
            )
            for i in range(10)
        ]
        resp = ScriptedFakeScorer().score(self._make_req(products))
        assert len(resp.recommendations) == 3

    def test_records_last_call(self):
        s = ScriptedFakeScorer()
        products = [ProductFeatures(product_id="P1", category="c", price=1, popularity_score=0.1)]
        s.score(self._make_req(products))
        assert s.call_count == 1
        assert s.last_request is not None
        assert s.last_request.trace_id == "t1"

    def test_carries_trace_id_through(self):
        s = ScriptedFakeScorer()
        products = [ProductFeatures(product_id="P1", category="c", price=1, popularity_score=0.1)]
        resp = s.score(self._make_req(products))
        assert resp.trace_id == "t1"
