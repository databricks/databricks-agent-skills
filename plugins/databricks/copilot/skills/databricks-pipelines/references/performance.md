# Performance Tuning

Liquid Clustering, state management for streaming, join strategy, query optimization, pre-aggregation. SQL is shown as canonical; Python equivalents use the obvious `@dp.table` + DataFrame translation (`cluster_by=[...]`, `table_properties={...}`).

---

## Liquid Clustering

**Recommended** for data layout. Replaces `PARTITION BY` + `ZORDER`. Adaptive, multi-dimensional, self-optimizing — no manual `OPTIMIZE` needed.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
CLUSTER BY (event_type, event_date)
AS SELECT *, current_timestamp() AS _ingested_at
FROM STREAM read_files('/Volumes/cat/sch/raw/events/', format => 'json');
```

Python: `@dp.table(cluster_by=["event_type", "event_date"])`.

Use `CLUSTER BY (AUTO)` / `cluster_by=["AUTO"]` while learning the workload, prototyping, or when access patterns are unclear. Pick keys manually for production once query patterns are stable.

### Cluster key data types

**Numeric, string, date, or timestamp only.** `BOOLEAN`, `ARRAY`, `MAP`, `STRUCT`, `BINARY` fail at first write with `DELTA_CLUSTERING_COLUMNS_DATATYPE_NOT_SUPPORTED` (no data-skipping stats). Low-cardinality flags also don't benefit from clustering — leave them out.

### Cluster key selection by layer

| Layer | Good keys | Rationale |
|-------|-----------|-----------|
| **Bronze** | `event_type`, `ingestion_date` | Filter by type for processing, by date for incremental loads. |
| **Silver** | `primary_key`, `business_date` | Entity lookups + time-range queries. |
| **Gold** | aggregation dimensions | Dashboard filters. |

Rules of thumb: most-selective key first, second-most-common filter second; order matters; cap at 4 keys (diminishing returns beyond). Use `AUTO` if unsure.

### Migrating from `PARTITION BY` + `ZORDER`

Replace:

```sql
PARTITIONED BY (date DATE)
TBLPROPERTIES ('pipelines.autoOptimize.zOrderCols' = 'user_id,event_type')
```

with:

```sql
CLUSTER BY (date, user_id, event_type)
```

Typical wins: 20–50% query improvement, no small-file problem, automatic optimization. **Keep `PARTITION BY` only for**: regulatory physical separation, data lifecycle requiring `DROP PARTITION`, DBR < 13.3 compatibility, or huge existing tables where migration cost > benefit.

---

## Table Properties

```sql
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',     -- right-size new files on write
  'delta.autoOptimize.autoCompact'   = 'true',     -- compact small files automatically
  'delta.enableChangeDataFeed'       = 'true',     -- if downstream needs CDF
  'delta.logRetentionDuration'        = '7 days',  -- high-volume tables only
  'delta.deletedFileRetentionDuration' = '7 days'  -- shortens time-travel window
)
```

Python: `table_properties={"delta.autoOptimize.optimizeWrite": "true", ...}`.

Short retention windows break time-travel queries beyond the window — only set on high-volume tables where storage cost dominates.

---

## Materialized View Refresh

```sql
CREATE OR REFRESH MATERIALIZED VIEW gold_live_metrics
REFRESH EVERY 5 MINUTES                  -- or REFRESH EVERY 1 DAY for batch reports
AS SELECT metric_name, AVG(metric_value) AS avg_value, MAX(last_updated) AS freshness
   FROM silver_metrics GROUP BY metric_name;
```

### Incremental refresh

MVs use incremental refresh automatically when possible. Requirements:

- **Serverless pipeline** (incremental refresh for aggregations is serverless-only).
- Source has Delta row tracking enabled (`delta.enableRowTracking = true`).
- No row-level filters on the source.
- Aggregation/expression pattern is supported.

Falls back to full recompute if any requirement isn't met.

---

## State Management for Streaming

Higher cardinality → more state. Watch the combinations in `GROUP BY`.

```sql
-- High state: every unique combination creates state
SELECT user_id, product_id, session_id, COUNT(*)
FROM STREAM(bronze_events)
GROUP BY user_id, product_id, session_id;   -- 1M × 10K × 100M — massive
```

Three strategies to bound state:

**1. Reduce cardinality** — group by coarser keys.

```sql
-- 100 categories instead of 10K products
GROUP BY user_id, product_category, DATE(event_time)
```

**2. Use time windows** — explicit retention boundary.

```sql
GROUP BY user_id, window(event_time, '1 hour')
```

**3. Materialize daily then aggregate batch monthly** — move state from streaming to batch.

```sql
CREATE OR REFRESH STREAMING TABLE user_daily_stats AS
SELECT user_id, DATE(event_time) AS event_date, COUNT(*) AS event_count
FROM STREAM(bronze_events)
GROUP BY user_id, DATE(event_time);

