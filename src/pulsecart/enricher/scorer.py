"""Scorer: three implementations of the same score(ScoreRequest)→ScoreResponse contract.

    SageMakerScorer      — production; hits an InvokeEndpoint on the real endpoint.
    LocalLightGBMScorer  — loads the checked-in LightGBM ranker artifact and predicts locally.
                           Used by Docker Compose (mode=local) and any developer without AWS creds.
    ScriptedFakeScorer   — deterministic stub for unit tests (defined in pulsecart.fakes).

Every implementation returns the exact same ScoreResponse shape, so the enricher
never branches. This is the parity contract that lets the DEMO.md say the code
paths for local and cloud are identical up to one boto3 client.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol

import joblib
import numpy as np

from pulsecart.config import Settings
from pulsecart.schemas import ProductFeatures, Recommendation, ScoreRequest, ScoreResponse
from pulsecart.tracing import get_logger

log = get_logger(__name__)


class Scorer(Protocol):
    def score(self, req: ScoreRequest) -> ScoreResponse: ...


def _feature_row(user_features_dim: int, req: ScoreRequest, product: ProductFeatures) -> np.ndarray:
    """Assemble the numeric feature vector fed to the ranker."""
    aff = req.user_features.category_affinity.get(product.category, 0.0)
    return np.array(
        [
            req.user_features.tenure_days,
            req.user_features.lifetime_orders,
            req.user_features.avg_order_value,
            req.session_features.session_length_seconds,
            req.session_features.events_in_session,
            req.session_features.cart_value,
            product.price,
            product.popularity_score,
            product.avg_rating,
            product.days_since_launch,
            aff,
        ],
        dtype=float,
    )


class LocalLightGBMScorer:
    """Loads the LightGBM ranker artifact and predicts in-process.

    This lets `mode=local` run the whole personalization loop with the *actual*
    trained model — no SageMaker required — which is what powers the Docker
    Compose demo.
    """

    def __init__(self, model_path: str, model_version: str = "lgbm-v1") -> None:
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"ranker artifact not found at {path}")
        payload = joblib.load(path)
        # Accept either a bare model or {"model": ..., "feature_names": [...]}.
        if isinstance(payload, dict) and "model" in payload:
            self._model = payload["model"]
            self._feature_names = payload["feature_names"]
        else:
            self._model = payload
            self._feature_names = None
        self._model_version = model_version

    def score(self, req: ScoreRequest) -> ScoreResponse:
        started = time.perf_counter()
        if not req.candidate_products:
            return ScoreResponse(
                trace_id=req.trace_id,
                recommendations=[],
                latency_ms=(time.perf_counter() - started) * 1000,
                model_version=self._model_version,
            )
        X = np.vstack([_feature_row(0, req, p) for p in req.candidate_products])
        scores = self._model.predict(X)
        order = np.argsort(-scores)[: req.top_k]
        recs = [
            Recommendation(
                product_id=req.candidate_products[int(idx)].product_id,
                score=float(scores[int(idx)]),
                rank=rank + 1,
            )
            for rank, idx in enumerate(order)
        ]
        return ScoreResponse(
            trace_id=req.trace_id,
            recommendations=recs,
            latency_ms=(time.perf_counter() - started) * 1000,
            model_version=self._model_version,
        )


class SageMakerScorer:
    """Calls a deployed SageMaker endpoint via boto3."""

    def __init__(self, endpoint_name: str, region: str, timeout_seconds: float) -> None:
        import boto3
        from botocore.config import Config

        cfg = Config(
            read_timeout=timeout_seconds,
            connect_timeout=timeout_seconds,
            retries={"max_attempts": 2, "mode": "standard"},
        )
        self._client = boto3.client("sagemaker-runtime", region_name=region, config=cfg)
        self._endpoint = endpoint_name

    def score(self, req: ScoreRequest) -> ScoreResponse:
        started = time.perf_counter()
        payload = req.model_dump_json().encode("utf-8")
        resp = self._client.invoke_endpoint(
            EndpointName=self._endpoint,
            ContentType="application/json",
            Accept="application/json",
            Body=payload,
        )
        body = json.loads(resp["Body"].read())
        latency_ms = (time.perf_counter() - started) * 1000
        # The endpoint returns {"recommendations": [...], "model_version": "..."}.
        return ScoreResponse(
            trace_id=req.trace_id,
            recommendations=[Recommendation.model_validate(r) for r in body["recommendations"]],
            latency_ms=latency_ms,
            model_version=body.get("model_version", "unknown"),
        )


def build_scorer(settings: Settings, scorer: Scorer | None = None) -> Scorer:
    """Factory. Tests inject `scorer` directly; the caller picks SageMaker vs Local.

    Falls back to LocalLightGBMScorer when sagemaker_endpoint_name is empty or
    the endpoint doesn't exist yet (e.g. pre-SageMaker deployment).
    """
    if scorer is not None:
        return scorer
    if (
        settings.mode == "aws"
        and settings.sagemaker_endpoint_name
        and settings.sagemaker_endpoint_name != "none"
    ):
        return SageMakerScorer(
            settings.sagemaker_endpoint_name, settings.aws_region, settings.scorer_timeout_seconds
        )
    return LocalLightGBMScorer(settings.model_path)
