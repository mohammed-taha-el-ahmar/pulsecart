-- Session funnel: for every session, count how far it got.
-- Used by the dashboard "conversion rate" panel and by the analytics team to
-- monitor whether personalization is moving cart-→purchase conversion.

{{ config(materialized='table') }}

WITH events AS (
    SELECT session_id, event_type, event_ts
    FROM {{ ref('stg_enriched_events') }}
)
SELECT
    session_id,
    MIN(event_ts)                                         AS session_started_at,
    MAX(event_ts)                                         AS session_ended_at,
    COUNT(*)                                              AS total_events,
    SUM(CASE WHEN event_type = 'product_view'  THEN 1 ELSE 0 END) AS n_product_views,
    SUM(CASE WHEN event_type = 'add_to_cart'   THEN 1 ELSE 0 END) AS n_add_to_cart,
    SUM(CASE WHEN event_type = 'purchase'      THEN 1 ELSE 0 END) AS n_purchases,
    MAX(CASE WHEN event_type = 'purchase'      THEN 1 ELSE 0 END) AS converted
FROM events
GROUP BY session_id
