# PulseCart

Real-time e-commerce clickstream personalization on AWS. Kinesis → Lambda → DynamoDB feature lookup → SageMaker ranker → Redshift streaming ingestion → `GET /recommendations/{user_id}`.

Every recommendation is walkable back to the click that triggered it via a `trace_id` propagated end-to-end.

## Architecture

```
┌──────────────────┐   POST /events   ┌───────────────────────┐
│  Web / mobile    │  ──────────────▶ │  Ingestion (FastAPI)   │
│  analytics SDK   │                  │  emits ClickEvent      │
└──────────────────┘                  └───────────┬────────────┘
                                                  │
                                                  ▼
                                    ┌──────────────────────────┐
                                    │  Kinesis Data Stream     │
                                    │  pulsecart-raw-clicks    │
                                    └───────────┬──────────────┘
                                                │  ESM (batch=50)
                                                ▼
                        ┌────────────────────────────────────────────┐
                        │   Lambda enricher                          │
                        │   ─ decode ClickEvent                      │
                        │   ─ DynamoDB feature lookup                │
                        │      · user_features (tenure, LTV, aff.)  │
                        │      · product_features (candidates)      │
                        │   ─ session_features (in-mem window)       │
                        │   ─ SageMaker InvokeEndpoint (top-K)       │
                        │   ─ emit EnrichedEvent + trace_id          │
                        └───────────┬────────────────────────────────┘
                                    │
                                    ▼
                       ┌───────────────────────────┐
                       │  Kinesis Data Stream       │
                       │  pulsecart-enriched-clicks │
                       └───────────┬───────────────┘
                                   │  Redshift Streaming Ingestion (MV)
                                   ▼
                      ┌──────────────────────────────┐
                      │  Redshift Serverless         │
                      │  raw.enriched_events (MV)    │
                      │  dbt → staging → marts       │
                      └──────────┬───────────────────┘
                                 │
                                 ▼
                      ┌──────────────────────────────┐
                      │  FastAPI recommender + UI    │
                      │  GET /recommendations/{u}    │
                      │  Dashboard: /                │
                      └──────────────────────────────┘
```

## Quickstart (offline, no AWS credentials)

```bash
uv sync

uv pip install -e ".[dev,dbt]"

# 1. Train the LightGBM ranker artifact.
uv run python scripts/train_ranker.py

# 2. Run the pipeline locally (populates DuckDB warehouse).
uv run python scripts/run_local_demo.py

# 3. Serve the producer (ingestion API).
uv run uvicorn pulsecart.producer.api:create_app --factory --port 8000

# 4. Serve the dashboard (recommender API).
uv run uvicorn pulsecart.recommender_api.app:app --port 8080
open http://localhost:8080

# Or all-in-one:
docker compose up --build
```

Then run tests:

```bash
uv run pytest -v
ruff check .
```

## Deploying to AWS

```bash
# Build the Lambda package
scripts/build_lambda_zip.sh  # see DEMO.md

# Provision infra

# export AWS_PROFILE=yourprofile #ex incidentcouncil

cd infra

# terraform init \
#   -backend-config="bucket=my-pulsecart-tfstate" \
#   -backend-config="key=pulsecart/terraform.tfstate" \
#   -backend-config="region=eu-west-1"

terraform init -backend-config="bucket=my-pulsecart-tfstate" -backend-config="region=eu-west-1"
terraform plan -var="redshift_admin_password=RedshiftPass1"
terraform apply -var="redshift_admin_password=RedshiftPass1"

# Install psql if needed: brew install libpq && brew link --force libpq

# Wire up Redshift streaming ingestion (once)
PGPASSWORD=RedshiftPass1 psql "host=$(terraform output -raw redshift_endpoint) port=5439 dbname=pulsecart user=pulsecart_admin sslmode=require" \
  -v iam_role="$(terraform output -raw redshift_streaming_role_arn)" \
  -v stream_name="$(terraform output -raw enriched_stream_name)" \
  -f ../src/pulsecart/warehouse/redshift_streaming.sql
```

## Layout

```
src/pulsecart/
  ├─ producer/          FastAPI ingestion + synthetic simulator + Kinesis client
  ├─ enricher/          Lambda handler, feature lookup, scorer, session state
  ├─ warehouse/         DuckDB (local) + Redshift streaming DDL (cloud)
  ├─ recommender_api/   FastAPI + vanilla JS dashboard
  ├─ fakes/             In-memory Kinesis / DynamoDB / Scorer for offline CI
  ├─ observability/     LatencyTracker + CloudWatch EMF helpers
  ├─ schemas.py         Pydantic contracts at every boundary
  ├─ config.py          pydantic-settings, PULSECART_* env
  └─ tracing.py         trace_id propagation + structured JSON logging
dbt/                    layered analytics (staging → marts)
infra/                  Terraform (S3 backend, Kinesis, DynamoDB, Lambda, Redshift, IAM, alarms)
scripts/                train_ranker.py, run_local_demo.py
tests/                  50+ tests, all run without cloud creds
```

