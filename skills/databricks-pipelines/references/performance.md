# Performance Tuning

Performance patterns for Spark Declarative Pipelines: Liquid Clustering, state management for streaming, join strategy, query optimization, and pre-aggregation. Examples are shown in both SQL and Python.

---

## Liquid Clustering

**Recommended** for data layout. Replaces `PARTITION BY` + `ZORDER`. Adaptive, multi-dimensional, self-optimizing — no more manual `OPTIMIZE`.

### Basic syntax

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
CLUSTER BY (event_type, event_date)
AS
SELECT *, current_timestamp() AS _ingested_at
FROM STREAM read_files('/Volumes/cat/sch/raw/events/', format => 'json');
```

```python
@dp.table(cluster_by=["event_type", "event_date"])
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/Volumes/cat/sch/raw/events/")
```

### Automatic key selection

```sql
CLUSTER BY (AUTO)
```

```python
cluster_by=["AUTO"]
```

Use `AUTO` while learning the workload, prototyping, or when access patterns are unclear. Pick keys manually for production once query patterns are stable.

### Cluster key data types

**Cluster keys must be numeric, string, date, or timestamp.** `BOOLEAN`, `ARRAY`, `MAP`, `STRUCT`, `BINARY` are rejected at runtime with `DELTA_CLUSTERING_COLUMNS_DATATYPE_NOT_SUPPORTED`. Low-cardinality flags also don't benefit from clustering — leave them out.

### Cluster key selection by layer

| Layer | Good keys | Rationale |
|-------|-----------|-----------|
| **Bronze** | `event_type`, `ingestion_date` | Filter by type for processing, by date for incremental loads. |
| **Silver** | `primary_key`, `business_date` | Entity lookups + time-range queries. |
| **Gold** | aggregation dimensions | Dashboard filters. |

**Rules of thumb**:
- First key: most-selective filter (e.g. `customer_id`).
- Second key: next-most-common filter (e.g. date).
- Order matters. Most-selective first.
- Limit to **4 keys** — diminishing returns beyond that.
- Use `AUTO` if unsure.

### Bronze example

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
CLUSTER BY (event_type, ingestion_date)
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true')
AS
SELECT *,
       current_timestamp() AS _ingested_at,
       CAST(current_date() AS DATE) AS ingestion_date
FROM STREAM read_files('/Volumes/cat/sch/raw/events/', format => 'json');
```

```python
@dp.table(
    name="bronze_events",
    cluster_by=["event_type", "ingestion_date"],
    table_properties={"delta.autoOptimize.optimizeWrite": "true"},
)
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
             .option("cloudFiles.format", "json")
             .load("/Volumes/cat/sch/raw/events/")
             .withColumn("_ingested_at", F.current_timestamp())
             .withColumn("ingestion_date", F.current_date())
    )
```

### Silver example (clustering for joins + time filters)

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders
CLUSTER BY (customer_id, order_date)
AS
SELECT order_id, customer_id, product_id,
       CAST(amount AS DECIMAL(10,2)) AS amount,     -- DECIMAL for monetary
       CAST(order_timestamp AS DATE) AS order_date,
       order_timestamp
FROM STREAM bronze_orders;
```

```python
@dp.table(name="silver_orders", cluster_by=["customer_id", "order_date"])
def silver_orders():
    return (
        spark.readStream.table("bronze_orders")
             .withColumn("order_date", F.to_date("order_timestamp"))
             .select("order_id", "customer_id", "product_id", "amount", "order_date")
    )
```

### Gold example (clustering on aggregation dimensions)

```sql
CREATE OR REFRESH MATERIALIZED VIEW gold_sales_summary
CLUSTER BY (product_category, year_month)
AS
SELECT product_category,
       DATE_FORMAT(order_date, 'yyyy-MM') AS year_month,
       SUM(amount) AS total_sales,
       COUNT(*) AS transaction_count,
       AVG(amount) AS avg_order_value
FROM silver_orders
GROUP BY product_category, DATE_FORMAT(order_date, 'yyyy-MM');
```

```python
@dp.materialized_view(name="gold_sales_summary", cluster_by=["product_category", "year_month"])
def gold_sales_summary():
    return (
        spark.read.table("silver_orders")
             .withColumn("year_month", F.date_format("order_date", "yyyy-MM"))
             .groupBy("product_category", "year_month")
             .agg(F.sum("amount").alias("total_sales"),
                  F.count("*").alias("transaction_count"),
                  F.avg("amount").alias("avg_order_value"))
    )
