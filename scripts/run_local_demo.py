"""Run the whole pipeline end-to-end locally.

Simulates 30 sessions of clicks, runs them through the enricher with the real
LightGBM ranker, lands enriched events in DuckDB, then prints a summary.

The FastAPI dashboard (started separately via `uv run uvicorn ...`) points at
the same DuckDB file and shows the results live.
"""

from __future__ import annotations

import json
from pathlib import Path

from pulsecart.config import get_settings
from pulsecart.enricher.handler import build_local_enricher
from pulsecart.enricher.scorer import LocalLightGBMScorer
from pulsecart.fakes.fake_dynamodb import FakeDynamoTable
from pulsecart.producer.simulator import generate_events
from pulsecart.warehouse.warehouse import DuckDBWarehouse


def _seed_dynamo(user_table: FakeDynamoTable, product_table: FakeDynamoTable) -> None:
    catalog = json.loads(Path("artifacts/product_catalog.json").read_text())
    for p in catalog:
        product_table.put_item({**p, "ttl": 9_999_999_999})
    # Seed a handful of "warm" users; the rest will cold-start.
    for i in [1, 2, 3, 4, 5, 42, 99, 123]:
        user_table.put_item(
            {
                "user_id": f"U{i:04d}",
                "tenure_days": 300 + i,
                "lifetime_orders": i,
                "avg_order_value": 45.0 + i,
                "category_affinity": {"electronics": 0.8, "apparel": 0.4},
                "ttl": 9_999_999_999,
            }
        )


def main() -> None:
    settings = get_settings()
    warehouse = DuckDBWarehouse(settings.duckdb_path)
    user_table = FakeDynamoTable("users", partition_key="user_id")
    product_table = FakeDynamoTable("products", partition_key="product_id")
    _seed_dynamo(user_table, product_table)

    scorer = LocalLightGBMScorer(settings.model_path)
    enricher = build_local_enricher(settings, scorer, user_table, product_table)

    n = 0
    for event in generate_events(n_sessions=30, seed=7):
        enriched = enricher.enrich(event)
        warehouse.insert(enriched)
        n += 1

    print(f"processed {n} events → {settings.duckdb_path}")
    print(f"summary: {warehouse.summary()}")


if __name__ == "__main__":
    main()
