---
name: databricks-metric-views
description: "Unity Catalog metric views: define, create, query, and manage governed business metrics in YAML. Use when building standardized KPIs, revenue metrics, order analytics, or any reusable business metrics that need consistent definitions across teams and tools."
---

# Unity Catalog Metric Views

Define reusable, governed business metrics in YAML that separate measure definitions from dimension groupings for flexible querying.

## When to Use

Use this skill when:
- Defining **standardized business metrics** (revenue, order counts, conversion rates)
- Building **KPI layers** shared across dashboards, Genie, and SQL queries
- Creating metrics with **complex aggregations** (ratios, distinct counts, filtered measures)
- Defining **window measures** (moving averages, running totals, period-over-period, YTD)
- Modeling **star or snowflake schemas** with joins in metric definitions
- Enabling **materialization** for pre-computed metric aggregations

## Prerequisites

- **Databricks Runtime 17.2+** (for YAML version 1.1)
- SQL warehouse with `CAN USE` permissions
- `SELECT` on source tables, `CREATE TABLE` + `USE SCHEMA` in the target schema

## Quick Start

### Inspect Source Table Schema

Before creating a metric view, call `get_table_stats_and_schema` to understand available columns for dimensions and measures:

```
get_table_stats_and_schema(
    catalog="catalog",
    schema="schema",
    table_names=["orders"],
    table_stat_level="SIMPLE"  # Use "DETAILED" for cardinality, min/max, histograms
)
```

### Create a Metric View

```sql
CREATE OR REPLACE VIEW catalog.schema.orders_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.orders
  comment: "Orders KPIs for sales analysis"
  filter: order_date > '2020-01-01'
  dimensions:
    - name: Order Month
      expr: DATE_TRUNC('MONTH', order_date)
      comment: "Month of order"
    - name: Order Status
      expr: CASE
        WHEN status = 'O' THEN 'Open'
        WHEN status = 'P' THEN 'Processing'
        WHEN status = 'F' THEN 'Fulfilled'
        END
      comment: "Human-readable order status"
  measures:
    - name: Order Count
      expr: COUNT(1)
    - name: Total Revenue
      expr: SUM(total_price)
      comment: "Sum of total price"
    - name: Revenue per Customer
      expr: SUM(total_price) / COUNT(DISTINCT customer_id)
      comment: "Average revenue per unique customer"
$$
```

### Query a Metric View

All measures must use the `MEASURE()` function. `SELECT *` is NOT supported.

```sql
SELECT
  `Order Month`,
  `Order Status`,
  MEASURE(`Total Revenue`) AS total_revenue,
  MEASURE(`Order Count`) AS order_count
FROM catalog.schema.orders_metrics
WHERE extract(year FROM `Order Month`) = 2024
GROUP BY ALL
ORDER BY ALL
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| YAML Syntax | [yaml-reference.md](yaml-reference.md) | Complete YAML spec: dimensions, measures, joins, materialization |
| Creation Patterns | [create-patterns.md](create-patterns.md) | Common creation patterns: star schema, snowflake, filtered measures, window measures, ratios, materialization |
| Querying | [query-patterns.md](query-patterns.md) | How to query metric views: `MEASURE()` basics, filtering/ordering, join-hierarchy rollups, window measures, casting, the MCP query tool, plus rules & gotchas (`CASE`+`MEASURE()` grouping, composed measures, no measures in `WHERE`/`GROUP BY`) |
| Genie Integration | [genie-integration.md](genie-integration.md) | Design rules for AI-ready metric views: one-fact-source, base views, agent metadata (comments, synonyms, formats), domain organization (Genie-space build/validation lives in the databricks-genie skill) |

## MCP Tools

Use the `manage_metric_views` tool for all metric view operations:

| Action | Description |
|--------|-------------|
| `create` | Create a metric view with dimensions and measures |
| `alter` | Update a metric view's YAML definition |
| `describe` | Get the full definition and metadata |
| `query` | Query measures grouped by dimensions |
| `drop` | Drop a metric view |
| `grant` | Grant SELECT privileges to users/groups |

### When to Fall Back to Raw SQL

`manage_metric_views(action="create"|"alter")` accepts only `{name, expr}` for each dimension/measure (plus top-level `comment`). It does **not** pass through:

- `synonyms` on dimensions or measures
- `format` specifications (e.g., `date_format`, currency)
- `window` blocks for window measures
- Per-dimension or per-measure `comment` fields

For any of these, build the full YAML and execute it via `execute_sql` with `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$`. The persisted definition will round-trip correctly (verified: `describe` returns synonyms under each column's `metadata`).

### Create via MCP

```python
manage_metric_views(
    action="create",
    full_name="catalog.schema.orders_metrics",
    source="catalog.schema.orders",
    or_replace=True,
    comment="Orders KPIs for sales analysis",
    filter_expr="order_date > '2020-01-01'",
    dimensions=[
        {"name": "Order Month", "expr": "DATE_TRUNC('MONTH', order_date)", "comment": "Month of order"},
        {"name": "Order Status", "expr": "status"},
    ],
    measures=[
        {"name": "Order Count", "expr": "COUNT(1)"},
        {"name": "Total Revenue", "expr": "SUM(total_price)", "comment": "Sum of total price"},
    ],
)
```

### Query via MCP

```python
manage_metric_views(
    action="query",
    full_name="catalog.schema.orders_metrics",
    query_measures=["Total Revenue", "Order Count"],
    query_dimensions=["Order Month"],
    where="extract(year FROM `Order Month`) = 2024",
    order_by="ALL",
    limit=100,
)
```

### Describe via MCP

```python
manage_metric_views(
    action="describe",
    full_name="catalog.schema.orders_metrics",
)
```

### Grant Access

```python
manage_metric_views(
    action="grant",
    full_name="catalog.schema.orders_metrics",
    principal="data-consumers",
    privileges=["SELECT"],
)
```

## YAML Spec Quick Reference

```yaml
version: 1.1                    # Required: "1.1" for DBR 17.2+
source: catalog.schema.table    # Required: source table/view
comment: "Description"          # Optional: metric view description
filter: column > value          # Optional: global WHERE filter

