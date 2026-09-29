# MASTER BUILD PROMPT

## End-to-End Real-Time E-Commerce Application + CDC + Kafka + Databricks Lakehouse

You are the primary coding/build agent for this project.

Your job is to build the entire project end-to-end from the architecture and requirements below.

This specification is the authoritative source of truth for the project.

Do NOT repeatedly ask for architectural decisions that are already explicitly locked below. Do NOT replace locked technologies or redesign the architecture unless you discover a genuine technical contradiction that makes the locked design impossible. If an implementation-level detail is unspecified, choose a sensible production-grade implementation while preserving all locked business and architectural semantics.

The goal is to produce a working, demonstrable, portfolio-quality system rather than a collection of disconnected demos.

---

# 1. PROJECT OBJECTIVE

Build an end-to-end real-time e-commerce application and data engineering platform that combines:

* a functional e-commerce application
* PostgreSQL transactional application state
* behavioral event streaming
* Apache Kafka
* PostgreSQL CDC using Debezium
* Avro + Confluent Schema Registry
* Bronze/Silver/Gold lakehouse architecture
* Azure Databricks
* Delta Lake
* PySpark
* Structured Streaming
* real-time reference resolution
* late-data handling and replay
* backfill/reprocessing
* data-quality/quarantine handling
* pipeline observability
* Power BI business analytics
* Power BI platform observability

The system must demonstrate the complete lifecycle:

```text
Customer behavior
        +
Authoritative application-state changes
        ↓
       Kafka
        ↓
Databricks Lakehouse
        ↓
Bronze
        ↓
Silver
        ↓
Gold
        ↓
Power BI
```

The project should demonstrate real-world data engineering concepts rather than merely moving sample CSV files between systems.

---

# 2. PRIMARY BUSINESS QUESTION

The platform should answer:

> What are customers doing, where are they dropping off, what are they buying, and what actually generates revenue?

The main analytical domains are:

1. Customer & Engagement
2. Conversion/Funnel
3. Product Performance
4. Revenue
5. Order Lifecycle

Payment analytics is NOT a primary domain.

There is no real payment gateway or real payment-processing subsystem.

---

# 3. IMPORTANT SEMANTIC DISTINCTION

The platform has two fundamentally different data sources.

## Behavioral events

Behavioral events answer:

> What did the customer do?

Examples:

* viewed a product
* searched
* added something to cart
* started checkout
* clicked cancel order

Source:

```text
Application
    ↓
Kafka
    ↓
Bronze Events
    ↓
Silver Events
    ↓
Gold
```

## CDC

CDC answers:

> What authoritative application state changed?

Source:

```text
PostgreSQL
    ↓
PostgreSQL WAL
    ↓
Debezium
    ↓
Kafka
    ↓
Bronze CDC
    ↓
Silver CDC
    ↓
Gold
```

Do NOT merge these concepts into one generic event model.

CDC is authoritative for application state.

Behavioral events are behavioral evidence/milestones.

For example:

* `order_created` is a behavioral milestone.
* `orders` in PostgreSQL is authoritative for the actual order.
* `fact_orders` must be built from CDC/application state, not from `order_created`.

---

# 4. HIGH-LEVEL ARCHITECTURE

Implement this architecture:

```text
                         E-COMMERCE APPLICATION
                         Azure + Docker
                                  │
                  ┌───────────────┴───────────────┐
                  │                               │
          Behavioral Events                 PostgreSQL
                  │                         Supabase
                  │                               │
                  │                              WAL
                  │                               │
                  │                           Debezium
                  │                               │
                  └───────────────┬───────────────┘
                                  ▼
                             APACHE KAFKA
                         Azure B2ms / KRaft
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
             Bronze Events                 Bronze CDC
                    │                           │
                    └─────────────┬─────────────┘
                                  ▼
                         DATABRICKS LAKEHOUSE
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
                  SILVER                       GOLD
                    │                           │
                    │               ┌───────────┴───────────┐
                    │               │                       │
                    │            Facts/Dimensions       Aggregates
                    │               │                       │
                    └───────────────┴───────────────────────┘
                                    │
                             ┌──────┴──────┐
                             │             │
                         Business      Platform
                         Analytics    Observability
                             │             │
                             └──────┬──────┘
                                    ▼
                                 POWER BI
```

---

# 5. CLOUD AND TECHNOLOGY STACK

Use:

* Azure
* Azure Databricks
* PySpark
* Spark Structured Streaming
* Delta Lake
* ADLS Gen2 where appropriate
* Unity Catalog where available/useful
* Databricks Workflows/Lakeflow capabilities where appropriate
* Apache Kafka
* Kafka KRaft
* Confluent Schema Registry
* Avro
* PostgreSQL
* Supabase-hosted PostgreSQL
* Debezium PostgreSQL Connector
* Docker
* Python
* Power BI
* Git/GitHub

The user wants the project to be primarily script-based and VS Code friendly.

Avoid unnecessary UI-driven development.

---

# 6. COST CONSTRAINT

The project is intended to run using Azure free credits during development.

The target is:

> ₹0 mandatory recurring cost after the available Azure credits are exhausted.

The user has approximately one month of Azure free credits available.

Therefore:

* avoid unnecessary Azure services
* avoid unnecessarily large compute
* use the smallest sensible development resources
* shut down/delete billable infrastructure when not needed
* do not introduce paid managed services unless explicitly necessary
* prefer self-hosted/free components where already decided

---

# 7. E-COMMERCE APPLICATION

Build a functional mini e-commerce store.

Initial catalog:

* approximately 30–50 products
* multiple categories

Potential categories:

* Electronics
* Clothing
* Home/Kitchen
* Fitness
* Books
* Accessories
* Beauty

The exact seed catalog can be implementation-defined.

The application must support:

* registration
* login
* logout
* profile
* saved addresses
* product browsing
* search
* filtering
* sorting
* product detail pages
* cart
* wishlist
* checkout
* order creation
* order history
* order cancellation

There is NO real payment gateway.

Do NOT build:

* real payment processing
* payment credentials
* payment gateway integration
* payment settlement
* payment reconciliation
* pending payment state

---

# 8. ORDER LIFECYCLE — LOCKED

Orders have exactly two lifecycle states:

```text
CONFIRMED
CANCELLED
```

Lifecycle:

```text
User completes checkout
        ↓
Order created
        ↓
CONFIRMED
        │
        │ Cancel Order
        ▼
CANCELLED
```

There is NO:

* PENDING
* PENDING_PAYMENT
* PAYMENT_PROCESSING
* PAYMENT_FAILED order state

A newly created order is immediately `CONFIRMED`.

For a newly created order:

```text
created_at   = order creation time
confirmed_at = order creation time
cancelled_at = NULL
```

When cancelled:

```text
status       = CANCELLED
cancelled_at = cancellation time
```

Cancellation is:

```text
CONFIRMED → CANCELLED
```

No reverse transition.

---

# 9. CHECKOUT

There is a checkout workflow, but there is NOT a persistent `checkouts` transactional table in v1.

`checkout_id` is a correlation identifier generated for the checkout flow and represented in behavioral events and, where useful, the order record.

Do not create an unnecessary payment/checkout subsystem merely because checkout exists.

Checkout captures a snapshot of the cart at checkout start.

