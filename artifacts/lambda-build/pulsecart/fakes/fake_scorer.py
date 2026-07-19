"""ScriptedFakeScorer: deterministic ranking for tests.

Mirrors the ScriptedFake* pattern used in the other AI portfolio projects: the
test author declares up front what the "model" should return, and the code
under test cannot tell the difference between this and a real SageMaker call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pulsecart.schemas import Recommendation, ScoreRequest, ScoreResponse


@dataclass
class ScriptedFakeScorer:
    """A Scorer that ranks candidates by a fixed rule so assertions are stable.

    Ranking strategy: sort candidate products by popularity_score descending,
    with a tiny deterministic tiebreak on product_id. This is enough to test
    the enricher's assembly and Redshift landing without a real model in the
    loop.
    """

    latency_ms: float = 3.7
    model_version: str = "scripted-v0"
    call_count: int = field(default=0, init=False)
    last_request: ScoreRequest | None = field(default=None, init=False)

    def score(self, req: ScoreRequest) -> ScoreResponse:
        self.call_count += 1
        self.last_request = req
        ranked = sorted(
            req.candidate_products,
            key=lambda p: (-p.popularity_score, p.product_id),
        )[: req.top_k]
        recs = [
            Recommendation(product_id=p.product_id, score=round(1.0 - i * 0.1, 4), rank=i + 1)
            for i, p in enumerate(ranked)
        ]
        return ScoreResponse(
            trace_id=req.trace_id,
            recommendations=recs,
            latency_ms=self.latency_ms,
            model_version=self.model_version,
        )
