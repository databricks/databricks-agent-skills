Streaming Tables in SQL Declarative Pipelines enable incremental processing of continuously arriving data.

**NOTE:** This guide focuses on streaming tables in SQL. For details on materialized views (batch processing), read [materialized-view-sql.md](materialized-view-sql.md) instead.

**API Reference:**

**CREATE STREAMING TABLE**
Creates a streaming table that processes data incrementally using `STREAM()` for streaming reads. For materialized views using batch reads (without `STREAM()`), see the materialized view reference ([materialized-view-sql.md](materialized-view-sql.md)).

```sql
CREATE OR REFRESH [PRIVATE] STREAMING TABLE
  table_name
  [ table_specification ]
  [ table_clauses ]
  [ AS query ]

table_specification
  ( { column_identifier column_type [column_properties] } [, ...]
    [ column_constraint ] [, ...]
    [ , table_constraint ] [...] )

   column_properties
      { NOT NULL | COMMENT column_comment | column_constraint | MASK clause } [ ... ]

table_clauses
  { USING DELTA
    PARTITIONED BY (col [, ...]) |
    CLUSTER BY clause |
    LOCATION path |
    COMMENT view_comment |
    TBLPROPERTIES clause |
    WITH { ROW FILTER clause } } [ ... ]
```

**Parameters:**

- `PRIVATE`: Restricts table to pipeline scope; prevents metastore publication
- `table_name`: Unique identifier for the table (fully qualified name including catalog and schema must be unique unless marked PRIVATE)
- `table_specification`: Optional schema definition with column names, types, and properties
  - `column_identifier`: Name of the column
  - `column_type`: Data type (STRING, BIGINT, DECIMAL, etc.)
  - `column_properties`: Column attributes:
    - `NOT NULL`: Column cannot contain null values
    - `COMMENT column_comment`: Description for the column
    - `column_constraint`: Data quality constraints, consult the expectations reference ([expectations-sql.md](expectations-sql.md)) for details.
    - `MASK clause`: Column masking syntax `MASK catalog.schema.mask_fn USING COLUMNS (other_column)`
  - `table_constraint`: Informational table-level constraints (Unity Catalog only, **not enforced** by Databricks):
    - Look up exact documentation when using
    - Note: Constraints are informational metadata for documentation and query optimization hints; data validation must be performed independently
- `table_clauses`: Optional clauses for table configuration:
  - `USING DELTA`: Optional format specification (only DELTA supported, can be omitted)
  - `PARTITIONED BY (col [, ...])`: Columns for traditional partitioning, mutually exclusive with CLUSTER BY
  - `CLUSTER BY (col [, ...])`: Explicit columns for liquid clustering (optimized query performance, recommended over partitioning)
  - `CLUSTER BY AUTO`: Databricks automatically selects the liquid-clustering columns; `AUTO` has no parentheses
  - `LOCATION path`: Storage path (defaults to pipeline storage location)
  - `COMMENT view_comment`: Description for the table
  - `TBLPROPERTIES clause`: Custom table properties `(key = value [, ...])`
  - `WITH ROW FILTER clause`: Row-level security filtering
    - Syntax: `ROW FILTER func_name ON (column_name [, ...])`
      - `func_name` must be a SQL UDF returning BOOLEAN (can be defined in Unity Catalog)
      - Rows are filtered out when function returns FALSE or NULL
      - Accepts table columns or constant literals (STRING, numeric, BOOLEAN, INTERVAL, NULL)
      - Filter applies when rows are fetched from the data source
      - Runs with pipeline owner's rights during refresh and invoker's rights during queries
    - Note: Using row filters on source tables forces full refresh of downstream materialized views
    - Note: It is NOT possible to call `CREATE FUNCTION` within a Spark Declarative Pipeline.
- `query`: A Spark SQL query that defines the streaming dataset. Must use `STREAM()` function for streaming semantics.

**STREAM() Function:**
Provides streaming read semantics for the source table. Required for streaming queries.

```sql
SELECT * FROM STREAM(source_catalog.schema.source_table);
```