The checkout snapshot contains:

* checkout_id
* cart_id
* item_count
* total_quantity
* gross_merchandise_value
* discount_amount
* cart_net_value
* currency

Definitions:

```text
GMV = quantity × transaction unit price before discounts

cart_net_value =
GMV - discount_amount
```

Shipping and tax are excluded.

---

# 10. ADDRESS MODEL

Users may have multiple saved addresses.

The selected address is used during checkout.

The order stores an immutable shipping-address snapshot.

Order fields:

```text
shipping_address_line1
shipping_address_line2
shipping_city
shipping_state
shipping_postal_code
shipping_country
```

Later changes to the user's saved addresses must NOT modify historical orders.

Addresses are therefore:

* application state
* NOT initially CDC-enabled

---

# 11. POSTGRESQL TRANSACTIONAL DATABASE

Transactional application database:

> PostgreSQL hosted by Supabase.

PostgreSQL is the authoritative source of application state.

MongoDB is NOT used.

Use UUID identifiers.

Use PostgreSQL `TIMESTAMPTZ` for timestamps.

Store application/lakehouse timestamps consistently in UTC.

Use `NUMERIC(18,2)` for monetary values.

Do NOT use floating point for money.

---

# 12. POSTGRESQL TABLES

The application database contains:

```text
users
addresses

categories
products

promotions
promotion_targets

cart
cart_items

wishlist
wishlist_items

orders
order_items
```

The five CDC-enabled tables are exactly:

```text
users
products
categories
orders
order_items
```

Do not expand CDC scope unless a real requirement forces it.

---

# 13. USERS

Conceptual schema:

```text
users
-----
user_id              UUID PK
registration_date    DATE NOT NULL
account_status       VARCHAR NOT NULL
city                 VARCHAR NULL
state                VARCHAR NULL
created_at           TIMESTAMPTZ NOT NULL
updated_at           TIMESTAMPTZ NOT NULL
```

Allowed account states:

```text
ACTIVE
DEACTIVATED
```

The application may obviously store authentication-related information such as email and password hash as required for login.

However:

* passwords must only be stored as secure hashes
* authentication secrets must never enter Kafka events
* authentication secrets must never enter Bronze
* authentication secrets must never enter Silver/Gold

Analytics should not expose unnecessary PII.

CDC: YES.

---

# 14. ADDRESSES

```text
addresses
---------
address_id       UUID PK
user_id          UUID FK → users
address_line1    VARCHAR NOT NULL
address_line2    VARCHAR NULL
city             VARCHAR NOT NULL
state            VARCHAR NOT NULL
postal_code      VARCHAR NOT NULL
country          VARCHAR NOT NULL
is_default       BOOLEAN NOT NULL
created_at       TIMESTAMPTZ NOT NULL
updated_at       TIMESTAMPTZ NOT NULL
```

A user may have multiple addresses.

A user may have at most one default address.

CDC: NO.

---

# 15. CATEGORIES

```text
categories
----------
category_id       UUID PK
category_name     VARCHAR NOT NULL UNIQUE
category_status   VARCHAR NOT NULL
created_at        TIMESTAMPTZ NOT NULL
updated_at        TIMESTAMPTZ NOT NULL
```

Statuses:

```text
ACTIVE
INACTIVE
```

CDC: YES.

---

# 16. PRODUCTS

```text
products
--------
product_id       UUID PK
product_name     VARCHAR NOT NULL
category_id      UUID FK → categories
brand            VARCHAR NULL
base_price       NUMERIC(18,2) NOT NULL
product_status   VARCHAR NOT NULL
created_at       TIMESTAMPTZ NOT NULL
updated_at       TIMESTAMPTZ NOT NULL
```

Statuses:

```text
ACTIVE
DISCONTINUED
```

Constraint:

```text
base_price >= 0
```

`base_price` is a catalog/reference price.

It is NOT the authoritative historical transaction price.

CDC: YES.

Do not introduce inventory quantities into `products` merely to implement an availability filter. That would unnecessarily turn inventory mutations into product CDC/SCD2 changes.

For v1, availability can be represented through application/product availability semantics without creating an inventory analytics domain.

---

# 17. PROMOTIONS

```text
promotions
----------
promotion_id        UUID PK
promotion_name      VARCHAR NOT NULL
discount_type       VARCHAR NOT NULL
discount_value      NUMERIC(18,2) NOT NULL
priority            INTEGER NOT NULL
start_at            TIMESTAMPTZ NOT NULL
end_at              TIMESTAMPTZ NULL
promotion_status    VARCHAR NOT NULL
created_at          TIMESTAMPTZ NOT NULL
updated_at          TIMESTAMPTZ NOT NULL
```

Discount types:

```text
PERCENTAGE
FIXED_AMOUNT
```

Scopes:

```text
PRODUCT
CATEGORY
SITEWIDE
```

The scope can be represented on the promotion itself.

Rules:

* highest-priority eligible promotion wins
* promotions do not stack
* transaction-time discount is snapshotted in order items
* base product price is never mutated to represent promotions

CDC: NO.

---

# 18. PROMOTION TARGETS

```text
promotion_targets
-----------------
promotion_target_id    UUID PK
promotion_id           UUID FK → promotions
target_type            VARCHAR NOT NULL
product_id             UUID NULL FK → products
category_id            UUID NULL FK → categories
created_at             TIMESTAMPTZ NOT NULL
```

Target semantics:

```text
PRODUCT
    → product_id populated

CATEGORY
    → category_id populated

SITEWIDE
    → neither product_id nor category_id
```

A promotion can have multiple targets.

Prevent duplicate targets.

CDC: NO.

---

# 19. CART

```text
cart
----
cart_id        UUID PK
user_id        UUID FK → users
cart_status    VARCHAR NOT NULL
created_at     TIMESTAMPTZ NOT NULL
updated_at     TIMESTAMPTZ NOT NULL
```

Statuses may include:

```text
ACTIVE
CHECKED_OUT
ABANDONED
```

There should be at most one ACTIVE cart per user.

CDC: NO.

---

# 20. CART ITEMS

```text
cart_items
----------
cart_item_id   UUID PK
cart_id        UUID FK → cart
product_id     UUID FK → products
quantity       INTEGER NOT NULL
created_at     TIMESTAMPTZ NOT NULL
updated_at     TIMESTAMPTZ NOT NULL
```

Rules:

```text
quantity > 0
UNIQUE(cart_id, product_id)
```

CDC: NO.

Cart behavior is represented through behavioral events.

---

# 21. WISHLIST

```text
wishlist
--------
wishlist_id    UUID PK
user_id        UUID FK → users UNIQUE
created_at     TIMESTAMPTZ NOT NULL
updated_at     TIMESTAMPTZ NOT NULL
```

One wishlist per user.

CDC: NO.

---

# 22. WISHLIST ITEMS

```text
wishlist_items
--------------
wishlist_item_id   UUID PK
wishlist_id        UUID FK → wishlist
product_id         UUID FK → products
created_at         TIMESTAMPTZ NOT NULL
```

Constraint:

```text
UNIQUE(wishlist_id, product_id)
```

CDC: NO.

---

# 23. ORDERS

