# Querying Metric Views

How to write correct SQL **against** a metric view. For *creating* metric views (the YAML definitions these examples query), see [create-patterns.md](create-patterns.md).

When the metric view is the data source for a Genie Agent, encode these patterns and rules into the Agent's example SQL and instructions (see [databricks-genie-agent agents.md](../../databricks-genie-agent/references/agents.md)).

## Basics

Measures are accessed only through the `MEASURE()` function in the `SELECT` list, and queries group with `GROUP BY ALL`. Dimensions are referenced by their quoted names:

```sql
-- Revenue by product
SELECT
  `Product Name`,
  MEASURE(`Total Revenue`) AS revenue,
  MEASURE(`Units Sold`) AS units
FROM catalog.schema.product_metrics
GROUP BY ALL
ORDER BY revenue DESC
LIMIT 10
```

You can transform a dimension inline (e.g. truncate a date) and still `GROUP BY ALL`:

```sql
-- Monthly trend
SELECT
  DATE_TRUNC('MONTH', `Sale Date`) AS month,
  MEASURE(`Total Revenue`) AS revenue
FROM catalog.schema.product_metrics
GROUP BY ALL
ORDER BY month
```

## Filtering and ordering

- **Filtering on dimensions** in `WHERE` is allowed and encouraged — including a dimension wrapped in an expression.
- **Never filter on a measure** in `WHERE` — see [Rule 3](#rule-3-never-put-a-measure-in-where-or-group-by). Use `HAVING` or an outer query instead.
- `ORDER BY ALL` orders by every selected column, or order by a measure alias.

```sql
SELECT
  `Order Month`,
  MEASURE(`Total Orders`) AS total,
  MEASURE(`Open Orders`) AS open_orders,
  MEASURE(`Fulfillment Rate`) AS fulfillment_rate
FROM catalog.schema.order_status_metrics
WHERE `Region` = 'EMEA'          -- filtering on a dimension is fine
GROUP BY ALL
ORDER BY ALL
```

Filtering on a transformed dimension:

```sql
SELECT
  `Order Month`,
  MEASURE(`Total Revenue`)::BIGINT AS revenue,
  MEASURE(`Order Count`) AS orders
FROM catalog.schema.tpch_orders_metrics
WHERE extract(year FROM `Order Month`) = 1995
GROUP BY ALL
ORDER BY ALL
```

## Querying across join hierarchies

Metric views with joins (star/snowflake schemas) roll up automatically — query a higher-level dimension and the measure aggregates across the lower levels:

```sql
-- Revenue by region (rolls up across nations and customers)
SELECT
  `Region`,
  MEASURE(`Total Revenue`) AS revenue
FROM catalog.schema.geo_sales
GROUP BY ALL

-- Revenue by nation within a specific region
SELECT
  `Nation`,
  MEASURE(`Total Revenue`) AS revenue,
  MEASURE(`Order Count`) AS orders
FROM catalog.schema.geo_sales
WHERE `Region` = 'EUROPE'
GROUP BY ALL
ORDER BY revenue DESC
```

## Querying window measures

Window measures (trailing, cumulative, period-over-period, semiadditive) are queried with the same `MEASURE()` syntax — no special clause needed:

```sql
SELECT
  date,
  MEASURE(t7d_customers) AS trailing_7d_customers,
  MEASURE(running_total_sales) AS running_total
FROM catalog.schema.customer_activity
WHERE date >= DATE'2024-06-01'
GROUP BY ALL
ORDER BY ALL
```

## Casting measure results

Wrap `MEASURE()` in a cast when you need a specific type (e.g. `::BIGINT` to drop fractional cents):

```sql
SELECT
  `Order Status`,
  MEASURE(`Total Revenue`)::BIGINT AS revenue,
  MEASURE(`Revenue per Customer`)::BIGINT AS rev_per_customer
FROM catalog.schema.tpch_orders_metrics
GROUP BY ALL
```

## Querying via the MCP tool

`manage_metric_views(action="query")` builds the `MEASURE()` / `GROUP BY ALL` SQL for you. `where` filters on **dimensions** only (the same Rule 3 applies):

```python
manage_metric_views(
    action="query",
    full_name="catalog.schema.sales_metrics",
    query_measures=["Total Revenue", "Order Count"],
    query_dimensions=["Customer Segment", "Sale Month"],
    where="`Customer Segment` = 'Enterprise'",
    order_by="ALL",
    limit=50,
)
```

## Rules & Gotchas

These govern **any** query against a metric view — AI/BI dashboards, ad-hoc SQL, and Genie-generated SQL alike. Violating them produces `MISSING_AGGREGATION` and similar errors.

### Rule 1: A dimension inside a `CASE` alongside `MEASURE()` must be grouped

If a `CASE` expression references a dimension **and** calls `MEASURE()`, that dimension **must** appear in `GROUP BY` — otherwise you get `MISSING_AGGREGATION`.

When you need conditional logic on a dimension (e.g. picking different measures by `asset_type`), use a **CTE**: query with the dimension in `GROUP BY ALL` first, then aggregate to the desired grain in the outer query.

```sql
-- ❌ WRONG: asset_type is in a CASE alongside MEASURE() but not grouped → MISSING_AGGREGATION
SELECT
  CASE WHEN asset_type = 'Loan' THEN MEASURE(zdm3yr) ELSE MEASURE(oas) END AS spread
FROM catalog.schema.position_metrics;

-- ✅ CORRECT: dimension in GROUP BY ALL in the inner query, then aggregate in the outer query
WITH by_asset AS (
  SELECT
    asset_type,
    CASE WHEN asset_type = 'Loan' THEN MEASURE(zdm3yr) ELSE MEASURE(oas) END AS spread
  FROM catalog.schema.position_metrics
  GROUP BY ALL
)
SELECT AVG(spread) AS avg_spread
FROM by_asset;
```

### Rule 2: Prefer a pre-built composed measure over reconstructing the logic

If a measure already encodes per-dimension branching, use it directly instead of rebuilding the `CASE` logic in the query. For example, if `blended_spread` is defined to apply `zdm3yr` for loans and `OAS` for other asset types internally, a request for "average spread" should be `MEASURE(blended_spread)` — not a hand-written `CASE WHEN asset_type = 'Loan' ...`. This is the query-side counterpart to [composing measures with `MEASURE()`](https://docs.databricks.com/en/metric-views/data-modeling/composability).

```sql
-- ✅ CORRECT: the measure already encodes the per-asset-type logic
SELECT MEASURE(blended_spread) AS avg_spread
FROM catalog.schema.position_metrics;
```

### Rule 3: Never put a measure in `WHERE` or `GROUP BY`

Measures are only accessible via `MEASURE()` in the `SELECT` list. They are **not** valid in `WHERE` or `GROUP BY`. Do not add predicates like `blended_spread IS NOT NULL` or `avg_oas > 0` to `WHERE`. To filter on a measure result, use `HAVING` after `GROUP BY`, or filter in an outer query / CTE that wraps the aggregated results.

```sql
-- ❌ WRONG: measure in WHERE
SELECT region, MEASURE(blended_spread) AS avg_spread
FROM catalog.schema.position_metrics
WHERE blended_spread IS NOT NULL   -- invalid: measure not allowed in WHERE
GROUP BY region;

-- ✅ CORRECT: filter the aggregated measure with HAVING
SELECT region, MEASURE(blended_spread) AS avg_spread
FROM catalog.schema.position_metrics
GROUP BY region
HAVING MEASURE(blended_spread) IS NOT NULL;

-- ✅ ALSO CORRECT: filter in an outer query wrapping the aggregate
WITH agg AS (
  SELECT region, MEASURE(blended_spread) AS avg_spread
  FROM catalog.schema.position_metrics
  GROUP BY region
)
SELECT * FROM agg WHERE avg_spread IS NOT NULL;
```
