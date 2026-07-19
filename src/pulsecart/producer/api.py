"""FastAPI clickstream ingestion endpoint.

POST /events accepts a ClickEvent and forwards it to Kinesis. This is the "front
door" a real e-commerce site would call from its analytics SDK. The trace_id is
minted here if the client didn't supply one, so every downstream row is
walkable back to this HTTP request.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from pulsecart.config import Settings, get_settings
from pulsecart.fakes.fake_kinesis import FakeKinesisStream
from pulsecart.producer.kinesis_client import KinesisProducer, build_producer
from pulsecart.schemas import ClickEvent
from pulsecart.tracing import get_logger, log_extra, new_trace_id, set_trace_id

log = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    producer: KinesisProducer | None = None,
) -> FastAPI:
    """FastAPI factory. Explicit dependencies keep tests one-liner-simple."""
    settings = settings or get_settings()
    if producer is None:
        producer = build_producer(settings, fake_stream=FakeKinesisStream())

    app = FastAPI(title="PulseCart Ingestion", version="0.1.0")
    app.state.producer = producer
    app.state.settings = settings

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.mode}

    @app.post("/events", status_code=202)
    def emit_event(event: ClickEvent) -> dict[str, str]:
        trace_id = event.trace_id or new_trace_id()
        set_trace_id(trace_id)
        try:
            # Rebind trace_id in case the client omitted one.
            evt = event if event.trace_id else event.model_copy(update={"trace_id": trace_id})
            result = app.state.producer.emit(evt)
        except Exception as exc:  # boto3 raises many things; surface as 502
            log.exception("kinesis put failed", extra=log_extra(trace_id=trace_id))
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {
            "event_id": evt.event_id,
            "trace_id": trace_id,
            "seq": str(result.get("SequenceNumber", "")),
        }

    return app


app = create_app()
