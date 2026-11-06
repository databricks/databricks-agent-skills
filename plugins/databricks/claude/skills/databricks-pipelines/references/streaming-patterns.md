# Streaming Patterns

Patterns for streaming pipelines: deduplication, windowed aggregations, late-arriving data, custom stateful logic, rescue-data quarantine, monitoring lag, anomaly detection. SQL is shown as canonical; Python equivalents use `@dp.table` + `spark.readStream.table(...)` with the obvious DataFrame translation.

For stream-to-stream joins as a perf-framed topic, see [performance.md](performance.md#join-optimization). For Auto Loader, see [auto-loader-python.md](auto-loader-python.md) / [auto-loader-sql.md](auto-loader-sql.md). For Kafka ingestion, see [kafka.md](kafka.md).

---

## Deduplication

Apply at the bronze → silver transition. Bronze accepts duplicates, silver is clean.

### By key, retries within a bounded delay

Use `dropDuplicatesWithinWatermark` in a Python flow. It drops duplicates of a key that arrive within the watermark delay, even when their event time differs, then forgets the key so state stays bounded ([stateful processing](https://docs.databricks.com/aws/en/ldp/stateful-processing)).

```python
from pyspark import pipelines as dp


@dp.table()
def silver_events_dedup():
    return (spark.readStream.table("bronze_events")
            .withWatermark("event_timestamp", "1 hour")
            .dropDuplicatesWithinWatermark(["event_id"]))
```

Do **not** use `ROW_NUMBER() OVER (PARTITION BY ...)` on `STREAM(...)`. Streaming rejects non-time window functions (`NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING`). Plain `.dropDuplicates(["event_id"])` keeps every key in state forever, and it wrongly drops a key that is legitimately reused later.

### Within a time window (tolerates late arrivals)

```sql
CREATE OR REFRESH STREAMING TABLE silver_events_dedup AS
SELECT event_id, user_id, event_type,
       MIN(event_timestamp) AS event_timestamp,
       MIN(_ingested_at)    AS first_seen_at
FROM STREAM(bronze_events) WATERMARK event_timestamp DELAY OF INTERVAL 10 MINUTES
GROUP BY event_id, user_id, event_type, window(event_timestamp, '1 hour');
```

Group by the `window(...)`, not also by the raw `event_timestamp`: grouping by both fails with `More than one event time columns are available`.

Same `GROUP BY` shape generalises to composite-key dedup (just add the key columns to the `GROUP BY`).

**Every streaming aggregation in SDP needs a `WATERMARK` clause.** Without one, the flow does not fail: SDP silently runs it in **Complete** output mode, which rewrites the whole table on every update and never evicts state (`DESCRIBE HISTORY` shows `outputMode: Complete`; with `WATERMARK` it shows `Append`). Syntax: `FROM STREAM(t) WATERMARK <time column> DELAY OF INTERVAL <n> <unit> [alias]`.

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
FROM STREAM(bronze_sensor_events) WATERMARK event_timestamp DELAY OF INTERVAL 2 MINUTES
GROUP BY sensor_id, window(event_timestamp, '5 minutes');
```

Python equivalent: `.withWatermark("event_timestamp", "2 minutes").groupBy("sensor_id", F.window("event_timestamp", "5 minutes")).agg(F.avg(...), F.min(...), F.max(...), F.count("*"))`.

With `WATERMARK`, a window is written once, after the watermark passes its end (final values; latency = window + delay). For multiple granularities, define a separate streaming table per window size (e.g. `gold_sensor_1min` + `gold_sensor_1hour`); same shape, different `window(...)` argument. To expose start/end as columns: `window(event_timestamp, '1 minute').start AS window_start`, `.end AS window_end`.

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
FROM STREAM(bronze_user_events) WATERMARK event_timestamp DELAY OF INTERVAL 10 MINUTES
GROUP BY user_id, session_window(event_timestamp, '30 minutes');
```

Python: `F.session_window("event_timestamp", "30 minutes")` after `.withWatermark("event_timestamp", "10 minutes")`. Use append output for finalised sessions; update mode is rejected for session windows, and complete mode runs but rewrites every session on each update. For a max session length or custom session output, use `transformWithState` with event-time timers (below).

### Window-size guidance

| Window | Use case |
|--------|----------|
| 1–5 minutes | Real-time monitoring, alerting |
| 15–60 minutes | Operational dashboards |
| 1–24 hours | Analytical reports |

Larger windows = less state pressure but stale results. Pick the smallest window that meets the freshness SLO. For genuine sub-second operational latency, use [Real-Time Mode](real-time-mode.md).

---

## Late-Arriving Data

Use event time (the timestamp in the row), not processing time (`_ingested_at`), as the aggregation key. Keep `_ingested_at` as a debugging field — never the aggregation key.

```sql
CREATE OR REFRESH STREAMING TABLE gold_daily_orders AS
SELECT window(order_timestamp, '1 day').start AS order_date,   -- event time
       COUNT(*)    AS order_count,
       SUM(amount) AS total_amount
FROM STREAM(silver_orders) WATERMARK order_timestamp DELAY OF INTERVAL 1 HOUR
GROUP BY window(order_timestamp, '1 day');
```

Python: `.withWatermark("order_timestamp", "1 hour").groupBy(F.window("order_timestamp", "1 day"))`.

Choose a delay that covers how late orders arrive: rows later than the delay are dropped, and each day's row lands once the day closes plus the delay. A `CAST(... AS DATE)` bucket would run in Complete mode and keep every day ([performance.md](performance.md)).

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

Define a watermark on **both** sides and an event-time interval on the same columns ([stateful processing](https://docs.databricks.com/aws/en/ldp/stateful-processing)). An interval alone does not bound state: without watermarks the inner join still runs, but keeps every row, and an outer join is rejected.

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders_with_payments AS
SELECT o.order_id, o.customer_id, o.order_timestamp,
       o.amount AS order_amount,
       p.payment_id, p.payment_timestamp, p.payment_method,
       p.amount AS payment_amount
FROM STREAM(bronze_orders) WATERMARK order_timestamp DELAY OF INTERVAL 10 MINUTES o
INNER JOIN STREAM(bronze_payments) WATERMARK payment_timestamp DELAY OF INTERVAL 10 MINUTES p
  ON o.order_id = p.order_id
 AND p.payment_timestamp BETWEEN o.order_timestamp
                              AND o.order_timestamp + INTERVAL 1 HOUR;
```

Python equivalent: `.withWatermark(...)` on both inputs, then the same join with the time-bound predicate as `(p.payment_timestamp >= o.order_timestamp) & (p.payment_timestamp <= o.order_timestamp + F.expr("INTERVAL 1 HOUR"))`.

For stream-to-static (broadcast small dimensions) and perf-tuning, see [performance.md](performance.md#join-optimization).

---

## Incremental Aggregations (Running Totals)

A bare `GROUP BY customer_id` on a stream has no watermark, so SDP runs it in Complete mode: it rewrites the table every update and keeps every customer in state forever. Scope the total to a time window with a watermark:

```sql
CREATE OR REFRESH STREAMING TABLE silver_customer_daily_totals AS
SELECT customer_id,
       window(transaction_timestamp, '1 day').start AS day,
       SUM(amount)                AS total_spent,
       COUNT(*)                   AS transaction_count,
       MAX(transaction_timestamp) AS last_transaction_at
FROM STREAM(bronze_transactions) WATERMARK transaction_timestamp DELAY OF INTERVAL 1 HOUR
GROUP BY customer_id, window(transaction_timestamp, '1 day');
```

In append mode each day's row lands once, after the day closes plus the delay. For lifetime totals, roll the daily table up in a materialized view. For a live per-key total in a triggered pipeline, use `transformWithState` in `EventTime` mode with a timer that clears idle keys. TTL is valid only with `timeMode="ProcessingTime"`, which never lets a triggered update finish (see below).

---

## Custom Stateful Logic (`transformWithState`)

Use this when dedup, windows, joins, and Auto CDC can't express the logic: a per-key state machine, sessions with a max duration, or "no event for this key for N minutes". Call `transformWithState` (row-based) or `transformWithStateInPandas` inside a Python flow ([TWS in pipelines](https://docs.databricks.com/aws/en/stateful-applications/#use-transformwithstate-in-lakeflow-pipelines)). It is Python only, with no SQL form. Prefer it over `applyInPandasWithState` for new pipelines when your runtime supports it.

> **Triggered pipelines: use `timeMode="EventTime"` (or `"None"`), never `"ProcessingTime"`.** A triggered update whose flow uses `timeMode="ProcessingTime"` never finishes, even when the processor registers no timer: it keeps running empty micro-batches. The docs' [heartbeat example](https://docs.databricks.com/aws/en/ldp/flow-examples) uses `ProcessingTime`, which suits only **continuous** pipelines.

Event-time silence alert. A triggered update gives `handleInputRows` all of a sensor's new rows at once, so the processor sorts them and alerts for each silence inside the batch. A timer alerts for the silence after the last event, when the watermark passes it. Other keys' events move the watermark, so if the *whole* stream stops, nothing fires; for wall-clock silence, run a continuous pipeline with `timeMode="ProcessingTime"`. Late rows inside the watermark delay can arrive after the alert for their gap has been emitted; when that matters and you only need the gaps, use `session_window`.

```python
import datetime as dt
from typing import Iterator

from pyspark import pipelines as dp
from pyspark.sql import Row
from pyspark.sql.streaming import StatefulProcessor, StatefulProcessorHandle

SILENCE_MS = 5 * 60 * 1000


def to_ms(t):  # store epoch-ms longs in state, not timestamps
    return int((t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).timestamp() * 1000)


class SilenceAlert(StatefulProcessor):
    def init(self, handle: StatefulProcessorHandle) -> None:
        self.handle = handle
        self.last = handle.getValueState("last", "last_event_ms long")

    def handleInputRows(self, key, rows: Iterator[Row], timerValues) -> Iterator[Row]:
        prev = self.last.get()
        last_ms = prev[0] if prev else None
        out = []
        for t in sorted(to_ms(r.event_timestamp) for r in rows):
            if last_ms is not None and t - last_ms >= SILENCE_MS:  # silence inside the batch, or since the last one
                out.append(Row(sensor_id=key[0], silent_since_ms=last_ms))
            last_ms = t if last_ms is None else max(last_ms, t)
        for old in self.handle.listTimers():
            self.handle.deleteTimer(old)
        self.handle.registerTimer(last_ms + SILENCE_MS)  # event-time ms
        self.last.update((last_ms,))
        return iter(out)

    def handleExpiredTimer(self, key, timerValues, expiredTimerInfo) -> Iterator[Row]:
        prev = self.last.get()
        self.last.clear()
        if prev:
            yield Row(sensor_id=key[0], silent_since_ms=prev[0])

    def close(self) -> None:
        pass


dp.create_streaming_table("sensor_alerts")


@dp.append_flow(target="sensor_alerts")
def sensor_alerts_flow():
    return (
        spark.readStream.table("bronze_sensor_events")
        .withWatermark("event_timestamp", "2 minutes")
        .groupBy("sensor_id")
        .transformWithState(
            statefulProcessor=SilenceAlert(),
            outputStructType="sensor_id long, silent_since_ms long",  # sensor_id: same type as the source column
            outputMode="Append",
            timeMode="EventTime",
        )
    )
```

Serverless pipelines manage the state store for you. On classic compute below DBR 17.3, set `spark.sql.streaming.stateStore.providerClass` to `com.databricks.sql.streaming.state.RocksDBStateStoreProvider` in the pipeline `configuration` and full-refresh ([heartbeat example](https://docs.databricks.com/aws/en/ldp/flow-examples)). For state types, initial state, and schema evolution, see the `databricks-spark-structured-streaming` skill's [transform-with-state.md](../../databricks-spark-structured-streaming/references/transform-with-state.md).

---

## Anomaly Detection

### Windowed z-score outlier flag

Row-based window functions (`OVER (... ROWS BETWEEN 100 PRECEDING ...)`) are not supported on streams; the flow fails with `NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING`. Compute the statistics per time window with a watermark instead:

```sql
CREATE OR REFRESH STREAMING TABLE silver_sensor_window_stats AS
SELECT sensor_id,
       window(event_timestamp, '10 minutes').start AS window_start,
       AVG(temperature)    AS avg_temperature,
       STDDEV(temperature) AS stddev_temperature,
       MAX(temperature)    AS max_temperature,
       MIN(temperature)    AS min_temperature
FROM STREAM(bronze_sensor_events) WATERMARK event_timestamp DELAY OF INTERVAL 2 MINUTES
GROUP BY sensor_id, window(event_timestamp, '10 minutes');
```

Flag outliers downstream against the previous window's statistics (a materialized view, or a stream-static join). For a true per-row rolling buffer per sensor, keep a bounded `ListState` in `transformWithState`.

---

## Monitoring Lag

Compare event-time max to processing time. Useful for alerting on ingestion delays from Kafka, Kinesis, or Auto Loader. Use a materialized view with a batch read: it recomputes the lag on each refresh. A streaming aggregation without a `WATERMARK` would run in Complete mode, and with one each window would land only after it closes plus the delay.

```sql
CREATE OR REFRESH MATERIALIZED VIEW monitoring_lag AS
SELECT 'kafka_events' AS source,
       MAX(kafka_timestamp) AS max_event_timestamp,
       current_timestamp()  AS processing_timestamp,
       unix_timestamp(current_timestamp()) - unix_timestamp(MAX(kafka_timestamp)) AS lag_seconds
FROM bronze_kafka_events;
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