```text
orders
------
order_id                    UUID PK
user_id                     UUID FK → users
checkout_id                 UUID
status                      VARCHAR NOT NULL
total_amount                NUMERIC(18,2) NOT NULL
currency                    CHAR(3) NOT NULL
item_count                  INTEGER NOT NULL
total_quantity              INTEGER NOT NULL

shipping_address_line1      VARCHAR NOT NULL
shipping_address_line2      VARCHAR NULL
shipping_city               VARCHAR NOT NULL
shipping_state              VARCHAR NOT NULL
shipping_postal_code        VARCHAR NOT NULL
shipping_country            VARCHAR NOT NULL

created_at                  TIMESTAMPTZ NOT NULL
confirmed_at                TIMESTAMPTZ NOT NULL
cancelled_at                TIMESTAMPTZ NULL
updated_at                  TIMESTAMPTZ NOT NULL
```

`checkout_id` should be unique so a checkout cannot accidentally produce multiple orders.

Statuses:

```text
CONFIRMED
CANCELLED
```

Constraints:

```text
total_amount >= 0
item_count > 0
total_quantity > 0
item_count <= total_quantity
```

Lifecycle:

```text
CONFIRMED:
    confirmed_at IS NOT NULL
    cancelled_at IS NULL

CANCELLED:
    confirmed_at IS NOT NULL
    cancelled_at IS NOT NULL
```

Indexes:

```text
user_id
status
created_at
cancelled_at
```

CDC: YES.

This table is authoritative for order lifecycle.

---

# 24. ORDER ITEMS

```text
order_items
-----------
order_item_id       UUID PK
order_id            UUID FK → orders
product_id          UUID FK → products
quantity            INTEGER NOT NULL
unit_price          NUMERIC(18,2) NOT NULL
discount_amount     NUMERIC(18,2) NOT NULL
line_revenue        NUMERIC(18,2) NOT NULL
currency            CHAR(3) NOT NULL
created_at          TIMESTAMPTZ NOT NULL
updated_at          TIMESTAMPTZ NOT NULL
```

Constraints:

```text
quantity > 0
unit_price >= 0
discount_amount >= 0
discount_amount <= quantity × unit_price

line_revenue =
(quantity × unit_price) - discount_amount
```

One product appears once per order:

```text
UNIQUE(order_id, product_id)
```

CDC: YES.

Historical transaction price must never be reconstructed from the current product price.

---

# 25. FOREIGN KEY DELETE POLICY

Historical source tables should resist accidental physical deletion.

Prefer restrictive FK behavior for:

```text
orders → users
products → categories
order_items → orders
order_items → products
products → categories
```

Normal lifecycle changes should use status:

```text
user       ACTIVE → DEACTIVATED
product    ACTIVE → DISCONTINUED
category   ACTIVE → INACTIVE
order      CONFIRMED → CANCELLED
```

Ephemeral application objects such as cart/wishlist child records may use cascading deletion where appropriate.

---

# 26. ORDER CREATION TRANSACTION

Creating an order should be one PostgreSQL transaction.

Conceptually:

```text
BEGIN

validate checkout/cart

create order as CONFIRMED

create order_items

calculate/validate:
    item_count
    total_quantity
    total_amount

mark cart as CHECKED_OUT

COMMIT
```

The exact implementation can be chosen by the coding agent, but the database state must never end up with a confirmed order without its corresponding order items.

---

# 27. CANCELLATION

The cancellation endpoint must:

1. authenticate the user
2. verify the order belongs to that user
3. verify current status is `CONFIRMED`
4. update:

   ```text
   status = CANCELLED
   cancelled_at = current timestamp
   updated_at = current timestamp
   ```

5. emit the appropriate behavioral event
6. allow Debezium to capture the authoritative database update

There is no `order_cancel_requested` state/table.

---

# 28. BEHAVIORAL EVENT ARCHITECTURE

Behavioral events are published to Kafka.

Common envelope:

```json
{
  "event_id": "...",
  "event_type": "...",
  "schema_version": 1,
  "event_timestamp": "...",
  "producer": "...",
  "context": {
    "user_id": "...",
    "session_id": "..."
  },
  "device": {
    "device_type": "...",
    "operating_system": "...",
    "browser": "..."
  },
  "payload": {}
}
```

`event_timestamp` is generated by the application at the time of the user action.

The pipeline adds:

```text
ingestion_timestamp
processing_timestamp
```

Do not use database ingestion time as the behavioral event timestamp.

---

# 29. BEHAVIORAL EVENT TYPES

## Authentication

### `user_registered`

Payload:

```json
{
  "registration": {
    "registration_method": "email"
  }
}
```

### `user_login`

```json
{
  "authentication": {
    "login_method": "email"
  }
}
```

### `user_logout`

Empty payload.

---

# 30. DISCOVERY EVENTS

### `page_view`

Page-level event.

Possible page types:

```text
home
category
product_listing
product_detail
cart
checkout
orders
profile
wishlist
```

Do NOT automatically attach `product_id` to every page view.

### `search`

Only emit when the user actually submits a search.

Payload:

```text
search_query
search_result_count
```

Do NOT emit an event for every keystroke.

### `filter_applied`

Each applied filter is represented.

Supported types:

```text
brand
category
price
rating
availability
```

Category filters should resolve to stable `category_id`.

### `sort_applied`

Supported sort values:

```text
price
rating
popularity
newest
```

Direction:

```text
asc
desc
```

### `product_view`

Must contain:

```text
product_id
```

Category can be reference-enriched downstream.

---

# 31. CART AND WISHLIST EVENTS

Events:

```text
add_to_cart
remove_from_cart
wishlist_added
wishlist_removed
wishlist_view
buy_now_clicked
```

There is NO generic `cart_updated` event.

For cart mutation:

If delta > 0:

```text
add_to_cart
quantity_added = delta
cart_quantity_after = new quantity
```

If delta < 0:

```text
remove_from_cart
quantity_removed = abs(delta)
cart_quantity_after = new quantity
```

If delta = 0:

```text
emit nothing
```

Only emit after the application mutation succeeds.

Failed mutations do not emit successful behavioral events.

Quantities must be:

```text
quantity_added > 0
quantity_removed > 0
cart_quantity_after >= 0
```

---

# 32. BUY NOW

`buy_now_clicked` contains:

```text
product_id
checkout_id
source
```

No `cart_id` is required.

Possible sources:

```text
product_detail
wishlist
search_results
product_listing
```

---

# 33. CHECKOUT EVENT

### `checkout_started`

Contains:

```text
checkout_id
cart_id
item_count
total_quantity
gross_merchandise_value
discount_amount
cart_net_value
currency
```

Definitions:

```text
GMV = transaction quantity × transaction unit price before discounts

cart_net_value =
GMV - discount_amount
```

Shipping/tax are excluded.

`item_count` = number of distinct cart lines.

`total_quantity` = total number of units.

Therefore:

```text
item_count > 0
total_quantity > 0
item_count <= total_quantity
```

This is a snapshot at checkout start.

---

# 34. PAYMENT EVENTS — REMOVED

Do NOT implement:

```text
payment_initiated
payment_success
payment_failed
```

There is no real payment subsystem in v1.

Do not create:

```text
payments table
```

Do not create payment CDC.

Do not create payment analytics.

The project simulates successful checkout directly into a confirmed order.

---

# 35. ORDER EVENTS

### `order_created`

