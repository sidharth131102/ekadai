"""Late Data Replay DAG (§66, §67).

Too-late behavioral events (silver_events.is_too_late: arrived more than watermark + allowed
lateness after their event time) stay in Silver but are held out of Gold's normal event-time
processing. This DAG:

  1. detect    — records each too-late event in late_data_replay_queue (ids + metadata only;
                 the payload stays in Bronze) as PENDING.
  2. replay    — re-reads the exact event from Bronze by event_id; if it's there, decodable and
                 present in Silver, the record becomes PROCESSED, which is what admits the event
                 into Gold on its next refresh. Otherwise FAILED, retried up to 3 times.
  3. retention — drops PROCESSED records 30 days after processing (§95).

Every step is a single set-based MERGE/DELETE on the SQL warehouse (never per-event queries,
§57), keyed on the stable replay_id = xxhash64(event_id), so re-running any step is a no-op.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.databricks.operators.databricks_sql import DatabricksSqlOperator

QUEUE = "ekadai_databricks.silver.late_data_replay_queue"
SILVER_EVENTS = "ekadai_databricks.silver.silver_events"
BRONZE_EVENTS = "ekadai_databricks.bronze.bronze_events"
MAX_RETRIES = 3

CREATE_QUEUE = f"""
CREATE TABLE IF NOT EXISTS {QUEUE} (
  replay_id BIGINT NOT NULL,
  source_type STRING NOT NULL,
  source_table_or_topic STRING NOT NULL,
  record_id STRING NOT NULL,
  event_timestamp TIMESTAMP,
  detected_at TIMESTAMP NOT NULL,
  lateness_seconds DOUBLE,
  reason STRING,
  status STRING NOT NULL,
  retry_count INT NOT NULL,
  last_attempt_at TIMESTAMP,
  processed_at TIMESTAMP,
  error_message STRING
) COMMENT 'Late data replay queue (§67): ids/metadata of too-late events; payload stays in Bronze.'
"""

DETECT = f"""
MERGE INTO {QUEUE} AS q
USING (
  SELECT xxhash64(event_id) AS replay_id,
         concat('bronze.bronze_events/', kafka_topic) AS source_table_or_topic,
         event_id,
         event_timestamp,
         (unix_millis(kafka_timestamp) - unix_millis(event_timestamp)) / 1000.0 AS lateness_seconds
  FROM {SILVER_EVENTS}
  WHERE is_too_late
) AS s
ON q.replay_id = s.replay_id
WHEN NOT MATCHED THEN INSERT (
  replay_id, source_type, source_table_or_topic, record_id, event_timestamp, detected_at,
  lateness_seconds, reason, status, retry_count, last_attempt_at, processed_at, error_message
) VALUES (
  s.replay_id, 'BEHAVIORAL_EVENT', s.source_table_or_topic, s.event_id, s.event_timestamp, current_timestamp(),
  s.lateness_seconds,
  concat('reached Kafka ', cast(round(s.lateness_seconds) AS STRING),
         's after event time, beyond watermark + allowed lateness'),
  'PENDING', 0, NULL, NULL, NULL
)
"""

REPLAY = f"""
MERGE INTO {QUEUE} AS q
USING (
  SELECT c.replay_id,
         b.event_id IS NOT NULL AS in_bronze,
         s.event_id IS NOT NULL AS in_silver
  FROM {QUEUE} AS c
  LEFT JOIN (SELECT DISTINCT event_id FROM {BRONZE_EVENTS} WHERE decode_error IS NULL) AS b
    ON b.event_id = c.record_id
  LEFT JOIN (SELECT event_id FROM {SILVER_EVENTS}) AS s
    ON s.event_id = c.record_id
  WHERE c.status = 'PENDING' OR (c.status = 'FAILED' AND c.retry_count < {MAX_RETRIES})
) AS r
ON q.replay_id = r.replay_id
WHEN MATCHED AND r.in_bronze AND r.in_silver THEN UPDATE SET
  status = 'PROCESSED', processed_at = current_timestamp(), last_attempt_at = current_timestamp(),
  error_message = NULL
WHEN MATCHED THEN UPDATE SET
  status = 'FAILED', retry_count = q.retry_count + 1, last_attempt_at = current_timestamp(),
  error_message = CASE WHEN NOT r.in_bronze THEN 'event_id not found (decodable) in bronze_events'
                       ELSE 'event_id not present in silver_events' END
"""

RETENTION = f"""
DELETE FROM {QUEUE}
WHERE status = 'PROCESSED' AND processed_at < current_timestamp() - INTERVAL 30 DAYS
"""

common = {
    "databricks_conn_id": "databricks_default",
    "http_path": os.environ.get("EKADAI_SQL_WAREHOUSE_HTTP_PATH"),
}

with DAG(
    dag_id="late_data_replay",
    description="Queue and replay too-late behavioral events from Bronze (§66, §67).",
    start_date=datetime(2026, 9, 29),
    # Hourly: the spec only asks that too-late data be replayed "later" (§66), and every run
    # wakes the serverless SQL warehouse (auto-stop 1 min) — cost over replay latency.
    schedule=timedelta(hours=1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["ekadai", "late-data"],
) as dag:
    ensure_queue = DatabricksSqlOperator(task_id="ensure_queue", sql=CREATE_QUEUE, **common)
    detect = DatabricksSqlOperator(task_id="detect", sql=DETECT, **common)
    replay = DatabricksSqlOperator(task_id="replay", sql=REPLAY, **common)
    retention = DatabricksSqlOperator(task_id="retention", sql=RETENTION, **common)

    ensure_queue >> detect >> replay >> retention
