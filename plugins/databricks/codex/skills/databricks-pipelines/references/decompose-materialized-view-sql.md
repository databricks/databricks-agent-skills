# Decomposing Materialized Views with Multiple Joins (SQL)

Decompose materialized views with more than 3 joins into smaller, more manageable views using SQL in Spark Declarative Pipelines.

## Why Decompose Complex Joins?

Materialized views with many joins can cause:

- **Performance degradation**: Complex join graphs are harder to optimize
- **Incremental refresh limitations**: More joins mean more dependencies to track, making the MV more likely to fall back to full recompute
- **Maintenance complexity**: Harder to debug and understand data lineage
- **Resource contention**: Large join operations consume significant compute

**Rule of thumb**: If a materialized view has **more than 3 joins**, consider decomposing it.

## Decomposition Strategy

### Step 1: Identify Join Groups

Analyze your complex query and identify logical groupings:

1. **Dimension enrichment joins**: Joining fact tables with dimension tables
2. **Cross-domain joins**: Joining tables from different business domains
3. **Aggregation-ready joins**: Joins that prepare data for final aggregations

### Step 2: Create Intermediate Materialized Views

Break the complex query into smaller views, each with at most 2-3 joins.

## Example: Before Decomposition

```sql
-- PROBLEMATIC: 5 joins in a single materialized view
CREATE MATERIALIZED VIEW sales_analytics_report
AS
SELECT
  o.order_id,
  o.order_date,
  c.customer_name,
  c.customer_segment,
  p.product_name,
  p.category,
  cat.category_description,
  r.region_name,
  r.country,
  sr.sales_rep_name,
  o.quantity,
  o.revenue,
  o.quantity * p.unit_cost AS total_cost,
  o.revenue - (o.quantity * p.unit_cost) AS profit
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN products p ON o.product_id = p.product_id
JOIN categories cat ON p.category_id = cat.category_id
JOIN regions r ON c.region_id = r.region_id
JOIN sales_reps sr ON o.sales_rep_id = sr.sales_rep_id;
```

## Example: After Decomposition

### Layer 1: Domain-specific intermediate views (1-2 joins each)

```sql
-- Intermediate MV 1: Customer with region enrichment (1 join)
CREATE MATERIALIZED VIEW customer_with_region
AS
SELECT
  c.customer_id,
  c.customer_name,
  c.customer_segment,
  r.region_name,
  r.country
FROM customers c
JOIN regions r ON c.region_id = r.region_id;

-- Intermediate MV 2: Product with category enrichment (1 join)
CREATE MATERIALIZED VIEW product_with_category
AS
SELECT
  p.product_id,
  p.product_name,
  p.category,
  p.unit_cost,
  cat.category_description
FROM products p
JOIN categories cat ON p.category_id = cat.category_id;
```

### Layer 2: Final aggregation view (2-3 joins on intermediate views)

```sql
-- Final MV: Joins the intermediate views plus the sales_reps dimension (3 joins)
CREATE MATERIALIZED VIEW sales_analytics_report
AS
SELECT
  o.order_id,
  o.order_date,
  cwr.customer_name,
  cwr.customer_segment,
  cwr.region_name,
  cwr.country,
  pwc.product_name,
  pwc.category,
  pwc.category_description,
  sr.sales_rep_name,
  o.quantity,
  o.revenue,
  o.quantity * pwc.unit_cost AS total_cost,
  o.revenue - (o.quantity * pwc.unit_cost) AS profit
FROM orders o
JOIN customer_with_region cwr ON o.customer_id = cwr.customer_id
JOIN product_with_category pwc ON o.product_id = pwc.product_id
JOIN sales_reps sr ON o.sales_rep_id = sr.sales_rep_id;
```

## Benefits of This Decomposition

| Aspect | Before | After |
|--------|--------|-------|
| Joins per view | 5 | Max 3 |
| Incremental refresh | Less likely | More likely |
| Debug complexity | High | Low (isolated layers) |
| Reusability | None | Intermediate views reusable |
| Refresh parallelism | Sequential | Parallel (Layer 1 views) |

## Advanced Patterns

Apply these once you've determined a view should be decomposed (based on the rule above); they're best practices for how to split, not reasons to split a simple view.

### Pattern 1: Aggregation Pushdown

When a view joins dimensions *and* computes a heavy aggregation, isolate the aggregation into its own intermediate MV. The expensive GROUP BY then refreshes on its own (and can be reused by other views), while the final view only does a cheap dimension join on the pre-aggregated result. Aggregations also tend to compress the source data, incurring less storage costs than extracting other subqueries.

Push aggregations into intermediate views when possible:

```sql
-- Intermediate: Pre-aggregate orders by customer
CREATE MATERIALIZED VIEW customer_order_summary
AS
SELECT
  customer_id,
  COUNT(*) AS total_orders,
  SUM(revenue) AS total_revenue,
  AVG(revenue) AS avg_order_value
FROM orders
GROUP BY customer_id;

-- Final: Join aggregated data with customer details (1 join)
CREATE MATERIALIZED VIEW customer_revenue_report
AS
SELECT
  c.customer_name,
  c.customer_segment,
  cos.total_orders,
  cos.total_revenue,
  cos.avg_order_value
FROM customers c
JOIN customer_order_summary cos ON c.customer_id = cos.customer_id;
```

### Pattern 2: Slowly Changing Dimension Isolation