Contains:

```text
order_id
checkout_id
item_count
total_quantity
order_value
```

This is a behavioral milestone only.

It is NOT authoritative for revenue/order state.

### `order_viewed`

Contains:

```text
order_id
```

and page context such as:

```text
order_details
```

### `order_cancel_clicked`

Contains:

```text
order_id
```

The actual cancellation is authoritative only after the PostgreSQL `orders.status` update is captured by CDC.

---

# 36. CHECKOUT ABANDONMENT

Do NOT emit a raw:

```text
checkout_abandoned
```

event.

Abandonment is derived.

Initial rule:

> If a checkout has no qualifying successful order outcome for 15 minutes, it can be classified as abandoned.

This timeout is independent of the 30-minute session timeout.

If a qualifying order happens later, the derived state must be corrected rather than permanently treating the checkout as abandoned.

---

# 37. KAFKA

Use Apache Kafka self-hosted on Azure.

Deployment:

```text
Azure VM
Standard_B2ms
2 vCPU
8 GiB RAM
Linux/Ubuntu
```

Kafka:

```text
Apache Kafka
KRaft mode
single broker
combined broker/controller
```

No ZooKeeper.

Kafka data disk:

```text
64 GiB Standard SSD LRS
```

Schema Registry runs on the same VM initially.

Replication factor:

```text
1
```

Retention:

```text
7 days
```

Kafka is a short-term streaming/replay buffer.

Bronze is the longer-lived raw replay source.

---

# 38. KAFKA TOPICS

Exactly 10 topics.

## Behavioral

```text
user-events
product-events
cart-events
checkout-events
order-events
```

## CDC

```text
cdc-users
cdc-products
cdc-categories
cdc-orders
cdc-order-items
```

---

# 39. KAFKA PARTITIONS

Final partition configuration:

| Topic             | Key           | Partitions |
| ----------------- | ------------- | ---------: |
| `user-events`     | `user_id`     |          3 |
| `product-events`  | `session_id`  |          6 |
| `cart-events`     | `cart_id`     |          4 |
| `checkout-events` | `checkout_id` |          4 |
| `order-events`    | `order_id`    |          3 |
| `cdc-users`       | `user_id`     |          3 |
| `cdc-products`    | `product_id`  |          6 |
| `cdc-categories`  | `category_id` |          3 |
| `cdc-orders`      | `order_id`    |          3 |
| `cdc-order-items` | `order_id`    |          3 |

Total:

```text
38 partitions
```

Partitioning principle:

> Choose the entity whose ordering must be preserved.

Kafka ordering is only guaranteed within a partition.

`product-events` intentionally uses `session_id`, not `product_id`, because we want the user's browsing journey preserved while avoiding a hot product partition.

---

# 40. KAFKA CONSUMER GROUPS

Use:

```text
bronze-events-consumer
```

for all behavioral topics.

Use:

```text
bronze-cdc-consumer
```

for all CDC topics.

Silver/Gold processing should operate from Bronze/lakehouse data rather than competing directly for the original Kafka stream.

Do not create a separate Kafka monitoring consumer group just to measure lag.

---

# 41. AVRO + SCHEMA REGISTRY

Use Avro serialization.

Use self-hosted Confluent Schema Registry.

Do NOT use Confluent Cloud.

Schema compatibility:

```text
BACKWARD
```

Use:

```text
TopicRecordNameStrategy
```

for subject naming.

Each distinct record/event type gets its own subject scoped appropriately by topic and record name.

Exact namespaces and record names can be implementation-defined, but they must be consistent and documented.

---

# 42. SCHEMA EVOLUTION

Compatible:

* adding optional fields
* adding nullable fields with safe defaults

Breaking:

* removing required fields
* incompatible datatype changes
* changing business meaning
* changing required semantics

Breaking changes require:

* new schema version
* controlled consumer migration

Schema-invalid events must not silently enter trusted Silver.

They must remain in Bronze and be routed to quarantine.

---

# 43. SCHEMA VERSION VS PIPELINE VERSION

These are different.

`schema_version`:

> Version of the producer event contract.

`pipeline_version`:

> Version of the processing implementation.

Use Git as the implementation source of truth.

Every execution should record:

```text
pipeline_version = Git release/tag
Git commit SHA = exact implementation revision
```

Backfill/recovery audit must record both.

Silver records `pipeline_version`.

---

# 44. POSTGRESQL CDC

Use:

```text
PostgreSQL logical replication/WAL
        ↓
native pgoutput
        ↓
Debezium PostgreSQL Connector
        ↓
Kafka
```

Debezium runs alongside Kafka on the same Azure B2ms VM.

Use a dedicated:

* replication slot
* publication

for Debezium.

Monitor:

* replication-slot lag
* WAL lag
* connector health

---

# 45. CDC TABLES

Exactly:

```text
users       → cdc-users       → silver_users
products    → cdc-products    → silver_products
categories  → cdc-categories  → silver_categories
orders      → cdc-orders      → silver_cdc_orders
order_items → cdc-order-items → silver_cdc_order_items
```

Do NOT initially CDC:

```text
promotions
promotion_targets
addresses
cart
cart_items
wishlist
wishlist_items
```

---

# 46. CDC SEMANTICS

Conceptually:

INSERT:

```text
before = null
after  = new row
```

UPDATE:

```text
before = old row
after  = new row
```

DELETE:

```text
before = old row
after  = null
```

Snapshot rows should preserve snapshot metadata.

Preserve:

```text
operation
transaction_id
change_timestamp
change_position
snapshot
```

The exact Debezium field names and LSN representation may be implementation-specific, but the semantic information must be retained.

---

# 47. CDC ORDERING

`change_timestamp` is NOT sufficient to determine authoritative ordering.

Use source CDC ordering metadata:

```text
change_position / WAL position
```

as the authoritative ordering mechanism.

Kafka partition ordering helps preserve per-entity delivery order.

If an older CDC record arrives after a newer record:

* do not allow the old record to overwrite newer state
* use source change position
* correct SCD2 history if necessary

Duplicate CDC must be idempotent.

It must not create duplicate SCD2 versions.

---

# 48. CDC TRANSACTIONS

Preserve:

```text
transaction_id
change_position
```

No cross-topic transaction coordinator is required.

Temporary cross-table incompleteness is acceptable.

For example:

```text
order arrives
order_items arrive slightly later
```

Gold/reconciliation should eventually converge to the correct state.

---

# 49. CDC INITIAL SNAPSHOT

Debezium should initially snapshot existing rows from all five CDC tables.

Then transition to normal WAL CDC.

Snapshot metadata must be preserved.

Do not repeatedly resnapshot unless explicitly performing bootstrap/recovery.

---

# 50. DELETE SEMANTICS

Reference/master tables:

```text
users
products
categories
```

normally use status updates instead of physical deletion.

If a physical delete nevertheless occurs:

* preserve CDC history
* close the current SCD2 version
* do not silently erase historical analytics
* record the unexpected deletion operationally

Transactional tables:

```text
orders
order_items
```

should normally not be physically deleted.

Order cancellation is represented by:

```text
CONFIRMED → CANCELLED
```

If physical deletion occurs:

* preserve CDC before image
* preserve historical Gold facts
* record the unexpected physical deletion operationally

---

# 51. BRONZE

