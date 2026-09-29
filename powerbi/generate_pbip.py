"""Generates the Power BI project (PBIP: TMDL semantic model + PBIR report) for Ekadai.

    python powerbi/generate_pbip.py --columns <columns.txt> [--mode import|directquery]

`--columns` is a pipe-separated export of
    SELECT table_schema, table_name, column_name, data_type
    FROM ekadai_databricks.information_schema.columns WHERE table_schema IN ('gold','ops')
so the model always matches the live tables exactly. `--mode directquery` produces the live
variant (pair with automatic page refresh for real-time demos); `import` is the cheap snapshot.

Output: powerbi/ekadai.pbip, powerbi/ekadai.SemanticModel/, powerbi/ekadai.Report/.
Open ekadai.pbip in Power BI Desktop, sign in to Azure Databricks (OAuth / Microsoft Entra ID),
then Refresh. See docs/powerbi.md.
"""

from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path

HOST = "adb-7405617818071366.6.azuredatabricks.net"
HTTP_PATH = "/sql/1.0/warehouses/68d5a8cb07485e9a"
CATALOG = "ekadai_databricks"
OUT = Path(__file__).resolve().parent
NAME = "ekadai"

GOLD_TABLES = [
    "dim_date", "dim_user", "dim_product", "dim_category", "dim_device",
    "fact_events", "fact_sessions", "fact_orders", "fact_order_items",
    "agg_user_activity", "agg_conversion_funnel", "agg_product_performance",
    "agg_daily_revenue", "agg_order_metrics", "agg_product_attribution",
]
OPS_TABLES = [
    "pipeline_runs", "pipeline_stage_metrics", "latency_metrics", "data_quality_metrics",
    "reference_resolution_status", "late_replay_status", "kafka_lag", "cdc_connector_health",
    "backfill_audit", "reconciliation_results",
]

# many-side column -> one-side column. No fact-to-fact links (§75); dim_product→dim_category is
# inactive because facts also reach dim_category directly (an active one would be ambiguous).
RELATIONSHIPS = [
    ("fact_events.user_key", "dim_user.user_key", True),
    ("fact_events.product_key", "dim_product.product_key", True),
    ("fact_events.category_key", "dim_category.category_key", True),
    ("fact_events.device_key", "dim_device.device_key", True),
    ("fact_events.date_key", "dim_date.date_key", True),
    ("fact_sessions.user_key", "dim_user.user_key", True),
    ("fact_sessions.device_key", "dim_device.device_key", True),
    ("fact_sessions.date_key", "dim_date.date_key", True),
    ("fact_orders.user_key", "dim_user.user_key", True),
    ("fact_orders.date_key", "dim_date.date_key", True),
    ("fact_order_items.product_key", "dim_product.product_key", True),
    ("fact_order_items.user_key", "dim_user.user_key", True),
    ("fact_order_items.date_key", "dim_date.date_key", True),
    ("agg_user_activity.user_key", "dim_user.user_key", True),
    ("agg_user_activity.date_key", "dim_date.date_key", True),
    ("agg_conversion_funnel.date_key", "dim_date.date_key", True),
    ("agg_product_performance.product_key", "dim_product.product_key", True),
    ("agg_product_performance.category_key", "dim_category.category_key", True),
    ("agg_product_performance.date_key", "dim_date.date_key", True),
    ("agg_daily_revenue.date_key", "dim_date.date_key", True),
    ("agg_order_metrics.date_key", "dim_date.date_key", True),
    ("agg_product_attribution.product_key", "dim_product.product_key", True),
    ("dim_product.category_key", "dim_category.category_key", False),
]

