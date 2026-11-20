# Performance Tuning

Liquid clustering, cluster key selection, state management, joins, and query optimization for Spark Declarative Pipelines.

---

## Liquid Clustering

Use liquid clustering for data layout instead of `PARTITIONED BY` + Z-ordering. It adapts to the data and needs no manual `OPTIMIZE`.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
CLUSTER BY (event_type, event_date)
AS SELECT *, current_timestamp() AS _ingested_at
FROM STREAM read_files('/Volumes/cat/sch/raw/events/', format => 'json');
```

Python: `@dp.table(cluster_by=["event_type", "event_date"])`.

Use `CLUSTER BY AUTO` (SQL) / `cluster_by_auto=True` (Python) while prototyping or when access patterns are unclear. Pick keys by hand for production once query patterns are stable.

### Cluster key data types

Cluster keys must be numeric, string, date, or timestamp columns. `BOOLEAN`, `ARRAY`, `MAP`, `STRUCT`, and `BINARY` keys fail at the first write with `DELTA_CLUSTERING_COLUMNS_DATATYPE_NOT_SUPPORTED`. Low-cardinality flags don't benefit from clustering, so leave them out.

### Migrating from `PARTITIONED BY` + Z-order

Replace:

```sql
PARTITIONED BY (date DATE)
TBLPROPERTIES ('pipelines.autoOptimize.zOrderCols' = 'user_id,event_type')
```

with:

```sql
CLUSTER BY (date, user_id, event_type)
```

Keep `PARTITIONED BY` only for regulatory physical separation, data lifecycle that relies on dropping partitions, DBR below 13.3, or very large existing tables where the migration costs more than it gains.

---

## Cluster Key Selection by Layer

### Bronze Layer

Cluster by event type + ingestion date:

**SQL:**

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
CLUSTER BY (event_type, ingestion_date)
AS SELECT *, CAST(current_date() AS DATE) AS ingestion_date
FROM STREAM read_files('/Volumes/catalog/schema/raw/', format => 'json');
```

**Python:**

```python
@dp.table(name="bronze_events", cluster_by=["event_type", "ingestion_date"])
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .load("/Volumes/catalog/schema/raw/")
        .withColumn("ingestion_date", F.current_date())
    )
```

**Why:** Bronze is filtered by event type for downstream processing and by date for incremental loads.

### Silver Layer

Cluster by primary key + business dimension:

**SQL:**

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders
CLUSTER BY (customer_id, order_date)
AS SELECT order_id, customer_id, amount, CAST(order_timestamp AS DATE) AS order_date
FROM STREAM bronze_orders;
```

**Python:**

```python
@dp.table(name="silver_orders", cluster_by=["customer_id", "order_date"])
def silver_orders():
    return (
        spark.readStream.table("bronze_orders")
        .withColumn("order_date", F.to_date("order_timestamp"))
        .select("order_id", "customer_id", "amount", "order_date")
    )
```

**Why:** Entity lookups (by ID) and time-range queries (by date) are common access patterns.

### Gold Layer

Cluster by aggregation/filter dimensions:

**SQL:**

```sql
CREATE OR REFRESH MATERIALIZED VIEW gold_sales_summary
CLUSTER BY (product_category, year_month)
AS SELECT product_category, DATE_FORMAT(order_date, 'yyyy-MM') AS year_month,
    SUM(amount) AS total_sales, COUNT(*) AS order_count
FROM silver_orders
GROUP BY product_category, DATE_FORMAT(order_date, 'yyyy-MM');
```

**Python:**

```python
@dp.materialized_view(name="gold_sales_summary", cluster_by=["product_category", "year_month"])
def gold_sales_summary():
    return (
        spark.read.table("silver_orders")
        .withColumn("year_month", F.date_format("order_date", "yyyy-MM"))
        .groupBy("product_category", "year_month")
        .agg(F.sum("amount").alias("total_sales"), F.count("*").alias("order_count"))
    )
