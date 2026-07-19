"""Lambda entry point.

The AWS Lambda service invokes `lambda_handler` with a batch of Kinesis records.
We decode each record, assemble session + user + candidate-product features,
call the Scorer, and emit an EnrichedEvent to the enriched stream (and, in
production, land it in Redshift via streaming ingestion on that stream).

The Enricher class exists to be assembled from unit tests directly (bypassing
Lambda's event shape) so we can pin behaviour with `ScriptedFakeScorer` and the
in-memory fakes.
"""

from __future__ import annotations

import base64
import json
import random
from dataclasses import dataclass, field
from typing import Any

from pulsecart.config import Settings, get_settings
from pulsecart.enricher.feature_lookup import FeatureStore, build_feature_store
from pulsecart.enricher.scorer import Scorer, build_scorer
from pulsecart.enricher.session_state import SessionStateStore
from pulsecart.fakes.fake_dynamodb import FakeDynamoTable
from pulsecart.fakes.fake_kinesis import FakeKinesisStream
from pulsecart.schemas import ClickEvent, EnrichedEvent, ScoreRequest
from pulsecart.tracing import get_logger, log_extra, set_trace_id

log = get_logger(__name__)


@dataclass
class Enricher:
    """The composable enricher pipeline. Prefer this over lambda_handler in tests."""

    feature_store: FeatureStore
    scorer: Scorer
    settings: Settings
    session_state: SessionStateStore = field(default_factory=SessionStateStore)

    def enrich(self, event: ClickEvent) -> EnrichedEvent:
        set_trace_id(event.trace_id)
        user_features = self.feature_store.get_user(event.user_id)
        candidate_ids = self._candidate_product_ids(event, user_features)
        candidate_products = self.feature_store.get_products(candidate_ids)
        session_features = self.session_state.features_for(
            event, {p.product_id: p for p in candidate_products}
        )
        req = ScoreRequest(
            trace_id=event.trace_id,
            user_id=event.user_id,
            session_id=event.session_id,
            user_features=user_features,
            session_features=session_features,
            candidate_products=candidate_products,
            top_k=self.settings.scorer_top_k,
        )
        resp = self.scorer.score(req)
        self.session_state.observe(event)
        enriched = EnrichedEvent(
            event_id=event.event_id,
            trace_id=event.trace_id,
            event_type=event.event_type,
            user_id=event.user_id,
            session_id=event.session_id,
            timestamp=event.timestamp,
            product_id=event.product_id,
            category=event.category,
            user_features=user_features,
            session_features=session_features,
            recommendations=resp.recommendations,
            scorer_latency_ms=resp.latency_ms,
            model_version=resp.model_version,
        )
        log.info(
            "enriched",
            extra=log_extra(
                event_id=event.event_id,
                user_id=event.user_id,
                rec_count=len(resp.recommendations),
                latency_ms=resp.latency_ms,
            ),
        )
        return enriched

    def _candidate_product_ids(self, event: ClickEvent, user_features) -> list[str]:
        """Pick a candidate set for the ranker.

        Real candidate generation would call an ANN index or an ElastiCache
        popular-items shortlist. Here we pick a deterministic band of product IDs
        seeded on user_id so the demo is reproducible; if the event carries a
        product_id (product_view / add_to_cart), it's always included so the
        ranker sees the item in play.
        """
        rng = random.Random(hash(event.user_id) & 0xFFFF)
        candidates = {f"P{rng.randint(1, 200):04d}" for _ in range(20)}
        if event.product_id:
            candidates.add(event.product_id)
        return sorted(candidates)


# ---------- Lambda entry ----------


def _decode_record(record: dict[str, Any]) -> ClickEvent:
    """Kinesis event schema: record["kinesis"]["data"] is base64 in production."""
    data = record["kinesis"]["data"]
    raw = data if isinstance(data, bytes) else base64.b64decode(data)
    return ClickEvent.model_validate(json.loads(raw))


def _emit_enriched(stream: FakeKinesisStream | Any, enriched: EnrichedEvent) -> None:
    payload = enriched.model_dump(mode="json")
    if isinstance(stream, FakeKinesisStream):
        stream.put_json(enriched.session_id, payload)
    else:
        stream.put_record(
            StreamName=stream._name,  # boto client won't have this; overridden in build_output_sink
            Data=enriched.model_dump_json().encode("utf-8"),
            PartitionKey=enriched.session_id,
        )


class _BotoOutputSink:
    def __init__(self, stream_name: str, region: str) -> None:
        import boto3

        self._client = boto3.client("kinesis", region_name=region)
        self._name = stream_name

    def put_json(self, partition_key: str, payload: dict[str, Any]) -> None:
        self._client.put_record(
            StreamName=self._name,
            Data=json.dumps(payload).encode("utf-8"),
            PartitionKey=partition_key,
        )


def _build_enricher_from_settings(settings: Settings) -> tuple[Enricher, Any]:
    """Wire real AWS clients (or, in tests, expect explicit injection)."""
    if settings.mode != "aws":
        raise RuntimeError(
            "lambda_handler entry expects mode=aws; use Enricher(...) directly locally"
        )
    feature_store = build_feature_store(settings)
    scorer = build_scorer(settings)
    sink = _BotoOutputSink(settings.kinesis_enriched_stream, settings.aws_region)
    return Enricher(feature_store=feature_store, scorer=scorer, settings=settings), sink


# Cached across warm Lambda invocations.
_CACHED: tuple[Enricher, Any] | None = None


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:  # noqa: ARG001
    """AWS Lambda entry point."""
    global _CACHED
    settings = get_settings()
    if _CACHED is None:
        _CACHED = _build_enricher_from_settings(settings)
    enricher, sink = _CACHED
    successes = 0
    failures: list[dict[str, str]] = []
    for record in event.get("Records", []):
        try:
            evt = _decode_record(record)
            enriched = enricher.enrich(evt)
            sink.put_json(enriched.session_id, enriched.model_dump(mode="json"))
            successes += 1
        except Exception as exc:  # partial batch failure — surface to Lambda ESM
            seq = record.get("kinesis", {}).get("sequenceNumber", "?")
            log.exception("enrich failed", extra=log_extra(seq=seq))
            failures.append({"itemIdentifier": seq})
            _ = exc
    return {"batchItemFailures": failures, "successful": successes}


# ---------- Local convenience ----------


def build_local_enricher(
    settings: Settings,
    scorer: Scorer,
    user_table: FakeDynamoTable,
    product_table: FakeDynamoTable,
) -> Enricher:
    """Assemble an Enricher wired to in-memory fakes. Used by tests + docker-compose demo."""
    feature_store = build_feature_store(
        settings, fake_user_table=user_table, fake_product_table=product_table
    )
    return Enricher(feature_store=feature_store, scorer=scorer, settings=settings)
