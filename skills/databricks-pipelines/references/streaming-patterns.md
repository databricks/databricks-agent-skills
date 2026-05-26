# Streaming Patterns

Patterns for streaming pipelines: deduplication, windowed aggregations, late-arriving data, rescue-data quarantine, monitoring lag, and anomaly detection. Examples are shown in both SQL and Python.

For perf-framed treatment of stream-to-stream joins, see [performance.md](performance.md#join-optimization). For Auto Loader API and options, see [auto-loader.md](auto-loader.md). For Kafka ingestion, see [kafka.md](kafka.md).

---

## Deduplication

Apply at the bronze → silver transition. Bronze accepts duplicates, silver is clean.

### By key (keep first)

```sql
CREATE OR REFRESH STREAMING TABLE silver_events_dedup AS
SELECT event_id, user_id, event_type, event_timestamp, _ingested_at
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_timestamp) AS rn
  FROM STREAM bronze_events
)
WHERE rn = 1;
```

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

@dp.table(name="silver_events_dedup", cluster_by=["event_date"])
def silver_events_dedup():
    w = Window.partitionBy("event_id").orderBy("event_timestamp")
    return (
        spark.readStream.table("bronze_events")
             .withColumn("rn", F.row_number().over(w))
             .filter(F.col("rn") == 1)
             .drop("rn")
    )
```

### Within a time window (tolerates late arrivals)

```sql
CREATE OR REFRESH STREAMING TABLE silver_events_dedup AS
SELECT event_id, user_id, event_type, event_timestamp,
       MIN(_ingested_at) AS first_seen_at
FROM STREAM bronze_events
GROUP BY event_id, user_id, event_type, event_timestamp,
         window(event_timestamp, '1 hour');
```

```python
@dp.table(name="silver_events_dedup")
def silver_events_dedup():
    return (
        spark.readStream.table("bronze_events")
             .groupBy("event_id", "user_id", "event_type", "event_timestamp",
                      F.window("event_timestamp", "1 hour"))
             .agg(F.min("_ingested_at").alias("first_seen_at"))
    )
```

### Composite key

```sql
CREATE OR REFRESH STREAMING TABLE silver_transactions_dedup AS
SELECT transaction_id, customer_id, amount, transaction_timestamp,
       MIN(_ingested_at) AS _ingested_at
FROM STREAM bronze_transactions
GROUP BY transaction_id, customer_id, amount, transaction_timestamp;
```

```python
@dp.table(name="silver_transactions_dedup")
def silver_transactions_dedup():
    return (
        spark.readStream.table("bronze_transactions")
             .groupBy("transaction_id", "customer_id", "amount", "transaction_timestamp")
             .agg(F.min("_ingested_at").alias("_ingested_at"))
    )
```

**Alternative for simple cases**: `SELECT DISTINCT ...` (SQL) or `.dropDuplicates(["event_id"])` (Python). These are fine for low-cardinality dedup but maintain state per unique row.

### When to use Auto CDC instead

For dedup with sequenced updates (most-recent-wins, deletes, late corrections), use Auto CDC with SCD Type 1 — see [auto-cdc.md](auto-cdc.md). Manual `ROW_NUMBER`/`GROUP BY` dedup is for append-only streams without semantic updates.

---

## Windowed Aggregations

### Tumbling windows (non-overlapping, fixed size)

```sql
CREATE OR REFRESH STREAMING TABLE silver_sensor_5min AS
SELECT sensor_id,
       window(event_timestamp, '5 minutes') AS time_window,
       AVG(temperature) AS avg_temperature,
       MIN(temperature) AS min_temperature,
       MAX(temperature) AS max_temperature,
       COUNT(*) AS event_count
FROM STREAM bronze_sensor_events
GROUP BY sensor_id, window(event_timestamp, '5 minutes');
```

```python
@dp.table(name="silver_sensor_5min", cluster_by=["sensor_id"])
def silver_sensor_5min():
    return (
        spark.readStream.table("bronze_sensor_events")
             .groupBy("sensor_id", F.window("event_timestamp", "5 minutes"))
             .agg(F.avg("temperature").alias("avg_temperature"),
                  F.min("temperature").alias("min_temperature"),
                  F.max("temperature").alias("max_temperature"),
                  F.count("*").alias("event_count"))
    )
```

### Multiple window sizes (separate tables per granularity)

```sql
CREATE OR REFRESH STREAMING TABLE gold_sensor_1min AS
SELECT sensor_id,
       window(event_timestamp, '1 minute').start AS window_start,
       window(event_timestamp, '1 minute').end   AS window_end,
       AVG(value) AS avg_value,
       COUNT(*)   AS event_count
FROM STREAM silver_sensor_data
GROUP BY sensor_id, window(event_timestamp, '1 minute');

CREATE OR REFRESH STREAMING TABLE gold_sensor_1hour AS
SELECT sensor_id,
       window(event_timestamp, '1 hour').start AS window_start,
       AVG(value)    AS avg_value,
       STDDEV(value) AS stddev_value
FROM STREAM silver_sensor_data
GROUP BY sensor_id, window(event_timestamp, '1 hour');
```

```python
@dp.table(name="gold_sensor_1min")
def gold_sensor_1min():
    return (
        spark.readStream.table("silver_sensor_data")
             .groupBy("sensor_id", F.window("event_timestamp", "1 minute"))
             .agg(F.avg("value").alias("avg_value"),
                  F.count("*").alias("event_count"))
             .select("sensor_id",
                     F.col("window.start").alias("window_start"),
                     F.col("window.end").alias("window_end"),
                     "avg_value", "event_count")
    )

@dp.table(name="gold_sensor_1hour")
def gold_sensor_1hour():
    return (
        spark.readStream.table("silver_sensor_data")
             .groupBy("sensor_id", F.window("event_timestamp", "1 hour"))
             .agg(F.avg("value").alias("avg_value"),
                  F.stddev("value").alias("stddev_value"))
    )
```

### Session windows (inactivity-bounded)

Group events into sessions terminated by an inactivity gap:

```sql
CREATE OR REFRESH STREAMING TABLE silver_user_sessions AS
SELECT user_id,
       session_window(event_timestamp, '30 minutes') AS session,
       MIN(event_timestamp)         AS session_start,
       MAX(event_timestamp)         AS session_end,
       COUNT(*)                     AS event_count,
       COLLECT_LIST(event_type)     AS event_sequence
FROM STREAM bronze_user_events
GROUP BY user_id, session_window(event_timestamp, '30 minutes');
```

```python
@dp.table(name="silver_user_sessions")
def silver_user_sessions():
    return (
        spark.readStream.table("bronze_user_events")
             .groupBy("user_id", F.session_window("event_timestamp", "30 minutes"))
             .agg(F.min("event_timestamp").alias("session_start"),
                  F.max("event_timestamp").alias("session_end"),
                  F.count("*").alias("event_count"),
                  F.collect_list("event_type").alias("event_sequence"))
    )
```

### Window-size guidance

| Window | Use case |
|--------|----------|
| 1–5 minutes | Real-time monitoring, alerting |
| 15–60 minutes | Operational dashboards |
| 1–24 hours | Analytical reports |

Larger windows = less state pressure but stale results. Pick the smallest window that meets the freshness SLO.

---

## Late-Arriving Data

### Use event time, not processing time, for business logic

```sql
CREATE OR REFRESH STREAMING TABLE gold_daily_orders AS
SELECT CAST(order_timestamp AS DATE) AS order_date,   -- event time
       COUNT(*) AS order_count,
       SUM(amount) AS total_amount
FROM STREAM silver_orders
GROUP BY CAST(order_timestamp AS DATE);
```

```python
@dp.table(name="gold_daily_orders")
def gold_daily_orders():
    return (
        spark.readStream.table("silver_orders")
             .groupBy(F.to_date("order_timestamp").alias("order_date"))   # event time
             .agg(F.count("*").alias("order_count"),
                  F.sum("amount").alias("total_amount"))
    )
```

Keep `_ingested_at` (processing time) in the schema as a debugging field — never the aggregation key.

---

## Rescue-Data Quarantine

Pattern: route malformed records to a quarantine table so the clean stream stays clean, but no data is silently dropped. Uses Auto Loader's rescued-data column (`_rescued_data`, default name; configurable via `rescuedDataColumn`).

```sql
-- Bronze: ingest everything, flag rows where Auto Loader rescued bad fields
CREATE OR REFRESH STREAMING TABLE bronze_events AS
SELECT *,
       current_timestamp() AS _ingested_at,
       _rescued_data IS NOT NULL AS _has_errors
FROM STREAM read_files('/Volumes/cat/sch/raw/events/', format => 'json');

-- Quarantine: only the rescued/malformed rows
CREATE OR REFRESH STREAMING TABLE bronze_quarantine AS
SELECT * FROM STREAM bronze_events WHERE _rescued_data IS NOT NULL;

-- Silver: only the clean rows
CREATE OR REFRESH STREAMING TABLE silver_clean AS
SELECT * FROM STREAM bronze_events WHERE _rescued_data IS NULL;
```

```python
@dp.table(name="bronze_events", cluster_by=["ingestion_date"])
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
             .option("cloudFiles.format", "json")
             .option("rescuedDataColumn", "_rescued_data")
             .load("/Volumes/cat/sch/raw/events/")
             .withColumn("_ingested_at", F.current_timestamp())
             .withColumn("_has_errors",  F.col("_rescued_data").isNotNull())
    )

