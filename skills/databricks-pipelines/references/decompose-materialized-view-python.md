# Decomposing Materialized Views with Multiple Joins (Python)

Decompose materialized views with more than 3 joins into smaller, more manageable views using Python in Spark Declarative Pipelines.

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

```python
from pyspark import pipelines as dp

# PROBLEMATIC: 5 joins in a single materialized view
@dp.materialized_view()
def sales_analytics_report():
    orders = spark.read.table("orders")
    customers = spark.read.table("customers")
    products = spark.read.table("products")
    categories = spark.read.table("categories")
    regions = spark.read.table("regions")
    sales_reps = spark.read.table("sales_reps")

    return (
        orders
        .join(customers, orders.customer_id == customers.customer_id)
        .join(products, orders.product_id == products.product_id)
        .join(categories, products.category_id == categories.category_id)
        .join(regions, customers.region_id == regions.region_id)
        .join(sales_reps, orders.sales_rep_id == sales_reps.sales_rep_id)
        .select(
            orders.order_id,
            orders.order_date,
            customers.customer_name,
            customers.customer_segment,
            products.product_name,
            products.category,
            categories.category_description,
            regions.region_name,
            regions.country,
            sales_reps.sales_rep_name,
            orders.quantity,
            orders.revenue,
            (orders.quantity * products.unit_cost).alias("total_cost"),
            (orders.revenue - (orders.quantity * products.unit_cost)).alias("profit")
        )
    )
```

## Example: After Decomposition

### Layer 1: Domain-specific intermediate views (1-2 joins each)

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Intermediate MV 1: Customer with region enrichment (1 join)
@dp.materialized_view()
def customer_with_region():
    customers = spark.read.table("customers")
    regions = spark.read.table("regions")

    return (
        customers
        .join(regions, customers.region_id == regions.region_id)
        .select(
            customers.customer_id,
            customers.customer_name,
            customers.customer_segment,
            regions.region_name,
            regions.country
        )
    )

# Intermediate MV 2: Product with category enrichment (1 join)
@dp.materialized_view()
def product_with_category():
    products = spark.read.table("products")
    categories = spark.read.table("categories")

    return (
        products
        .join(categories, products.category_id == categories.category_id)
        .select(
            products.product_id,
            products.product_name,
            products.category,
            products.unit_cost,
            categories.category_description
        )
    )
```

### Layer 2: Final aggregation view (2-3 joins on intermediate views)

```python
# Final MV: Joins the intermediate views plus the sales_reps dimension (3 joins)
@dp.materialized_view()
def sales_analytics_report():
    orders = spark.read.table("orders")
    cwr = spark.read.table("customer_with_region")
    pwc = spark.read.table("product_with_category")
    sales_reps = spark.read.table("sales_reps")

    return (
        orders
        .join(cwr, orders.customer_id == cwr.customer_id)
        .join(pwc, orders.product_id == pwc.product_id)
        .join(sales_reps, orders.sales_rep_id == sales_reps.sales_rep_id)
        .select(
            orders.order_id,
            orders.order_date,
            cwr.customer_name,
            cwr.customer_segment,
            cwr.region_name,
            cwr.country,
            pwc.product_name,
            pwc.category,
            pwc.category_description,
            sales_reps.sales_rep_name,
            orders.quantity,
            orders.revenue,
            (orders.quantity * pwc.unit_cost).alias("total_cost"),
            (orders.revenue - (orders.quantity * pwc.unit_cost)).alias("profit")
        )
    )
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

```python
# Intermediate: Pre-aggregate orders by customer
@dp.materialized_view()
def customer_order_summary():
    orders = spark.read.table("orders")

    return (
        orders
        .groupBy("customer_id")
        .agg(
            F.count("*").alias("total_orders"),
            F.sum("revenue").alias("total_revenue"),
            F.avg("revenue").alias("avg_order_value")
        )
    )

# Final: Join aggregated data with customer details (1 join)
@dp.materialized_view()
def customer_revenue_report():
    customers = spark.read.table("customers")
    cos = spark.read.table("customer_order_summary")

    return (
        customers
        .join(cos, customers.customer_id == cos.customer_id)
        .select(
            customers.customer_name,
            customers.customer_segment,
            cos.total_orders,
            cos.total_revenue,
            cos.avg_order_value
        )
    )
```

### Pattern 2: Slowly Changing Dimension Isolation

Isolate joins with slowly changing dimensions:

