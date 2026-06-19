# SQL Basics

## Core statements

- `CREATE OR REFRESH STREAMING TABLE` — continuous incremental processing. See [streaming-table-sql.md](streaming-table-sql.md).
- `CREATE OR REFRESH MATERIALIZED VIEW` — batch table. See [materialized-view-sql.md](materialized-view-sql.md).
- `CREATE TEMPORARY VIEW` — pipeline-scoped view. See [temporary-view-sql.md](temporary-view-sql.md).
- `CREATE VIEW` — UC-published view. See [view-sql.md](view-sql.md).
- `AUTO CDC INTO` (inside `CREATE FLOW`) — CDC. See [auto-cdc-sql.md](auto-cdc-sql.md).
- `CREATE FLOW ... AS INSERT INTO [ONCE] target_table` — append / backfill flows. See [streaming-table-sql.md](streaming-table-sql.md).

## Source functions (streaming)

Used as `FROM STREAM read_*(...)` inside a streaming table:

- `read_files(path, format => '...')` — Auto Loader. See [auto-loader-sql.md](auto-loader-sql.md).
- `read_kafka(bootstrapServers => '...', subscribe => '...')` — Kafka. Also covers Event Hubs via Kafka protocol. See [kafka.md](kafka.md).
- `read_kinesis(streamName => '...', region => '...')` — AWS Kinesis.
- `read_pubsub(subscriptionId => '...', topicId => '...')` — GCP Pub/Sub.
- `read_pulsar(serviceUrl => '...', topics => '...')` — Apache Pulsar.

## Critical rules

- ✅ Prefer `CREATE OR REFRESH` over bare `CREATE` for SDP datasets (idiomatic convention; both parse).
- ✅ Use `FROM STREAM(table)` (function form with parens) for table sources in streaming tables; `FROM STREAM read_files(...)` (no extra parens) for function sources.
- ❌ Never use the `LIVE.` prefix when reading sibling datasets — deprecated, errors in modern pipelines.
- ❌ Never `CREATE LIVE TABLE` / `CREATE STREAMING LIVE TABLE` / `CREATE TEMPORARY LIVE VIEW` — all legacy. (Exception: `CREATE LIVE VIEW` is retained for the edge case of expectations on a temp view — see [temporary-view-sql.md#using-expectations-with-temporary-views](temporary-view-sql.md#using-expectations-with-temporary-views).)
- ❌ Never `CREATE OR REPLACE STREAMING TABLE` — that's standard SQL, not SDP. Use `CREATE OR REFRESH`.
- ❌ `PIVOT` clause is unsupported.

## Streaming vs batch

`STREAM(...)` opts in to streaming semantics; omit it for batch reads. Streaming tables require streaming reads. Materialized views require batch reads.

## `GROUP BY ALL`

Prefer `SELECT category, region, SUM(sales) FROM t GROUP BY ALL` over enumerating the grouping columns — less drift when columns are added/removed, no risk of forgetting a column in the `GROUP BY` clause.

## Configuration

- Reference pipeline config values with `${var_name}` interpolation in SQL files.
- Use `SET key = value;` for Spark-level config.

## Python UDFs in SQL

UDFs must be declared in a Python file in the pipeline (e.g. `@dp.temporary_view()` is not enough — you need a top-level `spark.udf.register(...)` or a UC SQL UDF). The SQL file can then call them by name.

## `skipChangeCommits`

```sql
CREATE OR REFRESH STREAMING TABLE downstream
AS SELECT * FROM STREAM read_stream("upstream_table", skipChangeCommits => true);
```

Use when reading from a streaming table that has updates/deletes (GDPR purges, Auto CDC targets). Without it, change commits fail.
