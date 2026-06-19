# Streaming Patterns

Patterns for streaming pipelines: deduplication, windowed aggregations, late-arriving data, rescue-data quarantine, monitoring lag, anomaly detection. SQL is shown as canonical; Python equivalents use `@dp.table` + `spark.readStream.table(...)` with the obvious DataFrame translation.

For stream-to-stream joins as a perf-framed topic, see [performance.md](performance.md#join-optimization). For Auto Loader, see [auto-loader-python.md](auto-loader-python.md) / [auto-loader-sql.md](auto-loader-sql.md). For Kafka ingestion, see [kafka.md](kafka.md).

---

## Deduplication

Apply at the bronze → silver transition. Bronze accepts duplicates, silver is clean.

### By key (keep first)

```sql
CREATE OR REFRESH STREAMING TABLE silver_events_dedup AS
SELECT event_id, user_id, event_type, event_timestamp, _ingested_at
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_timestamp) AS rn
  FROM STREAM(bronze_events)
)
WHERE rn = 1;
```

Python equivalent: `Window.partitionBy("event_id").orderBy("event_timestamp")` + `.withColumn("rn", F.row_number().over(w)).filter(F.col("rn") == 1).drop("rn")`.

**Simple alternative**: `SELECT DISTINCT` (SQL) / `.dropDuplicates(["event_id"])` (Python). Cheaper for low-cardinality append-only streams; maintains state per unique row.

### Within a time window (tolerates late arrivals)

```sql
CREATE OR REFRESH STREAMING TABLE silver_events_dedup AS
SELECT event_id, user_id, event_type, event_timestamp,
       MIN(_ingested_at) AS first_seen_at
FROM STREAM(bronze_events)
GROUP BY event_id, user_id, event_type, event_timestamp,
         window(event_timestamp, '1 hour');
```

Same `GROUP BY` shape generalises to composite-key dedup (just add the key columns to the `GROUP BY`).

### When to use Auto CDC instead

For dedup with sequenced updates (most-recent-wins, deletes, late corrections), use Auto CDC with SCD Type 1 — see [auto-cdc-python.md](auto-cdc-python.md) / [auto-cdc-sql.md](auto-cdc-sql.md). Manual `ROW_NUMBER` / `GROUP BY` dedup is for append-only streams without semantic updates.

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
       COUNT(*)         AS event_count
FROM STREAM(bronze_sensor_events)
GROUP BY sensor_id, window(event_timestamp, '5 minutes');
```

Python equivalent: `.groupBy("sensor_id", F.window("event_timestamp", "5 minutes")).agg(F.avg(...), F.min(...), F.max(...), F.count("*"))`.

For multiple granularities, define a separate streaming table per window size (e.g. `gold_sensor_1min` + `gold_sensor_1hour`) — same shape, different `window(...)` argument. To expose start/end as columns: `window(event_timestamp, '1 minute').start AS window_start`, `.end AS window_end`.

### Session windows (inactivity-bounded)

Group events into sessions terminated by an inactivity gap.

```sql
CREATE OR REFRESH STREAMING TABLE silver_user_sessions AS
SELECT user_id,
       session_window(event_timestamp, '30 minutes') AS session,
       MIN(event_timestamp)     AS session_start,
       MAX(event_timestamp)     AS session_end,
       COUNT(*)                 AS event_count,
       COLLECT_LIST(event_type) AS event_sequence
FROM STREAM(bronze_user_events)
GROUP BY user_id, session_window(event_timestamp, '30 minutes');
```

Python: `F.session_window("event_timestamp", "30 minutes")`.

### Window-size guidance

| Window | Use case |
|--------|----------|
| 1–5 minutes | Real-time monitoring, alerting |
| 15–60 minutes | Operational dashboards |
| 1–24 hours | Analytical reports |

Larger windows = less state pressure but stale results. Pick the smallest window that meets the freshness SLO.

---

## Late-Arriving Data

Use event time (the timestamp in the row), not processing time (`_ingested_at`), as the aggregation key. Keep `_ingested_at` as a debugging field — never the aggregation key.

```sql
CREATE OR REFRESH STREAMING TABLE gold_daily_orders AS
SELECT CAST(order_timestamp AS DATE) AS order_date,   -- event time
       COUNT(*)    AS order_count,
       SUM(amount) AS total_amount
FROM STREAM(silver_orders)
GROUP BY CAST(order_timestamp AS DATE);
```

Python: `.groupBy(F.to_date("order_timestamp").alias("order_date"))`.

---

## Rescue-Data Quarantine

Route malformed records to a quarantine table so the clean stream stays clean but no data is silently dropped. Uses Auto Loader's `_rescued_data` column (default name; configurable via `rescuedDataColumn`).

```sql
-- Bronze: ingest everything, flag rows where Auto Loader rescued bad fields
CREATE OR REFRESH STREAMING TABLE bronze_events AS
SELECT *,
       current_timestamp() AS _ingested_at,
       _rescued_data IS NOT NULL AS _has_errors
FROM STREAM read_files('/Volumes/cat/sch/raw/events/', format => 'json');

-- Quarantine and clean streams branch from the flagged bronze
CREATE OR REFRESH STREAMING TABLE bronze_quarantine AS
SELECT * FROM STREAM(bronze_events) WHERE _rescued_data IS NOT NULL;

CREATE OR REFRESH STREAMING TABLE silver_clean AS
SELECT * FROM STREAM(bronze_events) WHERE _rescued_data IS NULL;
```

Python equivalent uses `.option("rescuedDataColumn", "_rescued_data")` on the Auto Loader read, then two `@dp.table` functions filtering on `_has_errors`.

**When to use**: schema drift on JSON / CSV, optional fields that arrive late, downstream tables that can't tolerate nulls in known columns. Alert on `bronze_quarantine` row growth.

**Alternative**: `@dp.expect_or_drop` / `CONSTRAINT ... ON VIOLATION DROP ROW`. Use expectations when the rule is a value check (`amount > 0`); use rescued-data quarantine when the rule is a schema/parse problem.

---

## Stream-to-Stream Joins

Always bound the join by event-time interval. Without bounds, state grows unbounded.

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders_with_payments AS
SELECT o.order_id, o.customer_id, o.order_timestamp,
       o.amount AS order_amount,
       p.payment_id, p.payment_timestamp, p.payment_method,
       p.amount AS payment_amount
FROM STREAM(bronze_orders)   o
INNER JOIN STREAM(bronze_payments) p
  ON o.order_id = p.order_id
 AND p.payment_timestamp BETWEEN o.order_timestamp
                              AND o.order_timestamp + INTERVAL 1 HOUR;
```

Python equivalent: same join with the time-bound predicate as `(p.payment_timestamp >= o.order_timestamp) & (p.payment_timestamp <= o.order_timestamp + F.expr("INTERVAL 1 HOUR"))`.

For stream-to-static (broadcast small dimensions) and perf-tuning, see [performance.md](performance.md#join-optimization).

---

## Incremental Aggregations (Running Totals)

Streaming `GROUP BY` without windows yields cumulative aggregates per group. Watch state size — see [performance.md](performance.md#state-management-for-streaming).

```sql
CREATE OR REFRESH STREAMING TABLE silver_customer_running_totals AS
SELECT customer_id,
       SUM(amount)                AS total_spent,
       COUNT(*)                   AS transaction_count,
       MAX(transaction_timestamp) AS last_transaction_at
FROM STREAM(bronze_transactions)
GROUP BY customer_id;
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
FROM STREAM(bronze_sensor_events)
WINDOW w AS (PARTITION BY sensor_id ORDER BY event_timestamp
             ROWS BETWEEN 100 PRECEDING AND CURRENT ROW);

-- Route anomalies for alerting
CREATE OR REFRESH STREAMING TABLE silver_sensor_anomalies AS
SELECT * FROM STREAM(silver_sensor_with_anomalies)
WHERE anomaly_flag IN ('HIGH_OUTLIER', 'LOW_OUTLIER');
```

Python: same shape with `Window.partitionBy("sensor_id").orderBy("event_timestamp").rowsBetween(-100, 0)` and `F.when(...).when(...).otherwise(...)`. Static-threshold variants are just `.filter(F.col("amount") > 10000)`.

---

## Monitoring Lag

Compare event-time max to processing time. Useful for alerting on ingestion delays from Kafka, Kinesis, or Auto Loader.

```sql
CREATE OR REFRESH STREAMING TABLE monitoring_lag AS
SELECT 'kafka_events' AS source,
       MAX(kafka_timestamp) AS max_event_timestamp,
       current_timestamp()  AS processing_timestamp,
       unix_timestamp(current_timestamp()) - unix_timestamp(MAX(kafka_timestamp)) AS lag_seconds
FROM STREAM(bronze_kafka_events)
GROUP BY window(kafka_timestamp, '1 minute');
```

---

## Best Practices

1. **Use event time, not processing time**, for aggregation keys.
2. **Deduplicate at silver**, not bronze. Bronze is append-only, silver is clean.
3. **Bound state**: time windows, lower cardinality, materialize intermediates — see [performance.md](performance.md#state-management-for-streaming).
4. **Quarantine, don't drop silently** — route bad rows to a side table for observability.
5. **Use Auto CDC for sequenced updates** instead of building dedup with `ROW_NUMBER` — see [auto-cdc-python.md](auto-cdc-python.md) / [auto-cdc-sql.md](auto-cdc-sql.md).

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