# (home table, name, DAX, format). Conversion rates derived, not stored (§87).
MEASURES = [
    ("agg_user_activity", "Active Users", "DISTINCTCOUNT('agg_user_activity'[user_key])", "#,0"),
    ("agg_user_activity", "Products Viewed", "SUM('agg_user_activity'[unique_products_viewed])", "#,0"),
    ("fact_sessions", "Sessions", "COUNTROWS('fact_sessions')", "#,0"),
    ("fact_sessions", "Converted Sessions", "CALCULATE(COUNTROWS('fact_sessions'), 'fact_sessions'[converted] = TRUE())", "#,0"),
    ("fact_sessions", "Session Conversion %", "DIVIDE([Converted Sessions], [Sessions])", "0.0%"),
    ("fact_sessions", "Avg Session Minutes", "AVERAGE('fact_sessions'[session_duration_seconds]) / 60", "#,0.0"),
    ("fact_sessions", "Returning Users",
     "COUNTROWS(FILTER(VALUES('fact_sessions'[user_key]), NOT ISBLANK('fact_sessions'[user_key]) && CALCULATE(DISTINCTCOUNT('fact_sessions'[date_key])) > 1))", "#,0"),
    ("agg_conversion_funnel", "Funnel 1 Product View", "SUM('agg_conversion_funnel'[product_view_sessions])", "#,0"),
    ("agg_conversion_funnel", "Funnel 2 Add To Cart", "SUM('agg_conversion_funnel'[add_to_cart_sessions])", "#,0"),
    ("agg_conversion_funnel", "Funnel 3 Checkout", "SUM('agg_conversion_funnel'[checkout_started_sessions])", "#,0"),
    ("agg_conversion_funnel", "Funnel 4 Successful Order", "SUM('agg_conversion_funnel'[successful_order_sessions])", "#,0"),
    ("agg_conversion_funnel", "View to Cart %", "DIVIDE([Funnel 2 Add To Cart], [Funnel 1 Product View])", "0.0%"),
    ("agg_conversion_funnel", "Cart to Checkout %", "DIVIDE([Funnel 3 Checkout], [Funnel 2 Add To Cart])", "0.0%"),
    ("agg_conversion_funnel", "Checkout to Order %", "DIVIDE([Funnel 4 Successful Order], [Funnel 3 Checkout])", "0.0%"),
    ("agg_conversion_funnel", "Checkout Abandonment %", "DIVIDE(SUM('agg_conversion_funnel'[checkout_abandoned_sessions]), [Funnel 3 Checkout])", "0.0%"),
    ("agg_conversion_funnel", "Cancelled Order Sessions", "SUM('agg_conversion_funnel'[cancelled_order_sessions])", "#,0"),
    ("agg_daily_revenue", "GMV", "SUM('agg_daily_revenue'[gross_merchandise_value])", "₹#,0.00"),
    ("agg_daily_revenue", "Discounts", "SUM('agg_daily_revenue'[discount_amount])", "₹#,0.00"),
    ("agg_daily_revenue", "Net Sales", "SUM('agg_daily_revenue'[net_transaction_sales])", "₹#,0.00"),
    ("agg_daily_revenue", "Cancelled Value", "SUM('agg_daily_revenue'[cancelled_order_value])", "₹#,0.00"),
    ("agg_daily_revenue", "Revenue After Cancellations", "SUM('agg_daily_revenue'[revenue_after_cancellations])", "₹#,0.00"),
    ("agg_order_metrics", "Orders", "SUM('agg_order_metrics'[order_count])", "#,0"),
    ("agg_order_metrics", "Confirmed Orders", "SUM('agg_order_metrics'[confirmed_order_count])", "#,0"),
    ("agg_order_metrics", "Cancelled Orders", "SUM('agg_order_metrics'[cancelled_order_count])", "#,0"),
    ("agg_order_metrics", "AOV", "DIVIDE(SUM('agg_order_metrics'[total_order_value]), [Orders])", "₹#,0.00"),
    ("agg_order_metrics", "Cancellation Rate", "DIVIDE([Cancelled Orders], [Orders])", "0.0%"),
    ("agg_product_performance", "Product Views", "SUM('agg_product_performance'[product_view_count])", "#,0"),
    ("agg_product_performance", "Unique Viewers", "SUM('agg_product_performance'[unique_viewing_users])", "#,0"),
    ("agg_product_performance", "Cart Additions", "SUM('agg_product_performance'[add_to_cart_count])", "#,0"),
    ("agg_product_performance", "Units Sold", "SUM('agg_product_performance'[units_sold])", "#,0"),
    ("agg_product_performance", "Product Net Revenue", "SUM('agg_product_performance'[net_revenue])", "₹#,0.00"),
    ("agg_product_attribution", "7d View to Purchase %",
     "DIVIDE(SUM('agg_product_attribution'[converted_users]), SUM('agg_product_attribution'[viewing_users]))", "0.0%"),
    ("fact_events", "Events", "COUNTROWS('fact_events')", "#,0"),
]

