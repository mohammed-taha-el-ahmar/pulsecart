"""Kinesis producer wrapper.

Same surface for real KDS (boto3) and the fake stream. Producer code never
imports boto3 directly, so a mode=local run in Docker Compose or CI exercises
the same code paths as production.
"""

from __future__ import annotations

from typing import Any, Protocol

from pulsecart.config import Settings
from pulsecart.fakes.fake_kinesis import FakeKinesisStream
from pulsecart.schemas import ClickEvent
from pulsecart.tracing import get_logger, log_extra

log = get_logger(__name__)


class KinesisProducer(Protocol):
    def emit(self, event: ClickEvent) -> dict[str, Any]: ...


class FakeKinesisProducer:
    """Producer that writes to an in-memory FakeKinesisStream."""

    def __init__(self, stream: FakeKinesisStream) -> None:
        self._stream = stream

    def emit(self, event: ClickEvent) -> dict[str, Any]:
        result = self._stream.put_json(event.session_id, event.model_dump(mode="json"))
        log.info(
            "emitted event",
            extra=log_extra(event_id=event.event_id, seq=result["SequenceNumber"]),
        )
        return result


class BotoKinesisProducer:
    """Producer that writes to a real Kinesis Data Stream via boto3."""

    def __init__(self, stream_name: str, region: str) -> None:
        import boto3  # local import so tests without boto3 configured still pass

        self._client = boto3.client("kinesis", region_name=region)
        self._stream_name = stream_name

    def emit(self, event: ClickEvent) -> dict[str, Any]:
        payload = event.model_dump_json().encode("utf-8")
        result = self._client.put_record(
            StreamName=self._stream_name,
            Data=payload,
            PartitionKey=event.session_id,
        )
        log.info(
            "emitted event",
            extra=log_extra(event_id=event.event_id, seq=result.get("SequenceNumber")),
        )
        return result


def build_producer(
    settings: Settings, fake_stream: FakeKinesisStream | None = None
) -> KinesisProducer:
    """Factory. `fake_stream` is used when settings.mode == 'local'."""
    if settings.mode == "aws":
        return BotoKinesisProducer(settings.kinesis_raw_stream, settings.aws_region)
    if fake_stream is None:
        raise ValueError("mode=local requires a FakeKinesisStream")
    return FakeKinesisProducer(fake_stream)