```

### Migrating from `PARTITION BY` + `ZORDER`

Before (legacy):

```sql
CREATE OR REFRESH STREAMING TABLE events
PARTITIONED BY (date DATE)
TBLPROPERTIES ('pipelines.autoOptimize.zOrderCols' = 'user_id,event_type')
AS SELECT ...;
```

After:

```sql
CREATE OR REFRESH STREAMING TABLE events
CLUSTER BY (date, user_id, event_type)
AS SELECT ...;
```

Typical wins: 20–50% query improvement, no small-file problem, automatic optimization, no manual `OPTIMIZE` job.

**Keep `PARTITION BY` only for**: regulatory requirements (physical separation), data-lifecycle (need to `DROP` partitions for retention), DBR < 13.3 compatibility, or existing huge tables where migration cost > benefit.

---

## Table Properties

### Auto-optimize

```sql
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact'   = 'true'
)
```

```python
table_properties={
    "delta.autoOptimize.optimizeWrite": "true",
    "delta.autoOptimize.autoCompact": "true",
}
```

### Change Data Feed

```sql
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
```

Enable when downstream systems need efficient change tracking.

### Retention (high-volume tables)

```sql
TBLPROPERTIES (
  'delta.logRetentionDuration'        = '7 days',
  'delta.deletedFileRetentionDuration' = '7 days'
)
```

Use for high-volume tables to reduce storage cost. Be careful: short retention windows break time-travel queries beyond the window.

---

## Materialized View Refresh

```sql
-- Near-real-time
CREATE OR REFRESH MATERIALIZED VIEW gold_live_metrics
REFRESH EVERY 5 MINUTES
AS SELECT metric_name, AVG(metric_value) AS avg_value, MAX(last_updated) AS freshness
   FROM silver_metrics GROUP BY metric_name;

-- Daily
CREATE OR REFRESH MATERIALIZED VIEW gold_daily_summary
REFRESH EVERY 1 DAY
AS SELECT report_date, SUM(amount) AS total_amount
   FROM silver_sales GROUP BY report_date;
```

### Incremental refresh

MVs use incremental refresh automatically when possible. Requirements:
- Source has Delta row tracking enabled.
- No row-level filters.
- Aggregation/expression pattern is supported.
- **Serverless pipeline.** Incremental refresh for aggregations is a serverless feature.

---

## State Management for Streaming

Higher cardinality → more state. Watch the combinations in `GROUP BY`.

```sql
-- High state: every unique combination creates state
SELECT user_id, product_id, session_id, COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, product_id, session_id;  -- 1M × 10K × 100M — massive
```

### Strategy 1: reduce cardinality

```sql
-- 100 categories instead of 10K products
SELECT user_id, product_category, DATE(event_time) AS event_date, COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, product_category, DATE(event_time);
```

```python
@dp.table(name="user_category_stats")
def user_category_stats():
    return (
        spark.readStream.table("bronze_events")
             .groupBy("user_id", "product_category",
                      F.to_date("event_time").alias("event_date"))
             .agg(F.count("*").alias("events"))
    )
```

### Strategy 2: use time windows

```sql
SELECT user_id, window(event_time, '1 hour') AS time_window, COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, window(event_time, '1 hour');
```

```python
@dp.table(name="user_hourly_stats")
def user_hourly_stats():
    return (
        spark.readStream.table("bronze_events")
             .groupBy("user_id", F.window("event_time", "1 hour"))
             .agg(F.count("*").alias("events"))
    )
```

### Strategy 3: materialize intermediates (move state to batch)

```sql
-- Streaming aggregation (maintains state)
CREATE OR REFRESH STREAMING TABLE user_daily_stats AS
SELECT user_id, DATE(event_time) AS event_date, COUNT(*) AS event_count
FROM STREAM bronze_events
GROUP BY user_id, DATE(event_time);

-- Batch aggregation on top (no streaming state)
CREATE OR REFRESH MATERIALIZED VIEW user_monthly_stats AS
SELECT user_id, DATE_TRUNC('month', event_date) AS month, SUM(event_count) AS total_events
FROM user_daily_stats
GROUP BY user_id, DATE_TRUNC('month', event_date);
```

---

## Join Optimization

### Stream-to-static (efficient)

```sql
-- Small static dimension joined to large streaming fact
CREATE OR REFRESH STREAMING TABLE sales_enriched AS
SELECT s.sale_id, s.product_id, s.amount, p.product_name, p.category
FROM STREAM bronze_sales s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

```python
@dp.table(name="sales_enriched")
def sales_enriched():
    sales    = spark.readStream.table("bronze_sales")
    products = spark.read.table("dim_products")        # static, broadcastable
    return sales.join(products, "product_id", "left") \
                .select("sale_id", "product_id", "amount", "product_name", "category")
```

**Rule**: keep static dimensions small (< 10K rows) so they broadcast.

### Stream-to-stream (stateful, time-bounded)

```sql
-- Time bounds limit state retention
CREATE OR REFRESH STREAMING TABLE orders_with_payments AS
SELECT o.order_id, o.amount AS order_amount, p.payment_id, p.amount AS payment_amount
FROM STREAM bronze_orders o
INNER JOIN STREAM bronze_payments p
  ON o.order_id = p.order_id
 AND p.payment_time BETWEEN o.order_time AND o.order_time + INTERVAL 1 HOUR;
```

