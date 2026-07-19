"""In-memory stand-in for a Kinesis Data Stream.

Preserves partition-key ordering per shard and gives tests a `drain()` helper
so they can pull records deterministically.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _FakeRecord:
    partition_key: str
    data: bytes
    sequence_number: int


@dataclass
class FakeKinesisStream:
    """Behaves enough like a Kinesis stream for the enricher's happy path."""

    name: str = "fake-stream"
    _records: dict[str, list[_FakeRecord]] = field(default_factory=lambda: defaultdict(list))
    _next_seq: int = 0

    def put_record(self, partition_key: str, data: bytes) -> dict[str, Any]:
        self._next_seq += 1
        record = _FakeRecord(partition_key=partition_key, data=data, sequence_number=self._next_seq)
        self._records[partition_key].append(record)
        shard = f"shard-{hash(partition_key) % 4}"
        return {"SequenceNumber": str(self._next_seq), "ShardId": shard}

    def put_json(self, partition_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.put_record(partition_key, json.dumps(payload).encode("utf-8"))

    def drain(self) -> list[dict[str, Any]]:
        """Return all buffered records as Lambda-event-shaped dicts and clear the buffer."""
        events = []
        for partition_key, records in self._records.items():
            for r in records:
                events.append(
                    {
                        "kinesis": {
                            "partitionKey": partition_key,
                            "sequenceNumber": str(r.sequence_number),
                            "data": r.data,  # Lambda would b64-encode this; enricher handles both.
                        }
                    }
                )
        self._records.clear()
        return sorted(events, key=lambda e: int(e["kinesis"]["sequenceNumber"]))

    def __len__(self) -> int:
        return sum(len(v) for v in self._records.values())
