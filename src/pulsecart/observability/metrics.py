"""Percentile-tracking metrics buffer.

Locally we keep a rolling window in memory and expose it via the FastAPI
dashboard's /summary endpoint. In AWS, the Lambda handler emits the same
records as CloudWatch EMF (Embedded Metric Format) log lines that CloudWatch
picks up automatically — no extra put_metric_data cost.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LatencyTracker:
    """Rolling latency window for one named stage (e.g. 'scorer', 'ddb_lookup')."""

    name: str
    window: int = 500
    samples: deque[float] = field(default_factory=deque)

    def observe(self, ms: float) -> None:
        self.samples.append(ms)
        while len(self.samples) > self.window:
            self.samples.popleft()

    def snapshot(self) -> dict[str, float]:
        if not self.samples:
            return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}
        data = sorted(self.samples)
        return {
            "n": len(data),
            "p50": _pct(data, 50),
            "p95": _pct(data, 95),
            "p99": _pct(data, 99),
            "avg": statistics.fmean(data),
        }


def _pct(sorted_data: list[float], p: float) -> float:
    if not sorted_data:
        return 0.0
    idx = min(len(sorted_data) - 1, int(math.ceil((p / 100.0) * len(sorted_data))) - 1)
    return sorted_data[max(0, idx)]


def emf_line(
    namespace: str,
    metric: str,
    value: float,
    unit: str = "Milliseconds",
    **dims: Any,
) -> str:
    """CloudWatch Embedded Metric Format line. Printing this to stdout emits a metric."""
    payload: dict[str, Any] = {
        "_aws": {
            "Timestamp": 0,  # CloudWatch fills this in
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [list(dims.keys())] if dims else [[]],
                    "Metrics": [{"Name": metric, "Unit": unit}],
                }
            ],
        },
        metric: value,
    }
    payload.update({k: str(v) for k, v in dims.items()})
    return json.dumps(payload)
