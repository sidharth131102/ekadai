-- Phase 13 — observability area (§97–102): ekadai_databricks.ops, separate from Gold.
-- Sources: the pipeline's event log (published to ops.pipeline_event_log by the pipeline spec),
-- the lakehouse tables themselves, and small tables written by the Airflow ops DAGs.
-- Applied by databricks/provision.ps1 (statements separated by lines containing only ";").

-- --- tables written by Airflow -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ekadai_databricks.ops.kafka_offsets (
  captured_at TIMESTAMP, topic STRING, `partition` INT, earliest_offset BIGINT, latest_offset BIGINT
) COMMENT 'Kafka partition watermarks sampled by the kafka_cdc_health DAG (§98).'
;
CREATE TABLE IF NOT EXISTS ekadai_databricks.ops.cdc_connector_status (
  captured_at TIMESTAMP, connector STRING, connector_state STRING, task_states STRING, worker_id STRING, error STRING
) COMMENT 'Debezium connector/task state sampled by the kafka_cdc_health DAG.'
;
CREATE TABLE IF NOT EXISTS ekadai_databricks.ops.backfill_audit (
  backfill_id STRING, supersedes_backfill_id STRING, requested_by STRING, reason STRING,
  source_start TIMESTAMP, source_end TIMESTAMP, tables_refreshed STRING,
  pipeline_version STRING, git_commit STRING, pipeline_update_id STRING,
  started_at TIMESTAMP, finished_at TIMESTAMP, status STRING,
  input_count BIGINT, output_count BIGINT, rejected_count BIGINT, duplicate_count BIGINT,
  missing_count BIGINT, errors STRING, reconciliation_passed BOOLEAN
) COMMENT 'One row per backfill/recovery run (§93). Written by the backfill_reconcile DAG.'
;
CREATE TABLE IF NOT EXISTS ekadai_databricks.ops.reconciliation_results (
  backfill_id STRING, checked_at TIMESTAMP, check_name STRING, expected BIGINT, actual BIGINT, passed BOOLEAN, detail STRING
) COMMENT 'Per-check reconciliation results (§94).'
;

-- --- pipeline health (§99) ---------------------------------------------------------------------

CREATE OR REPLACE VIEW ekadai_databricks.ops.pipeline_runs
COMMENT 'One row per pipeline update: status, duration, cause, failures (§99).'
AS SELECT
  origin.update_id AS update_id,
  min(timestamp) AS started_at,
  max(timestamp) AS last_event_at,
  max_by(details:update_progress.state::string, timestamp) FILTER (WHERE event_type = 'update_progress') AS state,
  max(details:create_update.cause::string) AS cause,
  max(details:create_update.full_refresh::boolean) AS full_refresh,
  unix_timestamp(max(timestamp)) - unix_timestamp(min(timestamp)) AS duration_seconds,
  count_if(level = 'ERROR') AS error_events,
  count_if(event_type = 'flow_progress' AND details:flow_progress.status::string = 'FAILED') AS failed_flow_events,
  max(CASE WHEN level = 'ERROR' THEN message END) AS last_error
FROM ekadai_databricks.ops.pipeline_event_log
WHERE origin.update_id IS NOT NULL
GROUP BY origin.update_id
;
CREATE OR REPLACE VIEW ekadai_databricks.ops.pipeline_stage_metrics
COMMENT 'Pipeline → stage → flow metrics from the event log (§99 hierarchy).'
AS SELECT
  CASE
    WHEN origin.flow_name LIKE '%bronze%' THEN 'Bronze'
    WHEN origin.flow_name LIKE '%reference_resolution%' THEN 'Reference Resolution'
    WHEN origin.flow_name LIKE '%silver_events%' OR origin.flow_name LIKE '%silver_event_%' THEN 'Silver Events'
    WHEN origin.flow_name LIKE '%silver%' THEN 'Silver CDC'
    WHEN origin.flow_name LIKE '%gold%' THEN 'Gold Aggregation'
    ELSE 'Other'
  END AS stage,
  origin.flow_name AS flow_name,
  origin.update_id AS update_id,
  max_by(details:flow_progress.status::string, timestamp) AS last_status,
  max(CASE WHEN details:flow_progress.status::string IN ('COMPLETED', 'RUNNING') THEN timestamp END) AS last_success_at,
  count_if(details:flow_progress.status::string = 'FAILED') AS failed_batches,
  count_if(details:flow_progress.metrics.num_output_rows IS NOT NULL) AS batches,
  sum(details:flow_progress.metrics.num_output_rows::bigint) AS output_records,
  max_by(details:flow_progress.metrics.backlog_bytes::bigint, timestamp) AS latest_backlog_bytes,
  max(timestamp) AS last_event_at
FROM ekadai_databricks.ops.pipeline_event_log
WHERE event_type = 'flow_progress'
GROUP BY 1, 2, 3
;