Bronze must preserve raw source information.

Behavioral Bronze table:

```text
bronze_events
```

contains:

```text
raw_payload
event_id
event_type
schema_version
event_timestamp

kafka_topic
kafka_partition
kafka_offset
kafka_timestamp

ingestion_timestamp
```

Also retain useful source metadata.

Do not perform aggressive transformation in Bronze.

Do not silently reject malformed data in Bronze.

Bronze is the raw recovery layer.

Retention:

```text
90 days
```

---

# 52. SILVER TABLES

Required Silver tables:

```text
silver_events
silver_event_filters

silver_cdc_orders
silver_cdc_order_items

silver_products
silver_categories
silver_users

silver_event_quarantine
reference_resolution_queue
late_data_replay_queue
```

Pipeline audit/control is a separate operational area.

---

# 53. SILVER EVENT MODEL

Use a hybrid model.

Do NOT create a giant generic JSON `event_attributes` column as the primary analytical model.

Use common/high-value fields as first-class columns.

Do not retain raw payload in Silver.

Bronze retains raw payload.

---

# 54. SILVER EVENTS

Final conceptual schema:

```text
event_id
event_type
schema_version

user_id
session_id
product_id
category_id
cart_id
checkout_id
order_id

event_timestamp
ingestion_timestamp
processing_timestamp

device_type
operating_system
browser

search_query
search_result_count

quantity_added
quantity_removed
cart_quantity_after

item_count
total_quantity

gross_merchandise_value
discount_amount
cart_net_value

order_value
currency

source

kafka_topic
kafka_partition
kafka_offset
kafka_timestamp

source_system
pipeline_version

validation_status
reference_status
reference_errors

is_late
is_too_late
```

There are NO payment-specific fields/events in v1.

Use explicit semantic field names.

Avoid generic fields such as:

```text
amount
value
quantity
```

when a more meaningful field name exists.

---

# 55. EVENT IDENTITY

`event_id` is the stable technical identity of a behavioral event.

Event contract identity is:

```text
event_type + schema_version
```

`schema_version` is the incoming producer contract version.

It is NOT the Silver table schema version.

---

# 56. EVENT DEDUPLICATION

Deduplicate behavioral events using:

```text
event_id
```

Do NOT add:

```text
is_duplicate
```

as the primary dedup mechanism.

Gold should not perform primary event deduplication.

If different event IDs contain identical payloads:

* calculate a business fingerprint excluding event_id
* treat it as suspected duplicate
* do not automatically delete it

Repeated identical user actions can be legitimate.

---

# 57. IDEMPOTENT REPROCESSING

Retries must be safe.

Reference resolution must be safe.

Late replay must be safe.

Backfill must be safe.

Use:

* stable identifiers
* distributed joins
* MERGE/upsert semantics
* deterministic transformations

Do NOT query the destination database once per event.

Use distributed/batch processing.

---

# 58. EVENT TIMING

Every behavioral event has:

```text
event_timestamp
```

Platform timestamps:

```text
ingestion_timestamp
processing_timestamp
```

Kafka timestamp is lineage metadata.

Metrics:

```text
ingestion latency =
ingestion_timestamp - event_timestamp

processing latency =
processing_timestamp - ingestion_timestamp

end-to-end latency =
processing_timestamp - event_timestamp
```

All lakehouse timestamps use UTC.

---

# 59. VALIDATION STATUS

`validation_status` describes event validity.

Allowed conceptual values:

```text
VALID
INVALID
```

Invalid includes:

* malformed structure
* schema incompatibility
* invalid business fields
* invalid required fields

Invalid events go to:

```text
silver_event_quarantine
```

---

# 60. REFERENCE STATUS

Reference status is separate from event validity.

Values:

```text
RESOLVED
PARTIALLY_RESOLVED
UNRESOLVED
```

A valid event referencing an unknown product/user/category is NOT automatically invalid.

Example:

```text
product_view
product_id = P123
```

If P123 has not arrived through CDC yet:

```text
validation_status = VALID
reference_status = UNRESOLVED
```

Keep the event in Silver.

---

# 61. REFERENCE RESOLUTION

If a valid event references a product/user/category that has not arrived yet:

1. keep the event in Silver
2. set unresolved reference status
3. record the dependency in `reference_resolution_queue`
4. when the corresponding CDC reference arrives, resolve affected events
5. update the original Silver event by stable `event_id`
6. correct affected Gold grains idempotently

Do NOT duplicate the event.

This resolution should be:

> streaming/event-driven

not a manual scheduled process.

Airflow is for safety/recovery/reconciliation/backfill/maintenance, not normal reference resolution.

---

# 62. REFERENCE RESOLUTION QUEUE

Conceptual fields:

```text
resolution_id
reference_type
reference_id
first_seen_at
last_seen_at
status
retry_count
last_attempt_at
resolved_at
error_message
affected_event_count
```

Reference types:

```text
PRODUCT
USER
CATEGORY
```

Statuses:

```text
PENDING
PROCESSING
RESOLVED
FAILED
```

Monitor:

* unresolved backlog
* resolution latency
* failures
* retries
* oldest unresolved age
* throughput

---

# 63. CATEGORY RESOLUTION

A product reference can provide category information.

If the product is unknown:

```text
UNKNOWN_PRODUCT
```

Do NOT also automatically mark:

```text
UNKNOWN_CATEGORY
```

unless the category itself is independently unresolved.

---

# 64. EVENT QUARANTINE

`silver_event_quarantine`:

```text
event_id
event_type
schema_version
raw_payload
error_type
validation_error

kafka_topic
kafka_partition
kafka_offset
kafka_timestamp

ingestion_timestamp
detected_at
source_system
pipeline_version
```

Only genuinely invalid events go here.

Bronze always retains the original event.

Retention:

```text
30 days
```

---

# 65. LATE DATA

Definitions:

```text
event time
= user action time

ingestion time
= arrival time

processing time
= processing time

watermark
= event-time progress

allowed lateness
= tolerance after watermark
```

Initial values:

```text
watermark = 10 minutes
allowed lateness = 5 minutes
```

These should be treated as initial project configuration and validated empirically.

---

# 66. TOO-LATE DATA

If an event arrives beyond allowed lateness:

* Bronze retains it
* normal event-time processing does not immediately include it
* create a replay-queue record
* later replay the exact event from Bronze
* correct downstream Gold state idempotently

Do NOT discard it.

---

# 67. LATE REPLAY QUEUE

Fields:

```text
replay_id
source_type
source_table_or_topic
record_id
event_timestamp
detected_at
lateness_seconds
reason
status
retry_count
last_attempt_at
processed_at
error_message
```

This stores metadata/IDs, not the raw payload.

Raw payload remains in Bronze.

Use a dedicated Airflow Late Data Replay DAG.

---

# 68. SILVER FILTER TABLE

`silver_event_filters`

Grain:

> one row per filter within one `filter_applied` event.

Fields:

```text
event_id
filter_type
filter_value_string
filter_value_min
filter_value_max
filter_value_boolean
category_id
```

Filter types:

```text
brand
category
price
rating
availability
```

Rules:

```text
brand → string

category → stable category_id

price → min/max
        at least one populated
        min <= max

rating → min/max
         0–5

availability → boolean
```

Do not populate irrelevant fields.

