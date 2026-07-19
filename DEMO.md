# PulseCart — Demo & Coverage

## What this project demonstrates

A **real-time e-commerce clickstream personalization pipeline** on AWS:

- Ingest at the edge (`POST /events` → Kinesis).
- Enrich on the stream (Lambda pulls DynamoDB features, invokes a SageMaker LightGBM ranker for top-K).
- Land in Redshift via **native Streaming Ingestion** (materialized view over the enriched Kinesis stream).
- Serve `GET /recommendations/{user_id}` from the warehouse.
- Every recommendation carries the `trace_id` of the click that produced it.

## Coverage matrix

The honest breakdown of what's exercised where.

| Component                                     | Proved locally (CI)                                                          | Requires AWS credentials                          | Deliberately deferred                            |
| --------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------ |
| ClickEvent / EnrichedEvent JSON contract      | ✅ `tests/test_schemas.py`                                                    | —                                                 | —                                                |
| Producer FastAPI ingestion                    | ✅ `tests/test_producer.py` w/ FakeKinesisStream                              | Real KDS `PutRecord`                              | Auth on the ingest endpoint (out of scope)       |
| Synthetic clickstream simulator (determinism) | ✅ `tests/test_producer.py::TestSimulator`                                    | —                                                 | —                                                |
| Kinesis stream semantics (ordering, drain)    | ✅ `tests/test_fakes.py::TestFakeKinesisStream`                               | Real KDS shard behaviour, hot-partition handling  | KCL-style resharding logic                       |
| DynamoDB feature lookup + TTL                 | ✅ `tests/test_fakes.py::TestFakeDynamoTable`, `tests/test_enricher.py`       | `BatchGetItem` on real tables                     | GSIs for reverse lookups (single-key access only)|
| Session-feature assembly                      | ✅ `tests/test_enricher.py::TestSessionState`                                 | —                                                 | Cross-Lambda-instance session sharing (Elasti$)  |
| SageMaker Scorer parity contract              | ✅ `ScriptedFakeScorer` + `LocalLightGBMScorer` used in enricher tests        | `SageMakerScorer` code path (real `InvokeEndpoint`)| Batch transform mode                            |
| LightGBM ranker artifact (trained + loaded)   | ✅ `scripts/train_ranker.py` + demo run                                       | Deploying the artifact to SageMaker endpoint      | Full training pipeline (owned by SignalFlow)     |
| Lambda handler batch semantics                | ✅ `tests/test_enricher.py::TestLambdaDecode` (base64 + raw bytes both)       | ✅ Direct invoke returns `{"successful": 1}`      | Partial-batch retry replay tests                 |
| End-to-end producer → enricher → warehouse    | ✅ `tests/test_e2e_offline.py`                                                | Real end-to-end AWS round-trip                    | —                                                |
| Redshift Streaming Ingestion (materialized view) | ⚠️ SQL applied against DuckDB shape locally; **not** run against Redshift | ✅ `redshift_streaming.sql` runs on real workgroup | Multi-region MV replication                     |
| dbt models (staging + marts)                  | ✅ `dbt build` w/ dbt-duckdb target in CI                                     | ✅ `dbt build --target aws` passes on real Redshift | Snapshots / seeds (not needed for this scope)    |
| Recommender API + dashboard                   | ✅ `tests/test_recommender_api.py` + TestClient                               | —                                                 | Server-Sent Events / websocket push              |
| Observability (LatencyTracker + EMF)          | ✅ `tests/test_observability.py`                                              | CloudWatch alarms fire in the account             | X-Ray tracing (trace_id in Redshift is our proxy)|
| Terraform HCL                                 | ✅ `terraform fmt` + `terraform validate -backend=false` in CI                | `terraform apply` against real AWS                | Multi-env workspace layout                       |
| CI (offline-only, no cloud creds)             | ✅ `.github/workflows/ci.yml`                                                 | —                                                 | —                                                |

### Key limitations, called out honestly