-- --- latency (§58) -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW ekadai_databricks.ops.latency_metrics
COMMENT 'Hourly ingestion / processing / end-to-end latency percentiles, seconds (§58).'
AS SELECT
  date_trunc('HOUR', event_timestamp) AS hour,
  count(*) AS events,
  percentile((unix_millis(ingestion_timestamp) - unix_millis(event_timestamp)) / 1000.0, 0.5) AS ingestion_p50_s,
  percentile((unix_millis(ingestion_timestamp) - unix_millis(event_timestamp)) / 1000.0, 0.95) AS ingestion_p95_s,
  percentile((unix_millis(processing_timestamp) - unix_millis(ingestion_timestamp)) / 1000.0, 0.5) AS processing_p50_s,
  percentile((unix_millis(processing_timestamp) - unix_millis(ingestion_timestamp)) / 1000.0, 0.95) AS processing_p95_s,
  percentile((unix_millis(processing_timestamp) - unix_millis(event_timestamp)) / 1000.0, 0.5) AS end_to_end_p50_s,
  percentile((unix_millis(processing_timestamp) - unix_millis(event_timestamp)) / 1000.0, 0.95) AS end_to_end_p95_s
FROM ekadai_databricks.silver.silver_events
GROUP BY 1
;

-- --- data quality (§99) ------------------------------------------------------------------------

CREATE OR REPLACE VIEW ekadai_databricks.ops.data_quality_metrics
COMMENT 'Daily behavioral data quality: decode failures, quarantine by type, late data, unresolved references.'
AS WITH b AS (
  SELECT to_date(ingestion_timestamp) AS d, count(*) AS bronze_records, count_if(decode_error IS NOT NULL) AS decode_failures
  FROM ekadai_databricks.bronze.bronze_events GROUP BY 1
), s AS (
  SELECT to_date(ingestion_timestamp) AS d, count(*) AS valid_events,
         count_if(is_late) AS late_events, count_if(is_too_late) AS too_late_events,
         count_if(reference_status = 'UNRESOLVED') AS unresolved_events,
         count_if(reference_status = 'PARTIALLY_RESOLVED') AS partially_resolved_events
  FROM ekadai_databricks.silver.silver_events GROUP BY 1
), q AS (
  SELECT to_date(ingestion_timestamp) AS d, count(*) AS quarantined,
         count_if(error_type = 'MALFORMED') AS malformed,
         count_if(error_type = 'SCHEMA_INVALID') AS schema_invalid,
         count_if(error_type = 'BUSINESS_RULE') AS business_rule_failures
  FROM ekadai_databricks.silver.silver_event_quarantine GROUP BY 1
)
SELECT coalesce(b.d, s.d, q.d) AS date,
       coalesce(bronze_records, 0) AS bronze_records, coalesce(decode_failures, 0) AS decode_failures,
       coalesce(valid_events, 0) AS valid_events, coalesce(quarantined, 0) AS quarantined,
       coalesce(malformed, 0) AS malformed, coalesce(schema_invalid, 0) AS schema_invalid,
       coalesce(business_rule_failures, 0) AS business_rule_failures,
       coalesce(quarantined, 0) / nullif(coalesce(valid_events, 0) + coalesce(quarantined, 0), 0) AS quarantine_rate,
       coalesce(late_events, 0) AS late_events, coalesce(too_late_events, 0) AS too_late_events,
       coalesce(unresolved_events, 0) AS unresolved_events,
       coalesce(partially_resolved_events, 0) AS partially_resolved_events
FROM b FULL OUTER JOIN s ON s.d = b.d FULL OUTER JOIN q ON q.d = coalesce(b.d, s.d)
;

-- --- reference resolution (§101) ---------------------------------------------------------------

CREATE OR REPLACE VIEW ekadai_databricks.ops.reference_resolution_status
COMMENT 'Reference resolution backlog, latency, failures and retries (§101).'
AS SELECT
  reference_type,
  count(*) AS references_needed,
  count_if(status = 'PENDING') AS pending_backlog,
  count_if(status = 'PROCESSING') AS processing,
  count_if(status = 'RESOLVED') AS resolved,
  count_if(status = 'FAILED') AS failed,
  sum(retry_count) AS total_retries,
  sum(affected_event_count) AS affected_events,
  avg(unix_timestamp(resolved_at) - unix_timestamp(first_seen_at)) FILTER (WHERE resolved_at IS NOT NULL) AS avg_resolution_latency_s,
  percentile(unix_timestamp(resolved_at) - unix_timestamp(first_seen_at), 0.5) FILTER (WHERE resolved_at IS NOT NULL) AS median_resolution_latency_s,
  min(first_seen_at) FILTER (WHERE status IN ('PENDING', 'FAILED')) AS oldest_unresolved_first_seen_at,
  unix_timestamp(current_timestamp()) - unix_timestamp(min(first_seen_at) FILTER (WHERE status IN ('PENDING', 'FAILED'))) AS oldest_unresolved_age_s
