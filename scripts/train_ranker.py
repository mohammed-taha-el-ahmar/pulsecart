"""Train the LightGBM ranker artifact used by LocalLightGBMScorer.

This is a *one-off* offline training script — the project scope is serving-only
per the design decision, but a real model artifact makes the demo credible.
The synthetic data is generated deterministically so `train_ranker.py` produces
a byte-identical artifact for a given seed.

Run: `uv run python scripts/train_ranker.py`
Outputs: artifacts/ranker.joblib, artifacts/product_catalog.json
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np

ARTIFACTS = Path(__file__).parent.parent / "artifacts"
CATEGORIES = ["electronics", "apparel", "home", "beauty", "sports"]


def build_catalog(n_products: int = 200, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    catalog = []
    for i in range(1, n_products + 1):
        catalog.append(
            {
                "product_id": f"P{i:04d}",
                "category": rng.choice(CATEGORIES),
                "price": round(rng.uniform(5, 400), 2),
                "popularity_score": round(rng.random() ** 2, 4),  # skewed toward low
                "avg_rating": round(rng.uniform(3.0, 5.0), 2),
                "days_since_launch": rng.randint(1, 900),
            }
        )
    return catalog


def build_training_set(
    catalog: list[dict], seed: int = 11
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Generate synthetic (user, product) rows with a plausible relevance label.

    Relevance ~ f(popularity, price fit, category affinity, rating) + noise.
    """
    rng = np.random.default_rng(seed)
    n_users = 100
    per_user = 20
    X, y, groups = [], [], []
    for _ in range(n_users):
        tenure_days = rng.integers(0, 900)
        lifetime_orders = rng.integers(0, 30)
        avg_order_value = rng.uniform(15, 200)
        session_length = rng.integers(30, 900)
        events_in_session = rng.integers(1, 20)
        cart_value = rng.uniform(0, 300)
        aff_pref = {c: rng.random() for c in CATEGORIES}
        # Sample a candidate set for this user
        candidates = rng.choice(catalog, size=per_user, replace=False)
        for prod in candidates:
            aff = aff_pref[prod["category"]]
            price_fit = 1.0 - min(1.0, abs(prod["price"] - avg_order_value) / (avg_order_value + 1))
            relevance_score = (
                0.5 * prod["popularity_score"]
                + 0.25 * aff
                + 0.15 * price_fit
                + 0.10 * (prod["avg_rating"] - 3.0) / 2.0
                + rng.normal(0, 0.05)
            )
            label = int(np.clip(round(relevance_score * 4), 0, 4))
            X.append(
                [
                    tenure_days,
                    lifetime_orders,
                    avg_order_value,
                    session_length,
                    events_in_session,
                    cart_value,
                    prod["price"],
                    prod["popularity_score"],
                    prod["avg_rating"],
                    prod["days_since_launch"],
                    aff,
                ]
            )
            y.append(label)
        groups.append(per_user)
    return np.array(X, dtype=float), np.array(y, dtype=int), groups


FEATURE_NAMES = [
    "tenure_days",
    "lifetime_orders",
    "avg_order_value",
    "session_length_seconds",
    "events_in_session",
    "cart_value",
    "price",
    "popularity_score",
    "avg_rating",
    "days_since_launch",
    "category_affinity",
]


def train() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    catalog = build_catalog()
    X, y, groups = build_training_set(catalog)
    ranker = lgb.LGBMRanker(
        objective="lambdarank",
        n_estimators=80,
        learning_rate=0.1,
        num_leaves=15,
        min_child_samples=5,
        random_state=17,
        verbose=-1,
    )
    ranker.fit(X, y, group=groups, feature_name=FEATURE_NAMES)
    joblib.dump({"model": ranker, "feature_names": FEATURE_NAMES}, ARTIFACTS / "ranker.joblib")
    (ARTIFACTS / "product_catalog.json").write_text(json.dumps(catalog, indent=2))
    print(f"wrote {ARTIFACTS / 'ranker.joblib'}  ({len(catalog)} products)")


if __name__ == "__main__":
    train()
