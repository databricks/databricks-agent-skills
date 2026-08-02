---
name: databricks-aibi-dashboards
description: "Create Databricks AI/BI dashboards. Must use when creating, updating, or deploying Lakeview dashboards as Databricks Dashboard have a unique json structure. CRITICAL: You MUST test ALL SQL queries via CLI BEFORE deploying. Follow guidelines strictly."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.2.1"
parent: databricks-core
---

# AI/BI Dashboard Skill

Create Databricks AI/BI dashboards (formerly Lakeview dashboards).
A dashboard should be showing something relevant for a human, typically some KPI on the top, and based on the story, some graph (often temporal), and we see "something happens".
**Follow these guidelines strictly.**

> **When a custom app fits better:** A managed AI/BI dashboard is the right tool for read-only KPIs, charts, and filters over governed tables. If the user instead needs a *custom-code interactive app* — write-back / data entry, bespoke UI or interactions beyond the dashboard grid, embedded or auth-gated workflows, or a conversational Genie/chat assistant as the primary surface — build a Databricks App instead with the `databricks-apps` skill (which brings in `databricks-app-design` for the data-screen UX). Linking an "Ask Genie" space to *this* dashboard stays here (see Linking a Genie Space below).

## Quick Reference

| Task | Command |
|------|---------|
| List warehouses | `databricks warehouses list` |
| List tables | `databricks experimental aitools tools query --warehouse WH "SHOW TABLES IN catalog.schema"` |
| Get schema | `databricks experimental aitools tools discover-schema catalog.schema.table1 catalog.schema.table2` |
| Test query | `databricks experimental aitools tools query --warehouse WH "SELECT..."` |
| Create dashboard | `databricks lakeview create --display-name "X" --warehouse-id "WH" --dataset-catalog CATALOG --dataset-schema SCHEMA --serialized-dashboard "$(cat file.json)" --json '{"parent_path": "/Workspace/Users/<you>/path"}'` — `--dataset-catalog` / `--dataset-schema` are **flag-only** (REQUIRED; CLI silently drops them if put in `--json`); `parent_path` is JSON-only (no flag). Queries must use bare table names. |
| Update dashboard | `databricks lakeview update DASHBOARD_ID --dataset-catalog CATALOG --dataset-schema SCHEMA --serialized-dashboard "$(cat file.json)"` — **always re-pass `--dataset-catalog` / `--dataset-schema` on update** (same flag-only rule as create); update replaces the serialized dashboard, so omitting them nulls the per-dataset defaults and breaks every bare-table query. |
| Publish | `databricks lakeview publish DASHBOARD_ID --warehouse-id WH` |
| Delete | `databricks lakeview trash DASHBOARD_ID` |

> **`--warehouse` flag**: if `databricks experimental aitools tools query --warehouse WH "..."` fails with `unknown flag: --warehouse` on your CLI version, set `DATABRICKS_WAREHOUSE_ID=WH` in the environment instead and drop the flag — the command auto-picks it from there.

---

## Widget Index (Version + Where Documented)

> **Wrong version = broken widget!** This is the #1 cause of dashboard errors.