dimensions:                     # Required: at least one
  - name: Display Name          # Backtick-quoted in queries
    expr: sql_expression        # Column ref or SQL transformation
    comment: "Description"      # Optional (v1.1+)
    synonyms: [alias1, alias2]  # Optional: up to 10, helps Genie match user terms

measures:                       # Required: at least one
  - name: Display Name          # Queried via MEASURE(`name`)
    expr: AGG_FUNC(column)      # Must be an aggregate expression
    comment: "Description"      # Optional (v1.1+)
    synonyms: [alias1, alias2]  # Optional: up to 10, helps Genie match user terms

joins:                          # Optional: star/snowflake schema
  - name: dim_table
    source: catalog.schema.dim_table
    on: source.fk = dim_table.pk

materialization:                # Optional (experimental)
  schedule: every 6 hours
  mode: relaxed
```

## Key Concepts

### Dimensions vs Measures

| | Dimensions | Measures |
|---|---|---|
| **Purpose** | Categorize and group data | Aggregate numeric values |
| **Examples** | Region, Date, Status | SUM(revenue), COUNT(orders) |
| **In queries** | Used in SELECT and GROUP BY | Wrapped in `MEASURE()` |
| **SQL expressions** | Any SQL expression | Must use aggregate functions |

### Why Metric Views vs Standard Views?

| Feature | Standard Views | Metric Views |
|---------|---------------|--------------|
| Aggregation locked at creation | Yes | No - flexible at query time |
| Safe re-aggregation of ratios | No | Yes |
| Star/snowflake schema joins | Manual | Declarative in YAML |
| Materialization | Separate MV needed | Built-in |
| AI/BI Genie integration | Limited | Native |

## Common Issues

| Issue | Solution |
|-------|----------|
| **SELECT * not supported** | Must explicitly list dimensions and use MEASURE() for measures |
| **"Cannot resolve column"** | Dimension/measure names with spaces need backtick quoting |
| **JOIN at query time fails** | Joins must be in the YAML definition, not in the SELECT query |
| **`INVALID_EXTRACT_BASE_FIELD_TYPE` on a fact column** | Join alias collides with a fact column prefix. E.g., alias `firm` + fact column `firm_global_id` → parser reads `firm_global_id` as `firm.global_id`. Rename alias to `dim_firm` (or any non-prefix) |
| **MEASURE() required** | All measure references must be wrapped: `MEASURE(\`name\`)` |
| **DBR version error** | Requires Runtime 17.2+ for YAML v1.1, or 16.4+ for v0.1 |
| **Materialization not working** | Requires serverless compute enabled; currently experimental |

## Integrations

Metric views work natively with:
- **AI/BI Dashboards** - Use as datasets for visualizations
- **AI/BI Genie** - Natural language querying of metrics
- **Alerts** - Set threshold-based alerts on measures
- **SQL Editor** - Direct SQL querying with MEASURE()
- **Catalog Explorer UI** - Visual creation and browsing

## Related Skills

- **`metric-view-advisor`** (from the `fe-metric-view-advisor` plugin) — interactive workflow that ingests tables, dashboards, SQL queries, Genie spaces, or KPI spreadsheets and **generates metric view YAML for you**. Use it when you want a guided scaffold from existing assets. Use this skill (`databricks-metric-views`) when you're authoring YAML directly or need the spec/pattern reference.
- **`databricks-genie`** — create, manage, and validate Genie spaces that consume the metric views built here. See [genie-integration.md](genie-integration.md) for metric-view design rules and [query-patterns.md](query-patterns.md) for the `MEASURE()` query rules Genie must follow.
- **`databricks-aibi-dashboards`** — build AI/BI dashboards on top of metric views.

## Resources

- [Metric Views Documentation](https://docs.databricks.com/en/metric-views/)
- [YAML Syntax Reference](https://docs.databricks.com/en/metric-views/data-modeling/syntax)
- [Joins](https://docs.databricks.com/en/metric-views/data-modeling/joins)
- [Window Measures](https://docs.databricks.com/aws/en/metric-views/data-modeling/window-measures) (Experimental)
- [Materialization](https://docs.databricks.com/en/metric-views/materialization)
- [MEASURE() Function](https://docs.databricks.com/en/sql/language-manual/functions/measure)