TYPE_MAP = {"INT": "int64", "LONG": "int64", "BIGINT": "int64", "SMALLINT": "int64", "TINYINT": "int64",
            "DOUBLE": "double", "FLOAT": "double", "STRING": "string", "BOOLEAN": "boolean",
            "TIMESTAMP": "dateTime", "DATE": "dateTime"}


def dtype(db_type: str) -> str | None:
    t = db_type.upper()
    if t.startswith("DECIMAL"):
        return "decimal"
    return TYPE_MAP.get(t)


def tag() -> str:
    return str(uuid.uuid4())


def load_columns(path: Path) -> dict[tuple[str, str], list[tuple[str, str]]]:
    cols: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4 or parts[1].startswith("__"):
            continue
        schema, table, column, typ = parts
        cols.setdefault((schema, table), []).append((column, typ))
    return cols


def m_source(schema: str, table: str) -> str:
    lines = [
        "let",
        f'    Source = Databricks.Catalogs("{HOST}", "{HTTP_PATH}", [Catalog=null, Database=null, EnableAutomaticProxyDiscovery=null]),',
        f'    Catalog = Source{{[Name="{CATALOG}"]}}[Data],',
        f'    Schema = Catalog{{[Name="{schema}"]}}[Data],',
        f'    Data = Schema{{[Name="{table}"]}}[Data]',
        "in",
        "    Data",
    ]
    return "\n".join("\t\t\t\t" + ln for ln in lines)


def table_tmdl(schema: str, table: str, columns: list[tuple[str, str]], mode: str) -> str:
    out = [f"table '{table}'", f"\tlineageTag: {tag()}"]
    if table == "dim_date":
        out.append("\tdataCategory: Time")
    out.append("")
    for name, typ in columns:
        t = dtype(typ)
        if t is None:
            continue  # structs/arrays aren't reportable columns
        out += [f"\tcolumn '{name}'", f"\t\tdataType: {t}"]
        if table == "dim_date" and name == "date":
            out.append("\t\tisKey")
        if t == "decimal":
            out.append("\t\tformatString: #,0.00")
        if t in ("int64", "decimal", "double") and (name.endswith("_key") or name.endswith("_id") or name in ("partition", "year", "month", "day", "quarter", "week_of_year")):
            out.append("\t\tsummarizeBy: none")
        out += [f"\t\tlineageTag: {tag()}", f"\t\tsourceColumn: {name}", ""]
    for home, mname, dax, fmt in MEASURES:
        if home == table:
            out += [f"\tmeasure '{mname}' = {dax}", f"\t\tformatString: {fmt}", f"\t\tlineageTag: {tag()}", ""]
    out += [f"\tpartition '{table}' = m", f"\t\tmode: {mode}", "\t\tsource =", m_source(schema, table), ""]
    return "\n".join(out) + "\n"


# --- report (PBIR) --------------------------------------------------------------------------------

SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def measure(table: str, name: str) -> dict:
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
            "queryRef": f"{table}.{name}", "nativeQueryRef": name}