## Interview vocabulary

- **Serving-only ML lifecycle.** The LightGBM ranker artifact is checked in; SignalFlow (Azure ML) is the sibling project that owns the training + MLOps story. PulseCart's story is *real-time inference at Kinesis rates.*
- **Parity contract.** `Scorer.score(ScoreRequest) → ScoreResponse` has three implementations (`SageMakerScorer` / `LocalLightGBMScorer` / `ScriptedFakeScorer`) that are drop-in interchangeable. This is what lets `mode=local` execute the same enricher code as `mode=aws`.
- **Traceability first-class.** `trace_id` is minted at the FastAPI ingest, propagated on the Kinesis record, echoed by the Scorer, and stored on the Redshift row. Any recommendation on the dashboard maps back to the originating click.

See `DEMO.md` for the honest coverage matrix (what's proved locally, what needs cloud credentials, what's deliberately deferred).

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `RequestEntityTooLargeException` on Lambda create | Zip exceeds 50 MB inline limit | Lambda deploys via S3 (already configured in `lambda.tf`) |
| Redshift password rejected | Must contain uppercase + lowercase + digit | Use e.g. `RedshiftPass1` |
| `psql` connection timeout | Workgroup not publicly accessible, or SG missing inbound rule | Set `publicly_accessible = true` in `redshift.tf`; add inbound TCP 5439 from your IP (see below) |
| `psql` auth failure / `no pg_hba.conf entry` | Missing `sslmode=require` | Use connection string format with `sslmode=require` |
| `IAM_ROLE should start with "arn:aws"` | Shell variables not substituted in SQL | Pass values via psql `-v` variables |
| `Column aliases are not supported` in streaming MV | Redshift streaming MVs forbid CTEs, aliases, mutable casts | Land raw SUPER + timestamp only; extract in dbt |
| `terraform output` not found | Output not yet in state | Run `terraform apply` first |
| `source_code_hash` plan inconsistency | Using S3 etag (changes with multipart) | Use `filebase64sha256(var.lambda_package)` |
| `No module named 'pandas'` in Lambda | pandas was in the zip, exceeding 250MB unzipped limit | Removed pandas; LightGBM `predict()` accepts numpy arrays directly |
| `Unzipped size must be smaller than 262144000 bytes` | Too many deps in Lambda zip | Remove unnecessary packages (pandas, etc.); keep only numpy/scipy/sklearn/lightgbm |
| `Unable to locate credentials` from producer | `AWS_PROFILE` not set when running in `mode=aws` | Export `AWS_PROFILE=<profile>` before starting the producer |
| `libgomp.so.1: cannot open shared object file` in Lambda | libgomp not bundled in zip | `build_lambda_zip.sh` extracts it from `amazonlinux:2` Docker image into `lib/` |
| `GLIBC_2.32 not found` for libgomp in Lambda | libgomp was extracted from amazonlinux:2023 (too new) | Must use `amazonlinux:2` (Lambda Python 3.11 runs on AL2 with glibc 2.26); also add `/var/task/scikit_learn.libs` to `LD_LIBRARY_PATH` |
| `Could not find profile named 'pulsecart'` (dbt) | No `profiles.yml` file | `cp dbt/profiles.example.yml dbt/profiles.yml`; use `--profiles-dir .` |
| dbt target `redshift` not found | Profile defines `aws` not `redshift` | Use `--target aws` (or `--target local` for DuckDB) |
| SageMaker endpoint not found | No endpoint deployed | Set `PULSECART_SAGEMAKER_ENDPOINT_NAME=none` — enricher falls back to `LocalLightGBMScorer` |

> **Security group tip:** In the AWS Console, find the default VPC security group attached to your Redshift Serverless workgroup and add an inbound rule:
> - **Type:** Redshift (or Custom TCP)
> - **Port:** 5439
> - **Source:** Your public IP (e.g. `212.195.74.171/32` — find yours with `curl ifconfig.me`)
>
> Without this rule, `psql` connections will time out even with `publicly_accessible = true`.

## Useful commands

