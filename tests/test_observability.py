"""Metrics buffer + EMF line format."""

from __future__ import annotations

import json

from pulsecart.observability.metrics import LatencyTracker, emf_line


def test_latency_tracker_empty_snapshot():
    snap = LatencyTracker("x").snapshot()
    assert snap == {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}


def test_latency_tracker_percentiles():
    t = LatencyTracker("scorer")
    for i in range(1, 101):
        t.observe(float(i))
    snap = t.snapshot()
    assert snap["n"] == 100
    assert snap["p50"] == 50.0
    assert snap["p95"] == 95.0
    assert snap["p99"] == 99.0
    assert 50.0 < snap["avg"] < 51.0


def test_latency_tracker_respects_window():
    t = LatencyTracker("x", window=10)
    for i in range(50):
        t.observe(float(i))
    assert t.snapshot()["n"] == 10


def test_emf_line_is_valid_json_with_metric():
    line = emf_line("PulseCart", "ScorerLatency", 12.3, unit="Milliseconds", stage="enricher")
    parsed = json.loads(line)
    assert parsed["ScorerLatency"] == 12.3
    assert parsed["stage"] == "enricher"
    assert "_aws" in parsed
