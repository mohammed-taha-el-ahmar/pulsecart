-- Recommendation coverage per user, per day.
-- Answers: "for a given user, how many distinct products has the ranker
-- surfaced, and what's the average scorer latency?" — the two questions that
-- come up first in every scale-of-personalization review.

{{ config(materialized='table') }}

SELECT
    user_id,
    CAST(event_ts AS DATE)                    AS event_date,
    COUNT(*)                                  AS n_scored_events,
    AVG(scorer_latency_ms)                    AS avg_scorer_latency_ms,
    MAX(scorer_latency_ms)                    AS max_scorer_latency_ms,
    MIN(scored_at)                            AS first_scored_at,
    MAX(scored_at)                            AS last_scored_at
FROM {{ ref('stg_enriched_events') }}
GROUP BY user_id, CAST(event_ts AS DATE)