```python
@dp.table(name="orders_with_payments")
def orders_with_payments():
    orders   = spark.readStream.table("bronze_orders")
    payments = spark.readStream.table("bronze_payments")
    return orders.join(
        payments,
        (orders.order_id == payments.order_id) &
        (payments.payment_time >= orders.order_time) &
        (payments.payment_time <= orders.order_time + F.expr("INTERVAL 1 HOUR")),
        "inner",
    )
```

Without time bounds, stream-to-stream state grows unbounded.

---

## Query Optimization

### Filter early

```sql
-- Filter at source
CREATE OR REFRESH STREAMING TABLE silver_recent AS
SELECT *
FROM STREAM bronze_events
WHERE event_date >= CURRENT_DATE() - INTERVAL 7 DAYS;
```

```python
@dp.table(name="silver_recent")
def silver_recent():
    return (spark.readStream.table("bronze_events")
                 .filter(F.col("event_date") >= F.current_date() - 7))
```

Pushing filters into the streaming read keeps downstream MV inputs small. The anti-pattern is wide-open silver tables filtered later in gold MVs — every row is processed twice.

### Select specific columns

Skip `SELECT *` once schema is stable. Narrowed projections enable column pruning in Delta and shrink wire/state size for stateful operations.

---

## Pre-Aggregation

When the same coarse aggregation is queried frequently, materialize it. Querying the MV is far cheaper than re-aggregating the underlying table.

```sql
CREATE OR REFRESH MATERIALIZED VIEW orders_monthly AS
SELECT customer_id, YEAR(order_date) AS year, MONTH(order_date) AS month,
       SUM(amount) AS total
FROM large_orders_table
GROUP BY customer_id, YEAR(order_date), MONTH(order_date);

-- Query the MV directly
SELECT * FROM orders_monthly WHERE year = 2024;
```

```python
@dp.materialized_view(name="orders_monthly")
def orders_monthly():
    return (spark.read.table("large_orders_table")
                 .groupBy("customer_id",
                          F.year("order_date").alias("year"),
                          F.month("order_date").alias("month"))
                 .agg(F.sum("amount").alias("total")))
```

---

## Compute Configuration

| Aspect | Serverless | Classic |
|--------|-----------|---------|
| Startup | Seconds | Minutes |
| Scaling | Automatic, instant | Manual / autoscale |
| Cost | Pay-per-use | Pay for cluster time |
| Best for | Variable / dev / test / most prod | Steady, very long-running workloads with special requirements |

**Default to serverless.** Switch to classic only when R, Spark RDD APIs, JAR/Maven libraries, or other serverless-incompatible features are required — see [pipeline-configuration.md](pipeline-configuration.md#serverless-limitations-force-classic-clusters).

---

## Monitoring Freshness

```sql
SELECT table_name,
       MAX(event_timestamp) AS latest_event,
       CURRENT_TIMESTAMP()  AS now,
       TIMESTAMPDIFF(MINUTE, MAX(event_timestamp), CURRENT_TIMESTAMP()) AS lag_minutes
FROM pipeline_monitoring.table_metrics
GROUP BY table_name;
```

Watch for:

1. Slow streaming tables (high processing lag).
2. Large state operations (high memory).
3. Expensive joins (long batch durations).
4. Small-file accumulation (raise auto-optimize, check write patterns).

---

## Complete Example (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(
    name="bronze_orders",
    cluster_by=["order_date"],
    table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact":   "true",
    },
)
def bronze_orders():
    return (
        spark.readStream.format("cloudFiles")
             .option("cloudFiles.format", "json")
             .load("/Volumes/cat/sch/raw/orders/")
             .withColumn("_ingested_at", F.current_timestamp())
             .withColumn("order_date",   F.to_date("order_timestamp"))
    )

@dp.table(name="silver_orders", cluster_by=["customer_id", "order_date"])
@dp.expect_or_drop("valid_amount", "amount > 0")
def silver_orders():
    return (
        spark.readStream.table("bronze_orders")
             .filter(F.col("order_date") >= F.current_date() - 90)      # filter early
             .withColumn("amount", F.col("amount").cast("decimal(10,2)"))
             .select("order_id", "customer_id", "amount", "order_date")
    )

@dp.materialized_view(name="gold_daily_revenue", cluster_by=["order_date"])
def gold_daily_revenue():
    return (
        spark.read.table("silver_orders")
             .groupBy("order_date")
             .agg(F.sum("amount").alias("total_revenue"),
                  F.count("order_id").alias("order_count"),
                  F.countDistinct("customer_id").alias("unique_customers"))
    )
```

---

## Common Issues

| Issue | Cause / Fix |
|-------|-------------|
| Pipeline running slowly | Check clustering keys, state size, join patterns. |
| High memory usage | Unbounded state — add time windows, reduce cardinality. |
| Many small files | Enable auto-optimize table properties. |
| Expensive queries on large tables | Add clustering on filter columns, build pre-aggregated MVs. |
| MV refresh slow | Enable row tracking on source, verify the refresh is actually incremental. |
| `DELTA_CLUSTERING_COLUMNS_DATATYPE_NOT_SUPPORTED` | A cluster key has an unsupported type (BOOLEAN / complex). Replace with a numeric / string / date / timestamp column. |
