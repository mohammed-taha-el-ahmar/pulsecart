-- =============================================================================
-- Redshift Streaming Ingestion for PulseCart enriched clickstream.
-- =============================================================================
-- Applied by CI or a one-off `psql < redshift_streaming.sql` after `terraform
-- apply`. This is the *only* piece of Redshift setup that lives in SQL rather
-- than dbt; dbt handles the layered analytics models downstream.
--
-- The materialized view auto-refreshes and reads directly from the enriched
-- Kinesis stream. Redshift Serverless workgroup + IAM role are provisioned by
-- Terraform; this file just wires up the ingestion contract.
--
-- Run once, per environment.
-- =============================================================================

CREATE EXTERNAL SCHEMA IF NOT EXISTS pulsecart_kinesis
FROM KINESIS
IAM_ROLE :'iam_role';

CREATE SCHEMA IF NOT EXISTS "raw";

-- The materialized view is the streaming target. Redshift streaming MVs are
-- highly restrictive (no CTEs, no column aliases, no mutable casts), so we
-- land the raw SUPER payload here and extract/cast in the dbt staging layer.
CREATE MATERIALIZED VIEW "raw".enriched_events
    AUTO REFRESH YES
AS
SELECT
    approximate_arrival_timestamp,
    JSON_PARSE(FROM_VARBYTE(kinesis_data, 'utf-8'))
FROM pulsecart_kinesis.:"stream_name";

-- One-shot refresh to prime the MV; AUTO REFRESH takes over from here.
REFRESH MATERIALIZED VIEW "raw".enriched_events;
