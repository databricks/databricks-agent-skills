# Metric View YAML Reference

Complete reference for the YAML specification used in Unity Catalog metric views.

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

### Dimension Synonyms (Recommended for Genie)

Add up to 10 synonyms per dimension so Genie can map user terminology to the correct field.

```yaml
dimensions:
  - name: Customer Segment
    expr: customer.segment
    synonyms:
      - segment
      - customer tier
      - tier
      - account type
```

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

  - name: Revenue per Customer           # Ratio measure
    expr: SUM(total_price) / COUNT(DISTINCT customer_id)

  - name: Open Order Revenue             # Filtered measure
    expr: SUM(total_price) FILTER (WHERE status = 'O')
    comment: "Revenue from open orders only"

  - name: Open Revenue per Customer      # Filtered ratio
    expr: SUM(total_price) FILTER (WHERE status = 'O') / COUNT(DISTINCT customer_id) FILTER (WHERE status = 'O')
```

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
- `expr` must contain an aggregate function (SUM, COUNT, AVG, MIN, MAX, etc.)
- Supports `FILTER (WHERE ...)` for conditional aggregation
- Supports ratios of aggregates
- Derived measures can reference other measures via `MEASURE()` (used with window measures)
- Window measures use `version: 0.1` (experimental feature)
- `SELECT *` on metric views is NOT supported; must use `MEASURE()` explicitly

### Measure Synonyms (Recommended for Genie)

Add up to 10 synonyms per measure so Genie can map business terminology (e.g., "revenue", "GMV", "top line") to the canonical measure name.

```yaml
measures:
  - name: Total Revenue
    expr: SUM(amount)
    comment: "Gross revenue across all transactions"
    synonyms:
      - sales
      - gross sales
      - top line
      - turnover
      - GMV
```

## Format Specifications

Add an optional `format` block to a dimension or measure to control how values display in dashboards and Genie (requires spec `version: 1.1`). See [Format specifications](https://docs.databricks.com/aws/en/business-semantics/agent-metadata#format-specifications).

**Every `format` block must start with a `type` discriminator.** Omitting it fails deployment with *"Could not resolve subtype … missing type id 'type'"* (`METRIC_VIEW_INVALID_VIEW_DEFINITION`). Values are **enum tokens** (e.g. `year_month_day`), not strftime/`yyyy-MM-dd` patterns.

| `type` | Type-specific keys |
|--------|--------------------|
| `number` | `decimal_places`, `hide_group_separator`, `abbreviation` (`none`/`compact`/`scientific`) |
| `currency` | `currency_code` (ISO-4217, **required**), `decimal_places`, `hide_group_separator`, `abbreviation` |
| `percentage` | `decimal_places`, `hide_group_separator` |
| `byte` | `decimal_places`, `hide_group_separator` |
| `date` | `date_format` (`year_month_day`/`locale_short_month`/`locale_long_month`/`locale_number_month`/`year_week`), `leading_zeros` |
| `date_time` | `date_format`, `time_format` (`no_time`/`locale_hour_minute`/`locale_hour_minute_second`), `leading_zeros` — at least one of `date_format`/`time_format` must be non-`no_*` |

`decimal_places` is itself an object: `{type: max|exact|all, places: N}` (`places` applies to `max`/`exact`).

```yaml
dimensions:
  - name: Order Date
    expr: order_date
    format:
      type: date
      date_format: year_month_day
      leading_zeros: true

measures:
  - name: Total Revenue
    expr: SUM(total_price)
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: Fulfillment Rate
    expr: COUNT(1) FILTER (WHERE status = 'F') * 1.0 / COUNT(1)
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
```

## Joins

### Star Schema (Single Level)

```yaml
source: catalog.schema.fact_orders
joins:
  - name: customer
    source: catalog.schema.dim_customer
    on: source.customer_id = customer.id

  - name: product
    source: catalog.schema.dim_product
    on: source.product_id = product.id
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
    on: source.customer_id = customer.id
    joins:
      - name: nation
        source: catalog.schema.nation
        on: customer.nation_id = nation.id
        joins:
          - name: region
            source: catalog.schema.region
            on: nation.region_id = region.id
