"""Runtime configuration. All settings driven by env vars with the PULSECART_ prefix."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration.

    The mode flag flips every external boundary (Kinesis, DynamoDB, SageMaker, warehouse)
    between real AWS clients and in-memory fakes, so unit tests and Docker Compose runs
    execute the same production code paths without cloud credentials.
    """

    model_config = SettingsConfigDict(env_prefix="PULSECART_", env_file=".env", extra="ignore")

    mode: Literal["local", "aws"] = "local"

    # AWS
    aws_region: str = "eu-west-1"

    # Kinesis
    kinesis_raw_stream: str = "pulsecart-raw-clicks"
    kinesis_enriched_stream: str = "pulsecart-enriched-clicks"

    # DynamoDB
    dynamodb_user_table: str = "pulsecart-user-features"
    dynamodb_product_table: str = "pulsecart-product-features"
    dynamodb_feature_ttl_seconds: int = 3600

    # SageMaker
    sagemaker_endpoint_name: str = "pulsecart-ranker-endpoint"
    scorer_timeout_seconds: float = 2.0
    scorer_top_k: int = 5

    # Warehouse
    redshift_workgroup: str = "pulsecart"
    redshift_database: str = "pulsecart"
    redshift_schema: str = "raw"
    duckdb_path: str = "artifacts/pulsecart.duckdb"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    # Model artifact
    model_path: str = "artifacts/ranker.joblib"
    catalog_path: str = "artifacts/product_catalog.json"


def get_settings() -> Settings:
    """Fresh Settings on each call so tests can patch env vars mid-suite."""
    return Settings()
