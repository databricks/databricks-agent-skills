---
name: databricks-pipelines
description: Develop Lakeflow Spark Declarative Pipelines (formerly Delta Live Tables) on Databricks. Use when building batch or streaming data pipelines with Python or SQL, including Auto CDC from event streams or periodic complete snapshots. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.3.0"
parent: databricks-core
---

# Lakeflow Spark Declarative Pipelines Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, profile selection, and data discovery commands.

SDP, LDP, Lakeflow Declarative Pipelines, and DLT (former name) all refer to the same product.

## Decision Tree

Use this tree to choose the dataset type first, then layer on applicable features. Multiple features can apply to the same dataset — e.g., a Streaming Table can use Auto Loader for ingestion, Append Flows for fan-in, and Expectations for data quality.

```
User request → What kind of output?
├── Intermediate/reusable logic (not persisted) → Temporary View (default)
│   ├── Preprocessing/filtering before Auto CDC → Temporary View feeding CDC flow
│   ├── Shared intermediate streaming logic reused by multiple downstream tables
│   ├── Pipeline-private helper logic (not published to catalog)
│   ├── Expensive intermediate that is reused across refreshes → Private ST/MV (materialized but pipeline-scoped)
│   └── Published to UC for external queries → Persistent View (SQL only)
├── Persisted dataset
│   ├── Source is a periodic complete snapshot that must be diffed by key → Streaming Table + Auto CDC FROM SNAPSHOT
│   ├── Source is streaming/incremental/continuously growing → Streaming Table
│   │   ├── File ingestion (cloud storage, Volumes) → Auto Loader
│   │   ├── Message bus (Kafka, Kinesis, Pub/Sub, Pulsar, Event Hubs) → streaming source read
│   │   ├── Existing streaming/Delta table → streaming read from table
│   │   ├── CDC / upserts / track changes / keep latest per key / SCD Type 1 or 2 → Auto CDC (only when this pipeline owns the target; merge/upsert into an existing/external table → ForEachBatch Sink)
│   │   ├── Multiple sources into one table → Append Flows (NOT union)
│   │   ├── Historical backfill + live stream → one-time Append Flow + regular flow
│   │   └── Windowed aggregation with watermark → stateful streaming
│   └── Source is batch/historical/full scan → Materialized View
│       ├── Aggregation/join across full dataset (GROUP BY, SUM, COUNT, etc.)
│       ├── Gold layer aggregation from streaming table → MV with batch read (spark.read / no STREAM)
│       ├── JDBC/Federation/external batch sources
│       └── Small static file load (reference data, no streaming read)
├── Output to a target the pipeline does NOT own (external / pre-existing / managed elsewhere) → Sink (Python only, even if the user asked for SQL)
│   ├── External or pre-existing Delta table → Sink with format="delta"
│   ├── Kafka / Event Hubs → Sink with format="kafka" + @dp.append_flow(target="sink_name")
│   ├── Custom destination not natively supported → Sink with custom format
│   ├── Custom merge/upsert into an existing/external table → ForEachBatch Sink, NOT Auto CDC
│   └── Multiple destinations per batch → ForEachBatch Sink
└── Data quality constraints → Expectations (on any dataset type)
```

## Common Traps

- **Changing dataset type (ST↔MV):** Not possible in place, and full refresh does not fix it. Define the dataset under a NEW name and repoint ALL downstream references. Dropping the existing table is a manual workaround; offer it only as a follow-up.
- **SCD Type 2 queries:** Use validity columns `__START_AT` / `__END_AT`, not invented names. Current rows: `__END_AT IS NULL`; point-in-time: `__START_AT <= t AND (__END_AT > t OR __END_AT IS NULL)`. Read [scd-2-querying](references/scd-2-querying.md).
- **UNRESOLVED_COLUMN / column not found:** Verify upstream columns. For Auto Loader, check that `schemaHints` match the actual file schema.
- **"Create a table" without a type:** Ask whether the source is streaming or batch. Streaming → Streaming Table; batch → Materialized View. Mismatched pairs fail validation.
- **Aggregating a streaming source:** Use a Materialized View with a batch read (no `STREAM`). Streaming tables are append-only and don't recompute aggregates when source rows change.
- **`Cannot create streaming table from batch query`:** The streaming table reads in batch. Use `FROM STREAM read_files(...)` / `FROM STREAM(table)`.
- **Python-only features** (sinks, ForEachBatch sinks, custom data sources, Real-Time Mode): When the user works in SQL, say so and suggest Python for that part.
- **`databricks fs` on Volumes:** The CLI needs the `dbfs:` prefix, e.g. `databricks fs ls dbfs:/Volumes/<catalog>/<schema>/<volume>/<path>`.
- **Recommend one approach.** Omit anti-patterns and inferior alternatives; mention alternatives only for viable trade-offs.

