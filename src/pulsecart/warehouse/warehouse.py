"""Warehouse abstraction.

Locally we materialize EnrichedEvents into DuckDB, which is fast, file-backed,
and lets dbt-duckdb run the same models CI runs. In AWS the same rows land in
Redshift via a materialized view over the enriched Kinesis stream — see
warehouse/redshift_streaming.sql.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import duckdb

from pulsecart.schemas import EnrichedEvent
from pulsecart.tracing import get_logger

log = get_logger(__name__)


class Warehouse(Protocol):
    def ensure_schema(self) -> None: ...
    def insert(self, event: EnrichedEvent) -> None: ...
    def latest_for_user(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]: ...


class DuckDBWarehouse:
    """Local warehouse. Deliberately mirrors the Redshift DDL shape."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._con = duckdb.connect(path)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self._con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        self._con.execute(
            """
            CREATE TABLE IF NOT EXISTS raw.enriched_events (
                event_id            VARCHAR PRIMARY KEY,
                trace_id            VARCHAR,
                event_type          VARCHAR,
                user_id             VARCHAR,
                session_id          VARCHAR,
                event_ts            TIMESTAMP,
                product_id          VARCHAR,
                category            VARCHAR,
                user_features_json  VARCHAR,
                session_features_json VARCHAR,
                recommendations_json VARCHAR,
                scored_at           TIMESTAMP,
                scorer_latency_ms   DOUBLE,
                model_version       VARCHAR
            )
            """
        )

    def insert(self, event: EnrichedEvent) -> None:
        self._con.execute(
            """
            INSERT OR REPLACE INTO raw.enriched_events VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                event.event_id,
                event.trace_id,
                event.event_type,
                event.user_id,
                event.session_id,
                event.timestamp,
                event.product_id,
                event.category,
                event.user_features.model_dump_json(),
                event.session_features.model_dump_json(),
                json.dumps([r.model_dump() for r in event.recommendations]),
                event.scored_at,
                event.scorer_latency_ms,
                event.model_version,
            ],
        )

    def latest_for_user(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        rows = self._con.execute(
            """
            SELECT event_id, trace_id, event_ts, recommendations_json, model_version
            FROM raw.enriched_events
            WHERE user_id = ?
            ORDER BY event_ts DESC
            LIMIT ?
            """,
            [user_id, limit],
        ).fetchall()
        cols = ["event_id", "trace_id", "event_ts", "recommendations_json", "model_version"]
        out = []
        for row in rows:
            record = dict(zip(cols, row, strict=True))
            record["recommendations"] = json.loads(record.pop("recommendations_json"))
            out.append(record)
        return out

    def summary(self) -> dict[str, Any]:
        row = self._con.execute(
            """
            SELECT COUNT(*) AS n_events,
                   COUNT(DISTINCT user_id) AS n_users,
                   COUNT(DISTINCT session_id) AS n_sessions,
                   AVG(scorer_latency_ms) AS avg_latency_ms
            FROM raw.enriched_events
            """
        ).fetchone()
        if row is None:
            return {"n_events": 0, "n_users": 0, "n_sessions": 0, "avg_latency_ms": 0.0}
        return {
            "n_events": int(row[0] or 0),
            "n_users": int(row[1] or 0),
            "n_sessions": int(row[2] or 0),
            "avg_latency_ms": float(row[3] or 0.0),
        }

    def close(self) -> None:
        self._con.close()
