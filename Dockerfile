FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for lightgbm's shared libs
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY artifacts ./artifacts

RUN pip install --upgrade pip && pip install -e .

EXPOSE 8080
CMD ["uvicorn", "pulsecart.recommender_api.app:app", "--host", "0.0.0.0", "--port", "8080"]
