"""Traceability primitives.

Every event carries a trace_id from the producer through the enricher and into
Redshift. This is the mechanism the AWS card promises: any recommendation shown
in the dashboard can be walked back to the originating click.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from pythonjsonlogger import jsonlogger

_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    """Mint a fresh trace_id at the producer boundary."""
    return uuid4().hex


def set_trace_id(trace_id: str) -> None:
    _trace_id_var.set(trace_id)


def current_trace_id() -> str | None:
    return _trace_id_var.get()


class _TraceInjector(logging.Filter):
    """Enriches every log record with the ambient trace_id (if any)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id() or "-"
        return True


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent JSON logging setup."""
    root = logging.getLogger()
    if getattr(root, "_pulsecart_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    fmt = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(trace_id)s %(message)s",
        rename_fields={"asctime": "ts", "levelname": "level"},
    )
    handler.setFormatter(fmt)
    handler.addFilter(_TraceInjector())
    root.handlers = [handler]
    root.setLevel(level)
    root._pulsecart_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def log_extra(**kwargs: Any) -> dict[str, Any]:
    """Convenience for structured log fields."""
    return {"extra": kwargs}