**CREATE FLOW with INSERT INTO**
Creates a flow that appends data from a source to an existing target streaming table. Multiple flows can write to the same target table.

```sql
CREATE FLOW flow_name [COMMENT comment] AS
INSERT INTO [ONCE] target_table BY NAME query
```

**Parameters:**

- `flow_name`: Unique identifier for the flow. Use distinct names when multiple flows target the same table.
- `ONCE`: Controls whether the flow runs continuously or once:
  - **Omitted (default)**: Flow continuously processes new data as it arrives in streaming mode. **Query must use `STREAM()` for streaming reads**.
  - **ONCE**: Flow processes data only once during pipeline execution and then stops. **Query uses non-streaming reads (without `STREAM()`)** for batch processing. Re-executes during pipeline complete refreshes to recreate data.
- `target_table_name`: The name of the target streaming table where data will be appended. Target must exist (created with `CREATE STREAMING TABLE`). **Required.**
- `SELECT ... FROM STREAM(source_table)`: The query to read source data
  - For continuous flows (no ONCE): Use `STREAM()` to return streaming data
  - For one-time flows (with ONCE): Omit `STREAM()` to return batch data

**Two Ways to Define Streaming Tables:**

1. **CREATE STREAMING TABLE with AS SELECT (MOST COMMON)**
   - Defines schema and query in one statement
   - Schema can be inferred from query or explicitly defined
   - **This automatically creates a continuous streaming pipeline - no separate flow needed**

   ```sql
   CREATE STREAMING TABLE events_stream
   AS SELECT * FROM STREAM(source_catalog.schema.events);
   ```

2. **CREATE STREAMING TABLE without AS SELECT**
   - Creates an empty streaming table target
   - Required for multi-source append patterns
   - Schema definition is optional
   - **Requires separate `CREATE FLOW` statements to populate the table**

   ```sql
   CREATE STREAMING TABLE users (
     user_id INT,
     name STRING,
     updated_at TIMESTAMP
   );
   ```

**CRITICAL: WHEN TO USE WHICH:**

Use **CREATE STREAMING TABLE with AS SELECT** when:

- Reading and transforming streaming data from a single source
- Creating streaming tables from Delta tables, Auto Loader sources, etc.
- This is the standard pattern for most streaming use cases
- **DO NOT add a separate `CREATE FLOW` - the AS SELECT clause already handles continuous processing**

Use **CREATE STREAMING TABLE without AS SELECT + CREATE FLOW** when:

- Creating a target table for multiple `INSERT INTO` flows from different sources
- Need to explicitly define table schema before data flows in
- Using `AUTO CDC INTO` for CDC. See the Auto CDC reference ([auto-cdc-sql.md](auto-cdc-sql.md)) for details.
- **In this case, you MUST create separate flows - the table definition alone does not process data**

**NEVER:**

- Create both `CREATE STREAMING TABLE ... AS SELECT` AND `CREATE FLOW` for the same source - this is redundant and incorrect
- The AS SELECT clause already provides continuous streaming; adding a flow duplicates the work

**Common Patterns:**

**Pattern 1: Simple streaming transformation**

```sql
-- Bronze layer: ingest raw data with Auto Loader
CREATE STREAMING TABLE bronze
AS SELECT * FROM STREAM(read_files(
  '/path/to/data',
  format => 'json'
));

-- Silver layer: filter and clean data
CREATE STREAMING TABLE silver
AS SELECT *
FROM STREAM(bronze)
WHERE id IS NOT NULL;
```

**Pattern 2: Multi-source aggregation with flows**

```sql
-- Create target table for multiple sources. Schema is optional.
CREATE STREAMING TABLE all_events (
  event_id STRING,
  event_type STRING,
  event_timestamp TIMESTAMP,
  source STRING
);

-- Flow from mobile source
CREATE FLOW mobile_flow
AS INSERT INTO all_events BY NAME
SELECT event_id, event_type, event_timestamp, 'mobile' as source
FROM STREAM(mobile.events);

-- Flow from web source
CREATE FLOW web_flow
AS INSERT INTO all_events BY NAME
SELECT event_id, event_type, event_timestamp, 'web' as source
FROM STREAM(web.events);
```

