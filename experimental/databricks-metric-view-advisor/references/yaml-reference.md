# Metric View YAML Reference

Complete reference for the YAML specification used in Unity Catalog metric views.

## Contents

- [Top-Level Fields](#top-level-fields)
- [YAML Formatting Gotchas](#yaml-formatting-gotchas)
- [Source](#source)
- [Dimensions](#dimensions)
- [Measures](#measures)
  - [Composability](#composability-recommended-for-complex-measures)
  - [Window Measures](#window-measures-experimental)
  - [Measure Rules](#measure-rules)
- [Joins](#joins)
  - [Star Schema](#star-schema-single-level)
  - [Snowflake Schema](#snowflake-schema-nested-joins-dbr-171)
  - [Join Rules](#join-rules)
- [Semantic Metadata](#semantic-metadata-v11)
- [Level of Detail (LOD) Expressions](#level-of-detail-lod-expressions)
- [Filter](#filter)
- [Materialization](#materialization-experimental)
- [Complete Example](#complete-example)

## Top-Level Fields

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `version` | No | string | YAML spec version. `"1.1"` for DBR 17.2+, `"0.1"` for DBR 16.4-17.1. Defaults to `1.1`. |
| `source` | Yes | string | Source table, view, or SQL query in three-level namespace format. |
| `comment` | No | string | Description of the metric view (v1.1+). |
| `filter` | No | string | SQL boolean expression applied as a global WHERE clause. |
| `dimensions` | Yes | list | Array of dimension definitions (at least one). |
| `measures` | Yes | list | Array of measure definitions (at least one). |
| `joins` | No | list | Star/snowflake schema join definitions. |
| `materialization` | No | object | Pre-computation configuration (experimental). |

## YAML Formatting Gotchas

These are common pitfalls that cause metric view creation to fail:

| Gotcha | Problem | Fix |
|--------|---------|-----|
| **Colons in expressions** | YAML interprets unquoted colons as key-value separators | Wrap `expr` in double quotes: `expr: "DATE_TRUNC('MONTH', order_date)"` |
| **Backtick-starting expressions** | YAML cannot start values with backticks | Wrap in double quotes: `expr: "\`First Name\`"` |
| **`on` keyword in joins** | YAML may interpret `on` as boolean `true` | Quote the key: `'on': source.fk = dim.pk` |
| **`yes`/`no`/`off` keywords** | YAML 1.1 interprets `on`, `off`, `yes`, `no`, `NO` as booleans | Always quote these when used as values or keys |
| **Multi-line expressions** | Indentation errors break YAML | Use `\|` block scalar: `expr: \|` then indent all lines 2+ spaces beyond `expr` |
| **Column mapping** | System maps YAML columns to `column_list` by position, not by name | Order dimensions and measures carefully in definitions |
| **MEASURE() with spaces** | `MEASURE(Total Revenue)` causes `PARSE_SYNTAX_ERROR` | Backtick-quote: `MEASURE(\`Total Revenue\`)` |
| **Snowflake column refs** | `nation.n_name` causes `UNRESOLVED_COLUMN` when `nation` is nested | Use full dot-chain: `customer.nation.n_name` |
| **`format` blocks** | API requires undocumented `type` discriminator, causing parse errors | Omit `format` blocks entirely |
| **Date subtraction** | `date1 - date2` returns `INTERVAL DAY`, not an integer — comparing to `0` or `3` causes `DATATYPE_MISMATCH` | Use `DATEDIFF(date1, date2)` which returns an integer |

## Source

The `source` field can be:
- A **table**: `catalog.schema.my_table`
- A **view**: `catalog.schema.my_view`
- A **metric view**: `catalog.schema.my_metric_view` — enables layered composition of metric views
- A **SQL query**: `(SELECT * FROM catalog.schema.my_table WHERE active = true)`

**Note:** Joins are only supported when source is a table or view, not a SQL query.

**Performance tip:** Databricks recommends setting primary and foreign key constraints on underlying tables with `RELY` for optimal join performance:
```sql
ALTER TABLE catalog.schema.dim_customer ADD CONSTRAINT pk_customer PRIMARY KEY (customer_id) RELY;
ALTER TABLE catalog.schema.fact_orders ADD CONSTRAINT fk_customer FOREIGN KEY (customer_id) REFERENCES catalog.schema.dim_customer(customer_id) RELY;
```

## Dimensions

Dimensions define the categorical attributes used to group and filter data.

```yaml
dimensions:
  - name: Region               # Display name, backtick-quoted in queries
    expr: region_name           # Direct column reference
    comment: "Sales region"     # Optional description (v1.1+)

  - name: Order Month
    expr: DATE_TRUNC('MONTH', order_date)  # SQL transformation

  - name: Order Year
    expr: EXTRACT(YEAR FROM `Order Month`)  # Can reference other dimensions

  - name: Customer Type
    expr: CASE
      WHEN customer_tier = 'A' THEN 'Enterprise'
      WHEN customer_tier = 'B' THEN 'Mid-Market'
      ELSE 'SMB'
      END                      # Multi-line CASE expressions supported

  - name: Nation
    expr: customer.c_name      # Reference joined table columns
```

### Dimension Rules

- `name` is required and becomes the column name in queries (backtick-quoted if it has spaces)
- `expr` is required and must be a valid SQL expression
- Can reference source columns, SQL functions, CASE expressions, and other dimensions
- Can reference columns from joined tables using `join_name.column_name`
- Cannot use aggregate functions (those belong in measures)

## Measures

Measures define aggregated values computed at query time.

```yaml
measures:
  - name: Total Revenue
    expr: SUM(total_price)
    comment: "Sum of all order prices"

  - name: Order Count
    expr: COUNT(1)

  - name: Average Order Value
    expr: AVG(total_price)

  - name: Unique Customers
    expr: COUNT(DISTINCT customer_id)

  - name: Revenue per Customer           # Ratio measure (inline)
    expr: SUM(total_price) / COUNT(DISTINCT customer_id)

  - name: Open Order Revenue             # Filtered measure
    expr: SUM(total_price) FILTER (WHERE status = 'O')
    comment: "Revenue from open orders only"

  - name: Open Revenue per Customer      # Filtered ratio
    expr: SUM(total_price) FILTER (WHERE status = 'O') / COUNT(DISTINCT customer_id) FILTER (WHERE status = 'O')
```

### Composability (Recommended for Complex Measures)

Composability lets you build complex metrics by reusing simpler, foundational measures. **Always define atomic measures first**, then build composed measures referencing them via `MEASURE()`.

```yaml
measures:
  # Step 1: Atomic measures (simple aggregations)
  - name: Total Revenue
    expr: SUM(o_totalprice)
  - name: Order Count
    expr: COUNT(1)
  - name: Unique Customers
    expr: COUNT(DISTINCT o_custkey)
  - name: Fulfilled Orders
    expr: "COUNT(1) FILTER (WHERE o_orderstatus = 'F')"

  # Step 2: Composed measures (reference atomic measures)
  # IMPORTANT: Backtick-quote measure names with spaces inside MEASURE()
  - name: Avg Order Value
    expr: "MEASURE(`Total Revenue`) / MEASURE(`Order Count`)"
    comment: "Average order value, safe for re-aggregation at any dimension"
  - name: Revenue per Customer
    expr: "MEASURE(`Total Revenue`) / MEASURE(`Unique Customers`)"
  - name: Fulfillment Rate
    expr: "MEASURE(`Fulfilled Orders`) / MEASURE(`Order Count`)"
    comment: "Percentage of orders fulfilled"
```

**Composability rules:**
- Reference previously defined dimensions in new dimensions
- Reference any dimension or previously defined measures in new measures
- Always establish fundamental measures (`SUM`, `COUNT`, `AVG`) before defining measures that reference them
- `MEASURE()` references work within a single metric view definition
- Metric views can also serve as sources for other metric views, enabling layered composition

### Window Measures (Experimental)

Add a `window` block to a measure for windowed, cumulative, or semiadditive aggregations. See [Window Measures Documentation](https://docs.databricks.com/aws/en/metric-views/data-modeling/window-measures).

```yaml
measures:
  - name: Running Total
    expr: SUM(total_price)
    window:
      - order: date              # Dimension that orders the window
        range: cumulative        # Window extent (see range values below)
        semiadditive: last       # How to summarize when order dim is not in GROUP BY

  - name: 7-Day Customers
    expr: COUNT(DISTINCT customer_id)
    window:
      - order: date
        range: trailing 7 day    # 7 days before current, EXCLUDING current day
        semiadditive: last
```

**Window range values:**

| Range | Description |
|-------|-------------|
| `current` | Only rows matching the current ordering value |
| `cumulative` | All rows up to and including the current row |
| `trailing <N> <unit>` | N units before current row (excludes current) |
| `leading <N> <unit>` | N units after current row |
| `all` | All rows |

**Window spec fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `order` | Yes | Dimension name that determines window ordering |
| `range` | Yes | Window extent (see values above) |
| `semiadditive` | Yes | `first` or `last` - value to use when order dimension is absent from GROUP BY |

**Multiple windows** can be composed on a single measure (e.g., for year-to-date):

```yaml
  - name: ytd_sales
    expr: SUM(total_price)
    window:
      - order: date
        range: cumulative
        semiadditive: last
      - order: year
        range: current
        semiadditive: last
```

**Derived measures** can reference window measures using `MEASURE()`:

```yaml
  - name: day_over_day_growth
    expr: (MEASURE(current_day_sales) - MEASURE(previous_day_sales)) / MEASURE(previous_day_sales) * 100
```

### Measure Rules

- `name` is required and queried via `MEASURE(\`name\`)`
- `expr` must contain an aggregate function (SUM, COUNT, AVG, MIN, MAX, etc.) — OR a `MEASURE()` reference to previously defined measures (composability)
- **Backtick-quote multi-word measure names** inside `MEASURE()`: use `MEASURE(\`Total Revenue\`)` — NOT `MEASURE(Total Revenue)`. Omitting backticks on names with spaces causes `PARSE_SYNTAX_ERROR` at deployment.
- **Composability**: Define atomic measures first, then compose complex measures using `MEASURE()`. This is the recommended pattern for ratios, rates, and derived KPIs.
- Supports `FILTER (WHERE ...)` for conditional aggregation
- Supports ratios of aggregates (both inline and via composability)
- Window measures use `version: 0.1` (experimental feature)
- `SELECT *` on metric views is NOT supported; must use `MEASURE()` explicitly
- `MEASURE()` cannot be used with the `OVER` clause (no window function usage)
- `MEASURE()` only works on columns defined as measures in a metric view

## Joins

### Star Schema (Single Level)

```yaml
source: catalog.schema.fact_orders
joins:
  - name: customer
    source: catalog.schema.dim_customer
    'on': source.customer_id = customer.id

  - name: product
    source: catalog.schema.dim_product
    'on': source.product_id = product.id
```

### Star Schema with USING

```yaml
joins:
  - name: customer
    source: catalog.schema.dim_customer
    using:
      - customer_id
      - region_id
```

### Snowflake Schema (Nested Joins, DBR 17.1+)

```yaml
source: catalog.schema.orders
joins:
  - name: customer
    source: catalog.schema.customer
    'on': source.customer_id = customer.id
    joins:
      - name: nation
        source: catalog.schema.nation
        'on': customer.nation_id = nation.id
        joins:
          - name: region
            source: catalog.schema.region
            'on': nation.region_id = region.id
```

### Join Rules

- `name` is required and used to reference joined columns: `name.column`
- `source` is the fully qualified table/view name
- Use either `on` (expression) or `using` (column list), not both
- In `on`, reference the fact table as `source` and join tables by their `name`
- The reference defaults to the join table if no prefix is provided in `on` clauses
- **CRITICAL — Snowflake column referencing**: Use the **full dot-chain path** through parent joins to access nested join columns. For example, `customer.nation.n_name` references `n_name` from the `nation` table nested under `customer`. Using just `nation.n_name` will cause `UNRESOLVED_COLUMN` errors. Similarly, `customer.nation.region.r_name` for a region nested two levels deep.
- Nested `joins` create snowflake schema (requires DBR 17.1+)
- Joined tables cannot include MAP type columns
- Joins must follow a **many-to-one** relationship; in many-to-many cases, the first matching row is selected
- All joins are **LEFT OUTER JOIN** semantics
- The optimizer automatically joins only necessary dimension tables based on selected dimensions and measures

## Semantic Metadata (v1.1+)

Semantic metadata enhances Genie and AI/BI dashboard interpretation of metric views. Add these fields to dimensions and measures.

### Fields

| Field | Max | Description |
|-------|-----|-------------|
| `comment` | — | Description of the dimension/measure. Powers Genie understanding. |
| `display_name` | 255 chars | Human-readable label replacing technical names in visualizations |
| `synonyms` | 10 items, 255 chars each | Alternative names for AI/NL tools to discover dimensions/measures |
| `format` | — | **Do not use** — causes parse errors (see Format Types warning below) |

### Example

```yaml
dimensions:
  - name: Order Date
    expr: o_orderdate
    comment: "Date when the order was placed"
    display_name: "Order Date"
    synonyms:
      - 'order time'
      - 'date of order'
      - 'purchase date'

measures:
  - name: Total Revenue
    expr: SUM(o_totalprice)
    comment: "Sum of all order prices in USD"
    display_name: "Total Revenue"
    synonyms:
      - 'total sales'
      - 'gross revenue'
      - 'sales amount'
```

### Format Types

> **Do NOT include `format` blocks in metric view definitions.** The API requires an undocumented `type` discriminator field that causes `METRIC_VIEW_INVALID_VIEW_DEFINITION` errors at deployment. Omit entirely — dashboards and Genie infer formatting from column types and names.

**Important:** When upgrading to spec v1.1, any single-line comments (`#`) in the YAML definition are removed when the definition is saved.

**Tip:** Adding `synonyms` is one of the highest-impact things you can do for Genie quality. Users ask questions using different terms — synonyms bridge that gap.

## Level of Detail (LOD) Expressions

LOD expressions control aggregation granularity independently of the dimensions in a query. There are two approaches:

### Fixed LOD (via SQL window functions in source)

Pre-compute aggregations at a fixed grain by using `OVER (PARTITION BY ...)` in the source query. The result becomes a dimension that measures can reference.

```yaml
version: 1.1
source: |
  SELECT
    o_orderkey, o_orderpriority, o_totalprice, o_orderdate,
    SUM(o_totalprice) OVER (PARTITION BY o_orderpriority) AS priority_total_price
  FROM samples.tpch.orders

dimensions:
  - name: Order Priority
    expr: o_orderpriority
  - name: Order Date
    expr: o_orderdate
  - name: Priority Total Price
    expr: priority_total_price
    comment: "Pre-computed total price for each priority level"

measures:
  - name: Total Sales
    expr: SUM(o_totalprice)
  - name: Pct of Priority Total
    expr: SUM(o_totalprice) / ANY_VALUE(priority_total_price)
    comment: "What % of the priority group's total does this slice represent"
```

**Key rules for Fixed LOD:**
- Computed in the source query, before query-time filters are applied
- Use `OVER ()` with empty parentheses for dataset-wide aggregates (e.g., grand total)
- When referencing a Fixed LOD dimension in a measure, wrap it in `ANY_VALUE()` since the value is constant within a group

### Coarser LOD (via window measures)

Aggregate at a coarser grain than the query by using window measures with `range: all`. This is filter-aware and adapts to query-time dimensions.

```yaml
dimensions:
  - name: Order Priority
    expr: o_orderpriority

measures:
  - name: Total Sales
    expr: SUM(o_totalprice)
  - name: All Priorities Sales
    expr: SUM(o_totalprice)
    window:
      - order: Order Priority
        range: all
        semiadditive: last
    comment: "Total sales across all priorities, ignoring priority grouping"
  - name: Pct of Total Sales
    expr: "SUM(o_totalprice) / MEASURE(`All Priorities Sales`)"
    comment: "Dynamic % of total that respects query-time filters"
```

| Aspect | Fixed LOD | Coarser LOD |
|--------|-----------|-------------|
| Mechanism | SQL window functions in `source` | Window measures with `range: all` |
| Filter behavior | Pre-computed, static (ignores query filters) | Respects query-time filters |
| Dimension dependency | Independent of query GROUP BY | Adapts to query dimensions |

LOD expressions are an advanced feature — only suggest them if the user's analysis requires cross-grain calculations (e.g., "percentage of total", "customer-level averages shown at region level").

## Filter

A global filter applied to all queries as a WHERE clause.

```yaml
filter: order_date > '2020-01-01'

# Multiple conditions
filter: order_date > '2020-01-01' AND status != 'CANCELLED'

# Using joined columns
filter: customer.active = true
```

## Materialization (Experimental)

Pre-compute aggregations for faster query performance. Uses Lakeflow Spark Declarative Pipelines under the hood.

```yaml
materialization:
  schedule: every 6 hours           # Same syntax as MV schedule clause
  mode: relaxed                     # Only "relaxed" supported currently

  materialized_views:
    - name: baseline
      type: unaggregated            # Full unaggregated data model

    - name: revenue_breakdown
      type: aggregated              # Pre-computed aggregation
      dimensions:
        - category
        - region
      measures:
        - total_revenue
        - order_count

    - name: daily_summary
      type: aggregated
      dimensions:
        - order_date
      measures:
        - total_revenue
```

### Materialization Types

| Type | Description | When to Use |
|------|-------------|-------------|
| `unaggregated` | Materializes full data model (source + joins + filter) | Expensive source views or many joins |
| `aggregated` | Pre-computes specific dimension/measure combos | Frequently queried combinations |

**Tips for aggregated materializations:**
- Include potential **filter columns as dimensions** — this improves query rewrite matching for filtered queries
- Aggregated type requires at least one dimension or measure
- Direct table references without selective filters may not benefit from unaggregated materialization

### Materialization Requirements

- Serverless compute must be enabled
- Databricks Runtime 17.2+
- `TRIGGER ON UPDATE` clause is not supported
- Schedule uses same syntax as materialized view schedules
- **Metric views using another metric view as source** cannot have unaggregated materializations
- Incremental refresh is used when possible (same limitations as standard materialized view incremental refresh)
- **Billing:** Refreshing materialized views incurs Lakeflow Spark Declarative Pipelines charges

### Refresh Materialization

**Via SQL:**
```sql
REFRESH MATERIALIZED VIEW <catalog.schema.metric_view_name>
```

**Via Python SDK:**
```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
pipeline_id = "your-pipeline-id"
w.pipelines.start_update(pipeline_id)
```

### Monitor Materialization

```sql
-- View materialization status, refresh timestamps, and pipeline link
DESCRIBE EXTENDED <catalog.schema.metric_view_name>
```

To verify a query uses materialization, run `EXPLAIN EXTENDED` — look for `__materialization_mat___metric_view` in the plan.

### Query Rewrite Behavior

The optimizer tries in order:
1. **Exact match** — query dimensions match a materialized aggregation exactly
2. **Unaggregated match** — falls back to unaggregated materialization if available
3. **Source tables** — queries source data directly if no materialization applies

Materializations must finish building before query rewrite takes effect. In `relaxed` mode, query rewrite skips freshness checks but falls back to source for queries with row-level security (RLS), column masking (CLM), or non-deterministic functions like `current_timestamp()`.

## Complete Example

```sql
CREATE OR REPLACE VIEW catalog.schema.sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Comprehensive sales metrics with customer and product dimensions"
  source: catalog.schema.fact_sales
  filter: "sale_date >= '2023-01-01'"

  joins:
    - name: customer
      source: catalog.schema.dim_customer
      'on': source.customer_id = customer.id
      joins:
        - name: region
          source: catalog.schema.dim_region
          'on': customer.region_id = region.id
    - name: product
      source: catalog.schema.dim_product
      'on': source.product_id = product.id

  dimensions:
    - name: Sale Month
      expr: "DATE_TRUNC('MONTH', sale_date)"
      comment: "Month of sale"
    - name: Customer Name
      expr: customer.name
    - name: Region
      expr: customer.region.name
      comment: "Geographic region (dot-chained through customer join)"
    - name: Product Category
      expr: product.category

  measures:
    # Atomic measures
    - name: Total Revenue
      expr: SUM(amount)
      comment: "Sum of sale amounts"
    - name: Transaction Count
      expr: COUNT(1)
    - name: Unique Customers
      expr: COUNT(DISTINCT customer_id)
    # Composed measures (backtick-quote multi-word names)
    - name: Average Transaction
      expr: "MEASURE(`Total Revenue`) / MEASURE(`Transaction Count`)"
      comment: "Average transaction value"
    - name: Revenue per Customer
      expr: "MEASURE(`Total Revenue`) / MEASURE(`Unique Customers`)"
      comment: "Average revenue per unique customer"

  materialization:
    schedule: every 1 hour
    mode: relaxed
    materialized_views:
      - name: hourly_region
        type: aggregated
        dimensions:
          - Sale Month
          - Region
        measures:
          - Total Revenue
          - Transaction Count
$$
```