---

# 69. SILVER CDC ORDERS

Grain:

> one row per CDC change to one orders row.

Fields:

```text
order_id
operation
change_timestamp
transaction_id
change_position
snapshot

status_before
status_after

user_id
total_amount
currency
created_at
confirmed_at
cancelled_at

shipping_address_line1
shipping_address_line2
shipping_city
shipping_state
shipping_postal_code
shipping_country
```

Only status requires explicit before/after fields in the normalized Silver model.

Bronze retains the complete raw Debezium before/after structure.

---

# 70. SILVER CDC ORDER ITEMS

Grain:

> one row per CDC change.

Fields:

```text
order_item_id
order_id
operation
change_timestamp
transaction_id
change_position
snapshot

product_id
quantity
unit_price
discount_amount
line_revenue
currency
```

Historical transaction values are authoritative.

---

# 71. SILVER PRODUCTS

SCD2 reference history.

Fields:

```text
product_version_key
product_id
product_name
category_id
brand
base_price
product_status
created_at
updated_at
valid_from
valid_to
is_current
```

Grain:

> one row per product version.

---

# 72. SILVER CATEGORIES

```text
category_version_key
category_id
category_name
category_status
created_at
updated_at
valid_from
valid_to
is_current
```

SCD2.

---

# 73. SILVER USERS

```text
user_version_key
user_id
registration_date
account_status
city
state
created_at
updated_at
valid_from
valid_to
is_current
```

SCD2 attributes:

```text
city
state
account_status
```

Do NOT propagate email/password/phone/full address into Gold.

---

# 74. GOLD MODEL

Gold contains:

## Dimensions

```text
dim_user
dim_product
dim_category
dim_date
dim_device
```

## Facts

```text
fact_events
fact_sessions
fact_orders
fact_order_items
```

## Aggregates

```text
agg_user_activity
agg_conversion_funnel
agg_product_performance
agg_daily_revenue
agg_order_metrics
```

Materialize expensive/reusable aggregates as Delta tables.

Use views where a calculation is lightweight.

---

# 75. CONFORMED DIMENSIONS

Conformed dimensions:

```text
user
product
category
date
device
```

Avoid blind fact-to-fact joins.

Facts should connect through conformed dimensions and business keys where appropriate.

---

# 76. GOLD SURROGATE KEYS

Generate surrogate keys for dimensions.

`dim_date` can use deterministic:

```text
YYYYMMDD
```

as `date_key`.

Business/source IDs remain separately available.

SCD2 versions receive distinct surrogate keys.

---

# 77. DIM_USER

```text
user_key
user_id
registration_date
account_status
city
state
valid_from
valid_to
is_current
```

SCD2.

No:

```text
email
phone
password
full address
last_login
```

---

# 78. DIM_PRODUCT

```text
product_key
product_id
product_name
category_key
brand
base_price
product_status
valid_from
valid_to
is_current
```

SCD2.

Historical facts must point to the appropriate historical product version.

---

# 79. DIM_CATEGORY

```text
category_key
category_id
category_name
category_status
valid_from
valid_to
is_current
```

SCD2.

---

# 80. DIM_DATE

```text
date_key
date
day
day_name
week_of_year
month
month_name
quarter
year
is_weekend
```

Use ISO week numbering.

Generate independently.

---

# 81. DIM_DEVICE

```text
device_key
device_type
operating_system
browser
```

No device ID.

No SCD2 required.

---

# 82. FACT_EVENTS

Behavioral events only.

Fields:

```text
event_key
event_id
event_type
schema_version

user_key
session_id
product_key
category_key
device_key
date_key

event_timestamp
ingestion_timestamp
source
```

Do NOT put:

* Kafka lineage fields
* quarantine fields
* pipeline diagnostics
* financial measures

into the business fact.

---

# 83. FACT_SESSIONS

Grain:

> one row per session.

Fields:

```text
session_key
session_id
user_key
device_key
date_key

session_start_timestamp
session_end_timestamp
session_duration_seconds

event_count
product_view_count
search_count
add_to_cart_count
remove_from_cart_count
checkout_started_count
order_created_count

converted
```

Session definition:

> 30 minutes of inactivity ends the session.

Rules:

* login does not start a new session
* logout does not immediately end a session
* anonymous → authenticated can remain the same session
* sessions may cross midnight
* `date_key` = session start date
* conversion requires an authoritative successful order outcome

---

# 84. FACT_ORDERS

Derived from authoritative CDC/application state.

Fields:

```text
order_key
order_id
user_key
date_key

status

created_timestamp
confirmed_timestamp
cancelled_timestamp

total_amount
currency

item_count
total_quantity

shipping_address_line1
shipping_address_line2
shipping_city
shipping_state
shipping_postal_code
shipping_country
```

Grain:

> one row per order.

Not one row per CDC update.

`date_key`:

> order creation date.

Current status is authoritative.

---

# 85. FACT_ORDER_ITEMS

```text
order_item_key
order_item_id
order_id
order_key
product_key
user_key
date_key

quantity
unit_price
discount_amount
line_revenue
currency
```

Date:

> order creation date.

`unit_price` = historical transaction price before discount.

`line_revenue`:

```text
quantity × unit_price - discount_amount
```

Never calculate historical revenue using today's product price.

---

# 86. AGG_USER_ACTIVITY

Grain:

> user × date

Fields:

```text
date_key
user_key

session_count
event_count
product_view_count
search_count

add_to_cart_count
remove_from_cart_count

wishlist_added_count
wishlist_removed_count

checkout_started_count
order_created_count

unique_products_viewed

total_cart_additions
total_cart_removals

active_user
```

Counts:

* cart action counts = number of actions
* total additions/removals = quantity delta sums

`active_user = true` if at least one valid behavioral event exists.

Anonymous activity is not attributed to a user without a user ID.

Materialize as incremental Delta.

---

# 87. AGG_CONVERSION_FUNNEL

Grain:

> date

Fields:

```text
date_key

product_view_sessions
add_to_cart_sessions
checkout_started_sessions
successful_order_sessions
checkout_abandoned_sessions
cancelled_order_sessions
```

Do not include payment stages.

Stage counts are distinct sessions reaching the stage.

Session journey is assigned to session-start date even if it crosses midnight.

Abandonment:

```text
15 minutes
```

Conversion percentages should be derived rather than redundantly stored.

---

# 88. AGG_PRODUCT_PERFORMANCE

Grain:

> product × date

Fields:

```text
date_key
product_key
category_key

product_view_count
unique_viewing_users

add_to_cart_count
unique_cart_users

order_count
units_sold

gross_merchandise_value
discount_amount
net_revenue
```

Definitions:

```text
GMV =
quantity × actual transaction unit price before discounts

net revenue =
GMV - discount
```

`order_count` = distinct orders containing the product.

Use historically correct product/category dimension versions.

---

# 89. PRODUCT ATTRIBUTION

7-day conversion definition:

A user:

1. views product X
2. later purchases product X
3. within 7 × 24 hours

Use the user's first qualifying view:

```text
view_timestamp
```

and first qualifying purchase:

```text
purchase_timestamp
```

Interval:

```text
view_timestamp <= purchase_timestamp
< view_timestamp + 7 days
```

Cross-session attribution is allowed.

Same product is required.

