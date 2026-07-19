"""Producer tier: ingestion HTTP, Kinesis fan-out, simulator determinism."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from pulsecart.config import Settings
from pulsecart.fakes.fake_kinesis import FakeKinesisStream
from pulsecart.producer.api import create_app
from pulsecart.producer.kinesis_client import FakeKinesisProducer
from pulsecart.producer.simulator import generate_events

_STABLE_FIELDS = ("event_type", "user_id", "session_id", "product_id", "category", "device")


def _stable(event) -> dict:
    dumped = event.model_dump()
    return {k: dumped[k] for k in _STABLE_FIELDS}


class TestSimulator:
    def test_generate_events_is_deterministic_with_seed(self):
        # event_id / trace_id are always UUID4 (per the ClickEvent schema), so the
        # simulator's determinism guarantee covers everything except those IDs.
        start = datetime(2026, 1, 1, tzinfo=UTC)
        one = list(generate_events(n_sessions=3, seed=42, start_ts=start))
        two = list(generate_events(n_sessions=3, seed=42, start_ts=start))
        assert [_stable(e) for e in one] == [_stable(e) for e in two]
        assert [e.timestamp for e in one] == [e.timestamp for e in two]

    def test_events_span_multiple_sessions(self):
        events = list(generate_events(n_sessions=5, seed=7))
        assert len({e.session_id for e in events}) == 5

    def test_timestamps_are_monotonic_within_a_session(self):
        events = list(
            generate_events(n_sessions=2, seed=3, start_ts=datetime(2026, 1, 1, tzinfo=UTC))
        )
        by_session: dict[str, list] = {}
        for e in events:
            by_session.setdefault(e.session_id, []).append(e.timestamp)
        for session_ts in by_session.values():
            assert session_ts == sorted(session_ts)


class TestIngestionAPI:
    def _client(self, stream: FakeKinesisStream) -> TestClient:
        producer = FakeKinesisProducer(stream)
        settings = Settings(mode="local")
        return TestClient(create_app(settings=settings, producer=producer))

    def test_health_reports_mode(self):
        stream = FakeKinesisStream()
        client = self._client(stream)
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "mode": "local"}

    def test_post_event_lands_on_kinesis(self):
        stream = FakeKinesisStream()
        client = self._client(stream)
        payload = {
            "event_type": "product_view",
            "user_id": "U1",
            "session_id": "S1",
            "product_id": "P0001",
        }
        r = client.post("/events", json=payload)
        assert r.status_code == 202
        assert len(stream) == 1
        body = r.json()
        assert body["event_id"]
        assert body["trace_id"]

    def test_trace_id_is_minted_when_missing(self):
        stream = FakeKinesisStream()
        client = self._client(stream)
        payload = {"event_type": "page_view", "user_id": "U1", "session_id": "S1"}
        r = client.post("/events", json=payload)
        # An empty-string trace_id in the wire payload would still make the
        # ClickEvent factory mint one; verify a non-empty ID comes back.
        assert len(r.json()["trace_id"]) > 8

    def test_trace_id_is_preserved_when_supplied(self):
        stream = FakeKinesisStream()
        client = self._client(stream)
        payload = {
            "event_type": "page_view",
            "user_id": "U1",
            "session_id": "S1",
            "trace_id": "trace-fixed-42",
        }
        r = client.post("/events", json=payload)
        assert r.json()["trace_id"] == "trace-fixed-42"

    def test_malformed_event_returns_422(self):
        stream = FakeKinesisStream()
        client = self._client(stream)
        r = client.post("/events", json={"event_type": "nope"})
        assert r.status_code == 422