@dp.table(name="bronze_quarantine")
def bronze_quarantine():
    return spark.readStream.table("bronze_events").filter("_has_errors = true")

@dp.table(name="silver_clean")
def silver_clean():
    return spark.readStream.table("bronze_events").filter("_has_errors = false")
```

**When to use**: Schema drift on JSON / CSV ingestion, optional fields that arrive late, downstream tables that can't tolerate nulls in known columns. Pair with an alert on `bronze_quarantine` row growth.

**Alternative**: `@dp.expect_or_drop` / `CONSTRAINT ... ON VIOLATION DROP ROW`. Use expectations when the rule is a value check (`amount > 0`); use rescued-data quarantine when the rule is a schema/parse problem.

---

## Stream-to-Stream Joins (Pattern)

Always bound the join by event-time interval. Without bounds, state grows unbounded.

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders_with_payments AS
SELECT o.order_id, o.customer_id, o.order_timestamp,
       o.amount   AS order_amount,
       p.payment_id, p.payment_timestamp, p.payment_method,
       p.amount   AS payment_amount
FROM STREAM bronze_orders   o
INNER JOIN STREAM bronze_payments p
  ON o.order_id = p.order_id
 AND p.payment_timestamp BETWEEN o.order_timestamp
                              AND o.order_timestamp + INTERVAL 1 HOUR;
```

