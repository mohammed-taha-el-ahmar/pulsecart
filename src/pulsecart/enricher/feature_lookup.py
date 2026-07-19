"""Feature lookup layer.

Reads UserFeatures and ProductFeatures from a DynamoDB-shaped store. Concrete
backends: FakeDynamoTable for tests / local, and boto3 DynamoDB for AWS.
"""

from __future__ import annotations

from typing import Any, Protocol

from pulsecart.config import Settings
from pulsecart.fakes.fake_dynamodb import FakeDynamoTable
from pulsecart.schemas import ProductFeatures, UserFeatures
from pulsecart.tracing import get_logger

log = get_logger(__name__)


class FeatureStore(Protocol):
    def get_user(self, user_id: str) -> UserFeatures: ...
    def get_products(self, product_ids: list[str]) -> list[ProductFeatures]: ...


def _default_user(user_id: str) -> UserFeatures:
    """Cold-start user features when the lookup misses."""
    return UserFeatures(user_id=user_id)


class FakeFeatureStore:
    """Backed by two FakeDynamoTables. Missing users get a cold-start row."""

    def __init__(self, user_table: FakeDynamoTable, product_table: FakeDynamoTable) -> None:
        self._users = user_table
        self._products = product_table

    def get_user(self, user_id: str) -> UserFeatures:
        item = self._users.get_item(user_id)
        if item is None:
            log.info("user cache miss; using cold-start", extra={"extra": {"user_id": user_id}})
            return _default_user(user_id)
        return UserFeatures.model_validate(_strip_ttl(item))

    def get_products(self, product_ids: list[str]) -> list[ProductFeatures]:
        items = self._products.batch_get(product_ids)
        return [ProductFeatures.model_validate(_strip_ttl(v)) for v in items.values()]


class DynamoFeatureStore:
    """Backed by real DynamoDB via boto3.resource."""

    def __init__(self, region: str, user_table: str, product_table: str) -> None:
        import boto3

        self._ddb = boto3.resource("dynamodb", region_name=region)
        self._user_table = self._ddb.Table(user_table)
        self._product_table = self._ddb.Table(product_table)

    def get_user(self, user_id: str) -> UserFeatures:
        resp = self._user_table.get_item(Key={"user_id": user_id})
        item = resp.get("Item")
        if item is None:
            return _default_user(user_id)
        return UserFeatures.model_validate(_strip_ttl(item))

    def get_products(self, product_ids: list[str]) -> list[ProductFeatures]:
        if not product_ids:
            return []
        # BatchGetItem, chunk of 100 max.
        out: list[ProductFeatures] = []
        for i in range(0, len(product_ids), 100):
            batch = product_ids[i : i + 100]
            resp = self._ddb.batch_get_item(
                RequestItems={
                    self._product_table.name: {"Keys": [{"product_id": pid} for pid in batch]}
                }
            )
            for item in resp["Responses"].get(self._product_table.name, []):
                out.append(ProductFeatures.model_validate(_strip_ttl(item)))
        return out


def _strip_ttl(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k != "ttl"}


def build_feature_store(
    settings: Settings,
    fake_user_table: FakeDynamoTable | None = None,
    fake_product_table: FakeDynamoTable | None = None,
) -> FeatureStore:
    if settings.mode == "aws":
        return DynamoFeatureStore(
            settings.aws_region, settings.dynamodb_user_table, settings.dynamodb_product_table
        )
    if fake_user_table is None or fake_product_table is None:
        raise ValueError("mode=local requires fake tables")
    return FakeFeatureStore(fake_user_table, fake_product_table)