Conversion time:

```text
purchase_timestamp - first_view_timestamp
```

Report average and median conversion time among converted users.

---

# 90. AGG_DAILY_REVENUE

Grain:

> date × currency

Fields:

```text
date_key
currency

order_count
units_sold

gross_merchandise_value
discount_amount
net_transaction_sales

cancelled_order_count
cancelled_order_value

revenue_after_cancellations
```

Definitions:

```text
GMV =
quantity × unit_price

net_transaction_sales =
GMV - discount

cancelled_order_value =
net transaction value of cancelled orders

revenue_after_cancellations =
net_transaction_sales - cancelled_order_value
```

Cancellation is reflected on the **cancellation date** for cancellation reporting.

Do NOT rewrite historical sales dates.

This is not accounting revenue.

Do not model:

* tax
* shipping
* refunds
* chargebacks
* returns

unless explicitly added in a future version.

---

# 91. AGG_ORDER_METRICS

Grain:

> order creation date × currency

Fields:

```text
date_key
currency

order_count
confirmed_order_count
cancelled_order_count

total_order_value
average_order_value

cancelled_order_value
cancellation_rate
```

`date_key` is order creation date.

Cancellation timestamp remains available for cancellation-date analysis.

---

# 92. SCD2 CORRECTION

For reference data:

```text
products
categories
users
```

source CDC ordering is authoritative.

If an older CDC change arrives after a newer change:

* do not simply append a new current version
* use `change_position`
* rebuild/correct affected SCD2 history into source order

Duplicate CDC must not create duplicate versions.

---

# 93. BACKFILL

Backfill source for behavioral data:

```text
Bronze raw events
```

Backfill source for CDC data:

```text
Bronze CDC
```

Backfill runs must be idempotent.

Each run receives:

```text
backfill_id
```

Every run is independently auditable.

Record:

* start/end time
* source range
* pipeline version
* Git commit
* input count
* output count
* rejected count
* duplicate count
* errors
* reconciliation results

A corrective run should reference/supersede the affected prior run where appropriate.

Do not add `backfill_id` to Gold purely for lineage.

---

# 94. RECONCILIATION

Backfill/recovery should reconcile:

```text
input records
output records
missing records
duplicate records

Gold facts
Gold aggregates
```

Validate that corrective processing produces the expected state.

---

# 95. RETENTION

Final retention:

| Layer/Data              |                 Retention |
| ----------------------- | ------------------------: |
| Kafka                   |                    7 days |
| Bronze events           |                   90 days |
| Bronze CDC              |                   90 days |
| Silver events           |                   90 days |
| Silver CDC              |                   90 days |
| Silver SCD2 references  |                Indefinite |
| Gold facts              |                Indefinite |
| Gold dimensions         |                Indefinite |
| Gold aggregates         |                Indefinite |
| Quarantine              |                   30 days |
| Resolution queue        |  Until resolved + 30 days |
| Replay queue            | Until processed + 30 days |
| Backfill/recovery audit |                Indefinite |

---

# 96. KAFKA RETENTION VS BRONZE

Kafka is a short-term replay buffer.

If Bronze ingestion is down for less than 7 days:

```text
Kafka can replay the records
```

If Kafka retention expires before Bronze receives them:

```text
those records cannot be recovered from Bronze
```

because they never reached Bronze.

For a production-scale system, longer Kafka retention and/or an independent durable archive could be added later.

Do not over-engineer this v1 implementation.

---

# 97. OBSERVABILITY

Create a dedicated operational/monitoring Delta area.

Do NOT mix platform observability into Gold business tables.

Potential operational tables:

```text
pipeline_runs
data_quality_metrics
backfill_audit
reconciliation_results
reference_resolution_status
late_replay_status
```

---

# 98. KAFKA OBSERVABILITY

Track:

* availability/connectivity
* throughput
* consumer lag
* oldest message age
* errors
* restarts
* rebalances
* offset progress
* partition imbalance
* hot partitions
* deserialization failures
* authentication/connection failures
* checkpoint/offset commit failures

---

# 99. PIPELINE OBSERVABILITY

Hierarchy:

```text
Pipeline
    ↓
Stage
    ↓
Diagnostic
```

Stages:

```text
Bronze
Silver Events
Silver CDC
Reference Resolution
Gold Aggregation
```

Track:

* status
* last successful run
* batch duration
* processing latency
* failed batches
* retry count
* input records
* output records
* processing rate
* quarantined records
* watermark
* late records
* too-late records
* replay backlog
* validation failures
* quarantine rate
* unknown references
* unresolved reference backlog
* schema failures

---

# 100. SPARK DIAGNOSTICS

Track where practical:

* task duration
* failed tasks
* retries
* shuffle
* spill
* skew
* stage duration
* data size
* executor CPU
* executor memory

These are diagnostic metrics.

The main dashboard should prioritize:

```text
health
↓
latency
↓
throughput
↓
watermark/late data
↓
failures
```

---

# 101. REFERENCE RESOLUTION MONITORING

Monitor:

```text
reference availability latency
resolution latency
unresolved backlog
resolution throughput
resolution failures
retry count
oldest unresolved record
```

---

# 102. LATE DATA MONITORING

Monitor:

```text
replay backlog
replay success
replay failure
replay latency
oldest replay record
```

---

# 103. POWER BI

Power BI is the final BI layer.

Architecture:

```text
Gold
 ↓
Power BI
```

Create two conceptual dashboard areas.

## Business Analytics

Include:

* customer activity
* session activity
* conversion funnel
* checkout abandonment
* product performance
* revenue
* cancellation
* order metrics

## Platform Observability

Include:

* pipeline health
* Kafka health
* lag
* latency
* throughput
* data quality
* quarantine
* late data
* replay backlog
* reference resolution
* failed pipelines

Do not mix infrastructure diagnostics into the main business dashboard.

---

# 104. BUSINESS METRICS

The business dashboard should make it possible to answer:

### Customer

* How many active users?
* How many sessions?
* How frequently do users return?
* How many products are viewed?

### Funnel

```text
product view
    ↓
add to cart
    ↓
checkout
    ↓
successful order
```

Also measure:

* abandonment
* cancellation

### Product

* views
* unique viewers
* cart additions
* unique cart users
* orders
* units sold
* GMV
* discounts
* net revenue
* 7-day conversion

### Revenue

* daily GMV
* discounts
* net transaction sales
* cancellation value
* revenue after cancellations
* AOV

### Orders

* confirmed orders
* cancelled orders
* cancellation rate
* order value

---

# 105. PROJECT ROADMAP

Build in this order:

```text
1. PostgreSQL transactional schema

2. E-commerce application

3. Behavioral event contracts

4. Kafka + Schema Registry

5. Debezium + PostgreSQL CDC

6. Bronze ingestion

7. Silver events + validation

8. Silver CDC + SCD2

9. Reference resolution

10. Late-data replay

11. Gold facts/dimensions

12. Gold aggregates

13. Observability

14. Power BI

15. Failure/recovery testing

16. Documentation + portfolio presentation
```

Do not skip directly to dashboards before validating the upstream pipeline.

---

# 106. DEVELOPMENT PRINCIPLES

The implementation must prioritize:

### Correctness

Do not fabricate data to make downstream dashboards look populated.

### Idempotency

