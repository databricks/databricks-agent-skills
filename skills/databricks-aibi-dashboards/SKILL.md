---
name: databricks-aibi-dashboards
description: "Create Databricks AI/BI dashboards. Must use when creating, updating, or deploying Lakeview dashboards as Databricks Dashboard have a unique json structure. CRITICAL: You MUST test ALL SQL queries via CLI BEFORE deploying. Follow guidelines strictly."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.2.3"
parent: databricks-core
---

# AI/BI Dashboard Skill

Create Databricks AI/BI dashboards (formerly Lakeview dashboards).
A dashboard should be showing something relevant for a human, typically some KPI on the top, and based on the story, some graph (often temporal), and we see "something happens".
**Follow these guidelines strictly.**

> **Building a dashboard, in order:** profile the data ([Steps 1-3](#new-dashboard-creation-workflow)) → pick widgets from the [Widget catalog](#widget-catalog) → read [4-examples.md](references/4-examples.md) end to end (a complete dashboard JSON) → read the spec section of each widget you picked (catalog Spec column) and [3-filters.md](references/3-filters.md) for filters → build the JSON, test every query, deploy ([Step 4](#step-4-plan-and-build-the-dashboard-json), [Step 5](#step-5-deploy)).

## Widget catalog

> **Wrong version = broken widget!** The #1 cause of dashboard errors: use the `v` below in `spec.version`. Spec = where the widget's exact JSON is (a section named after it): **1** [1-widget-specifications.md](references/1-widget-specifications.md), **2** [2-advanced-widget-specifications.md](references/2-advanced-widget-specifications.md), **F** [3-filters.md](references/3-filters.md), **6** [6-custom-visualizations.md](references/6-custom-visualizations.md). Anchored index: [1- § Widget Index](references/1-widget-specifications.md#widget-index-version--where-documented).

| Widget (`widgetType`) | Use for | v | Spec |
|---|---|---|---|
| text (markdown) | titles, section headers, notes; no spec block | – | 1 |
| `counter` | a KPI number, with sparkline and period-over-period delta | 2 | 1 |
| `table` | row-level detail, high-cardinality lists | 2 | 1 |
| `bar`, `line` | comparisons across categories; trends over time (stacked/grouped, horizontal, annotations) | 3 | 1 |
| `pie` | share of a few categories | 3 | 1 |
| `area` | trends showing volume or stacked composition | 3 | 2 |
| `scatter` | relationship between two measures; bubble = size by a third | 3 | 2 |
| `combo` | bar + line on one chart, metrics with different scales (dual axis) | 1 | 2 |
| `pivot` | cross-tab (dimensions on rows and columns) with conditional cell styling; cohort retention | 3 | 2 |
| `histogram` | frequency distribution of a numeric column | 3 | 2 |
| `heatmap` | "X by Y" matrix, color = aggregate | 3 | 2 |
| `box` | distribution (median, quartiles, outliers) across categories | 1 | 2 |
| `funnel` | stage-by-stage conversion | 1 | 2 |
| `waterfall` | positive/negative deltas to a total (P&L bridge, MoM walk) | 1 | 2 |
| `sankey` | flow between two or more stages | 1 | 2 |
| `forecast-line` | history continued by a forecast band (`AI_FORECAST` SQL) | 1 | 2 |
| `gantt` | schedules and events with a start and end | 1 | 2 |
| `symbol-map` | lat/lon points (bubble map) | 2 | 1 |
| `choropleth-map` | regions (countries, states) colored by value | 1 | 2 |
| `path-map` | routes and ordered tracks | 1 | 2 |
| `filter-single-select`, `filter-multi-select`, `filter-date-range-picker`, `filter-date-picker`, `filter-text-entry` | global or page-level filters | 2 | F |
| `range-slider` | numeric range filter | 2 | F |
| `custom-vega-viz` | what standard widgets can't draw (bullet, layered, gauge, radar, sunburst) | 1 | 6 |

There is no `cohort` widget (use `pivot` with a color-scale cell style) and no Genie widget (see [Linking a Genie Space](#linking-a-genie-space-optional)).

**Standard or custom?** Use standard widgets by default. Use Vega-Lite when the required visualization cannot be expressed with standard widgets. A different aggregation, color palette, tooltip, reference line, or small multiple usually does not require a custom specification. Case-by-case guide: [6-custom-visualizations.md § Standard widget or custom Vega-Lite?](references/6-custom-visualizations.md#standard-widget-or-custom-vega-lite).

For custom charts, confirm the required marks and transforms are supported by **Vega-Lite**. It does not support every Vega example or chart type. Keep joins and business calculations in dataset SQL; the custom specification controls how the returned data is drawn.

> **When a custom app fits better:** dashboards are for read-only KPIs, charts, and filters over governed tables. For write-back / data entry, UI or interactions beyond the grid, embedded or auth-gated workflows, or a Genie/chat assistant as the main surface, build a Databricks App with `databricks-apps` (it brings in `databricks-app-design`). Linking an "Ask Genie" space to *this* dashboard stays here (see Linking a Genie Space below).

## Quick Reference

| Task | Command |
|------|---------|
| List warehouses | `databricks warehouses list` |
| List tables | `databricks experimental aitools tools query --warehouse WH "SHOW TABLES IN catalog.schema"` |
| Get schema | `databricks experimental aitools tools discover-schema catalog.schema.table1 catalog.schema.table2` |
| Test query | `databricks experimental aitools tools query --warehouse WH "SELECT..."` |
| Create dashboard | `databricks lakeview create --display-name "X" --warehouse-id "WH" --dataset-catalog CATALOG --dataset-schema SCHEMA --serialized-dashboard "$(cat file.json)" --json '{"parent_path": "/Workspace/Users/<you>/path"}'` (flag-only vs JSON-only fields: [Step 5](#step-5-deploy)) |
| Update dashboard | `databricks lakeview update DASHBOARD_ID --dataset-catalog CATALOG --dataset-schema SCHEMA --serialized-dashboard "$(cat file.json)"`: **re-pass both dataset flags** (update replaces the dashboard; omitting them nulls the defaults and breaks every bare-table query) |
| Publish / unpublish | `databricks lakeview publish DASHBOARD_ID --warehouse-id WH --embed-credentials` / `databricks lakeview unpublish DASHBOARD_ID`: `--embed-credentials` runs viewers' queries as the publisher so `/published` works without table access; resets on every publish. New dashboard: pass it unless queries must run as each viewer (RLS / individual permissions). Republish: keep the current mode ([Updating](#updating-an-existing-dashboard)). |
| List / get / delete | `databricks lakeview list` / `databricks lakeview get DASHBOARD_ID` / `databricks lakeview trash DASHBOARD_ID` |
| Tag after creation (default; tracks this skill's resources) | `databricks workspace-entity-tag-assignments create-tag-assignment dashboards DASHBOARD_ID aidevkit_project --tag-value ai-dev-kit` |

> **`--warehouse` flag:** if `aitools tools query` fails with `unknown flag: --warehouse` on your CLI version, drop the flag and set `DATABRICKS_WAREHOUSE_ID=WH` in the environment (picked up automatically).

---

## NEW DASHBOARD CREATION WORKFLOW

**You MUST test ALL SQL queries via CLI BEFORE deploying. Follow the overall logic in these steps for new dashboard - Skipping validation causes broken dashboards.**

### Step 1: Get Warehouse ID if not already known

```bash
# List warehouses to find one for SQL execution
databricks warehouses list
```

### Step 2: Discover Table Schemas and existing data pattern

Know the data first: this exploration drives the Step 4 design (which widgets, filters, groupings).

Use `discover-schema` as the default — one call returns columns, types, sample rows, null counts, and row count. If you only know the schema, list tables first with `query "SHOW TABLES IN ..."`.

`databricks experimental aitools tools discover-schema catalog.schema.orders catalog.schema.customers`

Then probe with aggregate SQL (cardinality, top values, distributions, trend grain, story confirmation) before designing; fan independent probes out in one multi-query call (`--output json`, check each statement's `state`): [7-dashboard-design.md § Profiling the data](references/7-dashboard-design.md#profiling-the-data).

> **Dashboard queries are different:** inside the dashboard JSON use bare table names (✅ `FROM trips`, ❌ `FROM samples.nyctaxi.trips`); a hardcoded prefix wins over the dataset flags and isn't portable ([Dataset architecture](#1-dataset-architecture)).


### Step 3: Verify Data Matches Story
Before finalizing, run the SQL Queries you intend to add in each dataset to confirm that they run properly and that the result are valid.
Widgets render the query output, so the values must also make sense at a business level.

If values don't match expectations, ensure the query is correct, fix the data if you can, or adjust the story before creating the dashboard.

### Step 4: Plan and build the dashboard JSON

1. **Plan the widgets:** pick each one from the [Widget catalog](#widget-catalog), map it to a dataset, and note which filter fields it needs ([example plan](references/7-dashboard-design.md#planning-example)).
2. **Read [4-examples.md](references/4-examples.md) end to end before writing any JSON.** It's a complete working dashboard exercising every construct (dataset measures + `MEASURE()`, sparkline counters, forecast-line with annotations, pivot with conditional cells, symbol-map, histogram, range-slider filter, theme). Keep its structure; swap the tables, metrics, palette, and narrative for the user's data and story.
3. **Read the spec section of every widget you picked** (catalog Spec column) for its exact JSON and version, and [3-filters.md](references/3-filters.md) for filters.
4. **Check the filters:** every dataset you want filtered must contain the filter field (typically group by it). A pre-aggregated table without dates WON'T be date-filtered.
5. **Build the dashboard JSON** as a local working file (intermediate step, not the deliverable), following the [skeleton](#json-structure-required-skeleton) and the [implementation guidelines](#implementation-guidelines).

### Step 5: Deploy

**Now deploy the JSON** with `databricks lakeview create` (below). The task isn't complete until it succeeds and returns a dashboard ID; the JSON file is only an intermediate artifact.

**Give the user the dashboard link** (host: `databricks auth env -o json` → `.env.DATABRICKS_HOST`; note the `v3`, plain `/sql/dashboards/` is the legacy path):
- **Draft:** `https://<host>/sql/dashboardsv3/<DASHBOARD_ID>`
- **Published:** append `/published` (only valid once you've run `databricks lakeview publish DASHBOARD_ID`)

After deploying, the [Quick Reference](#quick-reference) `lakeview` commands manage the lifecycle (list, get, update, publish, unpublish, trash, tag).

```bash
# parent_path must ALREADY EXIST or create fails "Tree node ... does not exist":
databricks workspace mkdirs /Workspace/Users/me@co.com/dashboards

# Create (mix flags + --json; each field has ONE valid place):
#   --dataset-catalog / --dataset-schema: FLAG-ONLY and required. In --json the CLI warns
#     "unknown field" and drops them, so no dataset query resolves its catalog.schema.
#   parent_path: JSON-ONLY (no flag); without it the dashboard lands at /Users/<you>/<display-name>.
#   display_name / warehouse_id / serialized_dashboard: either form; flags read better.
# Capture the id with -o json and don't add 2>&1: create echoes the dashboard back and merged
# stderr breaks jq (the dashboard IS created, but you lose the id and the step looks failed).
DASHBOARD_ID=$(databricks lakeview create \
  --display-name "My Dashboard" \
  --warehouse-id "abc123def456" \
  --dataset-catalog "my_catalog" \
  --dataset-schema "my_schema" \
  --serialized-dashboard "$(cat dashboard.json)" \
  --json '{"parent_path": "/Workspace/Users/me@co.com/dashboards"}' \
  -o json | jq -r '.dashboard_id')
# Publish (--embed-credentials: see the CLI table above)
databricks lakeview publish "$DASHBOARD_ID" --warehouse-id "abc123def456" --embed-credentials
```

---

## UPDATING AN EXISTING DASHBOARD

To change a dashboard that already exists, build the updated JSON with the [creation workflow](#new-dashboard-creation-workflow) above, then deploy it with `update` + `publish` on the **same** `DASHBOARD_ID` — never re-run `create`/import. Commands: [Quick Reference](#quick-reference) (`update` must re-pass `--dataset-catalog` / `--dataset-schema`).

- **Don't `create`/import to update:** it mints a new id + URL and breaks shared links; `create` is for brand-new dashboards only.
- **`update` changes only the draft:** `/published` stays on the last snapshot until you `publish` again, so always `publish` after `update`.
- **Keep the published credential mode:** read it first (`databricks lakeview get-published DASHBOARD_ID -o json | jq .embed_credentials`); pass `--embed-credentials` only if `true`. Switching from individual permissions to embedded widens what viewers see: only when asked.

---

## JSON Structure (Required Skeleton)

Every dashboard's `serialized_dashboard` content must follow this exact structure:

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
- Query binding: `query.fields[].name` == `encodings.*.fieldName` ([rule](#2-widget-field-expressions)). Filters bind differently: range sliders expose `MIN`/`MAX` query fields for one `fieldName`; parameter-bound date filters use `query.parameters`.

### Theme & Color (always set this)

Set top-level `uiSettings.theme` on every dashboard (light/dark canvas, widget, font, selection colors; `visualizationColors`; `widgetHeaderAlignment`): the highest-impact polish. Two gotchas: counters take **no** per-widget color (`value.color` renders "unsupported widget definition"; the theme `fontColor` colors their number), and semantic colors go in `color.scale.mappings` as a bare hex string (`{"hex": ...}` and `themeColorType` are silently dropped on charts). Full block, theme keys, palette rules, and starter palettes: [7-dashboard-design.md § Theme & Color](references/7-dashboard-design.md#theme--color).

### Linking a Genie Space (Optional)

For an "Ask Genie" button, add `uiSettings.genieSpace` (`isEnabled`, `overrideId`, `enablementMode`) next to `theme`. Genie is **not** a widget (no `"widgetType": "assistant"`). JSON: [7-dashboard-design.md § Linking a Genie Space](references/7-dashboard-design.md#linking-a-genie-space-optional).

---

## Design Best Practices

Apply unless the user says otherwise: a global date filter when data has time columns, time-bounded KPIs that support period comparison (MoM, YoY), value formatting by meaning (currency, %, compact K/M/B), and chart type matched to cardinality. Details: [7-dashboard-design.md § Design best practices](references/7-dashboard-design.md#design-best-practices).

## Reference Files

| What are you building? | Reference |
|------------------------|-----------|
| **Start here** (read end to end before writing JSON): full working dashboard | [4-examples.md](references/4-examples.md) |
| Text, counter, table, bar/line, pie, symbol-map; naming, formatting, field expressions | [1-widget-specifications.md](references/1-widget-specifications.md) |
| Area, scatter, combo, pivot, histogram, heatmap, box, funnel, waterfall, sankey, forecast-line, gantt, choropleth / path maps | [2-advanced-widget-specifications.md](references/2-advanced-widget-specifications.md) |
| Dashboard with filters (global or page-level) | [3-filters.md](references/3-filters.md) |
| Custom Vega-Lite widgets (layered charts, bullet, gauge, radar, sunburst), standard vs custom choice | [6-custom-visualizations.md](references/6-custom-visualizations.md) |
| Data profiling probes, theme & colors, grid layout and sizes, Genie link, data variance | [7-dashboard-design.md](references/7-dashboard-design.md) |
| Dataset-level measures and `MEASURE()` | [8-dataset-measures.md](references/8-dataset-measures.md) |
| Debugging a broken dashboard | [5-troubleshooting.md](references/5-troubleshooting.md) |

---

## Implementation Guidelines

### 1) DATASET ARCHITECTURE

- **Fewer datasets is better: one dataset backing as many widgets as possible.** Clicking a chart value (a bar, a slice) filters **that dataset**, so every widget sharing it re-renders; narrow per-widget datasets break this cross-filtering and force explicit filter widgets. Prefer one wide dataset per domain (orders, cases, customers); split only for a different grain, pre-aggregation, or a parameter the others can't tolerate.
- **Two ways to define a dataset:** SQL via `queryLines` (full control: `WITH` / `JOIN` / `AI_FORECAST`), or the UC asset shorthand `{"name": "ds_x", "asset_name": "catalog.schema.table_or_view"}` (tables, views, metric views; no SQL). Shapes: [8-dataset-measures.md § Defining a dataset](references/8-dataset-measures.md#defining-a-dataset).
- **Exactly ONE valid SQL query per dataset** when using `queryLines` (no multiple queries separated by `;`)
- **Queries must use bare table names only** — no catalog, no schema prefix. Example: `FROM orders`, never `FROM gold.orders` or `FROM main.gold.orders`. The catalog and schema come from the `--dataset-catalog` and `--dataset-schema` flags at creation time. These flags only fill in missing parts — they do NOT override any catalog/schema written in the query.
- SELECT must include all dimensions needed by widgets and all derived columns via `AS` aliases
- Put ALL business logic (CASE/WHEN, COALESCE, ratios) into the dataset SELECT with explicit aliases
- **Add ORDER BY** when visualization depends on data order:
  - Time series: `ORDER BY date` for chronological display
  - Rankings/Top-N: `ORDER BY metric DESC LIMIT 10` for "Top 10" charts
  - Categorical charts: `ORDER BY metric DESC` to show largest values first

#### Dataset-level measures + `MEASURE()`

Declare reusable measures in a dataset's `columns` (or rely on a metric view's YAML measures, without redeclaring them) and reference them from any widget as ``MEASURE(`Name`)`` (counter, table, bar, line, pie, pivot; mixes with inline aggregations). Shapes and examples: [8-dataset-measures.md](references/8-dataset-measures.md).

### 2) WIDGET FIELD EXPRESSIONS

> **CRITICAL: Field Name Matching Rule**
> For chart, table, counter, and custom-viz widgets, each selected `name` in `query.fields` MUST exactly match its `fieldName` in `encodings`.
> If they don't match, the widget shows "no selected fields to visualize" error!

For `custom-vega-viz` the binding has extra layers (`spec.encodings.fields`, `spec.data.queryName`, Vega-Lite `data.name: "databricks_query"`, spec as a JSON **string** in `spec.jsonSpec.spec`): read [6-custom-visualizations.md § Widget Contract](references/6-custom-visualizations.md#widget-contract) before generating one.

Correct vs mismatched example: [5-troubleshooting.md § no selected fields](references/5-troubleshooting.md#widget-shows-no-selected-fields-to-visualize).

Allowed expressions in widget queries (you CANNOT use CAST or other SQL in expressions):

```json
{"name": "(sum|avg|count|countdistinct|min|max)(col)", "expression": "(SUM|AVG|COUNT|COUNT(DISTINCT)|MIN|MAX)(`col`)"}
{"name": "(daily|weekly|monthly)(date)", "expression": "DATE_TRUNC(\"(DAY|WEEK|MONTH)\", `date`)"}
{"name": "field", "expression": "`field`"}
```

If you need conditional logic or multi-field formulas, compute a derived column in the dataset SQL first.

Some widgets support additional expressions: Gantt can use `FIRST(...)` for status fields, and geometry map bindings require `ST_ASGEOJSON(...)`. See the corresponding widget reference for these shapes.

### 3) SPARK SQL PATTERNS

- Date math: `date_sub(current_date(), N)` for days, `add_months(current_date(), -N)` for months
- Date truncation: `DATE_TRUNC('DAY'|'WEEK'|'MONTH'|'QUARTER'|'YEAR', column)`
- **AVOID** `INTERVAL` syntax - use functions instead

### 4) LAYOUT (12-Column Grid, NO GAPS)

**Every page must include `"layoutVersion": "GRID_V1"`** alongside `pageType`. Positions are `{"x", "y", "width", "height"}`; by default each row fills width 12 exactly (no gaps). Counters height 3-4 (never 2), charts 5-6, text headers 12x1 with title and subtitle as separate widgets. Column subdivision by audience, the size table, a standard page structure, and staggered layouts: [7-dashboard-design.md § Layout](references/7-dashboard-design.md#layout-12-column-grid-no-gaps).

### 5) CARDINALITY & READABILITY (CRITICAL)

**Dashboard readability depends on limiting distinct values:**

| Dimension Type | Max Values | Examples |
|----------------|------------|----------|
| Chart color/groups | **3-8** | 4 regions, 5 product lines, 3 tiers |
| Filters | 4-15 | 8 countries, 5 channels |
| High cardinality | **Table only** | customer_id, order_id, SKU |

**Before creating any chart with color/grouping:**
1. Check column cardinality via discover-schema or a COUNT DISTINCT query
2. If >10 distinct values, aggregate to higher level OR use TOP-N + "Other" bucket
3. For high-cardinality dimensions, use a table widget instead of a chart

**Before a trend chart, check variance:** a small `MAX - MIN` range (e.g. 83-89% on 0-100) looks flat; prefer a KPI with delta or a table ([details](references/7-dashboard-design.md#data-variance-considerations)).

### 6) QUALITY CHECKLIST

Before deploying, verify:
1. All widget names use only alphanumeric + hyphens + underscores
2. **Every page has `"layoutVersion": "GRID_V1"`**
3. All rows sum to width=12 with no gaps
4. KPIs use height 3-4, charts use height 5-6
5. Chart dimensions have reasonable cardinality (≤8 for colors/groups)
6. All widget query expressions reference existing dataset columns or aliases
7. **Visualization field bindings match exactly** (charts, tables, counters, custom viz: `query.fields[].name` == encoding `fieldName`, e.g. both `"sum(spend)"`); validate filters against their own contracts.
8. Counter datasets: use `disaggregated: true` for 1-row datasets, `disaggregated: false` with aggregation for multi-row
9. **Percent values must be 0-1 for `number-percent` format** (0.865 displays as "86.5%", don't forget to set the format). If data is 0-100, either divide by 100 in SQL or use `number` format instead.
10. SQL uses Spark syntax (date_sub, not INTERVAL)
11. **All SQL queries tested via CLI and return expected data**
12. **Every dataset you want filtered MUST contain the filter field** — filters only affect datasets with that column in their query
13. **`abbreviation: "compact"` needs `decimalPlaces`** — without it the value isn't rounded (renders `$9.756278496M`, not `$9.76M`)

---

## Related Skills

- **[databricks-apps](../databricks-apps/SKILL.md)** - a custom-code interactive app (write-back, bespoke UI, in-app chat / Genie) instead of a managed dashboard
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - for querying the underlying data and system tables
- **[databricks-pipelines](../databricks-pipelines/SKILL.md)** - for building the data pipelines that feed dashboards
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - for scheduling dashboard data refreshes