**Pattern 3: Row filters for data security**

```sql
-- Assumes filter_by_dept is a SQL UDF defined in Unity Catalog that returns BOOLEAN

CREATE STREAMING TABLE employees (
  emp_id INT,
  emp_name STRING,
  dept STRING,
  salary DECIMAL(10,2)
)
WITH ROW FILTER my_catalog.my_schema.filter_by_dept ON (dept)
AS SELECT * FROM STREAM(source.employees);
```

**Pattern 4: Partitioning and clustering**

```sql
-- Using partitioning (traditional approach)
CREATE STREAMING TABLE orders_partitioned
PARTITIONED BY (order_date)
AS SELECT * FROM STREAM(source.orders);

-- Using liquid clustering (recommended)
CREATE STREAMING TABLE orders_clustered
CLUSTER BY (order_date, customer_id)
AS SELECT * FROM STREAM(source.orders);
```

**Pattern 5: Sensitive data masking**

```sql
CREATE STREAMING TABLE customers (
  customer_id INT,
  name STRING,
  email STRING,
  ssn STRING MASK catalog.schema.ssn_mask USING COLUMNS (customer_id)
)
AS SELECT * FROM STREAM(source.customers);
```

**Pattern 6: Private streaming table (pipeline-internal staging)**

```sql
CREATE OR REFRESH PRIVATE STREAMING TABLE staging_events
AS SELECT *
FROM STREAM(raw_events)
WHERE event_type IS NOT NULL;
```

Use `PRIVATE` for internal staging datasets that should not be published to the catalog. Private tables are only accessible within the pipeline.

**Pattern 7: One-time backfill with flow**

```sql
CREATE STREAMING TABLE transactions (
  transaction_id STRING,
  customer_id STRING,
  amount DECIMAL(10,2),
  transaction_date TIMESTAMP
);

-- Continuous streaming flow for new data
CREATE FLOW live_stream
AS INSERT INTO transactions
SELECT * FROM STREAM(source.transactions);

-- One-time backfill flow for historical data (uses batch read without STREAM)
CREATE FLOW historical_backfill
AS INSERT INTO ONCE transactions
SELECT * FROM archive.historical_transactions;
```

**Pattern 8: Stream-static join (enrich streaming data with dimension table)**

```sql
CREATE OR REFRESH STREAMING TABLE enriched_transactions
AS SELECT t.*, c.name, c.email
FROM STREAM(transactions) t
JOIN customers c ON t.customer_id = c.id;
```

The dimension table (`customers`) is read as a static snapshot at stream start, while the streaming source (`transactions`) is read incrementally. This is the standard pattern for enriching streaming data with lookup/dimension tables.

**Pattern 9: Reading from upstream ST with updates/deletes (skipChangeCommits)**

```sql
CREATE OR REFRESH STREAMING TABLE downstream
AS SELECT * FROM STREAM read_stream("upstream_with_deletes", skipChangeCommits => true)
```

Use `skipChangeCommits` when reading from a streaming table that has updates/deletes (e.g., GDPR compliance, Auto CDC targets). Without this flag, change commits cause errors.

**WARNING: Do NOT use `FROM STREAM` to read from a materialized view.** Materialized views always produce overwrite commits on every refresh, making them invalid streaming sources. `SKIPCHANGECOMMITS` will not help — the downstream must be converted to a materialized view (`CREATE MATERIALIZED VIEW` without `STREAM`) instead. Attempting this causes the error `DELTA_SOURCE_TABLE_IGNORE_CHANGES`.

---

## Advanced Streaming Patterns

**Every streaming aggregation needs a `WATERMARK` clause.** Without one, the flow does not fail: the pipeline runs it in **Complete** output mode, which rewrites the whole table on every update and never evicts state (`DESCRIBE HISTORY` shows `outputMode: Complete`; with a `WATERMARK` it shows `Append`). Syntax: `FROM STREAM(t) WATERMARK <time column> DELAY OF INTERVAL <n> <unit> [alias]`, placed immediately after `STREAM(...)` and before the alias.

