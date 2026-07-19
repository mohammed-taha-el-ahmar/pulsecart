"""Shared test fixtures.

All fixtures here run in offline mode (no boto3 calls, no LocalStack). The
Settings object is pinned to mode=local and the fake fixtures are drop-in
replacements for their AWS counterparts.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from pulsecart.config import Settings
from pulsecart.enricher.handler import Enricher, build_local_enricher
from pulsecart.fakes.fake_dynamodb import FakeDynamoTable
from pulsecart.fakes.fake_scorer import ScriptedFakeScorer
from pulsecart.schemas import ClickEvent
from pulsecart.warehouse.warehouse import DuckDBWarehouse


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PULSECART_MODE", "local")
    monkeypatch.setenv("PULSECART_DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("PULSECART_MODEL_PATH", str(tmp_path / "no-model.joblib"))
    # Ensure no accidental AWS creds leak.
    for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(k, raising=False)
        os.environ.pop(k, None)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def user_table() -> FakeDynamoTable:
    table = FakeDynamoTable("users", partition_key="user_id")
    table.set_clock(1_700_000_000.0)
    return table


@pytest.fixture
def product_table() -> FakeDynamoTable:
    table = FakeDynamoTable("products", partition_key="product_id")
    table.set_clock(1_700_000_000.0)
    seed_ttl = 1_700_000_000.0 + 3600  # valid for 1h
    for i in range(1, 21):
        table.put_item(
            {
                "product_id": f"P{i:04d}",
                "category": "electronics" if i % 2 else "apparel",
                "price": 10.0 + i,
                "popularity_score": 1.0 - i * 0.03,
                "avg_rating": 4.0,
                "days_since_launch": 30 + i,
                "ttl": seed_ttl,
            }
        )
    return table


@pytest.fixture
def scorer() -> ScriptedFakeScorer:
    return ScriptedFakeScorer()


@pytest.fixture
def enricher(
    settings: Settings,
    scorer: ScriptedFakeScorer,
    user_table: FakeDynamoTable,
    product_table: FakeDynamoTable,
) -> Enricher:
    return build_local_enricher(settings, scorer, user_table, product_table)


@pytest.fixture
def warehouse(tmp_path) -> Iterator[DuckDBWarehouse]:
    wh = DuckDBWarehouse(str(tmp_path / "wh.duckdb"))
    yield wh
    wh.close()


@pytest.fixture
def sample_click() -> ClickEvent:
    return ClickEvent(
        event_type="product_view",
        user_id="U0001",
        session_id="S-test-1",
        timestamp=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        product_id="P0007",
        category="electronics",
    )


@pytest.fixture
def click_batch() -> list[ClickEvent]:
    """A small session of chronologically-ordered clicks."""
    base_ts = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    return [
        ClickEvent(
            event_type="page_view",
            user_id="U0001",
            session_id="S-test-1",
            timestamp=base_ts,
        ),
        ClickEvent(
            event_type="product_view",
            user_id="U0001",
            session_id="S-test-1",
            timestamp=base_ts + timedelta(seconds=10),
            product_id="P0007",
            category="electronics",
        ),
        ClickEvent(
            event_type="add_to_cart",
            user_id="U0001",
            session_id="S-test-1",
            timestamp=base_ts + timedelta(seconds=30),
            product_id="P0007",
            category="electronics",
        ),
    ]