def column(table: str, name: str) -> dict:
    return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}},
            "queryRef": f"{table}.{name}", "nativeQueryRef": name}


def M(name: str) -> dict:
    home = next(h for h, n, _, _ in MEASURES if n == name)
    return measure(home, name)


def visual(vtype: str, x: int, y: int, w: int, h: int, roles: dict[str, list[dict]], title: str | None = None) -> dict:
    v: dict = {"visualType": vtype, "query": {"queryState": {r: {"projections": p} for r, p in roles.items()}},
               "drillFilterOtherVisuals": True}
    if title:
        v["visualContainerObjects"] = {"title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'" + title.replace("'", "''") + "'"}}}}}]}
    return {"position": {"x": x, "y": y, "z": 0, "width": w, "height": h}, "visual": v}


def cards(names: list[str], y: int = 16, h: int = 110) -> list[dict]:
    w = (1280 - 32 - 12 * (len(names) - 1)) // len(names)
    return [visual("card", 16 + i * (w + 12), y, w, h, {"Values": [M(n)]}) for i, n in enumerate(names)]


D = lambda c: column("dim_date", c)  # noqa: E731

PAGES = [
    ("overview", "Overview", cards(["Active Users", "Sessions", "Orders", "Net Sales", "AOV", "Cancellation Rate"]) + [
        visual("lineChart", 16, 140, 820, 560, {"Category": [D("date")], "Y": [M("Net Sales"), M("GMV")]}, "Net sales vs GMV by day"),
        visual("clusteredColumnChart", 848, 140, 416, 560, {"Category": [D("date")], "Y": [M("Sessions")]}, "Sessions by day"),
    ]),
    ("customers", "Customers & Sessions", cards(["Sessions", "Session Conversion %", "Avg Session Minutes", "Returning Users", "Products Viewed"]) + [
        visual("clusteredColumnChart", 16, 140, 620, 560, {"Category": [column("dim_device", "device_type")], "Y": [M("Sessions")]}, "Sessions by device"),
        visual("clusteredBarChart", 648, 140, 616, 560, {"Category": [column("dim_user", "city")], "Y": [M("Sessions")]}, "Sessions by city"),
    ]),
    ("funnel", "Conversion Funnel", cards(["View to Cart %", "Cart to Checkout %", "Checkout to Order %", "Checkout Abandonment %", "Cancelled Order Sessions"]) + [
        visual("clusteredBarChart", 16, 140, 1248, 560, {"Y": [M("Funnel 1 Product View"), M("Funnel 2 Add To Cart"),
                                                                 M("Funnel 3 Checkout"), M("Funnel 4 Successful Order")]},
               "Sessions reaching each stage (view → cart → checkout → order)"),
    ]),
    ("products", "Products", [
        visual("tableEx", 16, 16, 780, 420, {"Values": [column("dim_product", "product_name"), column("dim_product", "brand"),
                                                         M("Product Views"), M("Unique Viewers"), M("Cart Additions"),
                                                         M("Units Sold"), M("Product Net Revenue")]}, "Product performance"),
        visual("clusteredColumnChart", 808, 16, 456, 420, {"Category": [column("dim_category", "category_name")], "Y": [M("Product Net Revenue")]},
               "Net revenue by category"),
        visual("tableEx", 16, 448, 1248, 256, {"Values": [column("agg_product_attribution", "product_name"),
                                                           column("agg_product_attribution", "viewing_users"),
                                                           column("agg_product_attribution", "converted_users"),
                                                           M("7d View to Purchase %"),
                                                           column("agg_product_attribution", "avg_conversion_seconds"),
                                                           column("agg_product_attribution", "median_conversion_seconds")]},
               "7-day view → purchase attribution"),
    ]),
    ("revenue", "Revenue & Orders", cards(["GMV", "Discounts", "Net Sales", "Cancelled Value", "Revenue After Cancellations"]) + [
        visual("clusteredColumnChart", 16, 140, 820, 560, {"Category": [D("date")], "Y": [M("Net Sales"), M("Cancelled Value"), M("Revenue After Cancellations")]},
               "Daily revenue (cancellations on cancellation date)"),
        visual("clusteredColumnChart", 848, 140, 416, 380, {"Category": [D("date")], "Y": [M("Confirmed Orders"), M("Cancelled Orders")]},
               "Confirmed vs cancelled orders"),
        visual("card", 848, 532, 200, 168, {"Values": [M("AOV")]}),
        visual("card", 1064, 532, 200, 168, {"Values": [M("Cancellation Rate")]}),
    ]),
    ("ops-health", "Platform: Health", [
        visual("tableEx", 16, 16, 1248, 300, {"Values": [column("pipeline_runs", c) for c in
                                                          ("started_at", "state", "cause", "duration_seconds", "failed_flow_events", "error_events", "update_id")]},
               "Pipeline runs"),
        visual("tableEx", 16, 328, 860, 376, {"Values": [column("pipeline_stage_metrics", c) for c in
                                                          ("stage", "flow_name", "last_status", "output_records", "failed_batches", "last_event_at")]},
               "Stage → flow metrics"),
        visual("tableEx", 888, 328, 376, 376, {"Values": [column("cdc_connector_health", c) for c in
                                                           ("connector", "connector_state", "task_states", "captured_at")]},
               "Debezium connector"),
    ]),
    ("ops-latency", "Platform: Latency & Kafka", [
        visual("lineChart", 16, 16, 1248, 330, {"Category": [column("latency_metrics", "hour")],
                                                 "Y": [column("latency_metrics", "end_to_end_p50_s"), column("latency_metrics", "end_to_end_p95_s"),
                                                       column("latency_metrics", "ingestion_p50_s")]},
               "Latency (seconds): end-to-end and ingestion"),
        visual("tableEx", 16, 358, 1248, 346, {"Values": [column("kafka_lag", c) for c in
                                                           ("topic", "partition", "latest_offset", "bronze_max_offset", "lag_messages", "partition_share", "captured_at")]},
               "Kafka lag per partition"),
    ]),
    ("ops-quality", "Platform: Data Quality & Late Data", [
        visual("tableEx", 16, 16, 1248, 300, {"Values": [column("data_quality_metrics", c) for c in
                                                          ("date", "bronze_records", "decode_failures", "valid_events", "quarantined", "malformed",
                                                           "business_rule_failures", "quarantine_rate", "late_events", "too_late_events", "unresolved_events")]},
               "Daily data quality"),
        visual("tableEx", 16, 328, 760, 376, {"Values": [column("reference_resolution_status", c) for c in
                                                          ("reference_type", "references_needed", "pending_backlog", "resolved", "failed",
                                                           "avg_resolution_latency_s", "oldest_unresolved_age_s")]},
               "Reference resolution"),
        visual("tableEx", 788, 328, 476, 376, {"Values": [column("late_replay_status", c) for c in
                                                           ("replay_records", "replay_backlog", "replay_succeeded", "replay_failed", "avg_replay_latency_s")]},
               "Late-data replay"),
    ]),
    ("ops-recovery", "Platform: Backfill & Reconciliation", [
        visual("tableEx", 16, 16, 1248, 330, {"Values": [column("backfill_audit", c) for c in
                                                          ("backfill_id", "status", "started_at", "finished_at", "input_count", "output_count",
                                                           "rejected_count", "duplicate_count", "missing_count", "reconciliation_passed", "supersedes_backfill_id")]},
               "Backfill runs"),
        visual("tableEx", 16, 358, 1248, 346, {"Values": [column("reconciliation_results", c) for c in
                                                           ("backfill_id", "check_name", "expected", "actual", "passed", "checked_at")]},
               "Reconciliation checks"),
    ]),
]

