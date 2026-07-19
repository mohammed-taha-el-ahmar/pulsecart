"""In-memory fakes for offline-first CI.

Every fake here implements the same public surface as its cloud counterpart so
production code can be unit-tested without any AWS credentials or LocalStack.
"""

from pulsecart.fakes.fake_dynamodb import FakeDynamoTable
from pulsecart.fakes.fake_kinesis import FakeKinesisStream
from pulsecart.fakes.fake_scorer import ScriptedFakeScorer

__all__ = ["FakeDynamoTable", "FakeKinesisStream", "ScriptedFakeScorer"]