```

**Why:** Dashboard filters typically use category, region, or time period.

### Selection Guidelines

| Layer  | Good Keys                  | Rationale                            |
| ------ | -------------------------- | ------------------------------------ |
| Bronze | event_type, ingestion_date | Filter by type; date for incremental |
| Silver | primary_key, business_date | Entity lookups + time ranges         |
| Gold   | aggregation_dimensions     | Dashboard filters                    |

**Best practices:**

- First key: Most selective filter (e.g., customer_id)
- Second key: Next common filter (e.g., date)
- Order matters: Most selective first
- Limit to 4 keys (diminishing returns beyond)
- Use `CLUSTER BY AUTO` (SQL) or `cluster_by_auto=True` (Python) if unsure which columns to cluster on

---

## State Management for Streaming

Streaming aggregations maintain state for each unique key combination. High cardinality = high memory usage.

### Problem: Unbounded State

```python
# High state: 1M users x 10K products x 100M sessions = massive state
.groupBy("user_id", "product_id", "session_id")
```

A window bounds state only together with a watermark (`WATERMARK` in SQL, `withWatermark` in Python); without one, the pipeline runs the aggregation in Complete mode and keeps every group. Group by `window(...)`, not a `DATE(event_time)` bucket, which also runs in Complete mode and keeps every day. With a watermark, each window's row lands once the window closes plus the delay.

### Strategy 1: Reduce Cardinality

Group by coarser dimensions. This shrinks state, but only the watermarked window bounds it:

**SQL:**

```sql
CREATE OR REFRESH STREAMING TABLE user_category_stats AS
SELECT user_id, product_category, window(event_time, '1 day').start AS event_date, COUNT(*) AS events
FROM STREAM(bronze_events) WATERMARK event_time DELAY OF INTERVAL 10 MINUTES
GROUP BY user_id, product_category, window(event_time, '1 day');
-- 100 categories instead of 10K products
```

**Python:**

```python
@dp.table(name="user_category_stats")
def user_category_stats():
    return (
        spark.readStream.table("bronze_events")
        .withWatermark("event_time", "10 minutes")
        .groupBy("user_id", "product_category", F.window("event_time", "1 day"))
        .agg(F.count("*").alias("events"))
        .select("user_id", "product_category", F.col("window.start").alias("event_date"), "events")
    )
```

### Strategy 2: Use Time Windows

Bound state with windowed aggregations:

**SQL:**

```sql
CREATE OR REFRESH STREAMING TABLE user_hourly_stats AS
SELECT user_id, window(event_time, '1 hour') AS time_window, COUNT(*) AS events
FROM STREAM(bronze_events) WATERMARK event_time DELAY OF INTERVAL 10 MINUTES
GROUP BY user_id, window(event_time, '1 hour');
```

**Python:**

```python
@dp.table(name="user_hourly_stats")
def user_hourly_stats():
    return (
        spark.readStream.table("bronze_events")
        .withWatermark("event_time", "10 minutes")
        .groupBy("user_id", F.window("event_time", "1 hour"))
        .agg(F.count("*").alias("events"))
    )
```

### Strategy 3: Materialize Intermediates

Split streaming and batch aggregations:

**Python:**

```python
# Streaming: Daily aggregation (bounded state per user per day)
@dp.table(name="user_daily_stats")
def user_daily_stats():
    return (
        spark.readStream.table("bronze_events")
        .withWatermark("event_time", "10 minutes")
        .groupBy("user_id", F.window("event_time", "1 day"))
        .agg(F.count("*").alias("event_count"))
        .select("user_id", F.col("window.start").alias("event_date"), "event_count")
    )

# Batch: Monthly rollup (no streaming state)
@dp.materialized_view(name="user_monthly_stats")
def user_monthly_stats():
    return (
        spark.read.table("user_daily_stats")
        .groupBy("user_id", F.date_trunc("month", "event_date").alias("month"))
        .agg(F.sum("event_count").alias("total_events"))
    )
```

**SQL:**

```sql
-- Streaming: Daily aggregation
CREATE OR REFRESH STREAMING TABLE user_daily_stats AS
SELECT user_id, window(event_time, '1 day').start AS event_date, COUNT(*) AS event_count
FROM STREAM(bronze_events) WATERMARK event_time DELAY OF INTERVAL 10 MINUTES
GROUP BY user_id, window(event_time, '1 day');

-- Batch: Monthly rollup
CREATE OR REFRESH MATERIALIZED VIEW user_monthly_stats AS
SELECT user_id, DATE_TRUNC('month', event_date) AS month, SUM(event_count) AS total_events
FROM user_daily_stats
GROUP BY user_id, DATE_TRUNC('month', event_date);
```

`event_date` is the start of a UTC day as a `TIMESTAMP`, not a `DATE`; for days in a fixed UTC offset, add a `startTime` offset, which does not adjust for daylight saving ([streaming-table-sql.md](streaming-table-sql.md#late-arriving-data)). `DATE_TRUNC` uses the session time zone, so the monthly rollup above is correct only when the session time zone is UTC, or when the daily window uses the `startTime` offset for the same zone: with `America/Los_Angeles`, the Feb 1 row (Jan 31 16:00 local) falls in January.

---

## Join Optimization

### Stream-to-Static (Efficient)

Join streaming facts with small static dimensions:

```python
@dp.table(name="sales_enriched")
def sales_enriched():
    sales = spark.readStream.table("bronze_sales")
    products = spark.read.table("dim_products")  # Small, will broadcast
    return sales.join(products, "product_id", "left")
```

**Best practice:** Keep static dimensions small (<10K rows) for automatic broadcast.

### Stream-to-Stream (Stateful)

Put a watermark on both sides and bound the join by an event-time interval on the same columns. The interval alone does not evict state.

```python
@dp.table(name="orders_with_payments")
def orders_with_payments():
    orders = spark.readStream.table("bronze_orders").withWatermark("order_time", "10 minutes")
    payments = spark.readStream.table("bronze_payments").withWatermark("payment_time", "10 minutes")
    return orders.join(
        payments,
        (orders.order_id == payments.order_id) &
        (payments.payment_time >= orders.order_time) &
        (payments.payment_time <= orders.order_time + F.expr("INTERVAL 1 HOUR")),
        "inner"
    )
