# Failure & recovery testing (§107)

Every scenario runs against the live cloud system, not mocks. Injections come from
`scripts/failure_tests.py <scenario>`, the Databricks CLI, or the Airflow `backfill_reconcile`
DAG. **Result** records what was actually observed, with the date.

## Kafka

| Scenario | How | Expected | Result |
|---|---|---|---|
| Malformed Avro | `failure_tests.py malformed-avro` | Kept in Bronze with `decode_error`; `silver_event_quarantine` MALFORMED with `raw_payload = base64:<bytes>`; pipeline keeps running | ✅ 2026-09-29 (Phase 7): `ValueError: unexpected magic byte 116`, quarantined, 0 flow failures |
| Broker unavailable | `failure_tests.py broker-outage` (stops `ekadai-kafka` for ~30s during app traffic) | The app keeps serving (event emission never blocks requests). The producer buffers and retries, and the events land once the broker is back | _run at restart_ |
| Consumer restart | `databricks pipelines stop` → `start-update` | Resumes from checkpoints; no gaps, no duplicates (row count = distinct ids) | ✅ repeatedly during Phases 6–10 (settings changes, mode switches): counts stayed = distinct ids |
| Consumer lag | Pipeline stopped while traffic flows (the triggered mode used on a budget does this by design), then started | `ops.kafka_lag` shows lag while stopped, 0 after catch-up | _run at restart_ |
| Partition imbalance / hot partition | `ops.kafka_lag.partition_share` per topic | Keyed topics spread by key (§39); a share far above 1/partitions flags a hot partition | _observe at restart_ |

## PostgreSQL / CDC

| Scenario | How | Expected | Result |
|---|---|---|---|
| Duplicate CDC | `failure_tests.py duplicate-cdc` (exact bytes re-produced) | Extra Bronze copy; no extra `silver_cdc_*` row or SCD2 version | ✅ 2026-09-29 (Phase 8): 3 Bronze rows, 2 change-log rows |
| Out-of-order CDC | `failure_tests.py out-of-order-cdc` (LSN 1, 3, 2, 3) | SCD2 history in LSN order; highest LSN current; the duplicate is ignored | ✅ 2026-09-29 (Phase 8): 100→200→300, 300 current, 3 versions from 5 messages |
| DELETE | Synthetic `op=d` | Current SCD2 version closed; history kept (§50) | ✅ 2026-09-29 (Phase 8): last version closed, `is_current` false everywhere |
| Debezium / connector restart | `failure_tests.py debezium-restart` | Resumes from the replication slot; the change made right after the restart arrives | _run at restart_ |
| Replication lag | Deallocating the VM (as the budget stop did) leaves the slot inactive while the DB keeps changing; then start the VM | Debezium catches up from the slot; nothing is lost | _run at restart_ (the VM was deallocated 2026-09-29) |
| Before-image on UPDATE | Cancel an order through the app | `status_before = CONFIRMED`, `status_after = CANCELLED` | ✅ 2026-09-29 (Phase 8, after `REPLICA IDENTITY FULL`) |

## Silver

| Scenario | How | Expected | Result |
|---|---|---|---|
| Malformed event | as above | Quarantined MALFORMED | ✅ |
| Schema incompatibility / business rule | `failure_tests.py business-rule` | Quarantined BUSINESS_RULE with message | ✅ Phase 7: `quantity_added must be a positive integer, got 0` |
| Invalid filter (§68) | `filter_applied` price min > max | Quarantined | ✅ Phase 7 |
| Duplicate event | `failure_tests.py duplicate-event` | 2 Bronze rows, 1 Silver row | ✅ Phase 7 |
| Unknown product / user / category | `failure_tests.py unknown-refs` | `UNRESOLVED` / `PARTIALLY_RESOLVED`, never quarantined (§60); unknown product ≠ unknown category (§63) | ✅ Phase 9 |
| Late event (12 min) | `failure_tests.py late-events` | `is_late` only; admitted to Gold | ✅ Phase 10 |
| Too-late event (20 min) | same | `is_too_late`; queued PENDING → PROCESSED by the replay DAG; admitted to Gold only after that | ✅ Phase 10 (queue); Gold admission _verify at restart_ |

## Reference resolution

| Scenario | How | Expected | Result |
|---|---|---|---|
| Reference arrives after event | Event for product X, then a CDC insert of X | The same row flips to RESOLVED (~8s); still one row | ✅ Phase 9 |
| Resolver restart | Pipeline stopped while an event is UNRESOLVED; the reference arrives; pipeline started | Resolved on the first batch after the restart (the correction trigger reads from its checkpoint) | _run at restart_ |
| Repeated / duplicate resolution | The reference's CDC insert delivered twice | Idempotent: still one row, still RESOLVED | ✅ by design: corrections are upserts by `event_id`; the Phase 8 duplicate-CDC test covers the trigger |
| Failed resolution | Reference never arrives | Stays PENDING; FAILED after 7 days with `error_message` | ✅ PENDING observed (Phase 9); FAILED path is time-based |

## Backfill (`backfill_reconcile` DAG)

| Scenario | How | Expected | Result |
|---|---|---|---|
| Rerun same range | Trigger twice with the same `source_start`/`source_end` | Identical Silver/Gold; two audit rows, both reconciliation-passed | _run at restart_ |
| Partial failure | Trigger with a bogus table name in `tables` | Pipeline update fails → audit row `FAILED`, no reconciliation | _run at restart_ |
| Corrective run | Trigger with `supersedes_backfill_id` = the failed run | New audit row referencing it; `SUCCEEDED` | _run at restart_ |
| Duplicate input | Range includes the duplicate-event / duplicate-CDC injections | `duplicate_count > 0` in the audit; no duplicate Silver/Gold rows (checks pass) | _run at restart_ |

## Gold

| Scenario | How | Expected | Result |
|---|---|---|---|
| Cancellation after the initial order | Place, then cancel an order in the app | `fact_orders.status` CANCELLED; `agg_daily_revenue` shows the sale on the order date and the cancellation on the cancellation date | _run at restart_ |
| Late event changing an aggregate | Too-late event → replay DAG → pipeline refresh | `fact_events` / `agg_user_activity` count goes up by one after replay | _run at restart_ |
| Replay correction | same | Admitted exactly once | _run at restart_ |
| SCD2 correction | Out-of-order CDC for a real-looking product | Facts point to the version valid at the fact time | _run at restart_ (synthetic products are excluded from Gold, so this uses a user city change) |