## Publishing Modes

Pipelines publish to the default catalog/schema in their settings.

- Use dataset-only names for pipeline reads/definitions unless existing code or the user requests qualification.
- `catalog.schema.table` publishes a **pipeline-owned** dataset elsewhere; no sink needed. **External, pre-existing, or separately managed targets require a Python sink**, even if the user requested SQL.
- `USE CATALOG` / `USE SCHEMA` changes the defaults for subsequent definitions in the same SQL file.
- `LIVE` is deprecated and ignored in default publishing mode.

## API Reference

**MANDATORY:** Before implementing, editing, or suggesting feature code, read its linked reference and these required companions:

- **Auto Loader, Auto CDC, sinks** → also read the streaming-table reference: Auto Loader/CDC target streaming tables; sinks use streaming append flows.
- **Auto Loader** → also read the format options: [CSV](references/options-csv.md), [JSON](references/options-json.md), [Avro](references/options-avro.md), [Parquet](references/options-parquet.md), [XML](references/options-xml.md), [Text](references/options-text.md), [ORC](references/options-orc.md).
- **Expectations** → also read the target dataset's definition reference for constraint placement.

| Feature | Python | SQL |
|---|---|---|
| Streaming tables; explicit targets; append and one-time backfill flows; skip upstream change commits | [Python](references/streaming-table-python.md) | [SQL](references/streaming-table-sql.md) |
| Materialized views; liquid clustering (prefer auto), partitioning, table properties, explicit schemas, generated columns, row filters and column masks (Public Preview), private datasets | [Python](references/materialized-view-python.md) | [SQL](references/materialized-view-sql.md) |
| Temporary views | [Python](references/temporary-view-python.md) | [SQL](references/temporary-view-sql.md) |
| Persistent UC views | Unsupported | [SQL](references/view-sql.md) |
| Delta/Kafka/Event Hubs/custom sinks | [Python](references/sink-python.md) | Unsupported |
| ForEachBatch sinks | [Python](references/foreach-batch-sink-python.md) | Unsupported |
| Auto CDC from a stream or periodic snapshots | [Python](references/auto-cdc-python.md) | [SQL](references/auto-cdc-sql.md) |
| Expectations: warn, drop, fail; individual or multiple constraints | [Python](references/expectations-python.md) | [SQL](references/expectations-sql.md) |
| Auto Loader | [Python](references/auto-loader-python.md) | [SQL](references/auto-loader-sql.md) |

Topics covering both languages:

- [Kafka / Event Hubs sources](references/kafka.md): authentication and payload deserialization.
- [Streaming patterns](references/streaming-patterns.md): dedup, windowed aggregations, late data, rescued-data quarantine, lag monitoring.
- [SCD Type 2 querying](references/scd-2-querying.md): current state, point-in-time, joining facts with historical dimensions.
- [Performance](references/performance.md): liquid clustering key selection, streaming state, joins.
- [Real-Time Mode](references/real-time-mode.md) (Python only): only for explicitly requested operational sub-second latency; requires always-on continuous compute.

### Reads and compatibility

- Pipeline batch reads: `spark.read.table("name")` / `SELECT ... FROM name`; streaming reads: `spark.readStream.table("name")` / `SELECT ... FROM STREAM(name)`.
- Kinesis, Pub/Sub, and Pulsar sources: `spark.readStream.format("kinesis" | "pubsub" | "pulsar")`; SQL uses `STREAM read_kinesis(...)`, `STREAM read_pubsub(...)`, or `STREAM read_pulsar(...)`.
- JDBC/Federation are batch sources; Python uses `spark.read.format("postgresql")` etc. and SQL references the federation catalog.
- Static files: `spark.read.format(...).load(...)` / `read_files(...)` without `STREAM`.
- Custom data sources are Python-only: `spark.read[Stream].format("custom")`.
- Use `from pyspark import pipelines as dp` and `spark.read[Stream].table` for Python.

### Legacy DLT Syntax — always migrate

If you see any of the following in user code, it is the legacy DLT syntax — **always migrate to the modern form**, do not extend it. Read [references/dlt-migration.md](references/dlt-migration.md) before suggesting changes so the conversion is correct (especially around `apply_changes` → `create_auto_cdc_flow` semantics and `partition_cols` → `cluster_by`).