Retries must not duplicate facts or aggregates.

### Traceability

Every record should be traceable where appropriate through:

```text
event_id
source ID
Kafka topic
partition
offset
pipeline version
CDC transaction/change position
```

### Separation of concerns

Keep:

```text
application state
behavioral events
CDC
Bronze
Silver
Gold
observability
```

conceptually separate.

### Explicit semantics

Do not use ambiguous fields.

Prefer:

```text
gross_merchandise_value
discount_amount
cart_net_value
line_revenue
total_quantity
```

rather than generic:

```text
value
amount
quantity
```

where semantics differ.

---

# 107. FAILURE HANDLING

The implementation must deliberately test:

### Kafka

* broker unavailable
* consumer restart
* consumer lag
* partition imbalance
* malformed Avro

### PostgreSQL/CDC

* Debezium restart
* replication lag
* duplicate CDC
* out-of-order CDC
* connector restart

### Silver

* malformed event
* schema incompatibility
* unknown product
* unknown user
* unknown category
* late event
* too-late event

### Reference resolution

* reference arrives after event
* resolver restart
* repeated resolution
* failed resolution
* duplicate resolution

### Backfill

* rerun same range
* partial failure
* corrective run
* duplicate input

### Gold

* replay corrections
* cancellation after initial order
* late event changing aggregate
* SCD2 correction

---

# 108. IMPLEMENTATION QUALITY

The codebase should be structured clearly.

Prefer separate modules for:

```text
application
event contracts
Kafka producer
CDC configuration
Bronze
Silver
validation
reference resolution
late replay
Gold
observability
backfill
configuration
tests
```

Use configuration rather than hardcoding environment-specific values.

Secrets must never be committed.

Use environment variables / secret management.

Provide:

* `.env.example`
* clear configuration documentation
* reproducible setup instructions
* migration/bootstrap scripts
* seed data
* tests
* README documentation

---

# 109. TESTING

Tests must cover:

## Application

* registration
* login
* product browsing
* search
* filtering
* cart
* wishlist
* checkout
* order creation
* order cancellation

## Events

* correct event trigger
* correct event payload
* correct IDs
* schema validation
* event timestamp
* duplicate handling

## CDC

* INSERT
* UPDATE
* DELETE behavior
* snapshot
* transaction metadata
* ordering
* duplicate handling

## Data pipeline

* Bronze ingestion
* Silver validation
* quarantine
* reference resolution
* late replay
* SCD2
* Gold facts
* Gold aggregates

## Recovery

Every major pipeline should be safely rerunnable.

---

# 110. DOCUMENTATION

Produce documentation explaining:

1. project objective
2. architecture
3. application architecture
4. PostgreSQL schema
5. behavioral event architecture
6. Kafka topology
7. Schema Registry
8. Debezium CDC
9. Bronze
10. Silver
11. Gold
12. reference resolution
13. late data
14. backfill
15. observability
16. Power BI
17. failure scenarios
18. cost considerations
19. deployment
20. local development
21. cloud deployment
22. design tradeoffs

Include architecture diagrams where useful.

---

# 111. IMPORTANT "DO NOT" RULES

Do NOT:

* replace PostgreSQL with MongoDB
* replace Kafka with Pub/Sub
* present Pub/Sub experience as Kafka experience
* replace Kafka with Azure Event Hubs
* introduce ZooKeeper
* introduce Confluent Cloud
* introduce real payment processing
* create a payment analytics domain
* add an order PENDING state
* make payment state authoritative
* treat behavioral `order_created` as authoritative order state
* make Gold facts directly dependent on raw clickstream for authoritative orders
* store raw payload as the primary Silver model
* silently discard invalid events
* silently discard late events
* manually resolve unknown references
* duplicate events during reference resolution
* use current product price to reconstruct historical order revenue
* physically delete historical reference data as the normal lifecycle
* add arbitrary CDC tables without justification
* add unnecessary Azure services
* use floating point for monetary values
* build only a static dashboard with fake data
* create disconnected toy pipelines
* ask the user to repeatedly re-explain the architecture

---

# 112. IMPLEMENTATION-LEVEL FREEDOM

The following are intentionally not fully locked and can be decided by the coding agent:

* exact backend framework
* exact frontend framework
* exact Azure application hosting service
* exact repository structure
* exact Avro namespace/record names
* exact Debezium connector JSON
* exact replication slot/publication names
* exact Spark checkpoint paths
* exact Databricks job configuration
* exact Delta physical partitioning
* exact Z-ORDER/liquid clustering decisions
* exact Power BI page layout
* exact DAX implementation
* exact authentication library
* exact networking/security configuration

However, these choices MUST preserve the architecture and semantics defined above.

When choosing among implementation options, prefer:

1. correctness
2. simplicity
3. low cost
4. maintainability
5. demonstrable real-world engineering value

---

# 113. BUILD STRATEGY

Do not build a fake end-to-end demo first and retrofit the architecture later.

Build the actual system incrementally in the specified dependency order.

At each phase:

1. implement
2. test
3. validate
4. document
5. continue

The final system should be capable of demonstrating:

```text
User performs action
        ↓
Application changes state / emits event
        ↓
Kafka receives event
        ↓
Bronze stores raw record
        ↓
Silver validates/enriches
        ↓
Reference resolution handles dependencies
        ↓
Gold models business state
        ↓
Power BI reflects the result
```

For an order:

```text
User completes checkout
        ↓
PostgreSQL creates CONFIRMED order
        ↓
CDC captures INSERT
        ↓
Debezium
        ↓
cdc-orders / cdc-order-items
        ↓
Bronze CDC
        ↓
Silver CDC
        ↓
Gold fact_orders / fact_order_items
        ↓
Revenue/order analytics
```

For cancellation:

```text
CONFIRMED order
        ↓
User clicks Cancel
        ↓
Application validates cancellation
        ↓
PostgreSQL:
status CONFIRMED → CANCELLED
        ↓
Debezium UPDATE
        ↓
cdc-orders
        ↓
Silver CDC
        ↓
Gold fact_orders
        ↓
Cancellation metrics
```

For a behavioral event:

```text
User views product
        ↓
Application emits product_view
        ↓
product-events
        ↓
Bronze
        ↓
Silver Events
        ↓
Reference resolution
        ↓
fact_events / sessions / product aggregates
        ↓
Power BI
```

---

# 114. FINAL INSTRUCTION TO THE CODING AGENT

Treat this document as the project's **architecture contract**.

Before writing implementation code, translate this specification into a concrete implementation plan and repository structure internally.

Do not reopen decisions that are marked as locked.

Do not simplify away important data-engineering functionality merely to make the project easier.

Do not over-engineer areas that are explicitly outside scope.

Where implementation details are unspecified, make reasonable production-grade choices and document them.

Build the system so that it can be run, tested, demonstrated, and explained as a genuine end-to-end data engineering project.

The final result should tell one coherent engineering story:

> A real e-commerce application generates behavioral data while PostgreSQL remains the authoritative source of transactional state. Kafka provides the streaming backbone, Debezium captures authoritative database changes, Databricks processes both behavioral and CDC data through Bronze/Silver/Gold layers, and Power BI exposes the resulting business and platform intelligence.

Start with the PostgreSQL schema and proceed through the roadmap in dependency order.
