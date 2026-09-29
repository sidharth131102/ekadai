"""Backfill + reconciliation (§93, §94). Triggered manually with parameters; never scheduled.

Silver and Gold are deterministic functions of Bronze (behavioral) and Bronze CDC, so a backfill
is: rebuild the selected pipeline tables from Bronze (a pipeline update with
`full_refresh_selection`), then reconcile what came out against what went in. Every run gets a
`backfill_id` and one row in ops.backfill_audit (start/end, source range, pipeline version,
git commit, pipeline update id, input/output/rejected/duplicate/missing counts, errors,
reconciliation verdict); each individual check lands in ops.reconciliation_results. A corrective
run names the run it supersedes (`supersedes_backfill_id`).

Idempotent: rebuilding from the same Bronze yields the same rows (stable event_ids, hashed keys,
MERGE/upsert semantics), so re-running the same range changes nothing but adds an audit row.
`refresh=false` runs reconciliation only (an audit of the current state).

Continuous pipelines reject a selective refresh, so if the pipeline is continuous the DAG
switches it to triggered for the refresh and restores continuous mode afterwards.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from datetime import datetime, timedelta

from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.models.param import Param
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.hooks.sql import fetch_all_handler
from airflow.providers.databricks.hooks.databricks_sql import DatabricksSqlHook

PIPELINE_ID = os.environ.get("EKADAI_PIPELINE_ID")
HTTP_PATH = os.environ.get("EKADAI_SQL_WAREHOUSE_HTTP_PATH")
C = "ekadai_databricks"
DEFAULT_TABLES = [
    f"{C}.silver.silver_events", f"{C}.silver.silver_event_filters", f"{C}.silver.silver_event_quarantine",
    f"{C}.silver.silver_cdc_orders", f"{C}.silver.silver_cdc_order_items",
    f"{C}.silver.silver_products_history", f"{C}.silver.silver_categories_history", f"{C}.silver.silver_users_history",
]
# Downstream of Silver: refreshed (recomputed, not reset) in the same update, so reconciliation
# sees Gold built from the rebuilt Silver.
DOWNSTREAM = [
    f"{C}.silver.reference_resolution_queue",
    *(f"{C}.gold.{t}" for t in (
        "dim_date", "dim_device", "dim_category", "dim_user", "dim_product",
        "fact_events", "fact_orders", "fact_order_items", "fact_sessions",
        "agg_user_activity", "agg_conversion_funnel", "agg_product_performance",
        "agg_daily_revenue", "agg_order_metrics", "agg_product_attribution",
    )),
]


def _sql():
    return DatabricksSqlHook(databricks_conn_id="databricks_default", http_path=HTTP_PATH)


def _q(v) -> str:
    return "NULL" if v is None else "'" + str(v).replace("'", "''")[:4000] + "'"


def _api(method: str, path: str, body: dict | None = None) -> dict:
    conn = BaseHook.get_connection("databricks_default")
    req = urllib.request.Request(
        conn.host.rstrip("/") + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {conn.password}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def start_audit(params, run_id, ti, **_):
    backfill_id = f"bf-{datetime.utcnow():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    spec = _api("GET", f"/api/2.0/pipelines/{PIPELINE_ID}")["spec"]
    version = spec.get("configuration", {}).get("ekadai.pipeline_version", "unknown")
    tables = params["tables"] or DEFAULT_TABLES
    _sql().run(f"""
      INSERT INTO {C}.ops.backfill_audit (backfill_id, supersedes_backfill_id, requested_by, reason, source_start,
        source_end, tables_refreshed, pipeline_version, git_commit, started_at, status)
      VALUES ({_q(backfill_id)}, {_q(params['supersedes_backfill_id'] or None)}, {_q(run_id)}, {_q(params['reason'])},
        TIMESTAMP{_q(params['source_start'])}, TIMESTAMP{_q(params['source_end'])},
        {_q(','.join(tables) if params['refresh'] else '(reconcile only)')}, {_q(version)}, {_q(params['git_commit'])},
        current_timestamp(), 'RUNNING')
    """)
    ti.xcom_push(key="backfill_id", value=backfill_id)
    ti.xcom_push(key="tables", value=tables)


def refresh(params, ti, **_):
    if not params["refresh"]:
        print("refresh=false: reconciliation only")
        return
    tables = ti.xcom_pull(key="tables")
    got = _api("GET", f"/api/2.0/pipelines/{PIPELINE_ID}")
    spec = got["spec"]
    was_continuous = bool(spec.get("continuous"))
    if was_continuous:
        _api("PUT", f"/api/2.0/pipelines/{PIPELINE_ID}", {**spec, "id": PIPELINE_ID, "continuous": False})
        for _ in range(60):  # wait for the running continuous update to stop
            if _api("GET", f"/api/2.0/pipelines/{PIPELINE_ID}").get("state") == "IDLE":
                break
            time.sleep(10)
    try:
        body = {"full_refresh_selection": tables, "refresh_selection": [t for t in DOWNSTREAM if t not in tables]}
        update_id = _api("POST", f"/api/2.0/pipelines/{PIPELINE_ID}/updates", body)["update_id"]
        ti.xcom_push(key="update_id", value=update_id)
        state = None
        for _ in range(180):
            state = _api("GET", f"/api/2.0/pipelines/{PIPELINE_ID}/updates/{update_id}")["update"]["state"]
            if state in ("COMPLETED", "FAILED", "CANCELED"):
                break
            time.sleep(10)
        if state != "COMPLETED":
            raise RuntimeError(f"pipeline update {update_id} ended {state}")
    finally:
        if was_continuous:
            _api("PUT", f"/api/2.0/pipelines/{PIPELINE_ID}", {**spec, "id": PIPELINE_ID, "continuous": True})


def _admitted(start: str, end: str) -> str:
    # Same admission rule as Gold (gold_pipeline.py ADMITTED), limited to the source range.
    return f"""
      SELECT e.event_id FROM {C}.silver.silver_events e
      WHERE e.kafka_timestamp >= TIMESTAMP{_q(start)} AND e.kafka_timestamp < TIMESTAMP{_q(end)}
        AND (NOT coalesce(e.is_too_late, false)
             OR e.event_id IN (SELECT record_id FROM {C}.silver.late_data_replay_queue WHERE status = 'PROCESSED'))
        AND (e.product_id IS NULL OR e.product_id NOT IN (SELECT product_id FROM {C}.silver.silver_products WHERE brand = 'zz-test'))
    """


def reconcile(params, ti, **_):
    backfill_id = ti.xcom_pull(key="backfill_id")
    s, e = params["source_start"], params["source_end"]
    rng = f"kafka_timestamp >= TIMESTAMP{_q(s)} AND kafka_timestamp < TIMESTAMP{_q(e)}"
    # (check_name, expected SQL, actual SQL) — each must return a single number.
    checks = [
        ("bronze_decodable_ids_all_accounted_for",
         f"SELECT count(DISTINCT event_id) FROM {C}.bronze.bronze_events WHERE {rng} AND decode_error IS NULL AND event_id IS NOT NULL",
         f"""SELECT count(DISTINCT b.event_id) FROM {C}.bronze.bronze_events b
             WHERE b.{rng} AND b.decode_error IS NULL AND b.event_id IS NOT NULL
               AND (b.event_id IN (SELECT event_id FROM {C}.silver.silver_events)
                    OR b.event_id IN (SELECT event_id FROM {C}.silver.silver_event_quarantine WHERE event_id IS NOT NULL))"""),
        ("bronze_undecodable_all_quarantined",
         f"SELECT count(*) FROM {C}.bronze.bronze_events WHERE {rng} AND decode_error IS NOT NULL",
         f"""SELECT count(*) FROM {C}.bronze.bronze_events b JOIN {C}.silver.silver_event_quarantine q
               ON q.kafka_topic = b.kafka_topic AND q.kafka_partition = b.kafka_partition AND q.kafka_offset = b.kafka_offset
             WHERE b.{rng} AND b.decode_error IS NOT NULL AND q.error_type = 'MALFORMED'"""),
        ("silver_events_no_duplicate_event_id",
         f"SELECT count(DISTINCT event_id) FROM {C}.silver.silver_events WHERE {rng}",
         f"SELECT count(*) FROM {C}.silver.silver_events WHERE {rng}"),
        ("gold_fact_events_match_admitted_silver",
         f"SELECT count(*) FROM ({_admitted(s, e)})",
         f"SELECT count(*) FROM {C}.gold.fact_events WHERE event_id IN ({_admitted(s, e)})"),
        ("gold_fact_orders_one_row_per_order",
         f"SELECT count(DISTINCT order_id) FROM {C}.silver.silver_cdc_orders WHERE operation <> 'DELETE'",
         f"SELECT count(*) FROM {C}.gold.fact_orders"),
        ("gold_fact_order_items_one_row_per_item",
         f"SELECT count(DISTINCT order_item_id) FROM {C}.silver.silver_cdc_order_items WHERE operation <> 'DELETE'",
         f"SELECT count(*) FROM {C}.gold.fact_order_items"),
        ("agg_order_metrics_count_matches_fact_orders",
         f"SELECT count(*) FROM {C}.gold.fact_orders",
         f"SELECT coalesce(sum(order_count), 0) FROM {C}.gold.agg_order_metrics"),
        ("agg_daily_revenue_net_matches_line_revenue_cents",
         f"SELECT CAST(coalesce(sum(line_revenue), 0) * 100 AS BIGINT) FROM {C}.gold.fact_order_items",
         f"SELECT CAST(coalesce(sum(net_transaction_sales), 0) * 100 AS BIGINT) FROM {C}.gold.agg_daily_revenue"),
    ]
    hook = _sql()
    results = []
    for name, exp_sql, act_sql in checks:
        expected = hook.run(exp_sql, handler=fetch_all_handler)[0][0]
        actual = hook.run(act_sql, handler=fetch_all_handler)[0][0]
        results.append((name, int(expected or 0), int(actual or 0)))
    hook.run(f"INSERT INTO {C}.ops.reconciliation_results VALUES " + ", ".join(
        f"({_q(backfill_id)}, current_timestamp(), {_q(n)}, {x}, {a}, {str(x == a).lower()}, "
        f"{_q('ok' if x == a else f'expected {x}, got {a}')})" for n, x, a in results))

    counts = hook.run(f"""
      SELECT (SELECT count(*) FROM {C}.bronze.bronze_events WHERE {rng}) AS input_count,
             (SELECT count(*) FROM {C}.silver.silver_events WHERE {rng}) AS output_count,
             (SELECT count(*) FROM {C}.silver.silver_event_quarantine WHERE {rng}) AS rejected_count,
             (SELECT count(*) - count(DISTINCT event_id) FROM {C}.bronze.bronze_events WHERE {rng} AND event_id IS NOT NULL) AS duplicate_count
    """, handler=fetch_all_handler)[0]
    missing = results[0][1] - results[0][2] + results[1][1] - results[1][2]
    passed = all(x == a for _, x, a in results)
    failures = "; ".join(f"{n}: expected {x}, got {a}" for n, x, a in results if x != a)
    hook.run(f"""
      UPDATE {C}.ops.backfill_audit SET
        pipeline_update_id = {_q(ti.xcom_pull(key='update_id'))}, finished_at = current_timestamp(),
        status = {_q('SUCCEEDED' if passed else 'RECONCILIATION_FAILED')},
        input_count = {counts[0]}, output_count = {counts[1]}, rejected_count = {counts[2]},
        duplicate_count = {counts[3]}, missing_count = {missing}, errors = {_q(failures or None)},
        reconciliation_passed = {str(passed).lower()}
      WHERE backfill_id = {_q(backfill_id)}
    """)
    for n, x, a in results:
        print(f"{'PASS' if x == a else 'FAIL'} {n}: expected={x} actual={a}")
    if not passed:
        raise RuntimeError(f"reconciliation failed: {failures}")


def mark_failed(ti, **_):
    backfill_id = ti.xcom_pull(key="backfill_id")
    if backfill_id:
        _sql().run(f"""UPDATE {C}.ops.backfill_audit SET status = 'FAILED', finished_at = current_timestamp()
                       WHERE backfill_id = {_q(backfill_id)} AND status = 'RUNNING'""")


with DAG(
    dag_id="backfill_reconcile",
    description="Rebuild Silver/Gold from Bronze for a range and reconcile, with a full audit trail (§93, §94).",
    start_date=datetime(2026, 9, 29),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    params={
        "source_start": Param((datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"), type="string"),
        "source_end": Param((datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"), type="string"),
        "refresh": Param(True, type="boolean", description="false = reconcile only"),
        "tables": Param([], type="array", description="Fully-qualified tables to rebuild; empty = all Silver"),
        "reason": Param("manual backfill", type="string"),
        "supersedes_backfill_id": Param("", type="string"),
        "git_commit": Param("uncommitted", type="string"),
    },
    tags=["ekadai", "backfill"],
) as dag:
    t_start = PythonOperator(task_id="start_audit", python_callable=start_audit)
    t_refresh = PythonOperator(task_id="refresh_from_bronze", python_callable=refresh)
    t_reconcile = PythonOperator(task_id="reconcile", python_callable=reconcile)
    t_fail = PythonOperator(task_id="mark_failed_if_needed", python_callable=mark_failed, trigger_rule="one_failed")
    t_start >> t_refresh >> t_reconcile >> t_fail