| Widget Type | Version | Documented in |
|-------------|---------|---------------|
| text (markdown, no spec block) | N/A | [1-widget-specifications.md#text-headersdescriptions](references/1-widget-specifications.md#text-headersdescriptions) |
| `counter` (KPI + sparkline + comparison) | **2** | [1-widget-specifications.md#counter-kpi](references/1-widget-specifications.md#counter-kpi) |
| `table` | **2** | [1-widget-specifications.md#table](references/1-widget-specifications.md#table) |
| `bar`, `line` | **3** | [1-widget-specifications.md#line--bar-charts](references/1-widget-specifications.md#line--bar-charts) |
| `pie` | **3** | [1-widget-specifications.md#pie-chart](references/1-widget-specifications.md#pie-chart) |
| `symbol-map` (lat/lon point map) | **2** | [1-widget-specifications.md#symbol-map-bubble-map](references/1-widget-specifications.md#symbol-map-bubble-map) |
| `area` | **3** | [2-advanced-widget-specifications.md#area-chart](references/2-advanced-widget-specifications.md#area-chart) |
| `scatter` | **3** | [2-advanced-widget-specifications.md#scatter-plot--bubble-chart](references/2-advanced-widget-specifications.md#scatter-plot--bubble-chart) |
| `combo` (bar+line, dual-axis) | **1** | [2-advanced-widget-specifications.md#combo-chart-bar--line](references/2-advanced-widget-specifications.md#combo-chart-bar--line) |
| `choropleth-map` (regions colored by value) | **1** | [2-advanced-widget-specifications.md#choropleth-map](references/2-advanced-widget-specifications.md#choropleth-map) |
| `forecast-line` (with `AI_FORECAST` SQL) | **1** | [2-advanced-widget-specifications.md#forecast-line-with-ai_forecast](references/2-advanced-widget-specifications.md#forecast-line-with-ai_forecast) |
| `pivot` (with conditional cell rules) | **3** | [2-advanced-widget-specifications.md#pivot](references/2-advanced-widget-specifications.md#pivot) |
| `histogram` (with `bin(col, binWidth=N)`) | **3** | [2-advanced-widget-specifications.md#histogram](references/2-advanced-widget-specifications.md#histogram) |
| `sankey` | **1** | [2-advanced-widget-specifications.md#sankey](references/2-advanced-widget-specifications.md#sankey) |
| `heatmap` | **3** | [2-advanced-widget-specifications.md#heatmap](references/2-advanced-widget-specifications.md#heatmap) |
| `funnel` | **1** | [2-advanced-widget-specifications.md#funnel](references/2-advanced-widget-specifications.md#funnel) |
| `box` | **1** | [2-advanced-widget-specifications.md#box](references/2-advanced-widget-specifications.md#box) |
| `waterfall` | **1** | [2-advanced-widget-specifications.md#waterfall](references/2-advanced-widget-specifications.md#waterfall) |
| `filter-single-select`, `filter-multi-select`, `filter-date-range-picker` | **2** | [3-filters.md#filter-widget-structure](references/3-filters.md#filter-widget-structure) |
| `range-slider` | **2** | [3-filters.md#range-slider-numeric-range-filter](references/3-filters.md#range-slider-numeric-range-filter) |

> Cohort retention charts are built as a `pivot` with a color-scale cell style — there is no `cohort` widget type. See pivot in [2-advanced-widget-specifications.md](references/2-advanced-widget-specifications.md).

---

## NEW DASHBOARD CREATION WORKFLOW

**You MUST test ALL SQL queries via CLI BEFORE deploying. Follow the overall logic in these steps for new dashboard - Skipping validation causes broken dashboards.**

### Step 1: Get Warehouse ID if not already known

```bash
# List warehouses to find one for SQL execution
databricks warehouses list
```

### Step 2: Discover Table Schemas and existing data pattern

A good dashboard comes from knowing the data first. Spend time here — the exploration drives design decisions in Step 4 (which widgets, which filters, which groupings).

Use `discover-schema` as the default — one call returns columns, types, sample rows, null counts, and row count. If you only know the schema, list tables first with `query "SHOW TABLES IN ..."`.

`databricks experimental aitools tools discover-schema catalog.schema.orders catalog.schema.customers`

Sample rows alone don't tell you what to build. you can write aggregate SQL through `databricks experimental aitools tools query --warehouse <WH> "..."` to probe typically:

- **Cardinality** of candidate grouping columns → decides chart color-group vs. table (≤8 distinct values for charts, see Cardinality & Readability below).
- **Top categorical values** → populates filter options and chart legends meaningfully.
- **Numeric distribution** (min/max/avg/percentiles) → decides KPI with delta vs. trend chart (flat metrics shouldn't be line charts, see Data Variance Considerations below).
- **Trend viability** at daily/weekly/monthly grain → picks the right trend granularity.
- **Story confirmation** — run the aggregations you plan to put in the dashboard and check they're not flat, empty, or uninteresting. Fix the query or adjust the story before moving on.

Fan out independent probes in one call — pass several positional SQLs (and/or repeated `--file`) and they run in parallel (default `--concurrency 8`):

```bash
DATABRICKS_WAREHOUSE_ID=<WH> databricks experimental aitools tools query --output json \
  "SELECT COUNT(*) FROM catalog.schema.orders" \
  "SELECT region, COUNT(*) FROM catalog.schema.orders GROUP BY region ORDER BY 2 DESC LIMIT 10" \
  "SELECT MIN(ts), MAX(ts) FROM catalog.schema.orders"
```

- **`--output json` is mandatory** in multi-query mode. Returns one object per statement: `{sql, state, rows, error}`; failures are per-statement (`state: "FAILED"`), others still succeed.
- ⚠️ **Don't trust the exit code** (a failed statement can still exit `0`) — gate on each object's `state != "SUCCEEDED"`.

> **Dashboard queries are different** — inside the dashboard JSON, the `FROM` clause must reference ONLY the table name, with no catalog or schema prefix:
> - ✅ Correct: `FROM trips`
> - ❌ Wrong: `FROM nyctaxi.trips`
> - ❌ Wrong: `FROM samples.nyctaxi.trips`
>
> The catalog and schema are supplied separately via the `--dataset-catalog` and `--dataset-schema` flags when you run `databricks lakeview create`. These flags do NOT rewrite the query — they only fill in the catalog/schema when the query omits them. If you hardcode a catalog or schema in the `FROM` clause, the flags are ignored for that query and the dashboard won't be portable across environments.


### Step 3: Verify Data Matches Story
The datasets.querylines in the dashboard json (see example below) must be tested to ensure 

Before finalizing, run the SQL Queries you intend to add in each dataset to confirm that they run properly and that the result are valid.
This is crucial, as the widget defined in the json will use the query field output to render the visualization. The value should also make sense at a business level.
Remember that for the filter to work, the query should have the field available (so typically group by the filter field)

If values don't match expectations, ensure the query is correct, fix the data if you can, or adjust the story before creating the dashboard.

### Step 4: Plan Dashboard Structure

Before writing JSON, plan your dashboard:

1. You must know the expected specific JSON structure. For this, **Read reference files**: [1-widget-specifications.md](references/1-widget-specifications.md), [3-filters.md](references/3-filters.md).

Always make sure you read an entire example to understand the structure, like [4-examples.md](references/4-examples.md).

2. Think: **What widgets?** Map each visualization to a dataset:
   | Widget | Type | Dataset | Has filter field? |
   |--------|------|---------|-------------------|
   | Revenue KPI | counter | ds_sales | ✓ date, region |
   | Trend Chart | line | ds_sales | ✓ date, region |
   | Top Products | table | ds_products | ✗ no date | 
   ...

3. **What filters?** For each filter, verify ALL datasets you want filtered contain the filter field.
   > **Filters only affect datasets that have the filter field.** A pre-aggregated table without dates WON'T be date-filtered.

4. **Build the dashboard JSON** as a local working file (intermediate step, not the deliverable).

### Step 5: Deploy

**Now deploy the JSON to the workspace.** Run `databricks lakeview create` (below). Your task is not complete until this command succeeds and returns a dashboard ID — the JSON file alone is an intermediate working artifact.

After deploying, the same `lakeview` subcommands manage the dashboard's lifecycle (list, get, update, publish, trash).

```bash
# Deploy: creates the dashboard in the workspace and returns a dashboard ID.
# Canonical form — MIX flags + --json. Each field has exactly ONE valid place:
#   --dataset-catalog / --dataset-schema : FLAG-ONLY (REQUIRED — no JSON field).
#       The CLI silently warns "unknown field" and drops them if put in --json,
#       leaving every dataset query unable to resolve its catalog.schema.
#   parent_path : JSON-ONLY (no flag). Without it, dashboard lands at
#       /Users/<you>/<display-name>.
#   display_name / warehouse_id / serialized_dashboard : either form works;
#       prefer flags for readability.
# Queries inside dashboard.json MUST use bare table names ("FROM trips", never
# "FROM schema.trips" or "FROM catalog.schema.trips") — --dataset-catalog and
# --dataset-schema only fill in missing parts, they do NOT rewrite hardcoded
# prefixes.
databricks lakeview create \
  --display-name "My Dashboard" \
  --warehouse-id "abc123def456" \
  --dataset-catalog "my_catalog" \
  --dataset-schema "my_schema" \
  --serialized-dashboard "$(cat dashboard.json)" \
  --json '{"parent_path": "/Workspace/Users/me@co.com/dashboards"}'

# List all dashboards
databricks lakeview list

# Get dashboard details
databricks lakeview get DASHBOARD_ID

# Update a dashboard
# ALWAYS re-pass --dataset-catalog / --dataset-schema: update replaces the
# serialized dashboard, so omitting them nulls the defaults and breaks queries.
databricks lakeview update DASHBOARD_ID \
  --dataset-catalog "my_catalog" \
  --dataset-schema "my_schema" \
  --serialized-dashboard "$(cat dashboard.json)"

# Publish a dashboard
databricks lakeview publish DASHBOARD_ID --warehouse-id WAREHOUSE_ID

# Unpublish a dashboard
databricks lakeview unpublish DASHBOARD_ID

# Delete (trash) a dashboard
databricks lakeview trash DASHBOARD_ID

# By default, after creation, tag dashboards to track resources created with this skill
databricks workspace-entity-tag-assignments create-tag-assignment \
  dashboards DASHBOARD_ID aidevkit_project --tag-value ai-dev-kit
```

---

## UPDATING AN EXISTING DASHBOARD

To change a dashboard that already exists, build the updated JSON with the [creation workflow](#new-dashboard-creation-workflow) above, then deploy it with `update` + `publish` on the **same** `DASHBOARD_ID` — never re-run `create`/import.

- **Don't `create`/import to update.** That mints a new dashboard id + URL and breaks any link you've already shared; `create` is for brand-new dashboards only.
- **`update` changes only the draft.** The `/published` link viewers see stays on the last snapshot until you `publish` again — so always `publish` after `update`.

---

## JSON Structure (Required Skeleton)

Every dashboard's `serialized_dashboard` content must follow this exact structure:

Important: ALWAYS add a space or `\n` at the end of each `queryLines` value as they are concatenated to create the dataset.

```json
{
  "datasets": [
    {
      "name": "ds_x",
      "displayName": "Dataset X",
      "queryLines": ["SELECT col1, col2 ", "FROM my_table"]
    }
  ],
  "pages": [
    {
      "name": "main",
      "displayName": "Main",
      "pageType": "PAGE_TYPE_CANVAS",
      "layout": [
        {"widget": {/* INLINE widget definition */}, "position": {"x":0,"y":0,"width":2,"height":3}}
      ]
    }
  ]
}
```

**Structural rules (violations cause "failed to parse serialized dashboard"):**
- `queryLines`: Array of strings, NOT `"query": "string"`. Elements are **joined verbatim** with no separator — end each line with ` ` or `\n` (or strip `-- comments`). A line ending in `-- comment` with no newline swallows the next line.
- Widgets: INLINE in `layout[].widget`, NOT a separate `"widgets"` array
- `pageType`: Required on every page (`PAGE_TYPE_CANVAS` or `PAGE_TYPE_GLOBAL_FILTERS`)
- Query binding: `query.fields[].name` must exactly match `encodings.*.fieldName`

### Theme & Color (always set this — it makes or breaks the dashboard)

Read [Theme & Color](references/6-theme-and-color.md) before writing the JSON:
it carries the full theme block, the palette rules, and the contrast
requirements. A dashboard shipped without a theme set looks unfinished.

### Linking a Genie Space (Optional)

To add an "Ask Genie" button to the dashboard, or to link a genie space/room with an ID, add `uiSettings.genieSpace` to the JSON (alongside `theme` if you have one):

```json
"uiSettings": {
  "theme": { /* ... */ },
  "genieSpace": {
    "isEnabled": true,
    "overrideId": "your-genie-space-id-here",
    "enablementMode": "ENABLED"
  }
}
```

> **Genie is NOT a widget.** Link via `uiSettings.genieSpace` only. There is no `"widgetType": "assistant"`.

---

## Design Best Practices

Apply unless user specifies otherwise:
- **Global date filter**: When data has temporal columns, add a date range filter. Most dashboards need time-based filtering.
- **KPI time bounds**: Use time-bounded metrics that enable period comparison (MoM, YoY). Unbounded "all-time" totals are less actionable.
- **Value formatting**: Format values based on their meaning — currency with symbol, percentages with %, large numbers compacted (K/M/B).
- **Chart selection**: Match cardinality to chart type. Few distinct values → bar with color grouping (or pie if you really want a snapshot); many values → table.

## Reference Files

> **Before generating any dashboard JSON, read [4-examples.md](references/4-examples.md) first.** It's a complete reference dashboard exercising every construct (dataset measures + `MEASURE()`, sparkline counters, forecast-line with annotations, pivot with conditional cells, symbol-map, histogram, range-slider filter, theme). Use it to learn the JSON shape; then adapt to the user's data and demo story — keep the structure, swap the tables, metrics, palette, and narrative for the case you're building.

| What are you building? | Reference |
|------------------------|-----------|
| **Start here** — full working dashboard template | [4-examples.md](references/4-examples.md) |
| Any widget (text, counter, table, chart) | [1-widget-specifications.md](references/1-widget-specifications.md) |
| Advanced charts (area, scatter/Bubble, combo (Line+Bar), Choropleth map) | [2-advanced-widget-specifications.md](references/2-advanced-widget-specifications.md) |
| Dashboard with filters (global or page-level) | [3-filters.md](references/3-filters.md) |
| Debugging a broken dashboard | [5-troubleshooting.md](references/5-troubleshooting.md) |

---

## Implementation Guidelines

Read [Implementation Guidelines](references/7-implementation-guidelines.md)
while writing the dashboard JSON: dataset architecture, widget field
expressions, Spark SQL patterns, the 12-column layout grid, cardinality and
readability limits, and the quality checklist to run before shipping.

## Data Variance Considerations

Before creating trend charts, check if the metric has enough variance to visualize meaningfully:

```sql
SELECT MIN(metric), MAX(metric), MAX(metric) - MIN(metric) as range FROM dataset
```

If the range is very small relative to the scale (e.g., 83-89% on a 0-100 scale), the chart will appear nearly flat. Consider:
- Showing as KPI with delta/comparison instead of chart
- Using a table to display exact values
- Adjusting the visualization to focus on the variance

---

## Related Skills

- **`databricks-apps`** - when the user needs a custom-code interactive app (write-back, bespoke UI, in-app chat / Genie) instead of a managed dashboard
- **`databricks-unity-catalog`** - for querying the underlying data and system tables
- **`databricks-pipelines`** - for building the data pipelines that feed dashboards
- **`databricks-jobs`** - for scheduling dashboard data refreshes