```

### Join Rules

- `name` is required and used to reference joined columns: `name.column`
- `source` is the fully qualified table/view name
- Use either `on` (expression) or `using` (column list), not both
- In `on`, reference the fact table as `source` and join tables by their `name`
- Nested `joins` create snowflake schema (requires DBR 17.1+)
- Joined tables cannot include MAP type columns
- **Join alias must not be a prefix of any fact-table column name.** If alias = `firm` and the fact has `firm_global_id`, the parser misreads `firm_global_id` as `firm.global_id` (struct access) and fails with `INVALID_EXTRACT_BASE_FIELD_TYPE: Can't extract a value from "firm_global_id"`. Use `dim_firm` (or any alias that isn't a prefix of a fact column).

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

### Clustering & Partitioning

An `unaggregated` materialized view can declare liquid clustering (`cluster_by`) or partitioning (`partition_by`) to optimize reads. These are **not supported on `aggregated` materializations**.

```yaml
  materialized_views:
    - name: baseline
      type: unaggregated
      cluster_by:                     # Liquid clustering on specific dimensions
        cols:
          - category
          - region

    - name: full_model
      type: unaggregated
      cluster_by:
        auto: true                    # Let Databricks pick clustering keys

    - name: daily_model
      type: unaggregated
      partition_by:                   # Partition instead of cluster
        - order_date
```

| Field | Description |
|-------|-------------|
| `cluster_by.cols` | List of dimensions to liquid-cluster on |
| `cluster_by.auto` | `true` enables automatic liquid clustering (Databricks chooses keys) |
| `partition_by` | List of dimensions to partition the MV on |

- `cluster_by` and `partition_by` are only valid on `unaggregated` materializations, not `aggregated` ones.
- You can only cluster/partition by **dimensions**, not measures.
- A materialized view can use `cluster_by` **or** `partition_by`, but **not both** — they cannot coexist.

### Materialization Types

| Type | Description | When to Use |
|------|-------------|-------------|
| `unaggregated` | Materializes full data model (source + joins + filter) | Expensive source views or many joins |
| `aggregated` | Pre-computes specific dimension/measure combos | Frequently queried combinations |

### Materialization Requirements

- Serverless compute must be enabled
- Databricks Runtime 17.2+
- `TRIGGER ON UPDATE` clause is not supported
- Schedule uses same syntax as materialized view schedules

### Refresh Materialization

```python
# Find and refresh the pipeline
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
pipeline_id = "your-pipeline-id"
w.pipelines.start_update(pipeline_id)
```

> For an end-to-end workflow to deploy, verify the backing pipeline, trigger a refresh, and confirm the optimizer is using the materialized views, see [create-patterns.md → Testing & Verifying Materialization](create-patterns.md#testing--verifying-materialization).

## Complete Example

```sql
CREATE OR REPLACE VIEW catalog.schema.sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Comprehensive sales metrics with customer and product dimensions"
  source: catalog.schema.fact_sales
  filter: sale_date >= '2023-01-01'

  joins:
    - name: customer
      source: catalog.schema.dim_customer
      on: source.customer_id = customer.id
      joins:
        - name: region
          source: catalog.schema.dim_region
          on: customer.region_id = region.id
    - name: product
      source: catalog.schema.dim_product
      on: source.product_id = product.id

  dimensions:
    - name: Sale Month
      expr: DATE_TRUNC('MONTH', sale_date)
      comment: "Month of sale"
    - name: Customer Name
      expr: customer.name
    - name: Region
      expr: region.name
      comment: "Geographic region"
    - name: Product Category
      expr: product.category

  measures:
    - name: Total Revenue
      expr: SUM(amount)
      comment: "Sum of sale amounts"
    - name: Transaction Count
      expr: COUNT(1)
    - name: Unique Customers
      expr: COUNT(DISTINCT customer_id)
    - name: Average Transaction
      expr: AVG(amount)
    - name: Revenue per Customer
      expr: SUM(amount) / COUNT(DISTINCT customer_id)
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
