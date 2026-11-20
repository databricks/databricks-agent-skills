#### Core SQL Statements

- `CREATE MATERIALIZED VIEW` - Batch processing with full refresh or incremental computation. See [materialized-view-sql.md](materialized-view-sql.md).
- `CREATE STREAMING TABLE` - Continuous incremental processing. See [streaming-table-sql.md](streaming-table-sql.md).
- `CREATE TEMPORARY VIEW` - Non-materialized views (pipeline lifetime only). See [temporary-view-sql.md](temporary-view-sql.md).
- `CREATE VIEW` - Non-materialized catalog views (Unity Catalog only). See [view-sql.md](view-sql.md).
- `AUTO CDC INTO` - Change data capture flows. See [auto-cdc-sql.md](auto-cdc-sql.md); for complete periodic snapshots (DBR 18.3+) see [auto-cdc-from-snapshot.md](auto-cdc-from-snapshot.md).
- `CREATE FLOW` - Define flows or backfills for streaming tables (`INSERT INTO ONCE` for a one-time backfill). See [streaming-table-sql.md](streaming-table-sql.md).

#### Message Bus Ingestion Functions

- `read_kafka(bootstrapServers => '...', subscribe => '...')` - Apache Kafka. See [kafka-streaming-sql.md](kafka-streaming-sql.md).
- `read_kinesis(streamName => '...', region => '...')` - AWS Kinesis. See [kinesis-streaming-sql.md](kinesis-streaming-sql.md).
- `read_pubsub(subscriptionId => '...', topicId => '...')` - Google Cloud Pub/Sub
- `read_pulsar(serviceUrl => '...', topics => '...')` - Apache Pulsar
- Event Hubs: Use `read_kafka()` with Kafka-compatible Event Hubs config

#### Critical Rules

- ✅ Prefer `CREATE OR REFRESH` syntax for defining datasets (bare `CREATE` also works, but `OR REFRESH` is the idiomatic convention)
- ✅ Use `STREAM` keyword when reading sources for streaming tables
- ✅ Use `read_files()` function for Auto Loader (cloud storage ingestion). See [auto-loader-sql.md](auto-loader-sql.md).
- ✅ In streaming tables, read tables with `FROM STREAM(table)` and function sources with `FROM STREAM read_files(...)` (`FROM STREAM(read_files(...))` also works).
- ✅ Look up documentation for statement parameters when unsure
- ❌ NEVER use `LIVE.` prefix when reading other datasets (deprecated)
- ❌ NEVER use `CREATE LIVE TABLE` or `CREATE LIVE VIEW` (deprecated - use `CREATE STREAMING TABLE`, `CREATE MATERIALIZED VIEW`, or `CREATE TEMPORARY VIEW` instead). Exception: `CREATE LIVE VIEW` is still the way to add expectations to a temporary view; see [temporary-view-sql.md](temporary-view-sql.md)
  - The same applies to `CREATE STREAMING LIVE TABLE` and `CREATE TEMPORARY LIVE VIEW`.
- ❌ NEVER use `CREATE OR REPLACE STREAMING TABLE` (standard SQL, not SDP) - use `CREATE OR REFRESH`
- ❌ Do not use `PIVOT` clause (unsupported)

#### SQL-Specific Considerations

**Streaming vs. Batch Semantics:**

- Omit `STREAM` keyword for materialized views (batch processing)
- Use `STREAM` keyword for streaming tables to enable streaming semantics
- Streaming tables require streaming reads; materialized views require batch reads

**GROUP BY Best Practices:**

- Prefer `GROUP BY ALL` over explicitly listing individual columns unless the user specifically requests explicit grouping
- Benefits: more maintainable when adding/removing columns, less verbose, reduces risk of missing columns in the GROUP BY clause
- Example: `SELECT category, region, SUM(sales) FROM table GROUP BY ALL` instead of `GROUP BY category, region`

**Python UDFs:**

- You can use Python user-defined functions (UDFs) in SQL queries
- UDFs must be defined in Python files before calling them in SQL source files
- Register them at the top level of a pipeline Python file with `spark.udf.register(...)` (defining a dataset such as `@dp.temporary_view()` does not register a UDF), or use a Unity Catalog SQL UDF; SQL files then call them by name

**Configuration:**

- For values that vary across updates, use pipeline parameters (`:name`); read [parameters-sql](parameters-sql.md).
- `SET key = value;` sets Spark-level config. `${var_name}` is legacy interpolation of the pipeline's `configuration` values; keep it only in existing code.

#### skipChangeCommits

When a downstream streaming table reads from an upstream streaming table that has updates or deletes, use `skipChangeCommits` to ignore change commits. Without it, the change commits cause the downstream stream to fail:

```sql
CREATE OR REFRESH STREAMING TABLE downstream
AS SELECT * FROM STREAM read_stream("upstream_table", skipChangeCommits => true)
```
