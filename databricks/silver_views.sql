-- Phase 8 — spec-shaped SCD2 views (§71–73) over the AUTO CDC history tables that
-- databricks/silver_cdc_pipeline.py maintains. Row-local mapping only, so the views cost
-- nothing and are always exactly as current as the pipeline.
--
-- __START_AT / __END_AT are the `_seq` struct (change_position, change_timestamp, snapshot)
-- of the change that opened / closed each version.
--   *_version_key : deterministic per version (id + WAL position) — same keys after a rebuild (§76)
--   valid_from    : when the opening change committed; for a version opened by the initial
--                   snapshot, the row's created_at (the snapshot only proves it existed by then)
--   valid_to      : when the closing change (next version or a DELETE) committed; null if open
--   is_current    : no closing change yet
-- Applied by databricks/provision.ps1 (statements are separated by lines containing only ";").

CREATE OR REPLACE VIEW ekadai_databricks.silver.silver_products
COMMENT 'Product versions, SCD2 (§71). One row per product version.'
AS SELECT
  xxhash64(product_id, __START_AT.change_position) AS product_version_key,
  product_id, product_name, category_id, brand, base_price, product_status, created_at, updated_at,
  CASE WHEN __START_AT.snapshot THEN least(created_at, __START_AT.change_timestamp)
       ELSE __START_AT.change_timestamp END AS valid_from,
  __END_AT.change_timestamp AS valid_to,
  __END_AT IS NULL AS is_current
FROM ekadai_databricks.silver.silver_products_history
;
CREATE OR REPLACE VIEW ekadai_databricks.silver.silver_categories
COMMENT 'Category versions, SCD2 (§72). One row per category version.'
AS SELECT
  xxhash64(category_id, __START_AT.change_position) AS category_version_key,
  category_id, category_name, category_status, created_at, updated_at,
  CASE WHEN __START_AT.snapshot THEN least(created_at, __START_AT.change_timestamp)
       ELSE __START_AT.change_timestamp END AS valid_from,
  __END_AT.change_timestamp AS valid_to,
  __END_AT IS NULL AS is_current
FROM ekadai_databricks.silver.silver_categories_history
;
CREATE OR REPLACE VIEW ekadai_databricks.silver.silver_users
COMMENT 'User versions, SCD2 on city/state/account_status (§73). No email/password/phone.'
AS SELECT
  xxhash64(user_id, __START_AT.change_position) AS user_version_key,
  user_id, registration_date, account_status, city, state, created_at, updated_at,
  CASE WHEN __START_AT.snapshot THEN least(created_at, __START_AT.change_timestamp)
       ELSE __START_AT.change_timestamp END AS valid_from,
  __END_AT.change_timestamp AS valid_to,
  __END_AT IS NULL AS is_current
FROM ekadai_databricks.silver.silver_users_history
;
