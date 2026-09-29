"""Kafka + CDC health sampling (§98).

Every 30 minutes: sample each topic partition's earliest/latest offsets from the broker and the
Debezium connector/task state from Kafka Connect, and append them to
ekadai_databricks.ops.kafka_offsets / ops.cdc_connector_status. The ops.kafka_lag view turns the
offsets into per-partition lag against what Bronze has actually ingested, plus the traffic share
per partition for hot-partition / imbalance checks.

The pipeline reads Kafka without a consumer group (the Spark Kafka source tracks offsets in its
own checkpoint), so "consumer lag" is computed from Bronze's last ingested offset, not from a
group's committed offsets.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.databricks.hooks.databricks_sql import DatabricksSqlHook

BOOTSTRAP = os.environ.get("EKADAI_KAFKA_BOOTSTRAP", "kafka:9092")
CONNECT_URL = os.environ.get("EKADAI_CONNECT_URL", "http://connect:8083")
HTTP_PATH = os.environ.get("EKADAI_SQL_WAREHOUSE_HTTP_PATH")
TOPICS = [
    "user-events", "product-events", "cart-events", "checkout-events", "order-events",
    "cdc-users", "cdc-products", "cdc-categories", "cdc-orders", "cdc-order-items",
]


def _q(value) -> str:
    """SQL string literal (values come from our own broker/Connect responses)."""
    return "NULL" if value is None else "'" + str(value).replace("'", "''")[:2000] + "'"


def sample(**_):
    from confluent_kafka import Consumer, TopicPartition

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": "ekadai-ops-health", "enable.auto.commit": False})
    offset_rows = []
    try:
        metadata = consumer.list_topics(timeout=15)
        for topic in TOPICS:
            if topic not in metadata.topics:
                continue
            for partition in sorted(metadata.topics[topic].partitions):
                low, high = consumer.get_watermark_offsets(TopicPartition(topic, partition), timeout=15)
                offset_rows.append(f"(TIMESTAMP'{now}', {_q(topic)}, {partition}, {low}, {high})")
    finally:
        consumer.close()

    connector_rows = []
    try:
        with urllib.request.urlopen(f"{CONNECT_URL}/connectors?expand=status", timeout=15) as resp:
            for name, info in json.loads(resp.read()).items():
                status = info["status"]
                tasks = ",".join(f"{t['id']}:{t['state']}" for t in status.get("tasks", []))
                errors = " | ".join(t.get("trace", "")[:500] for t in status.get("tasks", []) if t.get("trace"))
                connector_rows.append(
                    f"(TIMESTAMP'{now}', {_q(name)}, {_q(status['connector']['state'])}, {_q(tasks)}, "
                    f"{_q(status['connector'].get('worker_id'))}, {_q(errors or None)})"
                )
    except Exception as exc:  # noqa: BLE001 — Connect being down IS the signal to record
        connector_rows.append(f"(TIMESTAMP'{now}', 'ekadai-postgres-cdc', 'UNREACHABLE', NULL, NULL, {_q(repr(exc))})")

    hook = DatabricksSqlHook(databricks_conn_id="databricks_default", http_path=HTTP_PATH)
    statements = []
    if offset_rows:
        statements.append("INSERT INTO ekadai_databricks.ops.kafka_offsets VALUES " + ", ".join(offset_rows))
    statements.append("INSERT INTO ekadai_databricks.ops.cdc_connector_status VALUES " + ", ".join(connector_rows))
    hook.run(statements)
    print(f"sampled {len(offset_rows)} partitions, {len(connector_rows)} connector rows")


with DAG(
    dag_id="kafka_cdc_health",
    description="Sample Kafka partition offsets and Debezium connector state into ops (§98).",
    start_date=datetime(2026, 9, 29),
    schedule=timedelta(minutes=30),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["ekadai", "observability"],
) as dag:
    PythonOperator(task_id="sample_kafka_and_cdc", python_callable=sample)
