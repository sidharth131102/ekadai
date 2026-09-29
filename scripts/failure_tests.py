"""Failure/recovery scenario injector (§107). Each subcommand performs ONE injection against the
live system and prints what to check; docs/failure_testing.md is the scenario matrix with the
verification queries and recorded results.

    python scripts/failure_tests.py <scenario> [--api http://localhost:8000]

Scenarios:
  malformed-avro        garbage bytes on product-events                → Bronze decode_error, quarantine MALFORMED
  business-rule         add_to_cart with quantity_added=0              → quarantine BUSINESS_RULE
  duplicate-event       the same envelope produced twice              → one silver_events row
  unknown-refs          product_view for a product that doesn't exist → UNRESOLVED; page_view w/ known category → PARTIAL
  late-events           events stamped 12 and 20 minutes in the past   → is_late / is_too_late; replay DAG queues the 20-min one
  duplicate-cdc         re-produce an existing cdc-orders message      → no extra change-log row
  out-of-order-cdc      synthetic product versions sent LSN 1,3,2      → SCD2 history in LSN order
  broker-outage         stop Kafka, drive app traffic, start Kafka     → buffered events still land (producer retries)
  debezium-restart      restart Kafka Connect, change a user's city   → CDC resumes from the slot, nothing lost
Pipeline restart / backfill / Gold-correction scenarios are driven from the Databricks CLI and
the Airflow backfill_reconcile DAG — see docs/failure_testing.md.
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import struct
import subprocess
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

BOOT, SR = "20.102.92.77:29092", "http://20.102.92.77:8081"
VM_SSH = ["ssh", "-i", str(Path.home() / ".ssh" / "ekadai_azure_vm"), "-o", "StrictHostKeyChecking=no", "ekadai@20.102.92.77"]


def tag(prefix: str) -> str:
    return f"ft-{prefix}-{int(time.time())}"


def now_ms() -> int:
    return int(time.time() * 1000)


# --- Avro helpers (Confluent wire format) ------------------------------------------------------

_schemas: dict[int, object] = {}


def _schema(sid: int):
    from fastavro import parse_schema
    if sid not in _schemas:
        _schemas[sid] = parse_schema(json.loads(httpx.get(f"{SR}/schemas/ids/{sid}", timeout=10).json()["schema"]))
    return _schemas[sid]


def decode(raw: bytes):
    from fastavro import schemaless_reader
    sid = struct.unpack(">I", raw[1:5])[0]
    return sid, schemaless_reader(io.BytesIO(raw[5:]), _schema(sid))


def encode(sid: int, rec) -> bytes:
    from fastavro import schemaless_writer
    buf = io.BytesIO()
    buf.write(b"\x00" + struct.pack(">I", sid))
    schemaless_writer(buf, _schema(sid), rec)
    return buf.getvalue()


def first_message(topic: str, match: bytes | None = None, partitions: int = 6):
    from confluent_kafka import Consumer, TopicPartition
    c = Consumer({"bootstrap.servers": BOOT, "group.id": f"ft-{uuid.uuid4()}", "enable.auto.commit": False})
    c.assign([TopicPartition(topic, p, 0) for p in range(partitions)])
    found, empty = [], 0
    while empty < 3:
        m = c.poll(5)
        if m is None:
            empty += 1
            continue
        if not m.error() and (match is None or match in m.value()):
            found.append(m)
            if match is None:
                break
    c.close()
    return found


def producer():
    from confluent_kafka import Producer
    return Producer({"bootstrap.servers": BOOT})


def transport():
    from events.transports.kafka_avro_transport import KafkaAvroTransport
    return KafkaAvroTransport(BOOT, SR)


# --- scenarios ---------------------------------------------------------------------------------

def malformed_avro(_):
    t = tag("malformed")
    p = producer()
    p.produce("product-events", key=t.encode(), value=b"not avro " + t.encode())
    p.flush(30)
    print(f"sent garbage tagged {t}. Check: bronze_events.decode_error set; quarantine MALFORMED with raw_payload 'base64:…'; pipeline still RUNNING")


def business_rule(_):
    from events.envelope import EventContext
    from events.producer import build_envelope
    t = tag("bizrule")
    cart_id = str(uuid.uuid4())
    env = build_envelope("add_to_cart", {"cart_id": cart_id, "product_id": str(uuid.uuid4()), "quantity_added": 0,
                                         "cart_quantity_after": 0}, EventContext(user_id=str(uuid.uuid4()), session_id=t))
    tr = transport()
    tr.send("cart-events", cart_id, env)
    tr.flush(30)
    print(f"sent {env['event_id']}. Check: quarantine BUSINESS_RULE 'quantity_added must be a positive integer'")


def duplicate_event(_):
    from events.envelope import EventContext
    from events.producer import build_envelope
    t = tag("dup")
    env = build_envelope("product_view", {"product_id": str(uuid.uuid4())}, EventContext(user_id=None, session_id=t))
    tr = transport()
    tr.send("product-events", t, env)
    tr.send("product-events", t, env)
    tr.flush(30)
    print(f"sent {env['event_id']} twice. Check: 2 bronze rows, 1 silver_events row")


def unknown_refs(args):
    t = tag("refs")
    c = httpx.Client(base_url=args.api, headers={"X-Session-Id": t}, timeout=30)
    known_cat = c.get("/categories").json()[0]["category_id"]
    missing = str(uuid.uuid4())
    a = c.post("/events", json={"event_type": "product_view", "event_timestamp": now_ms(), "payload": {"product_id": missing}})
    b = c.post("/events", json={"event_type": "page_view", "event_timestamp": now_ms(),
                                "payload": {"page_type": "product_detail", "product_id": missing, "category_id": known_cat}})
    print(f"product_view {a.json()['event_id']} → expect UNRESOLVED [UNKNOWN_PRODUCT:{missing}]")
    print(f"page_view    {b.json()['event_id']} → expect PARTIALLY_RESOLVED, only UNKNOWN_PRODUCT (§63)")


def late_events(args):
    t = tag("late")
    c = httpx.Client(base_url=args.api, headers={"X-Session-Id": t}, timeout=30)
    pid = c.get("/products", params={"page_size": 1}).json()["items"][0]["product_id"]
    for minutes in (12, 20):
        r = c.post("/events", json={"event_type": "product_view", "event_timestamp": now_ms() - minutes * 60_000,
                                    "payload": {"product_id": pid}})
        print(f"{minutes} min late: {r.json()['event_id']}")
    print("Check: 12 → is_late only; 20 → is_too_late, excluded from gold.fact_events until the late_data_replay DAG marks it PROCESSED")


def duplicate_cdc(_):
    msgs = first_message("cdc-orders", partitions=3)
    m = msgs[0]
    p = producer()
    p.produce("cdc-orders", key=m.key(), value=m.value(), partition=m.partition())
    p.flush(30)
    _, rec = decode(m.value())
    print(f"re-sent cdc-orders p{m.partition()} o{m.offset()} (order {(rec['after'] or rec['before'])['order_id']}). "
          "Check: bronze has an extra copy; silver_cdc_orders row count for that order unchanged")


def out_of_order_cdc(_):
    m = first_message("cdc-products")[0]
    key_sid, key_rec = decode(m.key())
    val_sid, val_rec = decode(m.value())
    pid = str(uuid.uuid4())
    key_bytes = encode(key_sid, {k: (pid if k == "product_id" else v) for k, v in key_rec.items()})
    base = copy.deepcopy(val_rec["after"])
    base.update({"product_id": pid, "product_name": "zz-ft-ooo-test", "brand": "zz-test", "image_url": None})
    lsn0, ts0 = 9_500_000_000 + int(time.time()) % 1_000_000 * 10, now_ms()

    def version(n, price, before=None):
        rec = copy.deepcopy(val_rec)
        after = dict(base, base_price=Decimal(price))
        rec.update(before=before, after=after, op="c" if n == 1 else "u", ts_ms=ts0 + n * 1000)
        rec["source"] = dict(rec["source"], ts_ms=ts0 + n * 1000, lsn=lsn0 + n, txId=950000 + n, snapshot="false",
                             sequence=json.dumps([None, str(lsn0 + n)]))
        return rec

    v1 = version(1, "100.00")
    v2 = version(2, "200.00", v1["after"])
    v3 = version(3, "300.00", v2["after"])
    p = producer()
    for rec in (v1, v3, v2, v3):  # out of order, plus a duplicate of v3
        p.produce("cdc-products", key=key_bytes, value=encode(val_sid, rec), partition=m.partition())
    p.flush(30)
    print(f"synthetic product {pid} (brand zz-test, excluded from Gold). Check silver_products: 100→200→300, 300 current, 3 versions")


def broker_outage(args):
    t = tag("outage")
    print("stopping Kafka on the VM …")
    subprocess.run(VM_SSH + ["sudo docker stop ekadai-kafka"], check=True)
    c = httpx.Client(base_url=args.api, headers={"X-Session-Id": t}, timeout=30)
    pid = c.get("/products", params={"page_size": 1}).json()["items"][0]["product_id"]
    ids = [c.post("/events", json={"event_type": "product_view", "event_timestamp": now_ms(),
                                   "payload": {"product_id": pid}}).json()["event_id"] for _ in range(3)]
    print(f"app still answered while Kafka was down; events {ids}")
    time.sleep(30)
    print("starting Kafka …")
    subprocess.run(VM_SSH + ["sudo docker start ekadai-kafka"], check=True)
    print(f"Check: all 3 event_ids (session {t}) reach silver_events once Kafka is back "
          "(librdkafka buffers and retries for up to message.timeout.ms = 5 min)")


def debezium_restart(args):
    print("restarting Kafka Connect (Debezium) …")
    subprocess.run(VM_SSH + ["sudo docker restart ekadai-debezium-connect"], check=True)
    email = f"ft-dbz-{int(time.time())}@example.com"
    c = httpx.Client(base_url=args.api, timeout=30)
    r = c.post("/auth/register", json={"email": email, "password": "ft-debezium-pass", "city": "Kochi", "state": "KL"})
    r.raise_for_status()
    print(f"registered {r.json()['user']['user_id']} right after the restart. "
          "Check: it reaches bronze_cdc_users / silver_users (Debezium resumes from its replication slot)")


SCENARIOS = {
    "malformed-avro": malformed_avro, "business-rule": business_rule, "duplicate-event": duplicate_event,
    "unknown-refs": unknown_refs, "late-events": late_events, "duplicate-cdc": duplicate_cdc,
    "out-of-order-cdc": out_of_order_cdc, "broker-outage": broker_outage, "debezium-restart": debezium_restart,
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--api", default="http://localhost:8000")
    SCENARIOS[(a := ap.parse_args()).scenario](a)
