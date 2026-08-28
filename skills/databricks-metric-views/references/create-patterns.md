# Metric View Patterns & YAML Reference

Patterns for **creating** metric views and the complete YAML field reference. For how to **query** them, see [query-patterns.md](query-patterns.md).

## Creation Patterns

### Pattern 1: Simple Metrics from a Single Table

```sql
CREATE OR REPLACE VIEW catalog.schema.product_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.sales
  comment: "Product sales metrics"
  dimensions:
    - name: Product Name
      expr: product_name
    - name: Sale Date
      expr: sale_date
  measures:
    - name: Units Sold
      expr: COUNT(1)
    - name: Total Revenue
      expr: SUM(price * quantity)
    - name: Average Price
      expr: AVG(price)
$$
```

> Subsequent patterns show the YAML body only. Wrap in `CREATE OR REPLACE VIEW <catalog.schema.name> WITH METRICS LANGUAGE YAML AS $$...$$` to deploy.

### Pattern 2: Derived Dimensions with CASE

Transform raw values into business-friendly categories.

```yaml
version: 1.1
source: catalog.schema.orders
dimensions:
  - name: Order Month
    expr: "DATE_TRUNC('MONTH', order_date)"
  - name: Priority Level
    expr: CASE
      WHEN priority <= 2 THEN 'High'
      WHEN priority <= 4 THEN 'Medium'
      ELSE 'Low'
      END
    comment: "Bucketed priority: High (1-2), Medium (3-4), Low (5)"
measures:
  - name: Order Count
    expr: COUNT(1)
  - name: Total Amount
    expr: SUM(total_amount)
```

### Pattern 3: Ratios and Composability

**Approach A — inline ratio:** directly express the ratio in `expr`.

```yaml
measures:
  - name: Profit Margin
    expr: (SUM(revenue) - SUM(cost)) / SUM(revenue)
  - name: Revenue per Employee
    expr: SUM(revenue) / COUNT(DISTINCT employee_id)
```

**Approach B — atomic first, then compose via `MEASURE()`:** define each atomic measure, then build ratios that reference them. Ratios defined this way re-aggregate safely at any dimension grain.

```yaml
measures:
  - name: Total Revenue
    expr: SUM(amount)
  - name: Order Count
    expr: COUNT(1)
  - name: Unique Customers
    expr: COUNT(DISTINCT customer_id)
  - name: Fulfilled Orders
    expr: COUNT(1) FILTER (WHERE status = 'FULFILLED')
  # Composed — backtick-quote names with spaces
  - name: Average Order Value
    expr: "MEASURE(`Total Revenue`) / MEASURE(`Order Count`)"
  - name: Fulfillment Rate
    expr: "MEASURE(`Fulfilled Orders`) / MEASURE(`Order Count`)"
```

Prefer Approach B when the same atomic measures are reused across multiple ratios or referenced in Genie queries.

### Pattern 4: Filtered Measures (FILTER clause)

```yaml
version: 1.1
source: catalog.schema.orders
dimensions:
  - name: Order Month
    expr: "DATE_TRUNC('MONTH', order_date)"
  - name: Region
    expr: region
measures:
  - name: Total Orders
    expr: COUNT(1)
  - name: Open Orders
    expr: COUNT(1) FILTER (WHERE status = 'OPEN')
  - name: Open Revenue
    expr: SUM(amount) FILTER (WHERE status = 'OPEN')
    comment: "Revenue at risk from unfulfilled orders"
  - name: Fulfillment Rate
    expr: COUNT(1) FILTER (WHERE status = 'FULFILLED') * 1.0 / COUNT(1)
```

### Pattern 5: Star Schema with Joins

