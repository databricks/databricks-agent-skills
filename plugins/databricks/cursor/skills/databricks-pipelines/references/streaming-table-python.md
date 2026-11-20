Streaming Tables in Spark Declarative Pipelines enable incremental processing of continuously arriving data.

**NOTE:** This guide focuses on streaming tables. For details on materialized views (batch processing with `spark.read`), read [materialized-view-python.md](materialized-view-python.md) instead.

**API Reference:**

**@dp.table() / @dlt.table()**
Decorator to define a streaming table or materialized view. Returns streaming table when function returns `spark.readStream`. For materialized views using `spark.read`, see the materialized view reference ([materialized-view-python.md](materialized-view-python.md)).

```python
@dp.table(
  name="<name>",
  comment="<comment>",
  spark_conf={"<key>": "<value>"},
  table_properties={"<key>": "<value>"},
  path="<storage-location-path>",
  partition_cols=["<partition-column>"],
  cluster_by_auto=True,
  cluster_by=["<clustering-column>"],
  schema="schema-definition",
  row_filter="row-filter-clause",
  private=False
)
def my_append_flow():
    return spark.readStream.table("source.data")
```

Parameters:

- `name` (str): Table name (defaults to function name)
- `comment` (str): Description for the table
- `spark_conf` (dict): Spark configurations for query execution
- `table_properties` (dict): Delta table properties
- `path` (str): Storage location for table data (defaults to managed location)
- `partition_cols` (list): Columns to partition the table by
  - Legacy; prefer `cluster_by` for new tables — see [performance-tuning.md](performance-tuning.md#liquid-clustering)
- `cluster_by_auto` (bool): Enable automatic liquid clustering
- `cluster_by` (list): Columns to use as clustering keys for liquid clustering
- `schema` (str or StructType): Schema definition (SQL DDL string or StructType)
  - Supports generated columns: `"<col_name> <type> GENERATED ALWAYS AS (<expression>)"` — see [Delta generated columns](https://docs.databricks.com/aws/en/tables/features/generated-columns) for syntax.
  - Supports default columns: `"<col_name> <type> DEFAULT <default_expression>"` (applied on INSERT/UPDATE/MERGE when the column is not supplied) — see the [CREATE TABLE reference](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-table-using) for DEFAULT syntax.
  - Supports constraints: Primary keys, foreign keys (informational, Unity Catalog only, **not enforced**)
  - Supports column masks: `"ssn STRING MASK catalog.schema.ssn_mask_fn USING COLUMNS (region)"`
- `row_filter` (str): (Public Preview) A row filter clause that filters rows when fetched from the table.
  - Must use syntax: `"ROW FILTER func_name ON (column_name [, ...])"` where `func_name` is a SQL UDF returning `BOOLEAN`. The UDF can be defined in Unity Catalog.
    - Rows are filtered out when the function returns `FALSE` or `NULL`.
    - You can pass table columns or constant literals (`STRING`, numeric, `BOOLEAN`, `INTERVAL`, `NULL`) as arguments.
    - The filter is applied as soon as rows are fetched from the data source.
    - The function runs with pipeline owner's rights during refresh and invoker's rights during queries (allowing user-context functions like `CURRENT_USER()` and `IS_MEMBER()` for data security).
  - Note: Using row filters on source tables forces full refresh of downstream materialized views.
  - Note: It is NOT possible to call `CREATE FUNCTION` within a Spark Declarative Pipeline.
- `private` (bool): Restricts table to pipeline scope; prevents metastore publication

**dp.create_streaming_table() / dlt.create_streaming_table()**
Creates an empty streaming table as target for CDC flows or append flows. Does NOT return a value - call at top level without assignment.

```python
dp.create_streaming_table(
  name="<table-name>",
  comment="<comment>",
  spark_conf={"<key>": "<value>"},
  table_properties={"<key>": "<value>"},
  path="<storage-location-path>",
  partition_cols=["<partition-column>"],
  cluster_by_auto=True,
  cluster_by=["<clustering-column>"],
  schema="schema-definition",
  expect_all={"<key>": "<value>"},
  expect_all_or_drop={"<key>": "<value>"},
  expect_all_or_fail={"<key>": "<value>"},
  row_filter="row-filter-clause"
)
```

Parameters: Same as @dp.table() except `private`, plus:

- `expect_all` (dict): Data quality expectations (warn on failure, include in target)
- `expect_all_or_drop` (dict): Expectations that drop failing rows from target
- `expect_all_or_fail` (dict): Expectations that fail pipeline on violation

**@dp.append_flow() / @dlt.append_flow()**
Decorator to define a flow that appends data from a source to an existing target table. Multiple append flows can write to the same target table.

```python
@dp.append_flow(
  target="<target-table-name>",
  name="<flow-name>",  # optional, defaults to function name
  once=<boolean>,  # optional, defaults to False
  spark_conf={"<key>": "<value>", "<key>": "<value>"},  # optional
  comment="<comment>"  # optional
)
def my_append_flow():
    # For once=False (streaming): use spark.readStream
    return spark.readStream.table("source.data")
    # For once=True (batch): use spark.read
    return spark.read.table("source.data")
```

Parameters:

- `target` (str): The name of the target streaming table where data will be appended. Target must exist (created with `dp.create_streaming_table()`). **Required.**
- `name` (str): The name of the flow. If not specified, defaults to the function name. Use distinct names when multiple flows target the same table.
- `once` (bool): Controls whether the flow runs continuously or once:
  - **False (default)**: Flow continuously processes new data as it arrives in streaming mode. **Must return a streaming DataFrame using `spark.readStream`**, CAN use `cloudFiles` (Auto Loader).
  - **True**: Flow processes data only once during pipeline execution and then stops. **Must return a batch DataFrame using `spark.read`**. Do NOT use `cloudFiles` (Auto Loader) with `once=True` - use regular batch reads like `spark.read.format("<format>")` instead.
- `spark_conf` (dict): A dictionary of Spark configuration key-value pairs to apply specifically to this flow's query execution (e.g., `{"spark.sql.shuffle.partitions": "10"}`).
- `comment` (str): A description of the flow that appears in the pipeline metadata and documentation.

**Two Ways to Define Streaming Tables:**

1. **@dp.table decorator (MOST COMMON)**
   - Returns a streaming DataFrame using `spark.readStream`
   - Automatically inferred as a streaming table when returning a streaming DataFrame

   ```python
   @dp.table(name="events_stream")
   def events_stream():
       return spark.readStream.table("source_catalog.schema.events")
   ```

2. **dp.create_streaming_table()**
   - Creates an empty streaming table target
   - Required as target for Auto CDC flows and append flows
   - Does NOT return a value (do not assign to a variable)

   ```python
   dp.create_streaming_table(
       name="users",
       schema="user_id INT, name STRING, updated_at TIMESTAMP"
   )
   ```

**WHEN TO USE WHICH:**

Use **@dp.table with readStream** when:

- Reading and transforming streaming data
- Creating streaming tables from sources (Auto Loader, Delta tables, etc.)
- This is the standard pattern for most streaming use cases

Use **dp.create_streaming_table()** when:

- Creating a target table for `dp.create_auto_cdc_flow()`
- Creating a target table for `@dp.append_flow` from multiple sources
- Need to explicitly define table schema before data flows in

**NEVER:**

- Define a table with `@dp.table` AND add a separate `@dp.append_flow` targeting it - the decorator already provides continuous processing; the flow is redundant

**Common Patterns:**

**Pattern 1: Simple streaming transformation**

```python
@dp.table()
def bronze():
    return spark.readStream.format("cloudFiles") \
        .option("cloudFiles.format", "json") \
        .load("/path/to/data")

@dp.table()
def silver():
    return spark.readStream.table("bronze").filter("id IS NOT NULL")
```

**Pattern 2: Multi-source aggregation**

```python
dp.create_streaming_table(name="all_events")

@dp.append_flow(target="all_events", name="mobile")
def mobile():
    return spark.readStream.table("mobile.events")

@dp.append_flow(target="all_events", name="web")
def web():
    return spark.readStream.table("web.events")
```

**Pattern 3: One-time backfill with append flow**

```python
dp.create_streaming_table(name="transactions")

# Continuous streaming flow for new data
@dp.append_flow(target="transactions", name="live_stream")
def live_transactions():
    return spark.readStream.table("source.transactions")

# One-time backfill flow for historical data (uses spark.read for batch)
@dp.append_flow(
    target="transactions",
    name="historical_backfill",
    once=True,
    comment="Backfill historical transactions from archive"
)
def backfill_transactions():
    return spark.read.table("archive.historical_transactions")
```

**Pattern 4: Row filters for data security**

```python
# Assumes filter_by_dept is a SQL UDF defined in Unity Catalog that returns BOOLEAN

# Apply row filter to streaming table
@dp.table(
    name="employees",
    schema="emp_id INT, emp_name STRING, dept STRING, salary DECIMAL(10,2)",
    row_filter="ROW FILTER my_catalog.my_schema.filter_by_dept ON (dept)"
)
def employees():
    return spark.readStream.table("source.employees")
```

**Pattern 5: Stream-static join (enrich streaming data with dimension table)**

```python
@dp.table()
def enriched_transactions():
    transactions = spark.readStream.table("transactions")
    customers = spark.read.table("customers")
    return transactions.join(customers, transactions.customer_id == customers.id)
```

The dimension table (`customers`) is read as a static snapshot at stream start, while the streaming source (`transactions`) is read incrementally.

**Pattern 6: Reading from upstream ST with updates/deletes (skipChangeCommits)**

```python
@dp.table()
def downstream():
    return spark.readStream.option("skipChangeCommits", "true").table("upstream_with_deletes")
```

Use `skipChangeCommits` when reading from a streaming table that has updates/deletes (e.g., GDPR compliance, Auto CDC targets). Without this flag, change commits cause errors.

**WARNING: Do NOT use `spark.readStream` to read from a materialized view.** Materialized views always produce overwrite commits on every refresh, making them invalid streaming sources. `skipChangeCommits` will not help — the downstream must be converted to a materialized view (`spark.read.table(...)`) instead. Attempting this causes the error `DELTA_SOURCE_TABLE_IGNORE_CHANGES`.

---

## Advanced Streaming Patterns

### Deduplication

**dropDuplicatesWithinWatermark (time-bounded, recommended for streaming):**

```python
@dp.table(name="silver_events_dedup")
def silver_events_dedup():
    return (
        spark.readStream.table("bronze_events")
        .withWatermark("event_timestamp", "10 minutes")
        .dropDuplicatesWithinWatermark(["event_id"])
    )
```

**Why `dropDuplicatesWithinWatermark`:** It drops duplicates of a key that arrive within the watermark delay, even when their event times differ, then forgets the key so state stays bounded. Plain `.dropDuplicates(["event_id"])` keeps every key in state forever and wrongly drops a key that is legitimately reused later. Use this for high-volume streams where exact global dedup is not required. Deduplicate at the bronze → silver transition.

Do not use a `row_number()` window over a stream: streaming rejects non-time window functions with `NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING`. For dedup with sequenced updates (most recent wins, deletes, late corrections), use Auto CDC with SCD Type 1 (see [auto-cdc-python.md](auto-cdc-python.md)).

### Windowed Aggregations

**Tumbling windows (non-overlapping fixed-size):**

```python
@dp.table(name="silver_sensor_5min", cluster_by=["sensor_id"])
def silver_sensor_5min():
    return (
        spark.readStream.table("bronze_sensor_events")
        .withWatermark("event_timestamp", "10 minutes")
        .groupBy(
            F.col("sensor_id"),
            F.window("event_timestamp", "5 minutes")
        )
        .agg(
            F.avg("temperature").alias("avg_temperature"),
            F.min("temperature").alias("min_temperature"),
            F.max("temperature").alias("max_temperature"),
            F.count("*").alias("event_count")
        )
    )
```

**Session windows (group by inactivity gap):**

```python
@dp.table(name="silver_user_sessions")
def silver_user_sessions():
    return (
        spark.readStream.table("bronze_user_events")
        .withWatermark("event_timestamp", "1 hour")
        .groupBy(
            F.col("user_id"),
            F.session_window("event_timestamp", "30 minutes")
        )
        .agg(
            F.min("event_timestamp").alias("session_start"),
            F.max("event_timestamp").alias("session_end"),
            F.count("*").alias("event_count"),
            F.collect_list("event_type").alias("event_sequence")
        )
    )
```

Each window is written once, after the watermark passes its end. A streaming aggregation without `withWatermark` runs in Complete mode: it rewrites the table on every update and keeps all state. Group by `F.window(...)`, not a `to_date(...)` bucket, which also keeps every day in state. `F.window(..., "1 day")` buckets are UTC days (`.start` is a `TIMESTAMP` at 00:00 UTC); for days in a fixed UTC offset, use the four-argument `window` with a `startTime` (see [streaming-table-sql.md](streaming-table-sql.md#late-arriving-data)). For late-arriving data, aggregate on the event time and pick a delay that covers how late rows arrive; rows later than the delay are dropped. The SQL reference has more patterns (running totals, rescued-data quarantine, anomaly statistics, lag monitoring) that translate directly; see [streaming-table-sql.md](streaming-table-sql.md#advanced-streaming-patterns).

### Stream-to-Stream Joins

Join two streaming sources with a watermark on both inputs and time bounds:

```python
@dp.table(name="silver_orders_with_payments")
def silver_orders_with_payments():
    orders = spark.readStream.table("bronze_orders").withWatermark("order_timestamp", "1 hour")
    payments = spark.readStream.table("bronze_payments").withWatermark("payment_timestamp", "1 hour")
    return (
        orders.join(
            payments,
            (orders.order_id == payments.order_id) &
            (payments.payment_timestamp >= orders.order_timestamp) &
            (payments.payment_timestamp <= orders.order_timestamp + F.expr("INTERVAL 1 HOUR")),
            "inner"
        )
        .select(
            orders.order_id,
            orders.customer_id,
            orders.order_timestamp,
            orders.amount.alias("order_amount"),
            payments.payment_id,
            payments.payment_timestamp,
            payments.amount.alias("payment_amount")
        )
    )
```

**Why watermarks and time bounds matter:** Without both, state grows indefinitely as the system waits for potential matches. Always include a time bound in stream-to-stream join conditions.

### Custom Stateful Logic (`transformWithState`)

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


### Streaming Best Practices

- **Use event timestamps** for business logic, not processing time (`_ingested_at`)
- **Add watermarks** to all stateful operations (windowed aggregations, stream-to-stream joins, `dropDuplicatesWithinWatermark`) to bound state and enable cleanup
- **Window size guidelines:** Real-time monitoring: 1-5 min, operational dashboards: 15-60 min, analytical reports: 1-24 hr

---

**KEY RULES:**

- Streaming tables use `spark.readStream` (streaming reads)
- Materialized views use `spark.read` (batch reads) - see the materialized view reference ([materialized-view-python.md](materialized-view-python.md))
- `@dp.table` returning a batch DataFrame creates a materialized view; prefer `@dp.materialized_view()` for batch datasets
- Never use `.writeStream`, `.start()`, or checkpoint options - Databricks manages these automatically
- For streaming flows (`once=False`): Use `spark.readStream` to return a streaming DataFrame
- For one-time flows (`once=True`): Use `spark.read` to return a batch DataFrame
- Generated columns, constraints, and masks require schema definition
- Row filters force full refresh of downstream materialized views
- Use `skipChangeCommits` when reading from STs that have updates/deletes
