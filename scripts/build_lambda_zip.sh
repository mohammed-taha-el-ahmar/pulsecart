#!/usr/bin/env bash
# Build a Lambda deployment package for the enricher.
#
# The zip contains:
#   - src/pulsecart/ (application code)
#   - runtime deps (boto3 is provided by the Lambda runtime; we install the rest)
#
# Output: artifacts/enricher.zip

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
BUILD="$ROOT/artifacts/lambda-build"
OUT="$ROOT/artifacts/enricher.zip"

rm -rf "$BUILD" "$OUT"
mkdir -p "$BUILD"

# Deps (excluding what Lambda provides).
uv pip install \
    --target "$BUILD" \
    --python-platform x86_64-manylinux2014 \
    --python-version 3.11 \
    --only-binary=:all: \
    --upgrade \
    "pydantic>=2.7" "pydantic-settings>=2.3" python-json-logger \
    lightgbm numpy scikit-learn joblib

# LightGBM needs libgomp (OpenMP) which isn't in the Lambda runtime.
# Extract from Amazon Linux 2023 Docker image (same OS as Lambda python3.11).
mkdir -p "$BUILD/lib"
echo "Extracting libgomp from amazonlinux:2 (matches Lambda AL2 glibc)..."
docker run --rm --platform linux/amd64 -v "$BUILD/lib:/out" amazonlinux:2 \
    bash -c "yum install -y libgomp >/dev/null 2>&1 && cp /usr/lib64/libgomp.so.1 /out/"

# App code + model artifact (in-Lambda LightGBM fallback if SageMaker is offline)
cp -r "$ROOT/src/pulsecart" "$BUILD/"
if [ -f "$ROOT/artifacts/ranker.joblib" ]; then
    mkdir -p "$BUILD/artifacts"
    cp "$ROOT/artifacts/ranker.joblib" "$BUILD/artifacts/"
fi

( cd "$BUILD" && zip -qr "$OUT" . )
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