> **Join alias naming:** alias must not be a prefix of any fact-table column name — use `dim_` prefix. See [Joins](#joins) below.

```yaml
version: 1.1
source: catalog.schema.fact_sales
joins:
  - name: dim_customer
    source: catalog.schema.dim_customer
    'on': source.customer_id = dim_customer.customer_id
  - name: dim_product
    source: catalog.schema.dim_product
    'on': source.product_id = dim_product.product_id
dimensions:
  - name: Customer Segment
    expr: dim_customer.segment
  - name: Product Category
    expr: dim_product.category
  - name: Sale Month
    expr: "DATE_TRUNC('MONTH', source.sale_date)"
measures:
  - name: Total Revenue
    expr: SUM(source.amount)
  - name: Unique Customers
    expr: COUNT(DISTINCT source.customer_id)
```

### Pattern 6: Snowflake Schema (Nested Joins)

Requires DBR 17.1+. **Nested join columns require the full dot-chain** — `customer.nation.name`, not `nation.name` (fails with `UNRESOLVED_COLUMN`).

```yaml
version: 1.1
source: catalog.schema.orders
joins:
  - name: dim_customer
    source: catalog.schema.customer
    'on': source.customer_key = dim_customer.customer_key
    joins:
      - name: nation
        source: catalog.schema.nation
        'on': dim_customer.nation_key = nation.nation_key
        joins:
          - name: region
            source: catalog.schema.region
            'on': nation.region_key = region.region_key
dimensions:
  - name: Nation
    expr: dim_customer.nation.name
  - name: Region
    expr: dim_customer.nation.region.name
measures:
  - name: Total Revenue
    expr: SUM(source.total_price)
```

### Pattern 7: Materialized Metric View

Requires serverless compute and DBR 17.2+.

```yaml
version: 1.1
source: catalog.schema.transactions
dimensions:
  - name: Category
    expr: product_category
  - name: Day
    expr: "DATE_TRUNC('DAY', transaction_date)"
measures:
  - name: Revenue
    expr: SUM(amount)
  - name: Transactions
    expr: COUNT(1)
materialization:
  schedule: every 1 hour
  mode: relaxed
  materialized_views:
    - name: daily_category
      type: aggregated
      dimensions: [Category, Day]
      measures: [Revenue, Transactions]
    - name: full_model
      type: unaggregated
      cluster_by:
        auto: true
```

**Design heuristics:** include filter columns as dimensions so filtered queries hit the aggregated MV. `aggregated` requires at least one dimension or measure. A metric view sourced from another metric view cannot use `unaggregated`. Refreshes incur Lakeflow Spark Declarative Pipelines charges.

### Pattern 8: Window Measures (Experimental, `version: 0.1`)

| Range | Description |
|-------|-------------|
| `current` | Only rows matching the current ordering value |
| `cumulative` | All rows up to and including the current row |
| `trailing <N> <unit>` | N units before current row (excludes current) |
| `leading <N> <unit>` | N units after current row |
| `all` | All rows regardless of ordering |

**Trailing window and period-over-period:**

```yaml
version: 0.1
source: catalog.schema.orders
filter: order_date > DATE'2024-01-01'
dimensions:
  - name: date
    expr: order_date
measures:
  - name: t7d_customers
    expr: COUNT(DISTINCT customer_id)
    window:
      - order: date
        range: trailing 7 day
        semiadditive: last
  - name: prev_day_sales
    expr: SUM(total_price)
    window:
      - order: date
        range: trailing 1 day
        semiadditive: last
  - name: curr_day_sales
    expr: SUM(total_price)
    window:
      - order: date
        range: current
        semiadditive: last
  - name: day_over_day_growth
    expr: (MEASURE(curr_day_sales) - MEASURE(prev_day_sales)) / MEASURE(prev_day_sales) * 100
```

`day_over_day_growth` references other window measures via `MEASURE()` and needs no `window` block itself. For YTD and semiadditive patterns, see the [Window Measures docs](https://docs.databricks.com/metric-views/data-modeling/window-measures). Query syntax: [query-patterns.md §Querying window measures](query-patterns.md#querying-window-measures).

### Pattern 9: SQL Query as Source

Use when declarative joins can't be expressed (DBR < 17.1, complex pre-joins). **`joins:` is not supported with a SQL-query source.**

```yaml
version: 1.1
source: "(SELECT o.o_totalprice, c.c_mktsegment, o.o_orderdate
          FROM catalog.schema.orders o
          JOIN catalog.schema.customer c ON o.o_custkey = c.c_custkey)"
dimensions:
  - name: Customer Segment
    expr: c_mktsegment
  - name: Order Month
    expr: "DATE_TRUNC('MONTH', o_orderdate)"
measures:
  - name: Total Revenue
    expr: SUM(o_totalprice)
```

A metric view can also use another metric view as `source` for layered composition.

### Pattern 10: Level of Detail (LOD) Expressions

#### Fixed LOD — via window functions in the source query

Pre-computed at a fixed grain before query-time filters apply. Reference in a measure with `ANY_VALUE()`.

```yaml
version: 1.1
source: |
  SELECT o_orderkey, o_orderpriority, o_totalprice,
         SUM(o_totalprice) OVER (PARTITION BY o_orderpriority) AS priority_total
  FROM samples.tpch.orders
dimensions:
  - name: Order Priority
    expr: o_orderpriority
measures:
  - name: Total Sales
    expr: SUM(o_totalprice)
  - name: Pct of Priority Total
    expr: SUM(o_totalprice) / ANY_VALUE(priority_total)
```

#### Coarser LOD — via window measures

Filter-aware, adapts to query-time dimensions. See window measure `version`/DBR requirements in [Pattern 8](#pattern-8-window-measures-experimental-version-01).

```yaml
measures:
  - name: Total Sales
    expr: SUM(o_totalprice)
  - name: All Priorities Sales
    expr: SUM(o_totalprice)
    window:
      - order: Order Priority
        range: all
        semiadditive: last
  - name: Pct of Total Sales
    expr: "SUM(o_totalprice) / MEASURE(`All Priorities Sales`)"
```

---

## YAML Field Reference

### Top-Level Fields

| Field | Required | Description |
|-------|----------|-------------|
| `version` | No | `"1.1"` for DBR 17.2+, `"0.1"` for DBR 16.4–17.1. Defaults to `1.1`. |
| `source` | Yes | Source table, view, SQL query, or metric view in three-level namespace. |
| `comment` | No | Description of the metric view (v1.1+). |
| `filter` | No | SQL boolean expression applied as a global WHERE clause. |
| `dimensions` | Yes | At least one required. |
| `measures` | Yes | At least one required. |
| `joins` | No | Star/snowflake schema join definitions. |
| `materialization` | No | Pre-computation configuration (experimental). |

### Dimensions

See Patterns 1–6 for code examples.

| Field | Req | Notes |
|-------|-----|-------|
| `name` | Yes | Display name; backtick-quoted in queries when it has spaces |
| `expr` | Yes | Non-aggregate SQL — column ref, function, CASE, or joined column via `join.col` (full dot-chain for nested: `customer.nation.name`) |
| `comment` | No | Description (v1.1+, DBR 17.2+) |
| `synonyms` | No | Up to 10 alternate names; Genie uses these to match user phrasing (DBR 17.3+) |
| `display_name` | No | Human-readable label in visualizations (DBR 17.3+, max 255 chars) |
| `format` | No | Display format hint — see [Format Specifications](#format-specifications) (DBR 17.3+) |

### Measures

See Patterns 1–4 and 3B for code examples.

| Field | Req | Notes |
|-------|-----|-------|
| `name` | Yes | Queried via `` MEASURE(`name`) `` — backtick-quote names with spaces |
| `expr` | Yes | Aggregate function (SUM/COUNT/AVG/MIN/MAX); supports `FILTER (WHERE ...)`; composed measures reference atomics via `MEASURE()` |
| `comment` | No | Description (v1.1+, DBR 17.2+) |
| `synonyms` | No | Up to 10 alternate names for Genie (DBR 17.3+) |
| `display_name` | No | Human-readable label in visualizations (DBR 17.3+) |
| `format` | No | Display format hint — see [Format Specifications](#format-specifications) (DBR 17.3+) |
| `window` | No | Window block for cumulative/trailing/semiadditive measures (v0.1, experimental) — see [Pattern 8](#pattern-8-window-measures-experimental-version-01) |

`MEASURE()` cannot be used with the `OVER` clause.

**Window spec fields:**

| Field | Req | Description |
|-------|-----|-------------|
| `order` | Yes | Dimension name that determines window ordering |
| `range` | Yes | `current` / `cumulative` / `trailing <N> <unit>` / `leading <N> <unit>` / `all` |
| `semiadditive` | Yes | `first` or `last` — value used when the order dimension is absent from GROUP BY |

### Format Specifications

Optional `format` block on a dimension or measure. Requires `version: 1.1`, DBR 17.3+. **Every `format` block must include a `type` discriminator** — omitting it fails with `METRIC_VIEW_INVALID_VIEW_DEFINITION`. Values are **enum tokens**, not strftime patterns. Omit `format` entirely if unsure — a malformed block fails the whole definition.

`decimal_places` is an object: `{type: max|exact|all, places: N}`.

| `type` | Type-specific keys |
|--------|--------------------|
| `number` | `decimal_places`, `hide_group_separator`, `abbreviation` (`none`/`compact`/`scientific`) |
| `currency` | `currency_code` (ISO-4217, **required**), `decimal_places`, `hide_group_separator`, `abbreviation` |
| `percentage` | `decimal_places`, `hide_group_separator` |
| `byte` | `decimal_places`, `hide_group_separator` |
| `date` | `date_format` (`year_month_day`/`locale_short_month`/`locale_long_month`/`locale_number_month`/`year_week`), `leading_zeros` |
| `date_time` | `date_format`, `time_format` (`no_time`/`locale_hour_minute`/`locale_hour_minute_second`), `leading_zeros` — at least one non-`no_*` required |

### Joins

See [Pattern 5](#pattern-5-star-schema-with-joins) and [Pattern 6](#pattern-6-snowflake-schema-nested-joins) for code examples. Use `on` (expression) **or** `using` (column list), not both.

| Field | Notes |
|-------|-------|
| `name` | Join alias — must NOT be a prefix of any fact-table column name (use `dim_<name>`) |
| `source` | Fully-qualified table/view |
| `on` | Join condition; quote the key: `'on':`. Reference fact table as `source`, join table by its alias |
| `using` | Column list alternative to `on` |
| `joins` | Nested joins for snowflake schema (DBR 17.1+); joined tables cannot include MAP type columns |

**Join rules:** many-to-one only (many-to-many silently skews aggregates). Nested join columns require the full dot-chain: `customer.nation.name`, not `nation.name`. Optimizer joins only the tables a query actually needs.

### Filter

```yaml
filter: order_date > '2020-01-01'
filter: order_date > '2020-01-01' AND status != 'CANCELLED'
filter: customer.active = true     # joined column
```

### Materialization

See [Pattern 7](#pattern-7-materialized-metric-view) for a code example. **Requirements:** serverless compute; DBR 17.2+; `TRIGGER ON UPDATE` not supported.

| Type | When to use |
|------|-------------|
| `unaggregated` | Expensive source views or many joins |
| `aggregated` | Frequently queried dimension/measure combos |

**Clustering & Partitioning** (only on `unaggregated`; only on dimensions; `cluster_by` and `partition_by` cannot coexist):

| Field | Description |
|-------|-------------|
| `cluster_by.cols` | List of dimensions to cluster on |
| `cluster_by.auto: true` | Databricks picks clustering keys automatically |
| `partition_by` | List of dimensions to partition on |

---

## YAML Formatting Gotchas

| Gotcha | Problem | Fix |
|--------|---------|-----|
| **Colons in expressions** | YAML interprets unquoted colons as key-value separators | Wrap `expr` in double quotes: `expr: "DATE_TRUNC('MONTH', order_date)"` |
| **Backtick-starting expressions** | YAML cannot start a value with a backtick | Wrap in double quotes: `expr: "\`First Name\`"` |
| **`on` keyword in joins** | YAML 1.1 may interpret `on` as boolean `true` | Quote the key: `'on': source.fk = dim.pk` |
| **`yes`/`no`/`off` values** | YAML 1.1 interprets these as booleans | Quote when used as values or keys |
| **Multi-line expressions** | Indentation errors break the YAML | Use `\|` block scalar: `expr: \|` then indent all lines 2+ spaces beyond `expr` |
| **MEASURE() with spaces** | `MEASURE(Total Revenue)` causes `PARSE_SYNTAX_ERROR` | Backtick-quote: `` MEASURE(`Total Revenue`) `` |
| **Snowflake column refs** | `nation.name` causes `UNRESOLVED_COLUMN` when `nation` is nested | Use full dot-chain: `customer.nation.name` |
| **`format` block without `type`** | Fails with `METRIC_VIEW_INVALID_VIEW_DEFINITION` | Set a valid `type`: `number`/`currency`/`percentage`/`byte`/`date`/`date_time` |
| **Date subtraction** | `date1 - date2` returns `INTERVAL`, not an integer | Use `DATEDIFF(date1, date2)` |
| **Column mapping by position** | System maps YAML columns to `column_list` by position, not by name | Order dimensions and measures carefully |

---

## Deployment Errors

| Error code | Cause | Fix |
|------------|-------|-----|
| `UNRESOLVED_COLUMN` | Snowflake join missing parent prefix, or column not in source | Use full dot-chain: `customer.nation.name`. Verify column exists with `discover-schema` |
| `PARSE_SYNTAX_ERROR` | Unquoted multi-word `MEASURE()` name | Backtick-quote: `` MEASURE(`Total Revenue`) `` |
| `METRIC_VIEW_INVALID_VIEW_DEFINITION` | Malformed `format` block (missing or invalid `type`) | Set a valid `type`; `currency` also needs `currency_code` |
| `INVALID_EXTRACT_BASE_FIELD_TYPE` | Join alias is a prefix of a fact-table column name | Rename alias to `dim_<name>` or any non-prefix |
| `DATATYPE_MISMATCH` | Date subtraction returns `INTERVAL`, not an integer | Use `DATEDIFF(date1, date2)` |
| `SCHEMA_NOT_FOUND` | Target schema does not exist | `CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>` |
| `TABLE_OR_VIEW_NOT_FOUND` | Source or joined table dropped or renamed | Verify with `SHOW TABLES IN <catalog>.<schema> LIKE '<table>'` |
| `INSUFFICIENT_PRIVILEGES` | Missing `CREATE VIEW` or `USE SCHEMA` on target | `GRANT CREATE TABLE, USE SCHEMA ON SCHEMA <schema> TO <principal>` |

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **DBR version error** | `version: 1.1` requires DBR 17.2+; `version: 0.1` requires DBR 16.4+. `synonyms`/`display_name`/`format` need DBR 17.3+ |
| **Materialization not working** | Serverless compute must be enabled; check pipeline state in Workflows → Pipelines |
| **`format:` block deploy error** | Every `format:` block requires a `type:` discriminator |
| **No Delta Sharing** | Metric views cannot be shared via Delta Sharing |
| **No data profiling** | Data profiling is not supported on metric views |
| **`ALTER VIEW` removes UC comments** | Always include `comment` fields in the YAML to preserve them across replacements |
