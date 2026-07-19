-- One-to-one view over the raw landing table.
-- Extracts fields from the SUPER payload (Redshift) or directly from named
-- columns (DuckDB local). Normalises types so marts don't parse JSON.

{{ config(materialized='view') }}

{% if target.type == 'redshift' %}

SELECT
    approximate_arrival_timestamp                              AS ingested_at,
    json_parse."event_id"::VARCHAR(64)                         AS event_id,
    json_parse."trace_id"::VARCHAR(64)                         AS trace_id,
    json_parse."event_type"::VARCHAR(32)                       AS event_type,
    json_parse."user_id"::VARCHAR(64)                          AS user_id,
    json_parse."session_id"::VARCHAR(64)                       AS session_id,
    json_parse."timestamp"::VARCHAR::TIMESTAMP                 AS event_ts,
    json_parse."product_id"::VARCHAR(32)                       AS product_id,
    json_parse."category"::VARCHAR(32)                         AS category,
    json_parse."scored_at"::VARCHAR::TIMESTAMP                 AS scored_at,
    json_parse."scorer_latency_ms"::DOUBLE PRECISION           AS scorer_latency_ms,
    json_parse."model_version"::VARCHAR(32)                    AS model_version,
    json_parse."recommendations"                               AS recommendations_json
FROM {{ source('raw', 'enriched_events') }}

{% else %}

SELECT
    event_id,
    trace_id,
    event_type,
    user_id,
    session_id,
    CAST(event_ts AS TIMESTAMP)          AS event_ts,
    product_id,
    category,
    CAST(scored_at AS TIMESTAMP)         AS scored_at,
    scorer_latency_ms,
    model_version,
    recommendations_json                 AS recommendations_json
FROM {{ source('raw', 'enriched_events') }}

{% endif %}
