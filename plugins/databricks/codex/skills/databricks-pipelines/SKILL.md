---
name: databricks-pipelines
description: "Spark Declarative Pipelines (formerly DLT) in Python or SQL: streaming tables, materialized views, expectations, Auto CDC, Auto Loader, and pipeline settings. Also covers continuous mode, run-as, parameters, rewind, views, sinks and ForEachBatch, append flows, pipeline setup, migrating from legacy DLT, cluster keys, streaming state, and dedup or windowed aggregations. Also file ingestion from volumes, cloud storage, SFTP, Google Drive, SharePoint or OneDrive and document parsing; debugging failed, slow, or flaky updates from the update history; and migrating dbt or Informatica projects to SDP."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.4.0"
parent: databricks-core
---

# Lakeflow Spark Declarative Pipelines Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, profile selection, and data discovery commands.

SDP, LDP, Lakeflow Declarative Pipelines, and DLT (former name) all refer to the same product. This skill covers the core syntax and rules for writing Spark Declarative Pipelines datasets. For file ingestion and document parsing read [file-ingestion](references/file-ingestion.md); for failed, slow, or flaky updates read [pipeline-debugging](references/pipeline-debugging.md); for migrating dbt or Informatica projects read [migrate-to-sdp](references/migrate-to-sdp.md).

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
│   │   ├── File ingestion (cloud storage, Volumes) → Auto Loader (see [file-ingestion](references/file-ingestion.md))
│   │   ├── Message bus (Kafka, Kinesis, Pub/Sub, Pulsar, Event Hubs) → streaming source read
│   │   ├── Existing streaming/Delta table → streaming read from table
│   │   ├── CDC / upserts / track changes / keep latest per key / SCD Type 1, 2, or bitemporal → Auto CDC (only when this pipeline owns the target; merge/upsert into an existing/external table → ForEachBatch Sink, see Sink branch)
│   │   ├── Source rows carry two timestamps with different semantic meaning — one for when the fact holds in the domain, the other for when the system learned or recorded it (e.g. effective_at + ingested_at, trade date + booking date, observation time + chart-entry time) → Auto CDC STORED AS BITEMPORAL (Beta, DBR 17.3+); read the Auto CDC reference before recommending.
│   │   ├── Multiple sources into one table → Append Flows (NOT union)
│   │   ├── Historical backfill + live stream → one-time Append Flow + regular flow
│   │   ├── Recompute/overwrite a bounded window or partition each run (late-arriving within a known lookback, rolling last-N-days aggregate, partition overwrite, scheduled re-runs) → REPLACE WHERE flow (NOT a Materialized View, plain streaming table, or full recompute)
│   │   ├── Streaming source re-emits all rows for a key and the latest should replace the old per key (re-ingesting mutable files, keyed in-place updates) → REPLACE USING flow (NOT Auto CDC, which is for change events/SCD; NOT REPLACE WHERE, which overwrites a predicate window not a key)
│   │   ├── Windowed aggregation with watermark → stateful streaming
│   │   └── Custom per-key state, timers, timeouts (Python) → transformWithState in a flow (timeMode EventTime or None in triggered pipelines)
│   └── Source is batch/historical/full scan → Materialized View
│       ├── Aggregation/join across full dataset (GROUP BY, SUM, COUNT, etc.)
│       ├── Gold layer aggregation from streaming table → MV with batch read (spark.read / no STREAM)
│       ├── JDBC/Federation/external batch sources
│       └── Small static file load (reference data, no streaming read)
├── Output to a target the pipeline does NOT own (external / pre-existing / managed elsewhere) → Sink (Python only, primary even if the user asked for SQL)
│   ├── External or pre-existing Delta table NOT owned by this pipeline → Sink with format="delta" (streaming tables/MVs are for tables this pipeline owns and manages — including ones it already created and refreshes each run — but they cannot write into a table owned outside the pipeline)
│   ├── Kafka / Event Hubs → Sink with format="kafka" + @dp.append_flow(target="sink_name")
│   ├── Custom destination not natively supported → Sink with custom format
│   ├── Custom merge/upsert into an existing/external table → ForEachBatch Sink, NOT Auto CDC
│   └── Multiple destinations per batch → ForEachBatch Sink
└── Data quality constraints → Expectations (on any dataset type)
```

## Common Traps

- **Changing dataset type (ST↔MV):** Read [changing-dataset-type](references/changing-dataset-type.md) BEFORE edits or commands. Create a NEW dataset name and repoint ALL downstream references; never convert in place. Full refresh cannot fix this. The platform's "drop first" message is a manual workaround; offer dropping only as a follow-up. A green dry run does not prove rewiring.
- **SCD Type 2 queries:** Use validity columns `__START_AT` / `__END_AT`, not invented names. Current rows: `__END_AT IS NULL`. Point-in-time predicate: `__START_AT <= t AND (__END_AT > t OR __END_AT IS NULL)`; temporal joins also match the key and use the event date as `t`. Read the Auto CDC reference ([Python](references/auto-cdc-python.md), [SQL](references/auto-cdc-sql.md)) and [scd-2-querying](references/scd-2-querying.md).
- **UNRESOLVED_COLUMN / UNRESOLVED_COLUMN.WITH_SUGGESTION:** Verify upstream columns. For Auto Loader, verify its schema includes them (e.g., via `cloudFiles.schemaHints` / `schemaHints`); read [auto-loader-schema](references/auto-loader-schema.md).
- **Existing ST column add/drop/rename/widen, DELTA_MERGE_INCOMPATIBLE_DATATYPE or DELTA_FAILED_TO_MERGE_FIELDS:** Read [streaming-table-schema-evolution](references/streaming-table-schema-evolution.md) before answering; `ALTER TABLE` is Beta with prerequisites.
- **"Create a table" without a type:** Ask whether the source is streaming or batch. Streaming → Streaming Table; batch → Materialized View. Mismatched pairs fail validation.
- **Aggregating a streaming source:** For per-window results (hourly, daily) from an append-only source, use a streaming table with a `WATERMARK` and `window()`, which bounds state ([SQL](references/streaming-table-sql.md#advanced-streaming-patterns) / [Python](references/streaming-table-python.md#advanced-streaming-patterns) streaming patterns). Otherwise use a Materialized View with a batch read (no `STREAM`): streaming tables are append-only and don't recompute aggregates when source rows change.
- **`Cannot create streaming table from batch query`:** The streaming table reads in batch. Use `FROM STREAM read_files(...)` / `FROM STREAM(table)`.
- **Python-only features** (sinks, ForEachBatch sinks, custom data sources, Real-Time Mode): When the user works in SQL, say so and suggest Python for that part.
- **`databricks fs` on Volumes:** The CLI needs the `dbfs:` prefix, e.g. `databricks fs ls dbfs:/Volumes/<catalog>/<schema>/<volume>/<path>`.
- **SQL parameters (DBR 17.0+):** Read [parameters-sql](references/parameters-sql.md) before writing. Use `:name` for values that vary across updates, not hardcoding or legacy `${name}`. Values are `STRING`: cast at use; identifiers need `IDENTIFIER()`.
- **Recommend one approach.** Omit anti-patterns and inferior alternatives; mention alternatives only for viable trade-offs.

## Publishing Modes

Pipelines publish to the default catalog/schema in their settings.

- Use dataset-only names for pipeline reads/definitions unless existing code or the user requests qualification.
- `catalog.schema.table` publishes a **pipeline-owned** dataset elsewhere; no sink needed. **External, pre-existing, or separately managed targets require a Python sink**, even if the user requested SQL.
- `USE CATALOG` / `USE SCHEMA` changes the defaults for subsequent definitions in the same SQL file.

## Comprehensive API Reference

**MANDATORY:** Before implementing, editing, or suggesting feature code, read its linked reference and these required companion references:

- **Auto Loader, Auto CDC, sinks** → also read the streaming-table reference: Auto Loader/CDC target streaming tables; sinks use streaming append flows.
- **Auto Loader** → also read the matching format options: [CSV](references/auto-loader-options-csv.md), [JSON](references/auto-loader-options-json.md), [Avro](references/auto-loader-options-avro.md), [Parquet](references/auto-loader-options-parquet.md), [XML](references/auto-loader-options-xml.md), [Text](references/auto-loader-options-text.md), [ORC](references/auto-loader-options-orc.md). For schema inference/evolution, hints, rescued data, partition inference or type widening, read [schema](references/auto-loader-schema.md).
- **Expectations** → also read the target dataset's definition reference for constraint placement.
- **Kafka / Event Hubs sources** → also read authentication: [Python](references/kafka-auth-python.md) or [SQL](references/kafka-auth-sql.md) (SASL, MSK IAM, Entra ID, GCP OAuth; shaded class names required).
  - Avro with Confluent Schema Registry → read [Kafka deserialization](references/kafka-deserialization-python.md), **Python only**. For SQL pipelines, explain the limitation and recommend switching to Python. Protobuf also works in SQL (`from_protobuf`, DBR 16.1+; see the SQL deserialization reference).
  - JSON/Avro without Schema Registry → [Python](references/deserialization-python.md) or [SQL](references/deserialization-sql.md), matching the pipeline language.
- **Real-Time Mode** → read [reference](references/real-time-mode-sdp.md). Only for explicitly requested operational sub-second latency; requires continuous mode + a real-time update flow.

### Feature references

| Feature | Python | SQL |
|---|---|---|
| Streaming tables; explicit targets; append and one-time backfill flows; skip upstream change commits | [Python](references/streaming-table-python.md) | [SQL](references/streaming-table-sql.md) |
| Materialized views; manual/auto liquid clustering, partitioning, table properties, explicit schemas, generated columns, row filters and column masks, private datasets | [Python](references/materialized-view-python.md) | [SQL](references/materialized-view-sql.md) |
| Temporary views | [Python](references/temporary-view-python.md) | [SQL](references/temporary-view-sql.md) |
| Persistent UC views | Unsupported | [SQL](references/view-sql.md) |
| Delta/Kafka/Event Hubs/custom sinks | [Python](references/sink-python.md) | Unsupported |
| ForEachBatch sinks | [Python](references/foreach-batch-sink-python.md) | Unsupported |
| Auto CDC from a stream | [Python](references/auto-cdc-python.md) | [SQL](references/auto-cdc-sql.md) |
| Auto CDC from periodic snapshots | [Python](references/auto-cdc-python.md) | [SQL](references/auto-cdc-from-snapshot.md) |
| Expectations: warn, drop, fail; individual or multiple constraints | [Python](references/expectations-python.md) | [SQL](references/expectations-sql.md) |
| Identity columns | [Python](references/identity-columns-python.md) | [SQL](references/identity-columns-sql.md) |
| Auto Loader | [Python](references/auto-loader-python.md) | [SQL](references/auto-loader-sql.md) |
| Kafka/Event Hubs sources | [Python](references/kafka-streaming-python.md) | [SQL](references/kafka-streaming-sql.md) |
| Kinesis sources | [Python](references/kinesis-streaming-python.md) | [SQL](references/kinesis-streaming-sql.md) |
| Payload deserialization (JSON/Avro/Protobuf; Avro with Schema Registry is Python only) | [Python](references/deserialization-python.md) | [SQL](references/deserialization-sql.md) |

- **REPLACE WHERE**: overwrite a bounded window/partition each run, such as a rolling lookback. Read [Python](references/replace-where-flow-python.md) or [SQL](references/replace-where-flow-sql.md).
- **REPLACE USING**: streaming keyed replacement of full rows with a required sequencing column; Beta, requires DBR 18.2+. Read [Python](references/replace-using-flow-python.md) or [SQL](references/replace-using-flow-sql.md).

Topics covering both languages:

- Streaming patterns ([SQL](references/streaming-table-sql.md#advanced-streaming-patterns) / [Python](references/streaming-table-python.md#advanced-streaming-patterns)): dedup, windowed aggregations, late data, stream-stream joins, rescued-data quarantine, lag monitoring, `transformWithState`.
- [SCD Type 2 querying](references/scd-2-querying.md): current state, point-in-time, joining facts with historical dimensions.

### Reads and compatibility

- Pipeline batch reads: `spark.read.table("name")` / `SELECT ... FROM name`; streaming reads: `spark.readStream.table("name")` / `SELECT ... FROM STREAM name`.
- Pub/Sub and Pulsar sources: use `spark.readStream.format("pubsub")` or `spark.readStream.format("pulsar")`; SQL uses `STREAM read_pubsub(...)` or `STREAM read_pulsar(...)`.
- JDBC/Federation are batch sources; Python uses `spark.read.format("postgresql")` etc. and SQL references the federation catalog.
- Static files: `spark.read.format(...).load(...)` / `read_files(...)` without `STREAM`.
- Custom data sources are Python-only: `spark.read[Stream].format("custom")`.
- Prefer `from pyspark import pipelines as dp` for new Python. Preserve existing `dlt` imports. Prefer `spark.read.table` / `spark.readStream.table` over the legacy `dp.read`, `dlt.read`, and their streaming variants.
- Never use `LIVE.` references or legacy `CREATE LIVE TABLE` / `CREATE LIVE VIEW` syntax; use current dataset definitions. The one exception is `CREATE LIVE VIEW` for expectations on a temporary view (see the table below).

### Migrating legacy DLT syntax

When the user asks to migrate legacy DLT code to the modern form, read [dlt-migration.md](references/dlt-migration.md) before suggesting changes so the conversion is correct (especially around `apply_changes` → `create_auto_cdc_flow` semantics and `partition_cols` → `cluster_by`). Common mappings:

| If you see…                                                                 | …migrate to                                                          |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `import dlt`                                                                | `from pyspark import pipelines as dp`                                |
| `@dlt.table(...)`, `@dlt.append_flow(...)`, `@dlt.expect*`                  | Same decorator name on `dp.*` (e.g. `@dp.table`, `@dp.expect_or_drop`). |
| `@dlt.view(...)` (or `@dp.view(...)` if present in older code)              | `@dp.temporary_view(...)`                                            |
| `dlt.read("name")` / `dlt.read_stream("name")`                              | `spark.read.table("name")` / `spark.readStream.table("name")`        |
| `dp.read(...)` / `dp.read_stream(...)`                                      | Also legacy — use `spark.read.table(...)` / `spark.readStream.table(...)`. |
| `dlt.apply_changes(...)` / `dp.apply_changes(...)`                          | `dp.create_auto_cdc_flow(...)`. `sequence_by` accepts a column name (string) or `col(...)`; `stored_as_scd_type` is `1` or `2` (integer or string). |
| `dlt.apply_changes_from_snapshot(...)`                                      | `dp.create_auto_cdc_from_snapshot_flow(...)`                         |
| `dlt.create_streaming_table(...)`                                           | `dp.create_streaming_table(...)`                                     |
| `LIVE.<name>` prefix in SQL                                                 | Bare name (`SELECT FROM name` for batch, `SELECT FROM STREAM(name)` for streaming). `LIVE.` will error in modern pipelines. |
| `CREATE LIVE TABLE` / `CREATE STREAMING LIVE TABLE` | `CREATE OR REFRESH MATERIALIZED VIEW` / `CREATE OR REFRESH STREAMING TABLE`. |
| `CREATE TEMPORARY LIVE VIEW` (a.k.a. `CREATE LIVE VIEW`) | `CREATE TEMPORARY VIEW`. **Exception**: `CREATE TEMPORARY VIEW` does NOT support `CONSTRAINT` clauses for expectations — for the rare case where you need expectations on a temp view, `CREATE LIVE VIEW` is retained. See [temporary-view-sql.md](references/temporary-view-sql.md) and [expectations-sql.md](references/expectations-sql.md). |
| `APPLY CHANGES INTO ... FROM STREAM ...` (SQL)                              | `AUTO CDC INTO ... FROM STREAM ...`                                  |
| `partition_cols=[...]` / `PARTITIONED BY (...)` + `ZORDER`                  | `cluster_by=[...]` / `CLUSTER BY (...)` (Liquid Clustering).         |
| `input_file_name()`                                                         | `_metadata.file_path` (SQL) / `F.col("_metadata.file_path")` (Python). |
| `target=...` parameter on `create_streaming_table` / pipeline config        | `schema=...`                                                         |

## Performance

- [Performance tuning](references/performance-tuning.md) - Liquid clustering, cluster key selection by layer, streaming state management, join optimization, query optimization, and pre-aggregation
- **Making a materialized view with more than 3 joins incremental** → [decompose-materialized-view-python](references/decompose-materialized-view-python.md) (Python) or [decompose-materialized-view-sql](references/decompose-materialized-view-sql.md) (SQL)

## Language-specific guides

- Before writing Python, first read [Python basics](references/python-basics.md): decorators, functions, and critical rules.
- Before writing SQL, first read [SQL basics](references/sql-basics.md): statements and critical rules.

## Project Setup

- **Language:** Keep an existing pipeline's language. For new pipelines default to SQL; use Python when the user asks for it or needs UDFs, ML inference, or Python-only features. If the request is ambiguous, ask.
- **New pipeline:** Read [setup-pipeline](references/setup-pipeline.md) for how to scope and build it.
- **Workflow:** Pick before scaffolding.
  - **A: Standalone project (DAB)**, no existing `databricks.yml` → [1-project-initialization-with-dab](references/1-project-initialization-with-dab.md). Default for production-bound work.
  - **B: Pipeline in an existing bundle** → add `resources/<name>.pipeline.yml`; see Workflow B in the same reference.
  - **C: Rapid CLI iteration (no bundle)** for prototypes and demos → [2-rapid-iteration-with-cli](references/2-rapid-iteration-with-cli.md).
- **Structure:** Medallion (Bronze → Silver → Gold) with just a few tables unless the user says otherwise. One dataset per file, named after the dataset, in `src/` or `transformations/`. In Gold, keep the dimensions consumers filter by (e.g., every dashboard filter).
- **Settings:** For create/update JSON, compute, channels, and multi-schema setups, read [pipeline-settings](references/pipeline-settings.md).

## Running a Pipeline

- **DAB (A/B):** Code changes take effect only after `databricks bundle deploy`; deploy before any run, dry run, or selective refresh. Sequence: `databricks bundle validate`, `databricks bundle deploy -t dev`, `databricks bundle run <pipeline_name> -t dev`.
- **CLI (C):** Re-upload with `databricks workspace import-dir ... --overwrite` after every change, then `databricks pipelines start-update`.
- Poll the update ID, not the top-level pipeline state, as described in the workflow reference. A serverless update can stay `INITIALIZING` for a few minutes on cold start; don't cancel it.
- Dry run (`--validate-only`) is a faster way to confirm the correctness of the pipeline code.
- Selective refresh is preferred when you only need to run one table; its dependencies must already be materialized.
- Full refresh is the most expensive and dangerous option and can lead to data loss (it resets streaming state); use it only when really necessary, and always as a follow-up the user must explicitly select.
- **Terminology**: Never say "run a dry run" — the phrase is redundant. Say "do a dry run" or "start a dry run" instead.
- To perform a rewind pipeline operation, first read [rewind-pipeline](references/rewind-pipeline.md).
- To refresh or reset-and-refresh a single flow of a table (rather than the whole table), first read [flow-reset-refresh](references/flow-reset-refresh.md). Resetting a flow cannot be undone; like a full refresh, the user must explicitly select it.

## Pipeline Settings

- To answer questions about or change pipeline settings, read [pipeline-settings.md](references/pipeline-settings.md).
- **Make a pipeline continuous / always-on / "run continuously", or set its maintenance window** → do NOT just set `continuous: true`; read [continuous-pipeline.md](references/continuous-pipeline.md) first, as the mechanism depends on the pipeline's current mode.