THEME = {"name": "ekadai", "dataColors": ["#1F3A5F", "#E07A5F", "#3D9970", "#F2CC8F", "#81B29A", "#6C757D", "#B5838D", "#264653"],
         "background": "#FFFFFF", "foreground": "#1B1B1B", "tableAccent": "#1F3A5F"}


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = content if isinstance(content, str) else json.dumps(content, indent=2, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--columns", required=True, type=Path)
    ap.add_argument("--mode", choices=["import", "directquery"], default="import")
    args = ap.parse_args()
    mode = "import" if args.mode == "import" else "directQuery"
    cols = load_columns(args.columns)

    sm, rp = OUT / f"{NAME}.SemanticModel", OUT / f"{NAME}.Report"
    for d in (sm / "definition", rp / "definition", rp / "StaticResources"):
        shutil.rmtree(d, ignore_errors=True)

    write(OUT / f"{NAME}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                 "settings": {"enableAutoRecovery": True}})

    # semantic model (TMDL)
    write(sm / "definition.pbism", {"version": "4.0", "settings": {}})
    write(sm / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1567\n")
    tables = [("gold", t) for t in GOLD_TABLES] + [("ops", t) for t in OPS_TABLES]
    missing = [f"{s}.{t}" for s, t in tables if (s, t) not in cols]
    if missing:
        raise SystemExit(f"columns export lacks: {missing}")
    model = ["model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
             "\tsourceQueryCulture: en-US", "\tdiscourageImplicitMeasures", ""]
    model += [f"ref table '{t}'" for _, t in tables]
    write(sm / "definition" / "model.tmdl", "\n".join(model) + "\n")
    for s, t in tables:
        write(sm / "definition" / "tables" / f"{t}.tmdl", table_tmdl(s, t, cols[(s, t)], mode))
    rels = []
    for frm, to, active in RELATIONSHIPS:
        rels += [f"relationship {tag()}"] + ([] if active else ["\tisActive: false"]) + [f"\tfromColumn: {frm}", f"\ttoColumn: {to}", ""]
    write(sm / "definition" / "relationships.tmdl", "\n".join(rels))

    # report (PBIR)
    write(rp / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    d = rp / "definition"
    write(d / "version.json", {"$schema": f"{SCHEMA_BASE}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    write(d / "report.json", {"$schema": f"{SCHEMA_BASE}/report/1.0.0/schema.json",
                              "themeCollection": {"baseTheme": {"name": "ekadai", "reportVersionAtImport": "5.59", "type": "SharedResources"}},
                              "layoutOptimization": "None"})
    write(rp / "StaticResources" / "SharedResources" / "BaseThemes" / "ekadai.json", THEME)
    write(d / "pages" / "pages.json", {"$schema": f"{SCHEMA_BASE}/pagesMetadata/1.0.0/schema.json",
                                       "pageOrder": [p for p, _, _ in PAGES], "activePageName": PAGES[0][0]})
    for pid, display, visuals in PAGES:
        page = {"$schema": f"{SCHEMA_BASE}/page/1.0.0/schema.json", "name": pid, "displayName": display,
                "displayOption": "FitToPage", "height": 720, "width": 1280}
        write(d / "pages" / pid / "page.json", page)
        for i, v in enumerate(visuals):
            vid = f"{pid.replace('-', '')}v{i}"
            write(d / "pages" / pid / "visuals" / vid / "visual.json",
                  {"$schema": f"{SCHEMA_BASE}/visualContainer/1.0.0/schema.json", "name": vid, **v})
    print(f"wrote {NAME}.pbip ({mode}): {len(tables)} tables, {len(RELATIONSHIPS)} relationships, "
          f"{len(MEASURES)} measures, {len(PAGES)} pages, {sum(len(v) for _, _, v in PAGES)} visuals")


if __name__ == "__main__":
    main()