CREATE OR REFRESH MATERIALIZED VIEW user_monthly_stats AS
SELECT user_id, DATE_TRUNC('month', event_date) AS month, SUM(event_count) AS total_events
FROM user_daily_stats
GROUP BY user_id, DATE_TRUNC('month', event_date);
```

---

## Join Optimization

### Stream-to-static (efficient)

Small static dimensions broadcast naturally — no special config needed.

```sql
CREATE OR REFRESH STREAMING TABLE sales_enriched AS
SELECT s.sale_id, s.product_id, s.amount, p.product_name, p.category
FROM STREAM(bronze_sales) s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

Python: `sales = spark.readStream.table("bronze_sales")` / `products = spark.read.table("dim_products")` (static, broadcastable) / `sales.join(products, "product_id", "left")`.

**Rule**: keep static dimensions small (< 10K rows) so they broadcast.

### Stream-to-stream (stateful, time-bounded)

Always bound by event-time interval. Without bounds, state grows unbounded.

```sql
CREATE OR REFRESH STREAMING TABLE orders_with_payments AS
SELECT o.order_id, o.amount AS order_amount, p.payment_id, p.amount AS payment_amount
FROM STREAM(bronze_orders) o
INNER JOIN STREAM(bronze_payments) p
  ON o.order_id = p.order_id
 AND p.payment_time BETWEEN o.order_time AND o.order_time + INTERVAL 1 HOUR;
```

Python: same shape, time-bound predicate as `(p.payment_time >= o.order_time) & (p.payment_time <= o.order_time + F.expr("INTERVAL 1 HOUR"))`.

---

## Query Optimization

**Filter early** — push filters into the streaming read so downstream MV inputs stay small. The anti-pattern is wide-open silver tables filtered later in gold MVs — every row is processed twice.

```sql
CREATE OR REFRESH STREAMING TABLE silver_recent AS
SELECT * FROM STREAM(bronze_events)
WHERE event_date >= CURRENT_DATE() - INTERVAL 7 DAYS;
```

**Skip `SELECT *`** once schema is stable. Narrow projections enable Delta column pruning and shrink wire/state size for stateful operations.

---

## Pre-Aggregation

When the same coarse aggregation is queried frequently, materialize it.

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

| Aspect | Serverless | Classic |
|--------|-----------|---------|
| Startup | Seconds | Minutes |
| Scaling | Automatic, instant | Manual / autoscale |
| Cost | Pay-per-use | Pay for cluster time |
| Best for | Variable / dev / test / most prod | Steady long-running workloads with special requirements |

**Default to serverless.** Switch to classic only when R, Spark RDD APIs, JAR/Maven libraries, or other serverless-incompatible features are required — see [pipeline-configuration.md](pipeline-configuration.md#serverless-limitations-force-classic-clusters).

---

## Monitoring Freshness

```sql
SELECT table_name,
       MAX(event_timestamp) AS latest_event,
       TIMESTAMPDIFF(MINUTE, MAX(event_timestamp), CURRENT_TIMESTAMP()) AS lag_minutes
FROM pipeline_monitoring.table_metrics
GROUP BY table_name;
```

Watch for slow streaming tables (high processing lag), large state ops (memory), expensive joins (long batch durations), small-file accumulation (raise auto-optimize).

---

## Common Issues

| Issue | Cause / Fix |
|-------|-------------|
| Pipeline running slowly | Check clustering keys, state size, join patterns. |
| High memory usage | Unbounded state — add time windows, reduce cardinality. |
| Many small files | Enable `delta.autoOptimize.optimizeWrite` + `autoCompact`. |
| Expensive queries on large tables | Add clustering on filter columns, build pre-aggregated MVs. |
| MV refresh slow / not incremental | Enable row tracking on source; verify serverless. |
| `DELTA_CLUSTERING_COLUMNS_DATATYPE_NOT_SUPPORTED` | A cluster key is BOOLEAN / ARRAY / MAP / STRUCT / BINARY. Replace with numeric / string / date / timestamp. |