```bash
# ─── Local development ───────────────────────────────────────────────────────
uv sync && uv pip install -e ".[dev,dbt]"
uv run python scripts/train_ranker.py          # train ranker artifact
uv run python scripts/run_local_demo.py        # populate DuckDB
uv run uvicorn pulsecart.producer.api:create_app --factory --port 8000   # ingestion API
uv run uvicorn pulsecart.recommender_api.app:app --port 8080             # dashboard
uv run pytest -v                               # run all tests
ruff check . && ruff format --check .          # lint

# ─── Docker ──────────────────────────────────────────────────────────────────
docker compose up --build

# ─── Terraform ───────────────────────────────────────────────────────────────
export AWS_PROFILE=incidentcouncil
cd infra
terraform init -backend-config="bucket=my-pulsecart-tfstate" -backend-config="region=eu-west-1"
terraform plan  -var="redshift_admin_password=RedshiftPass1"
terraform apply -var="redshift_admin_password=RedshiftPass1"
terraform output                               # show all outputs

# ─── Redshift (psql) ────────────────────────────────────────────────────────
# Connect interactively
PGPASSWORD=RedshiftPass1 psql "host=$(terraform output -raw redshift_endpoint) port=5439 dbname=pulsecart user=pulsecart_admin sslmode=require"

# Apply streaming ingestion DDL
PGPASSWORD=RedshiftPass1 psql "host=$(terraform output -raw redshift_endpoint) port=5439 dbname=pulsecart user=pulsecart_admin sslmode=require" \
  -c 'DROP MATERIALIZED VIEW IF EXISTS "raw".enriched_events;' \
  -v iam_role="$(terraform output -raw redshift_streaming_role_arn)" \
  -v stream_name="$(terraform output -raw enriched_stream_name)" \
  -f ../src/pulsecart/warehouse/redshift_streaming.sql

# Check MV status
PGPASSWORD=RedshiftPass1 psql "host=$(terraform output -raw redshift_endpoint) port=5439 dbname=pulsecart user=pulsecart_admin sslmode=require" \
  -c "SELECT * FROM SVV_MV_INFO WHERE schema_name = 'raw';"

# Manual refresh + query
PGPASSWORD=RedshiftPass1 psql "host=$(terraform output -raw redshift_endpoint) port=5439 dbname=pulsecart user=pulsecart_admin sslmode=require" \
  -c 'REFRESH MATERIALIZED VIEW "raw".enriched_events;' \
  -c 'SELECT * FROM analytics.stg_enriched_events LIMIT 5;'

# ─── Lambda ──────────────────────────────────────────────────────────────────
bash scripts/build_lambda_zip.sh               # rebuild deployment package (no pandas!)
cd infra && terraform apply -var="redshift_admin_password=RedshiftPass1"  # redeploy
aws logs tail /aws/lambda/pulsecart-enricher --since 5m --region eu-west-1  # check logs

# Direct invoke (useful for debugging without waiting for Kinesis trigger):
echo '{"Records":[{"kinesis":{"data":"eyJldmVudF9pZCI6InRlc3QxMjMiLCJldmVudF90eXBlIjoicHJvZHVjdF92aWV3IiwidXNlcl9pZCI6IlUwMDAxIiwic2Vzc2lvbl9pZCI6IlMxIiwicHJvZHVjdF9pZCI6IlAwMDA3IiwidGltZXN0YW1wIjoiMjAyNi0wNy0xM1QxNTowMDowMFoifQ==","sequenceNumber":"1","partitionKey":"U0001","approximateArrivalTimestamp":1720882800}}]}' > /tmp/payload.json
aws lambda invoke --function-name pulsecart-enricher --payload fileb:///tmp/payload.json --region eu-west-1 /tmp/out.json && cat /tmp/out.json
# Expected: {"batchItemFailures": [], "successful": 1}

# ─── Kinesis ─────────────────────────────────────────────────────────────────
aws kinesis describe-stream --stream-name pulsecart-raw-clicks
aws kinesis describe-stream --stream-name pulsecart-enriched-clicks

# ─── Send test traffic ───────────────────────────────────────────────────────
# Producer in local mode (in-memory fake, no AWS needed):
uv run uvicorn pulsecart.producer.api:create_app --factory --port 8000

# Producer in AWS mode (writes to real Kinesis — needs AWS_PROFILE):
AWS_PROFILE=incidentcouncil PULSECART_MODE=aws \
  PULSECART_KINESIS_RAW_STREAM=pulsecart-raw-clicks PULSECART_AWS_REGION=eu-west-1 \
  uv run uvicorn pulsecart.producer.api:create_app --factory --port 8000

# Then send events:
curl -X POST http://localhost:8000/events \
  -H "Content-Type: application/json" \
  -d '{"event_type":"product_view","user_id":"U0001","session_id":"S1","product_id":"P0007"}'

# ─── dbt ─────────────────────────────────────────────────────────────────────
cd dbt
cp profiles.example.yml profiles.yml           # one-time setup
uv run dbt build --target local --profiles-dir .      # DuckDB locally
REDSHIFT_HOST=$(cd ../infra && terraform output -raw redshift_endpoint) \
  REDSHIFT_USER=pulsecart_admin REDSHIFT_PASSWORD=RedshiftPass1 \
  uv run dbt build --target aws --profiles-dir .      # against real Redshift

# ─── Cleanup ─────────────────────────────────────────────────────────────────
cd infra && terraform destroy -var="redshift_admin_password=RedshiftPass1"
```