| If you see…                                                                 | …it's DLT. Migrate to                                                |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `import dlt`                                                                | `from pyspark import pipelines as dp`                                |
| `@dlt.table(...)`, `@dlt.append_flow(...)`, `@dlt.expect*`                  | Same decorator name on `dp.*` (e.g. `@dp.table`, `@dp.expect_or_drop`). |
| `@dlt.view(...)` (or `@dp.view(...)` if present in older code)              | `@dp.temporary_view(...)` — the modern API has no `view` decorator, only `temporary_view`. |
| `dlt.read("name")` / `dlt.read_stream("name")`                              | `spark.read.table("name")` / `spark.readStream.table("name")`        |
| `dp.read(...)` / `dp.read_stream(...)`                                      | Also legacy — use `spark.read.table(...)` / `spark.readStream.table(...)`. |
| `dlt.apply_changes(...)` / `dp.apply_changes(...)`                          | `dp.create_auto_cdc_flow(...)`. `sequence_by` accepts a column name (string) or `col(...)`; `stored_as_scd_type` is integer `2` for Type 2 or string `"1"` for Type 1. |
| `dlt.apply_changes_from_snapshot(...)`                                      | `dp.create_auto_cdc_from_snapshot_flow(...)`                         |
| `dlt.create_streaming_table(...)`                                           | `dp.create_streaming_table(...)`                                     |
| `LIVE.<name>` prefix in SQL                                                 | Bare name (`SELECT FROM name` for batch, `SELECT FROM STREAM(name)` for streaming). `LIVE.` will error in modern pipelines. |
| `CREATE LIVE TABLE` / `CREATE STREAMING LIVE TABLE` | `CREATE OR REFRESH MATERIALIZED VIEW` / `CREATE OR REFRESH STREAMING TABLE`. |
| `CREATE TEMPORARY LIVE VIEW` (a.k.a. `CREATE LIVE VIEW`) | `CREATE TEMPORARY VIEW`. **Exception**: `CREATE TEMPORARY VIEW` does NOT support `CONSTRAINT` clauses for expectations — for the rare case where you need expectations on a temp view, `CREATE LIVE VIEW` is retained. See [temporary-view-sql.md](references/temporary-view-sql.md#using-expectations-with-temporary-views) and [expectations-sql.md](references/expectations-sql.md). |
| `APPLY CHANGES INTO ... FROM STREAM ...` (SQL)                              | `AUTO CDC INTO ... FROM STREAM ...`                                  |
| `partition_cols=[...]` / `PARTITIONED BY (...)` + `ZORDER`                  | `cluster_by=[...]` / `CLUSTER BY (...)` (Liquid Clustering).         |
| `input_file_name()`                                                         | `_metadata.file_path` (SQL) / `F.col("_metadata.file_path")` (Python). |
| `target=...` parameter on `create_streaming_table` / pipeline config        | `schema=...`                                                         |

### Language-specific guides

- [Python basics](references/python-basics.md) - Python decorators, functions, and critical rules
- [SQL basics](references/sql-basics.md) - SQL statements and critical rules

## Project Setup

- **Language:** Keep an existing pipeline's language. For new pipelines default to SQL; use Python when the user asks for it or needs UDFs, ML inference, or Python-only features. If the request is ambiguous, ask.
- **Workflow:** Pick before scaffolding.
  - **A: Standalone project (DAB)**, no existing `databricks.yml` → [1-project-initialization-with-dab](references/1-project-initialization-with-dab.md). Default for production-bound work.
  - **B: Pipeline in an existing bundle** → add `resources/<name>.pipeline.yml`; see Workflow B in the same reference.
  - **C: Rapid CLI iteration (no bundle)** for prototypes and demos → [2-rapid-iteration-with-cli](references/2-rapid-iteration-with-cli.md).
- **Structure:** Medallion (Bronze → Silver → Gold) with just a few tables unless the user says otherwise. One dataset per file, named after the dataset, in `src/` or `transformations/`. In Gold, keep the dimensions consumers filter by (e.g., every dashboard filter).
- **Settings:** For create/update JSON, compute, channels, and multi-schema setups, read [pipeline-configuration](references/pipeline-configuration.md).

## Running a Pipeline

- **DAB (A/B):** Code changes take effect only after `databricks bundle deploy`; deploy before any run, dry run, or selective refresh. Sequence: `databricks bundle validate`, `databricks bundle deploy -t dev`, `databricks bundle run <pipeline_name> -t dev`.
- **CLI (C):** Re-upload with `databricks workspace import-dir ... --overwrite` after every change, then `databricks pipelines start-update`.
- Poll the update ID, not the top-level pipeline state, as described in the workflow reference. A serverless update can stay `INITIALIZING` for a few minutes on cold start; don't cancel it.
- Dry run (`--validate-only`) is a faster way to confirm the correctness of the pipeline code.
- Selective refresh is preferred when you only need to run one table; its dependencies must already be materialized.
- Full refresh is the most expensive and dangerous option and can lead to data loss (it resets streaming state); use it only when really necessary, and always as a follow-up the user must explicitly select.