### Deduplication

Deduplicate at the bronze → silver transition: bronze accepts duplicates, silver is clean.

**With time window (bounded state):**

```sql
CREATE OR REFRESH STREAMING TABLE silver_events_dedup AS
SELECT event_id, user_id, event_type,
  MIN(event_timestamp) AS event_timestamp,
  MIN(_ingested_at) AS first_seen_at
FROM STREAM(bronze_events) WATERMARK event_timestamp DELAY OF INTERVAL 10 MINUTES
GROUP BY event_id, user_id, event_type, window(event_timestamp, '1 hour');
```

Group by the `window(...)`, not also by the raw `event_timestamp`: grouping by both fails with `More than one event time columns are available`. For a composite key, add the key columns to the `GROUP BY`.

For dedup by key regardless of window (retries that arrive within a bounded delay), use `dropDuplicatesWithinWatermark` in a Python flow (see [streaming-table-python.md](streaming-table-python.md#deduplication)). Do not use `ROW_NUMBER() OVER (PARTITION BY ...)` on `STREAM(...)`: streaming rejects non-time window functions with `NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING`.

For dedup with sequenced updates (most recent wins, deletes, late corrections), use Auto CDC with SCD Type 1 instead (see [auto-cdc-sql.md](auto-cdc-sql.md)). Manual dedup is for append-only streams without semantic updates.

### Windowed Aggregations

**Tumbling windows (non-overlapping fixed-size):**

```sql
CREATE OR REFRESH STREAMING TABLE silver_sensor_5min AS
SELECT
  sensor_id,
  window(event_timestamp, '5 minutes') AS time_window,
  AVG(temperature) AS avg_temperature,
  MIN(temperature) AS min_temperature,
  MAX(temperature) AS max_temperature,
  COUNT(*) AS event_count
FROM STREAM(bronze_sensor_events) WATERMARK event_timestamp DELAY OF INTERVAL 2 MINUTES
GROUP BY sensor_id, window(event_timestamp, '5 minutes');
```

With a `WATERMARK`, each window is written once, after the watermark passes its end (final values; latency = window + delay). For several granularities, define one streaming table per window size.

**Extracting window bounds:**

```sql
CREATE OR REFRESH STREAMING TABLE gold_hourly_metrics AS
SELECT
  sensor_id,
  window(event_timestamp, '1 hour').start AS window_start,
  window(event_timestamp, '1 hour').end AS window_end,
  AVG(value) AS avg_value
FROM STREAM(silver_sensor_data) WATERMARK event_timestamp DELAY OF INTERVAL 10 MINUTES
GROUP BY sensor_id, window(event_timestamp, '1 hour');
```

**Session windows (group by inactivity gap):**

```sql
CREATE OR REFRESH STREAMING TABLE silver_user_sessions AS
SELECT
  user_id,
  session_window(event_timestamp, '30 minutes') AS session,
  MIN(event_timestamp) AS session_start,
  MAX(event_timestamp) AS session_end,
  COUNT(*) AS event_count,
  COLLECT_LIST(event_type) AS event_sequence
FROM STREAM(bronze_user_events) WATERMARK event_timestamp DELAY OF INTERVAL 10 MINUTES
GROUP BY user_id, session_window(event_timestamp, '30 minutes');
```

Each session is written once it closes. Update output mode is rejected for session windows, and Complete mode runs but rewrites every session on each update. For a maximum session length or custom session output, use `transformWithState` in Python (see [streaming-table-python.md](streaming-table-python.md#custom-stateful-logic-transformwithstate)).

### Late-Arriving Data

Aggregate on event time (the timestamp in the row), not processing time (`_ingested_at`). Keep `_ingested_at` as a debugging field.

```sql
CREATE OR REFRESH STREAMING TABLE gold_daily_orders AS
SELECT window(order_timestamp, '1 day').start AS order_date,  -- TIMESTAMP at 00:00 UTC, not a DATE
       COUNT(*)    AS order_count,
       SUM(amount) AS total_amount
FROM STREAM(silver_orders) WATERMARK order_timestamp DELAY OF INTERVAL 1 HOUR
GROUP BY window(order_timestamp, '1 day');
```

`window(..., '1 day')` buckets are UTC days: each starts at 00:00 UTC, and `.start` is a `TIMESTAMP`. A `CAST(... AS DATE)` bucket uses the session time zone and gives a `DATE`. With the session time zone `America/Los_Angeles`, an order at 10:00 local time on Jan 1 falls in the window that starts at 16:00 local time on Dec 31. For days in a fixed UTC offset, add a `startTime` offset: `window(order_timestamp, '1 day', '1 day', '8 hours')` for UTC-8, which is `America/Los_Angeles` in winter only. `startTime` and one-day windows do not adjust for daylight saving, so this does not give year-round local calendar days in a zone that observes it. `startTime` is the negative of the UTC offset, so for a zone east of UTC use a negative value or its complement: for UTC+5:30, `'-5 hours -30 minutes'` (or `'18 hours 30 minutes'`). `'5 hours 30 minutes'` would start each day at 11:00 local time, with no error. Use the same four-argument `window(...)` in `SELECT` and in `GROUP BY`.

Choose a delay that covers how late rows arrive: rows later than the delay are dropped, and each day's row lands once the day closes plus the delay. A `CAST(... AS DATE)` bucket instead of `window(...)` runs in Complete mode and keeps every day in state, even with a `WATERMARK`.

### Running Totals

A bare `GROUP BY customer_id` on a stream runs in Complete mode and keeps every customer in state forever. Scope the total to a watermarked time window:

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

In append mode each day's row lands once, after the day closes plus the delay. `day` is the UTC day start as a `TIMESTAMP`; for days in a fixed UTC offset, see the `startTime` offset under [Late-Arriving Data](#late-arriving-data), which does not adjust for daylight saving. For lifetime totals, roll the daily table up in a materialized view. For a live per-key total in a triggered pipeline, use `transformWithState` in Python with `timeMode="EventTime"` and a timer that clears idle keys. State TTL needs `timeMode="ProcessingTime"`, which never lets a triggered update finish.

### Stream-to-Stream Joins

Join two streaming sources with a watermark on **both** inputs and a time-range bound:

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders_with_payments AS
SELECT
  o.order_id, o.customer_id, o.order_timestamp, o.amount AS order_amount,
  p.payment_id, p.payment_timestamp, p.amount AS payment_amount
FROM STREAM(bronze_orders) WATERMARK order_timestamp DELAY OF INTERVAL 1 HOUR o
INNER JOIN STREAM(bronze_payments) WATERMARK payment_timestamp DELAY OF INTERVAL 1 HOUR p
  ON o.order_id = p.order_id
  AND p.payment_timestamp BETWEEN o.order_timestamp AND o.order_timestamp + INTERVAL 1 HOUR;
```

**Why watermarks and time bounds matter:** The watermark tells the engine how late events can arrive so it can evict join state; the time-range condition bounds the window matches are searched in. Without both, state grows indefinitely as the system waits for potential matches. Watermarks are **required** for outer joins; an inner join without them still runs but keeps every row. The `DELAY OF INTERVAL` must be positive and under 1 month.

### Rescued-Data Quarantine

Route malformed records to a quarantine table so the clean stream stays clean and nothing is dropped silently. Auto Loader puts fields it can't parse in the `_rescued_data` column.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events AS
SELECT *, current_timestamp() AS _ingested_at
FROM STREAM read_files('/Volumes/cat/sch/raw/events/', format => 'json');

CREATE OR REFRESH STREAMING TABLE bronze_quarantine AS
SELECT * FROM STREAM(bronze_events) WHERE _rescued_data IS NOT NULL;

CREATE OR REFRESH STREAMING TABLE silver_clean AS
SELECT * FROM STREAM(bronze_events) WHERE _rescued_data IS NULL;
```

Use quarantine for schema and parse problems (schema drift, late optional fields); use expectations (`CONSTRAINT ... ON VIOLATION DROP ROW`, see [expectations-sql.md](expectations-sql.md)) for value checks such as `amount > 0`. Alert on `bronze_quarantine` growth.

### Windowed Statistics for Anomaly Detection

Row-based window functions (`OVER (... ROWS BETWEEN 100 PRECEDING ...)`) fail on streams with `NON_TIME_WINDOW_NOT_SUPPORTED_IN_STREAMING`. Compute statistics per time window instead, and flag outliers downstream against the previous window (a materialized view or a stream-static join):

```sql
CREATE OR REFRESH STREAMING TABLE silver_sensor_window_stats AS
SELECT sensor_id,
       window(event_timestamp, '10 minutes').start AS window_start,
       AVG(temperature)    AS avg_temperature,
       STDDEV(temperature) AS stddev_temperature
FROM STREAM(bronze_sensor_events) WATERMARK event_timestamp DELAY OF INTERVAL 2 MINUTES
GROUP BY sensor_id, window(event_timestamp, '10 minutes');
```

For a true per-row rolling buffer per sensor, keep a bounded `ListState` in `transformWithState` (Python).

### Monitoring Lag

Alert on ingestion delays from Kafka, Kinesis, or Auto Loader by comparing the latest event time with the current time in a materialized view (a batch read), which recomputes the lag on each refresh:

```sql
CREATE OR REFRESH MATERIALIZED VIEW monitoring_lag AS
SELECT MAX(kafka_timestamp) AS max_event_timestamp,
       unix_timestamp(current_timestamp()) - unix_timestamp(MAX(kafka_timestamp)) AS lag_seconds
FROM bronze_kafka_events;
```

### Streaming Best Practices

- **Use event timestamps** for business logic, not processing time (`_ingested_at`)
- **Add watermarks** to every streaming aggregation and stream-to-stream join (the `WATERMARK ... DELAY OF INTERVAL ...` clause) to bound state and enable cleanup
- **Window size guidelines:** Real-time monitoring: 1-5 min, operational dashboards: 15-60 min, analytical reports: 1-24 hr. Pick the smallest window that meets the freshness need; for sub-second operational latency, see [real-time-mode-sdp.md](real-time-mode-sdp.md)

### Common Issues

| Issue | Cause / Fix |
| ----- | ----------- |
| Table rewritten on every update, state keeps growing | Streaming aggregation without a `WATERMARK` runs in Complete mode. Add one and group by `window(...)`. |
| Duplicate events in output | Add dedup by unique key, or switch to Auto CDC SCD Type 1. |
| Missing late-arriving events | Delay too short, or the aggregation uses processing time instead of event time. |
| Stream-to-stream join empty | Missing or too narrow time bound on the join condition. |
| `bronze_quarantine` unexpectedly empty | The source is not Auto Loader, or the rescued-data column was renamed or disabled. |

---

**KEY RULES:**

- Streaming tables require `STREAM()` keyword for streaming reads
- Never use batch reads (`SELECT * FROM table` without `STREAM()`) in streaming table definitions
- Most `ALTER TABLE` commands are not supported - use `CREATE OR REFRESH` or `ALTER STREAMING TABLE` instead. The exception is column-level schema evolution (add/drop/rename a column, widen a type), which uses `ALTER TABLE` - see [streaming-table-schema-evolution](streaming-table-schema-evolution.md)
- Supports generated columns: `<col_name> <type> GENERATED ALWAYS AS (<expression>)` — see [Delta generated columns](https://docs.databricks.com/aws/en/tables/features/generated-columns) for syntax.
- Supports default columns: `<col_name> <type> DEFAULT <default_expression>` (applied on INSERT/UPDATE/MERGE when the column is not supplied) — see the [CREATE TABLE reference](https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-ddl-create-table-using) for DEFAULT syntax.
- Row filters force full refresh of downstream materialized views
- Only table owners can refresh streaming tables
- Table renaming and ownership changes prohibited
- `CLUSTER BY` is recommended over `PARTITIONED BY` for most use cases
- For batch processing, use materialized views instead (see the materialized view reference ([materialized-view-sql.md](materialized-view-sql.md)))
- Use `skipChangeCommits` when reading from STs that have updates/deletes
