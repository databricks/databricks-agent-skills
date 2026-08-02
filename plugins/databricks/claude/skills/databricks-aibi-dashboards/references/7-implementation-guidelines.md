# Implementation Guidelines

Dataset architecture, widget field expressions, Spark SQL patterns, the
12-column layout grid, cardinality limits, and the pre-ship quality checklist.
Read this while writing the dashboard JSON, not before.

## Contents

  - [1) DATASET ARCHITECTURE](#1-dataset-architecture)
  - [2) WIDGET FIELD EXPRESSIONS](#2-widget-field-expressions)
  - [3) SPARK SQL PATTERNS](#3-spark-sql-patterns)
  - [4) LAYOUT (12-Column Grid, NO GAPS)](#4-layout-12-column-grid-no-gaps)
  - [5) CARDINALITY & READABILITY (CRITICAL)](#5-cardinality--readability-critical)
  - [6) QUALITY CHECKLIST](#6-quality-checklist)

---

### 1) DATASET ARCHITECTURE

- **Fewer datasets is better — aim for one dataset that backs as many widgets as possible.** Clicking a value on a chart (e.g., a bar, a slice) acts as a filter on **that dataset**, and every other widget sharing the same dataset re-renders with the click applied. Splitting widgets across many narrow datasets breaks this cross-filtering and forces users to set explicit filter widgets for what should "just work". Prefer one wide dataset per domain (orders, cases, customers); only split when a widget genuinely needs different grain, pre-aggregation, or a parameter the others can't tolerate.
- **Two ways to define a dataset**:
  - **SQL query**: `{"name": "ds_x", "displayName": "...", "queryLines": ["SELECT ...", "FROM table"]}` — full control, can include `WITH` / `JOIN` / `AI_FORECAST` / etc.
  - **UC asset shorthand**: `{"name": "ds_x", "asset_name": "catalog.schema.table_or_view"}` — no SQL needed. Works for tables, views, and metric views. You can still stack `columns` (measures + derived dimensions) on top: `{"name": "ds_x", "asset_name": "...", "columns": [{"displayName": "Total Revenue", "expression": "SUM(\`amount_usd\`)"}]}` — same `MEASURE()` pattern.
- **Exactly ONE valid SQL query per dataset** when using `queryLines` (no multiple queries separated by `;`)
- **Queries must use bare table names only** — no catalog, no schema prefix. Example: `FROM orders`, never `FROM gold.orders` or `FROM main.gold.orders`. The catalog and schema come from the `--dataset-catalog` and `--dataset-schema` flags at creation time. These flags only fill in missing parts — they do NOT override any catalog/schema written in the query.
- SELECT must include all dimensions needed by widgets and all derived columns via `AS` aliases
- Put ALL business logic (CASE/WHEN, COALESCE, ratios) into the dataset SELECT with explicit aliases
- **Contract rule**: Every widget `fieldName` must exactly match a dataset column or alias
- **Add ORDER BY** when visualization depends on data order:
  - Time series: `ORDER BY date` for chronological display
  - Rankings/Top-N: `ORDER BY metric DESC LIMIT 10` for "Top 10" charts
  - Categorical charts: `ORDER BY metric DESC` to show largest values first

#### Dataset-level measures + `MEASURE()`

Widget expressions are usually inline aggregations (`{"name": "sum(x)", "expression": "SUM(\`x\`)"}`). But you can also **declare reusable measures on the dataset itself** and reference them by name — every widget that consumes the dataset can use the same metric without redefining it.

Two ways to define measures:

1. **Dashboard-level `columns`** (works on any dataset — SQL query or `asset_name`):
   ```json
   {
     "name": "ds_support",
     "queryLines": ["SELECT * FROM support_cases"],
     "columns": [
       {"displayName": "Total Cases",     "description": "Count of cases",
        "expression": "COUNT(`case_id`)"},
       {"displayName": "Reopen Rate %",   "description": "% of reopened cases",
        "expression": "SUM(CASE WHEN `reopened_flag` THEN 1 ELSE 0 END) * 100.0 / COUNT(`case_id`)"},
       {"displayName": "Priority Level",  "description": "Sorted priority label",
        "expression": "CASE WHEN `priority`='Critical' THEN '1-Critical' ELSE '4-Low' END"}
     ]
   }
   ```

2. **Metric-view source** — if the dataset's `asset_name` (or `FROM` clause) is a UC metric view, its YAML-defined measures are already queryable. **Do not redeclare them** in `columns`. See the `databricks-metric-views` skill.

Either way, widgets reference the measure by name:

```json
"fields": [{"name": "measure(Total Cases)", "expression": "MEASURE(`Total Cases`)"}],
"encodings": {"value": {"fieldName": "measure(Total Cases)", "displayName": "Total Cases"}}
```

`MEASURE(\`...\`)` works in counter, table, bar, line, pie, pivot — any widget that takes a field expression. Mix it with inline aggregations freely.

### 2) WIDGET FIELD EXPRESSIONS

> **CRITICAL: Field Name Matching Rule**
> The `name` in `query.fields` MUST exactly match the `fieldName` in `encodings`.
> If they don't match, the widget shows "no selected fields to visualize" error!

**Correct pattern for aggregations:**
```json
// In query.fields:
{"name": "sum(spend)", "expression": "SUM(`spend`)"}

// In encodings (must match!):
{"fieldName": "sum(spend)", "displayName": "Total Spend"}
```

**WRONG - names don't match:**
```json
// In query.fields:
{"name": "spend", "expression": "SUM(`spend`)"}  // name is "spend"

// In encodings:
{"fieldName": "sum(spend)", ...}  // ERROR: "sum(spend)" ≠ "spend"
```

Allowed expressions in widget queries (you CANNOT use CAST or other SQL in expressions):

```json
{"name": "(sum|avg|count|countdistinct|min|max)(col)", "expression": "(SUM|AVG|COUNT|COUNT(DISTINCT)|MIN|MAX)(`col`)"}
{"name": "(daily|weekly|monthly)(date)", "expression": "DATE_TRUNC(\"(DAY|WEEK|MONTH)\", `date`)"}
{"name": "field", "expression": "`field`"}
```

If you need conditional logic or multi-field formulas, compute a derived column in the dataset SQL first.

### 3) SPARK SQL PATTERNS

- Date math: `date_sub(current_date(), N)` for days, `add_months(current_date(), -N)` for months
- Date truncation: `DATE_TRUNC('DAY'|'WEEK'|'MONTH'|'QUARTER'|'YEAR', column)`
- **AVOID** `INTERVAL` syntax - use functions instead

### 4) LAYOUT (12-Column Grid, NO GAPS)

**Every page must include `"layoutVersion": "GRID_V1"`** alongside `pageType`.

```json
{
  "name": "overview",
  "displayName": "Overview",
  "pageType": "PAGE_TYPE_CANVAS",
  "layoutVersion": "GRID_V1",
  "layout": [...]
}
```

Each widget has a position: `{"x": 0, "y": 0, "width": 4, "height": 4}`

**Pick the subdivision based on the audience.** The 12-column grid divides cleanly into 3, 4, or 6 columns: a 3-column layout (each widget `width: 4`) reduces cognitive load and fits an executive overview; a 4-column (`width: 3`) is the all-rounder; a 6-column (`width: 2`) packs the most density for technical / operations dashboards where the reader is hunting through many metrics at once.

**Default rule**: each row should fill width=12 exactly — no gaps. Once you're confident with the grid, you can stagger heights across columns (a tall widget on the left paired with several shorter ones on the right) so the two halves don't share row boundaries — see 4-examples#layout-12-col-grid for the pattern. Start with strict rows; relax only when the stagger reads better visually.

```
CORRECT:                            WRONG:
y=0: [w=12]                         y=0: [w=8]____  ← gap!
y=1: [w=4][w=4][w=4]  ← fills 12    y=1: [w=2][w=2][w=2][w=2]__  ← gap!
y=4: [w=6][w=6]       ← fills 12
```

**Recommended widget sizes:**

| Widget Type | Width | Height | Notes |
|-------------|-------|--------|-------|
| Text header | 12 | 1 | Full width; use SEPARATE widgets for title and subtitle |
| Counter/KPI | 4 | **3-4** | **NEVER height=2** - too cramped! |
| Line/Bar/Area chart | 6 | **5-6** | Pair side-by-side to fill row |
| Pie chart | 6 | **5-6** | Needs space for legend |
| Full-width chart | 12 | 5-7 | For detailed time series |
| Table | 12 | 5-8 | Full width for readability |

**Standard dashboard structure:**
```text
y=0:  Title (w=12, h=1) - Dashboard title (use separate widget!)
y=1:  Subtitle (w=12, h=1) - Description (use separate widget!)
y=2:  KPIs (w=4 each, h=3) - 3 key metrics side-by-side
y=5:  Section header (w=12, h=1) - "Trends" or similar
y=6:  Charts (w=6 each, h=5) - Two charts side-by-side
y=11: Section header (w=12, h=1) - "Details"
y=12: Table (w=12, h=6) - Detailed data
```

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

### 6) QUALITY CHECKLIST

Before deploying, verify:
1. All widget names use only alphanumeric + hyphens + underscores
2. **Every page has `"layoutVersion": "GRID_V1"`**
3. All rows sum to width=12 with no gaps
4. KPIs use height 3-4, charts use height 5-6
5. Chart dimensions have reasonable cardinality (≤8 for colors/groups)
6. All widget fieldNames match dataset columns exactly
7. **Field `name` in query.fields matches `fieldName` in encodings exactly** (e.g., both `"sum(spend)"`)
8. Counter datasets: use `disaggregated: true` for 1-row datasets, `disaggregated: false` with aggregation for multi-row
9. **Percent values must be 0-1 for `number-percent` format** (0.865 displays as "86.5%", don't forget to set the format). If data is 0-100, either divide by 100 in SQL or use `number` format instead.
10. SQL uses Spark syntax (date_sub, not INTERVAL)
11. **All SQL queries tested via CLI and return expected data**
12. **Every dataset you want filtered MUST contain the filter field** — filters only affect datasets with that column in their query

---