FROM ekadai_databricks.silver.reference_resolution_queue
GROUP BY reference_type
;

-- --- late data / replay (§102) -----------------------------------------------------------------

CREATE OR REPLACE VIEW ekadai_databricks.ops.late_replay_status
COMMENT 'Late-data replay backlog, success, failure, latency (§102).'
AS SELECT
  count(*) AS replay_records,
  count_if(status = 'PENDING') AS replay_backlog,
  count_if(status = 'PROCESSED') AS replay_succeeded,
  count_if(status = 'FAILED') AS replay_failed,
  sum(retry_count) AS total_retries,
  avg(unix_timestamp(processed_at) - unix_timestamp(detected_at)) FILTER (WHERE processed_at IS NOT NULL) AS avg_replay_latency_s,
  min(detected_at) FILTER (WHERE status IN ('PENDING', 'FAILED')) AS oldest_open_replay_detected_at,
  max(lateness_seconds) AS max_lateness_s
FROM ekadai_databricks.silver.late_data_replay_queue
;

-- --- Kafka (§98) -------------------------------------------------------------------------------

CREATE OR REPLACE VIEW ekadai_databricks.ops.kafka_lag
COMMENT 'Per-partition lag = latest Kafka offset (last DAG sample) − last offset in Bronze; plus traffic share for hot-partition/imbalance checks (§98).'
AS WITH latest AS (
  SELECT * FROM ekadai_databricks.ops.kafka_offsets
  QUALIFY row_number() OVER (PARTITION BY topic, `partition` ORDER BY captured_at DESC) = 1
), bronze AS (
  SELECT kafka_topic AS topic, kafka_partition AS `partition`, max(kafka_offset) AS bronze_max_offset FROM ekadai_databricks.bronze.bronze_events GROUP BY 1, 2
  UNION ALL SELECT kafka_topic, kafka_partition, max(kafka_offset) FROM ekadai_databricks.bronze.bronze_cdc_users GROUP BY 1, 2
  UNION ALL SELECT kafka_topic, kafka_partition, max(kafka_offset) FROM ekadai_databricks.bronze.bronze_cdc_products GROUP BY 1, 2
  UNION ALL SELECT kafka_topic, kafka_partition, max(kafka_offset) FROM ekadai_databricks.bronze.bronze_cdc_categories GROUP BY 1, 2
  UNION ALL SELECT kafka_topic, kafka_partition, max(kafka_offset) FROM ekadai_databricks.bronze.bronze_cdc_orders GROUP BY 1, 2
  UNION ALL SELECT kafka_topic, kafka_partition, max(kafka_offset) FROM ekadai_databricks.bronze.bronze_cdc_order_items GROUP BY 1, 2
)
SELECT l.topic, l.`partition`, l.captured_at, l.earliest_offset, l.latest_offset,
       b.bronze_max_offset,
       -- latest_offset is the next offset to be written; Bronze has consumed up to bronze_max_offset.
       greatest(l.latest_offset - coalesce(b.bronze_max_offset + 1, l.earliest_offset), 0) AS lag_messages,
       l.latest_offset - l.earliest_offset AS retained_messages,
       (l.latest_offset - l.earliest_offset) / nullif(sum(l.latest_offset - l.earliest_offset) OVER (PARTITION BY l.topic), 0) AS partition_share
FROM latest l LEFT JOIN bronze b ON b.topic = l.topic AND b.`partition` = l.`partition`
;
CREATE OR REPLACE VIEW ekadai_databricks.ops.cdc_connector_health
COMMENT 'Latest Debezium connector state (§98).'
AS SELECT * FROM ekadai_databricks.ops.cdc_connector_status
QUALIFY row_number() OVER (PARTITION BY connector ORDER BY captured_at DESC) = 1
;

-- --- retention (§95) ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW ekadai_databricks.ops.retention_status
COMMENT 'Oldest record per governed table vs its §95 retention policy.'
AS SELECT *, datediff(current_date(), to_date(oldest_record)) AS oldest_age_days,
          datediff(current_date(), to_date(oldest_record)) > retention_days AS overdue
FROM (
  SELECT 'bronze.bronze_events' AS table_name, 90 AS retention_days, min(ingestion_timestamp) AS oldest_record FROM ekadai_databricks.bronze.bronze_events
  UNION ALL SELECT 'bronze.bronze_cdc_orders', 90, min(ingestion_timestamp) FROM ekadai_databricks.bronze.bronze_cdc_orders
  UNION ALL SELECT 'silver.silver_events', 90, min(ingestion_timestamp) FROM ekadai_databricks.silver.silver_events
  UNION ALL SELECT 'silver.silver_event_quarantine', 30, min(detected_at) FROM ekadai_databricks.silver.silver_event_quarantine
  UNION ALL SELECT 'silver.late_data_replay_queue (processed)', 30, min(processed_at) FROM ekadai_databricks.silver.late_data_replay_queue WHERE status = 'PROCESSED'
)
;