```

**SQL:**

```sql
CREATE OR REFRESH STREAMING TABLE orders_with_payments AS
SELECT o.order_id, o.amount AS order_amount, p.payment_id, p.amount AS payment_amount
FROM STREAM(bronze_orders) WATERMARK order_time DELAY OF INTERVAL 10 MINUTES o
INNER JOIN STREAM(bronze_payments) WATERMARK payment_time DELAY OF INTERVAL 10 MINUTES p
  ON o.order_id = p.order_id
 AND p.payment_time BETWEEN o.order_time AND o.order_time + INTERVAL 1 HOUR;
```

**Why watermarks and time bounds matter:** Without them, state grows indefinitely waiting for matches.

---

## Table Properties

```sql
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',             -- right-size new files on write
  'delta.autoOptimize.autoCompact'   = 'true',             -- compact small files automatically
  'delta.enableChangeDataFeed'       = 'true',             -- only if downstream readers need CDF
  'delta.logRetentionDuration'        = 'interval 7 days', -- high-volume tables only
  'delta.deletedFileRetentionDuration' = 'interval 7 days' -- shortens the time-travel window
)
```

Python: `table_properties={"delta.autoOptimize.optimizeWrite": "true", ...}`.

Short retention windows break time travel beyond the window. Set them only on high-volume tables where storage cost dominates.

---

## Materialized View Refresh

A materialized view in a pipeline has no schedule clause of its own: it refreshes when the pipeline updates, so schedule the pipeline (or a job that runs it). On serverless pipelines, materialized views refresh incrementally when the query and sources allow it, and fall back to a full recompute otherwise. For the supported operators and the row tracking requirement on sources, see [materialized-view-sql.md](materialized-view-sql.md) / [materialized-view-python.md](materialized-view-python.md).

---

## Query Optimization

**Filter early.** Push filters into the streaming read so downstream inputs stay small. A wide-open silver table that gold materialized views filter later processes every row twice.

```sql
CREATE OR REFRESH STREAMING TABLE silver_recent AS
SELECT * FROM STREAM(bronze_events)
WHERE event_date >= CURRENT_DATE() - INTERVAL 7 DAYS;
```

**Skip `SELECT *`** once the schema is stable. Narrow projections enable column pruning and shrink state for stateful operations.

---

## Pre-Aggregation

When the same coarse aggregation is queried often, materialize it:

```sql
CREATE OR REFRESH MATERIALIZED VIEW orders_monthly AS
SELECT customer_id, YEAR(order_date) AS year, MONTH(order_date) AS month,
       SUM(amount) AS total
FROM large_orders_table
GROUP BY customer_id, YEAR(order_date), MONTH(order_date);
```

Querying `orders_monthly` is far cheaper than re-aggregating the underlying table.

---

## Compute Configuration

| Aspect   | Serverless                        | Classic                                                  |
| -------- | --------------------------------- | -------------------------------------------------------- |
| Startup  | Seconds                           | Minutes                                                  |
| Scaling  | Automatic                         | Fixed size or autoscale                                  |
| Cost     | Pay per use                       | Pay for cluster time                                     |
| Best for | Most dev, test, and production    | Steady long-running workloads with special requirements  |

Default to serverless. Use classic only when the pipeline needs R, Spark RDD APIs, JAR/Maven libraries, or another feature serverless doesn't support (see [pipeline-settings.md](pipeline-settings.md#serverless-limitations-force-classic-clusters)).

---

## Monitoring Freshness

Measure a table's lag from its own event-time column:

```sql
SELECT MAX(event_timestamp) AS latest_event,
       TIMESTAMPDIFF(MINUTE, MAX(event_timestamp), CURRENT_TIMESTAMP()) AS lag_minutes
FROM silver_events;
```

Watch for slow streaming tables (high processing lag), large state (memory), expensive joins (long batch durations), and small-file accumulation (enable auto-optimize).

---

## Common Issues

| Issue | Cause / Fix |
| ----- | ----------- |
| Pipeline running slowly | Check clustering keys, state size, and join patterns. |
| High memory usage | Unbounded state: add watermarked time windows, reduce cardinality. |
| Many small files | Enable `delta.autoOptimize.optimizeWrite` and `autoCompact`. |
| Expensive queries on large tables | Cluster on filter columns; build pre-aggregated materialized views. |
| Materialized view refresh slow or not incremental | Enable row tracking on the sources; check the pipeline is serverless. |
| `DELTA_CLUSTERING_COLUMNS_DATATYPE_NOT_SUPPORTED` | A cluster key is BOOLEAN / ARRAY / MAP / STRUCT / BINARY. Use a numeric, string, date, or timestamp column. |