```python
# Intermediate: Geography hierarchy (changes rarely)
@dp.materialized_view()
def geography_hierarchy():
    regions = spark.read.table("regions")
    countries = spark.read.table("countries")

    return (
        regions
        .join(countries, regions.country_id == countries.country_id)
        .select(
            regions.region_id,
            regions.region_name,
            countries.country_name,
            countries.continent
        )
    )

# Final: Use pre-joined geography in reporting views
@dp.materialized_view()
def sales_by_geography():
    orders = spark.read.table("orders")
    gh = spark.read.table("geography_hierarchy")

    return (
        orders
        .join(gh, orders.region_id == gh.region_id)
        .groupBy(gh.region_name, gh.country_name, gh.continent)
        .agg(F.sum("revenue").alias("total_revenue"))
    )
```

### Pattern 3: Private Intermediate Views

Mark intermediate views as private if they shouldn't be queried directly:

```python
# Private intermediate view - not published to catalog
@dp.materialized_view(private=True)
def order_product_details():
    orders = spark.read.table("orders")
    products = spark.read.table("products")

    return (
        orders
        .join(products, orders.product_id == products.product_id)
        .select(
            orders.order_id,
            orders.customer_id,
            orders.order_date,
            orders.quantity,
            orders.revenue,
            products.product_name,
            products.category,
            products.unit_cost
        )
    )
```

### Pattern 4: Clustering & Partitioning for Join Performance

Use liquid clustering on join keys (or partitioning for time-series data) so intermediate views prune efficiently:

```python
# Intermediate view clustered on the join key
@dp.materialized_view(
    cluster_by=["customer_id"]
)
def customer_with_region():
    customers = spark.read.table("customers")
    regions = spark.read.table("regions")

    return (
        customers
        .join(regions, customers.region_id == regions.region_id)
        .select(
            customers.customer_id,
            customers.customer_name,
            customers.customer_segment,
            regions.region_name,
            regions.country
        )
    )

# Time-series intermediate partitioned by date
@dp.materialized_view(
    partition_cols=["order_date"]
)
def daily_order_metrics():
    orders = spark.read.table("orders")

    return (
        orders
        .groupBy("order_date", "product_id", "customer_id")
        .agg(
            F.sum("quantity").alias("daily_quantity"),
            F.sum("revenue").alias("daily_revenue")
        )
    )
```

## Best Practices

1. **Limit joins to 2-3 per view**: Easier to maintain and more likely to use incremental refresh
2. **Create reusable intermediate views**: Design for reuse across multiple downstream views
3. **Push filters early**: Apply filters in intermediate views to reduce data volume
4. **Use `private=True` for internal views**: Mark intermediate views as private if not needed externally
5. **Document dependencies**: Use docstrings to explain the view hierarchy
6. **Consider liquid clustering**: Use `cluster_by` on intermediate views for better join performance
7. **Use meaningful names**: Name intermediate views to reflect their purpose (e.g., `customer_with_region`)

## Other Incremental-Refresh Blockers

Too many joins is only one reason a materialized view falls back to full recompute. Before concluding that decomposition alone is the fix, also check for:

- **Non-deterministic functions in the projection**: `F.current_date()`, `F.now()`, `F.current_timestamp()`, `F.rand()` in a `select`/`withColumn` force full recompute regardless of join count. Remove them from the projection. Two clarifications:
  - **In a filter they are fine.** A rolling date window such as `.filter(F.col("order_date") >= F.current_date() - F.expr("INTERVAL 30 DAYS"))` is a temporal filter and can still refresh incrementally, so don't restructure a query just because `F.current_date()` appears somewhere in it.
  - **Don't use them to capture a "last processed date/timestamp".** An MV is a snapshot of its query over the current source data, not an append log, so there is no per-row processing time to record: the column reflects whenever the last refresh happened to run, and its meaning differs between an incremental refresh and a full recompute. Use a streaming table if you need ingestion-time semantics.
- **Unsupported operators**: certain window functions, non-deterministic UDFs, and some outer joins or correlated subqueries.
- **Row tracking disabled on the sources**: most incremental-refresh techniques — joins, filters, `unionAll`, projection expressions — require row tracking on every source table. Enable it with `ALTER TABLE <source> SET TBLPROPERTIES ('delta.enableRowTracking' = 'true')`. Without it, decomposing the view will not make any layer refresh incrementally.
- **Non-serverless compute**: incremental MV refresh requires serverless (a serverless Lakeflow pipeline, or Serverless SQL warehouse / SQL Editor for SQL MVs). On Classic / standard compute the MV will not refresh incrementally no matter how the query is structured.
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
- **Use `@dp.materialized_view()`**: Preferred decorator for materialized views
- **Do not manually persist intermediates**: Define each layer as a materialized view and let SDP manage the write. Do not call `.write`/`.save()` to persist a decomposition layer yourself
- **Test incrementally**: Verify each intermediate view works before building the next layer
- **Monitor performance**: Compare refresh times before and after decomposition