```python
@dp.table(name="silver_orders_with_payments")
def silver_orders_with_payments():
    orders   = spark.readStream.table("bronze_orders")
    payments = spark.readStream.table("bronze_payments")
    return orders.join(
        payments,
        (orders.order_id == payments.order_id) &
        (payments.payment_timestamp >= orders.order_timestamp) &
        (payments.payment_timestamp <= orders.order_timestamp + F.expr("INTERVAL 1 HOUR")),
        "inner",
    )
```

For stream-to-static (broadcast small dimensions) and perf-tuning, see [performance.md](performance.md#join-optimization).

---

## Incremental Aggregations (Running Totals)

Streaming `GROUP BY` without windows yields cumulative aggregates per group. Watch state size — see [performance.md](performance.md#state-management-for-streaming).

```sql
CREATE OR REFRESH STREAMING TABLE silver_customer_running_totals AS
SELECT customer_id,
       SUM(amount)                  AS total_spent,
       COUNT(*)                     AS transaction_count,
       MAX(transaction_timestamp)   AS last_transaction_at
FROM STREAM bronze_transactions
GROUP BY customer_id;
```

```python
@dp.table(name="silver_customer_running_totals")
def silver_customer_running_totals():
    return (
        spark.readStream.table("bronze_transactions")
             .groupBy("customer_id")
             .agg(F.sum("amount").alias("total_spent"),
                  F.count("*").alias("transaction_count"),
                  F.max("transaction_timestamp").alias("last_transaction_at"))
    )
```

---

## Anomaly Detection

### Rolling z-score outlier flag

```sql
CREATE OR REFRESH STREAMING TABLE silver_sensor_with_anomalies AS
SELECT sensor_id, event_timestamp, temperature,
       AVG(temperature)    OVER w AS rolling_avg_100,
       STDDEV(temperature) OVER w AS rolling_stddev_100,
       CASE
         WHEN temperature > AVG(temperature) OVER w + 3 * STDDEV(temperature) OVER w THEN 'HIGH_OUTLIER'
         WHEN temperature < AVG(temperature) OVER w - 3 * STDDEV(temperature) OVER w THEN 'LOW_OUTLIER'
         ELSE 'NORMAL'
       END AS anomaly_flag
FROM STREAM bronze_sensor_events
WINDOW w AS (PARTITION BY sensor_id ORDER BY event_timestamp
             ROWS BETWEEN 100 PRECEDING AND CURRENT ROW);

-- Route anomalies for alerting
CREATE OR REFRESH STREAMING TABLE silver_sensor_anomalies AS
SELECT * FROM STREAM silver_sensor_with_anomalies
WHERE anomaly_flag IN ('HIGH_OUTLIER', 'LOW_OUTLIER');
```

```python
@dp.table(name="silver_sensor_with_anomalies")
def silver_sensor_with_anomalies():
    w = Window.partitionBy("sensor_id").orderBy("event_timestamp").rowsBetween(-100, 0)
    return (
        spark.readStream.table("bronze_sensor_events")
             .withColumn("rolling_avg",     F.avg("temperature").over(w))
             .withColumn("rolling_stddev",  F.stddev("temperature").over(w))
             .withColumn("anomaly_flag",
                 F.when(F.col("temperature") > F.col("rolling_avg") + 3 * F.col("rolling_stddev"), "HIGH_OUTLIER")
                  .when(F.col("temperature") < F.col("rolling_avg") - 3 * F.col("rolling_stddev"), "LOW_OUTLIER")
                  .otherwise("NORMAL"))
    )

@dp.table(name="silver_sensor_anomalies")
def silver_sensor_anomalies():
    return (
        spark.readStream.table("silver_sensor_with_anomalies")
             .filter(F.col("anomaly_flag").isin("HIGH_OUTLIER", "LOW_OUTLIER"))
    )
```

### Static threshold filtering

```sql
CREATE OR REFRESH STREAMING TABLE silver_high_value_transactions AS
SELECT transaction_id, customer_id, amount, transaction_timestamp
FROM STREAM bronze_transactions
WHERE amount > 10000;
```

```python
@dp.table(name="silver_high_value_transactions")
def silver_high_value_transactions():
    return (spark.readStream.table("bronze_transactions").filter(F.col("amount") > 10000))
```

---

## Monitoring Lag

Track end-to-end freshness by comparing event-time max to processing time. Useful for alerting on ingestion delays from Kafka, Kinesis, or Auto Loader.

```sql
CREATE OR REFRESH STREAMING TABLE monitoring_lag AS
SELECT 'kafka_events' AS source,
       MAX(kafka_timestamp)  AS max_event_timestamp,
       current_timestamp()   AS processing_timestamp,
       unix_timestamp(current_timestamp()) - unix_timestamp(MAX(kafka_timestamp)) AS lag_seconds
FROM STREAM bronze_kafka_events
GROUP BY window(kafka_timestamp, '1 minute');
```

```python
@dp.table(name="monitoring_lag")
def monitoring_lag():
    return (
        spark.readStream.table("bronze_kafka_events")
             .groupBy(F.window("kafka_timestamp", "1 minute"))
             .agg(F.lit("kafka_events").alias("source"),
                  F.max("kafka_timestamp").alias("max_event_timestamp"),
                  F.current_timestamp().alias("processing_timestamp"))
             .withColumn("lag_seconds",
                 F.unix_timestamp("processing_timestamp") - F.unix_timestamp("max_event_timestamp"))
    )
```

---

## Best Practices

1. **Use event time, not processing time**, for aggregation keys.
2. **Deduplicate at silver**, not bronze. Bronze is append-only, silver is clean.
3. **Bound state**: time windows, lower cardinality, materialize intermediates — see [performance.md](performance.md#state-management-for-streaming).
4. **Quarantine, don't drop silently** — route bad rows to a side table for observability.
5. **Use Auto CDC for sequenced updates** instead of building dedup with `ROW_NUMBER` — see [auto-cdc.md](auto-cdc.md).

---

## Common Issues

| Issue | Cause / Fix |
|-------|-------------|
| High memory with windows | Larger windows; reduce group-by cardinality. |
| Duplicate events in output | Add explicit dedup by unique key, or switch to Auto CDC SCD Type 1. |
| Missing late-arriving events | Larger window; check that aggregation uses event time not processing time. |
| Stream-to-stream join empty | Missing or too-narrow time bound on join condition. |
| State growth over time | Add time windows; reduce cardinality; materialize daily then aggregate batch monthly. |
| `bronze_quarantine` empty unexpectedly | `rescuedDataColumn` not enabled; check Auto Loader options. |