- **`terraform apply` has been executed against a real AWS account.** Lambda deploys via S3 (the zip exceeds the 50 MB inline limit). Redshift Serverless namespace + workgroup provision successfully. The `redshift_endpoint` output is wired to the workgroup address.
- **The Lambda enricher runs end-to-end on AWS.** Direct invocation returns `{"batchItemFailures": [], "successful": 1}`. The zip bundles `libgomp.so.1` from `amazonlinux:2` (matching Lambda's AL2 glibc 2.26) and sets `LD_LIBRARY_PATH` to include both `/var/task/lib` and `/var/task/scikit_learn.libs`. SageMaker is bypassed — the enricher uses `LocalLightGBMScorer` with the bundled `ranker.joblib`.
- **The Lambda enricher requires a lean zip (< 250MB unzipped).** `pandas` was removed — LightGBM's `predict()` accepts numpy arrays directly. The zip includes: numpy, scipy, scikit-learn, lightgbm, joblib, pydantic, python-json-logger.
- **The Redshift streaming DDL is hand-written, not `dbt run --defer`-generated.** dbt takes over from `raw.enriched_events` onward. This mirrors the standard pattern (streaming MV lives outside dbt).
- **The ranker is a small LightGBM trained on synthetic data.** Training MLOps (registry, blue/green, drift, feature store) is the *SignalFlow* project's story; PulseCart deliberately stays serving-only to avoid overlapping it.

## Running the demo

### 1. Fully offline (no AWS)

```bash
uv pip install -e ".[dev,dbt]"
python scripts/train_ranker.py             # writes artifacts/ranker.joblib
python scripts/run_local_demo.py           # populates DuckDB
uvicorn pulsecart.recommender_api.app:app --port 8080
open http://localhost:8080
# Look up user U0042, U0099, U0123 etc.
```

### 2. Docker Compose

```bash
docker compose up --build
open http://localhost:8080
```

### 3. CI

```bash
pytest -v
ruff check .
ruff format --check .
```

Expected: **all tests pass, no ruff findings, no cloud calls attempted.**

### 4. On AWS

```bash
cd infra
terraform init -backend-config="bucket=my-pulsecart-tfstate" -backend-config="region=eu-west-1"
terraform apply -var="redshift_admin_password=RedshiftPass1"

# Install psql if needed: brew install libpq && brew link --force libpq

# Wire streaming ingestion (uses psql -v variables, no envsubst needed)
PGPASSWORD=RedshiftPass1 psql "host=$(terraform output -raw redshift_endpoint) port=5439 dbname=pulsecart user=pulsecart_admin sslmode=require" \
  -c 'DROP MATERIALIZED VIEW IF EXISTS "raw".enriched_events;' \
  -v iam_role="$(terraform output -raw redshift_streaming_role_arn)" \
  -v stream_name="$(terraform output -raw enriched_stream_name)" \
  -f ../src/pulsecart/warehouse/redshift_streaming.sql

# Send test traffic (producer must run in AWS mode to write to real Kinesis)
# Start producer:
#   AWS_PROFILE=incidentcouncil PULSECART_MODE=aws \
#   PULSECART_KINESIS_RAW_STREAM=pulsecart-raw-clicks PULSECART_AWS_REGION=eu-west-1 \
#   uv run uvicorn pulsecart.producer.api:create_app --factory --port 8000
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{"event_type":"product_view","user_id":"U0001","session_id":"S1","product_id":"P0007"}'

# Run dbt against Redshift (profiles.yml must exist — cp profiles.example.yml profiles.yml)
cd ../dbt
REDSHIFT_HOST=$(cd ../infra && terraform output -raw redshift_endpoint) \
  REDSHIFT_USER=pulsecart_admin \
  REDSHIFT_PASSWORD=RedshiftPass1 \
  uv run dbt build --target aws --profiles-dir .
```

### 5. Verifying the live pipeline

After sending traffic via the producer, verify data flows end-to-end:

```bash
cd infra

# Refresh the streaming MV and query the staged data
PGPASSWORD=RedshiftPass1 psql "host=$(terraform output -raw redshift_endpoint) port=5439 dbname=pulsecart user=pulsecart_admin sslmode=require" \
  -c 'REFRESH MATERIALIZED VIEW "raw".enriched_events;' \
  -c 'SELECT * FROM analytics.stg_enriched_events LIMIT 5;'

# Check mart tables
PGPASSWORD=RedshiftPass1 psql "host=$(terraform output -raw redshift_endpoint) port=5439 dbname=pulsecart user=pulsecart_admin sslmode=require" \
  -c 'SELECT * FROM analytics.recommendation_coverage LIMIT 5;' \
  -c 'SELECT * FROM analytics.session_funnel LIMIT 5;'
```

If rows appear with valid `event_id`, `trace_id`, and `recommendations_json`, the full pipeline is working:
**Producer → Kinesis → Lambda → Kinesis → Redshift MV → dbt staging → dbt marts** ✅

## Interview talking points

- **"Streaming with what for what?"** — Kinesis Data Streams for ordered ingest, Lambda for stateless enrichment, DynamoDB for millisecond feature lookup, SageMaker for the ranker, Redshift Streaming Ingestion for zero-Firehose landing. Each choice pins to a specific latency / cost / coupling trade-off.
- **"Why not Firehose to S3?"** — Streaming Ingestion into a MV skips the S3 hop and gives us `< 10s` freshness in Redshift without a Glue job in the middle. Firehose is still the right answer if downstream needs S3 for other consumers.
- **"How do you test this without AWS?"** — Every AWS boundary has a fake with the same public surface (`FakeKinesisStream`, `FakeDynamoTable`, `ScriptedFakeScorer`). The `Scorer` contract has three implementations (Scripted / LocalLightGBM / SageMaker) — the enricher never branches. Full end-to-end runs on CI runners with no creds.
- **"How do you trace a bad recommendation back to a click?"** — `trace_id` is minted at the FastAPI ingest, put on the Kinesis record, echoed by the Scorer, and lands on the Redshift row. The dashboard shows the trace_id next to every recommendation; a single Redshift query walks it back.
- **"Where's the drift monitoring?"** — Deliberately in SignalFlow (Azure ML MLOps), not here. This project owns real-time inference; conflating it with training tooling would blur the story.