Isolate joins with slowly changing dimensions:

```sql
-- Intermediate: Geography hierarchy (changes rarely)
CREATE MATERIALIZED VIEW geography_hierarchy
AS
SELECT
  r.region_id,
  r.region_name,
  c.country_name,
  c.continent
FROM regions r
JOIN countries c ON r.country_id = c.country_id;

-- Final: Use pre-joined geography in reporting views
CREATE MATERIALIZED VIEW sales_by_geography
AS
SELECT
  gh.region_name,
  gh.country_name,
  gh.continent,
  SUM(o.revenue) AS total_revenue
FROM orders o
JOIN geography_hierarchy gh ON o.region_id = gh.region_id
GROUP BY gh.region_name, gh.country_name, gh.continent;
```

### Pattern 3: Private Intermediate Views

Mark intermediate views as PRIVATE if they shouldn't be queried directly. This keeps decomposition layers out of the catalog while still materializing them for reuse across refreshes:

```sql
-- Private intermediate view - not published to catalog
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW order_product_details
AS
SELECT
  o.order_id,
  o.customer_id,
  o.order_date,
  o.quantity,
  o.revenue,
  p.product_name,
  p.category,
  p.unit_cost
FROM orders o
JOIN products p ON o.product_id = p.product_id;
```

### Pattern 4: Clustering & Partitioning for Join Performance

Use liquid clustering on join keys (or partitioning for time-series data) so intermediate views prune efficiently:

```sql
-- Intermediate view clustered on the join key
CREATE OR REFRESH MATERIALIZED VIEW customer_with_region
CLUSTER BY (customer_id)
AS
SELECT
  c.customer_id,
  c.customer_name,
  c.customer_segment,
  r.region_name,
  r.country
FROM customers c
JOIN regions r ON c.region_id = r.region_id;

-- Time-series intermediate partitioned by date
CREATE OR REFRESH MATERIALIZED VIEW daily_order_metrics
PARTITIONED BY (order_date)
AS
SELECT
  order_date,
  product_id,
  customer_id,
  SUM(quantity) AS daily_quantity,
  SUM(revenue) AS daily_revenue
FROM orders
GROUP BY order_date, product_id, customer_id;
```

## Best Practices

1. **Limit joins to 2-3 per view**: Easier to maintain and more likely to use incremental refresh
2. **Create reusable intermediate views**: Design for reuse across multiple downstream views
3. **Push filters early**: Apply filters in intermediate views to reduce data volume
4. **Use PRIVATE for internal views**: Mark intermediate views as PRIVATE if they shouldn't be queried directly
5. **Document dependencies**: Use comments to explain the view hierarchy
6. **Consider liquid clustering**: Use `CLUSTER BY` on intermediate views for better join performance

## Other Incremental-Refresh Blockers

Too many joins is only one reason a materialized view falls back to full recompute. Before concluding that decomposition alone is the fix, also check for:

- **Non-deterministic functions in the SELECT clause**: `current_date()`, `now()`, `current_timestamp()`, `rand()` in the projection force full recompute regardless of join count. Remove them from the SELECT clause. Two clarifications:
  - **In a filter they are fine.** A rolling date window such as `WHERE order_date >= current_date() - INTERVAL 30 DAYS` is a temporal filter and can still refresh incrementally, so don't restructure a query just because `current_date()` appears somewhere in it.
  - **Don't use them to capture a "last processed date/timestamp".** An MV is a snapshot of its query over the current source data, not an append log, so there is no per-row processing time to record: the column reflects whenever the last refresh happened to run, and its meaning differs between an incremental refresh and a full recompute. Use a streaming table if you need ingestion-time semantics.
- **Unsupported operators**: certain window functions, non-deterministic UDFs, and some outer joins or correlated subqueries.
- **Row tracking disabled on the sources**: most incremental-refresh techniques — joins, `WHERE`/`HAVING`, `UNION ALL`, SELECT expressions — require row tracking on every source table. Enable it with `ALTER TABLE <source> SET TBLPROPERTIES ('delta.enableRowTracking' = 'true')`. Without it, decomposing the view will not make any layer refresh incrementally.
- **Non-serverless compute**: incremental MV refresh requires serverless (Serverless SQL warehouse / SQL Editor, or a serverless Lakeflow pipeline). On Classic / standard compute the MV will not refresh incrementally no matter how the query is structured.
- **Streaming-table sources do not help**: connecting an MV to streaming-table sources does NOT by itself make it refresh incrementally — eligibility depends on the MV's own query (join count, non-deterministic functions, unsupported operators), not the source type.

When diagnosing "why isn't this refreshing incrementally?", enumerate these causes rather than blaming joins alone; decomposition fixes the join-count cause specifically.

## When NOT to Decompose

- The query has 3 or fewer joins
- All joins are on small dimension tables (< 1000 rows)
- The complex view is only used once and refresh performance is acceptable
- Creating intermediate views would significantly increase storage costs
- The real cause of full recompute is a non-deterministic function or non-serverless compute (see above) rather than join count

## KEY RULES

- **Decompose when joins > 3**: Break complex views into layers with 2-3 joins each
- **Create logical groupings**: Group related joins (dimensions, aggregations, domains)
- **Reuse intermediate views**: Design intermediate views for multiple downstream consumers
- **Test incrementally**: Verify each intermediate view works before building the next layer
- **Monitor performance**: Compare refresh times before and after decomposition
```
