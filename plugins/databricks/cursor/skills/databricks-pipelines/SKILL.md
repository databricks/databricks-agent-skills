---
name: databricks-pipelines
description: Develop Lakeflow Spark Declarative Pipelines (formerly Delta Live Tables) on Databricks. Use when building batch or streaming data pipelines with Python or SQL. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.3.0"
parent: databricks-core
---

# Lakeflow Spark Declarative Pipelines Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, profile selection, and data discovery commands.

## Decision Tree

Use this tree to determine which dataset type and features to use. Multiple features can apply to the same dataset — e.g., a Streaming Table can use Auto Loader for ingestion, Append Flows for fan-in, and Expectations for data quality. Choose the dataset type first, then layer on applicable features.

```
User request → What kind of output?
├── Intermediate/reusable logic (not persisted) → Temporary View
│   ├── Preprocessing/filtering before Auto CDC → Temporary View feeding CDC flow
│   ├── Shared intermediate streaming logic reused by multiple downstream tables
│   ├── Pipeline-private helper logic (not published to catalog)
│   └── Published to UC for external queries → Persistent View (SQL only)
├── Persisted dataset
│   ├── Source is streaming/incremental/continuously growing → Streaming Table
│   │   ├── File ingestion (cloud storage, Volumes) → Auto Loader
│   │   ├── Message bus (Kafka, Kinesis, Pub/Sub, Pulsar, Event Hubs) → streaming source read
│   │   ├── Existing streaming/Delta table → streaming read from table
│   │   ├── CDC / upserts / track changes / keep latest per key / SCD Type 1 or 2 → Auto CDC
│   │   ├── Multiple sources into one table → Append Flows (NOT union)
│   │   ├── Historical backfill + live stream → one-time Append Flow + regular flow
│   │   └── Windowed aggregation with watermark → stateful streaming
│   └── Source is batch/historical/full scan → Materialized View
│       ├── Aggregation/join across full dataset (GROUP BY, SUM, COUNT, etc.)
│       ├── Gold layer aggregation from streaming table → MV with batch read (spark.read / no STREAM)
│       ├── JDBC/Federation/external batch sources
│       └── Small static file load (reference data, no streaming read)
├── Output to external system (Python only) → Sink
│   ├── Existing external table not managed by this pipeline → Sink with format="delta"
│   │   (prefer fully-qualified dataset names if the pipeline should own the table — see Publishing Modes)
│   ├── Kafka / Event Hubs → Sink with format="kafka" + @dp.append_flow(target="sink_name")
│   ├── Custom destination not natively supported → Sink with custom format
│   ├── Custom merge/upsert logic per batch → ForEachBatch Sink (Public Preview)
│   └── Multiple destinations per batch → ForEachBatch Sink (Public Preview)
└── Data quality constraints → Expectations (on any dataset type)
```

## Common Traps

- **Names** → SDP = LDP = Lakeflow Declarative Pipelines = (formerly) DLT. All interchangeable when the user mentions them.
- **"Create a table" without specifying type** → ask whether the source is streaming or batch. Streaming source → Streaming Table; batch source → Materialized View. Mismatched pairs error at validation.
- **Aggregation over a streaming source** → use a Materialized View with a batch read (`spark.read.table` / `SELECT FROM` without `STREAM`). STs are append-only and don't recompute aggregates when source rows change; MVs do.
- **Intermediate logic** → default to a Temporary View. Even for shared logic reused by multiple downstream tables. Use a Private MV/ST (`private=True` / `CREATE PRIVATE ...`) only when materializing once saves significant reprocessing. For preprocessing before Auto CDC, the temp view is required — the CDC flow reads from `STREAM(view_name)` (SQL) or `spark.readStream.table("view_name")` (Python).
- **Union of streams** → use multiple Append Flows. UNION across streaming sources is an anti-pattern.
- **Changing dataset type** → cannot change ST→MV or MV→ST in place. Full refresh does NOT help. Drop the existing table manually or rename the new dataset.
- **`CREATE OR REFRESH` vs `CREATE`** → both parse for SQL datasets, but `CREATE OR REFRESH` is the idiomatic convention. For PRIVATE datasets: `CREATE OR REFRESH PRIVATE STREAMING TABLE` / `... MATERIALIZED VIEW`.
- **Kafka/Event Hubs sink serialization** → the `value` column is mandatory; serialize the row with `to_json(struct(*)) AS value`. See [sink-python.md](references/sink-python.md).
- **Multi-column Auto CDC sequencing** → SQL: `SEQUENCE BY STRUCT(col1, col2)`. Python: `sequence_by=struct("col1", "col2")`. See the auto-cdc references.
- **Auto CDC TRUNCATE** (SCD Type 1 only) → SQL: `APPLY AS TRUNCATE WHEN condition`. Python: `apply_as_truncates=expr("condition")`. Do NOT claim truncate is unsupported.
- **Python-only features** → Sinks, ForEachBatch Sinks, CDC from snapshots, and custom data sources are Python-only. When the user is working in SQL, clarify this and suggest switching to Python.
- **Recommend ONE clear approach** → present a single recommended path. Don't list anti-patterns or inferior alternatives — they confuse. Only mention alternatives when they genuinely offer different trade-offs.

## Common Issues

Error → cause/fix mappings agents hit constantly. For DAB-bundle vs CLI-iteration deploy issues, see the workflow-specific reference files.

| Error / symptom | Cause / fix |
|-----------------|-------------|
| Rejection of `CREATE OR REPLACE STREAMING TABLE` / `MATERIALIZED VIEW` | `CREATE OR REPLACE` is standard SQL, NOT SDP. Use `CREATE OR REFRESH STREAMING TABLE` / `CREATE OR REFRESH MATERIALIZED VIEW`. |
| CLI errors on `databricks fs ls /Volumes/...` | The `dbfs:` prefix is required even for UC Volume paths: `databricks fs ls dbfs:/Volumes/<catalog>/<schema>/<volume>/<path>`. |
| `DELTA_CLUSTERING_COLUMNS_DATATYPE_NOT_SUPPORTED` at first write | A `CLUSTER BY` column is BOOLEAN / ARRAY / MAP / STRUCT / BINARY. SDP doesn't pre-validate — verify with `DESCRIBE` before submitting. Cluster keys must be numeric / string / date / timestamp. Full type rules in [references/performance.md](references/performance.md#cluster-key-data-types). |
| `Cannot create streaming table from batch query` | In a streaming-table query you wrote `FROM read_files(...)` (batch). Use `FROM STREAM read_files(...)` so Auto Loader kicks in. |
| `Column not found` at ingest time | `schemaHints` don't match the actual file schema. `DESCRIBE` a sample file and align the hints. |
| Streaming reads fail with parser error | Use `FROM STREAM read_files(...)` for file ingestion and `FROM stream(table)` (or `FROM STREAM table_name` — legacy DLT, prefer function form) for table-to-table streams. Don't mix. |
| Pipeline stuck `INITIALIZING` for serverless | Normal — first run takes a few minutes for cold start. Don't kill it. |
| Materialized View doesn't incrementally refresh | Automatic incremental refresh for aggregations requires **serverless** + Delta row tracking on the source (`delta.enableRowTracking = true`). Without both, falls back to full recompute. Mention the serverless requirement when the user asks about incremental refresh. |
| SCD2 query returns nothing / "column not found" on `START_AT` | Lakeflow uses `__START_AT` / `__END_AT` (double underscore). Current rows: `WHERE __END_AT IS NULL`. |
| `error.exceptions[0].message` missing from your events output | Your `jq` is reading `.message` (which is just "Update X is FAILED"). Read `error.exceptions[0].message` for the real cause — see [2-rapid-iteration-with-cli.md](references/2-rapid-iteration-with-cli.md#step-4-start-an-update-and-poll-that-update). |

## Publishing Modes

Pipelines use a **default catalog and schema** configured in the pipeline settings. All datasets are published there unless overridden.

- **Fully-qualified names**: Use `catalog.schema.table` in the dataset name to write to a different catalog/schema than the pipeline default. The pipeline creates the dataset there directly — no Sink needed.
- **USE CATALOG / USE SCHEMA**: SQL commands that change the current catalog/schema for all subsequent definitions in the same file.
- **LIVE prefix**: Deprecated. Ignored in the default publishing mode.
- When reading or defining datasets within the pipeline, use the dataset name only — do NOT use fully-qualified names unless the pipeline already does so or the user explicitly requests a different target catalog/schema.

## API Reference

**Before writing pipeline code for any feature, read the linked reference file.** Each table below maps the feature to the exact API and to the detail file for that (feature, language).

Some features sit on top of others — read both:

- **Auto Loader** / **Auto CDC** / **Sinks** target a streaming table → also read [streaming-table-python.md](references/streaming-table-python.md) / [streaming-table-sql.md](references/streaming-table-sql.md).
- **Expectations** attach to a dataset → also read the dataset definition file (streaming-table / materialized-view / temporary-view).

### Dataset Definition APIs

| Feature                    | Description                                                      | Python                            | SQL                                         | Skill (Py)                                              | Skill (SQL)                                       |
| -------------------------- | ---------------------------------------------------------------- | --------------------------------- | ------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| Streaming Table            | Continuous incremental processing, exactly-once, append-only.    | `@dp.table()` returning streaming DF | `CREATE OR REFRESH STREAMING TABLE`         | [streaming-table-python](references/streaming-table-python.md) | [streaming-table-sql](references/streaming-table-sql.md) |
| Materialized View          | Physically stored query result, incrementally refreshed.         | `@dp.materialized_view()`         | `CREATE OR REFRESH MATERIALIZED VIEW`       | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Temporary View             | Pipeline-private, not persisted to Unity Catalog.                | `@dp.temporary_view()`            | `CREATE TEMPORARY VIEW`                     | [temporary-view-python](references/temporary-view-python.md) | [temporary-view-sql](references/temporary-view-sql.md) |
| Persistent View (UC)       | Published to UC; query runs on access (no storage).              | N/A — SQL only                    | `CREATE VIEW`                               | —                                                       | [view-sql](references/view-sql.md)                |
| Streaming Table (explicit) | Empty target, populated by separate flows (Append Flow, AUTO CDC). | `dp.create_streaming_table()`     | `CREATE OR REFRESH STREAMING TABLE` (no AS) | [streaming-table-python](references/streaming-table-python.md) | [streaming-table-sql](references/streaming-table-sql.md) |

### Flow and Sink APIs

| Feature                      | Description                                                      | Python                       | SQL                                    | Skill (Py)                                                  | Skill (SQL)                                       |
| ---------------------------- | ---------------------------------------------------------------- | ---------------------------- | -------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------- |
| Append Flow                  | Fan-in: multiple sources → one streaming table. Use instead of UNION. | `@dp.append_flow()`     | `CREATE FLOW ... INSERT INTO`          | [streaming-table-python](references/streaming-table-python.md) | [streaming-table-sql](references/streaming-table-sql.md) |
| Backfill Flow                | One-time historical load + ongoing live stream into same table. | `@dp.append_flow(once=True)` | `CREATE FLOW ... INSERT INTO ... ONCE` | [streaming-table-python](references/streaming-table-python.md) | [streaming-table-sql](references/streaming-table-sql.md) |
| Sink (Delta/Kafka/EH/custom) | Write streaming output to external Delta / Kafka / Event Hubs.   | `dp.create_sink()`           | N/A — Python only                      | [sink-python](references/sink-python.md)                    | —                                                 |
| ForEachBatch Sink            | Custom per-batch Python logic (merge/upsert, multi-destination). Public Preview. | `@dp.foreach_batch_sink()` | N/A — Python only         | [foreach-batch-sink-python](references/foreach-batch-sink-python.md) | —                                       |

### CDC APIs

| Feature                      | Description                                                          | Python                                      | SQL                             | Skill (Py)                                | Skill (SQL)                          |
| ---------------------------- | -------------------------------------------------------------------- | ------------------------------------------- | ------------------------------- | ----------------------------------------- | ------------------------------------ |
| Auto CDC (streaming source)  | SCD Type 1 (overwrite) or Type 2 (history) from a CDC feed.          | `dp.create_auto_cdc_flow()`                 | `AUTO CDC INTO ... FROM STREAM` | [auto-cdc-python](references/auto-cdc-python.md) | [auto-cdc-sql](references/auto-cdc-sql.md) |
| Auto CDC (periodic snapshot) | Compare consecutive full snapshots to detect changes.                | `dp.create_auto_cdc_from_snapshot_flow()`   | N/A — Python only               | [auto-cdc-python](references/auto-cdc-python.md) | —                                    |

For querying SCD Type 2 history tables (`__START_AT` / `__END_AT`, point-in-time, joining facts with historical dimensions), see [scd-2-querying.md](references/scd-2-querying.md).

### Data Quality APIs

| Feature            | Description                                | Python                       | SQL                                                    | Skill (Py)                                            | Skill (SQL)                                     |
| ------------------ | ------------------------------------------ | ---------------------------- | ------------------------------------------------------ | ----------------------------------------------------- | ----------------------------------------------- |
| Expect (warn)      | Log violations, keep all rows.             | `@dp.expect()`               | `CONSTRAINT ... EXPECT (...)`                          | [expectations-python](references/expectations-python.md) | [expectations-sql](references/expectations-sql.md) |
| Expect or drop     | Drop violating rows.                       | `@dp.expect_or_drop()`       | `CONSTRAINT ... EXPECT (...) ON VIOLATION DROP ROW`    | [expectations-python](references/expectations-python.md) | [expectations-sql](references/expectations-sql.md) |
| Expect or fail     | Fail the pipeline on first violation.      | `@dp.expect_or_fail()`       | `CONSTRAINT ... EXPECT (...) ON VIOLATION FAIL UPDATE` | [expectations-python](references/expectations-python.md) | [expectations-sql](references/expectations-sql.md) |
| Expect all (warn)  | Multiple constraints at once, warn only.   | `@dp.expect_all({})`         | Multiple `CONSTRAINT` clauses                          | [expectations-python](references/expectations-python.md) | [expectations-sql](references/expectations-sql.md) |
| Expect all or drop | Multiple constraints, drop on violation.   | `@dp.expect_all_or_drop({})` | Multiple constraints with `DROP ROW`                   | [expectations-python](references/expectations-python.md) | [expectations-sql](references/expectations-sql.md) |
| Expect all or fail | Multiple constraints, fail on violation.   | `@dp.expect_all_or_fail({})` | Multiple constraints with `FAIL UPDATE`                | [expectations-python](references/expectations-python.md) | [expectations-sql](references/expectations-sql.md) |

### Reading Data APIs

| Feature                           | Description                                            | Python                                         | SQL                                              | Skill (Py)                                              | Skill (SQL)                                       |
| --------------------------------- | ------------------------------------------------------ | ---------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------- |
| Batch read (pipeline dataset)     | Read a sibling table as a static DataFrame.            | `spark.read.table("name")`                     | `SELECT ... FROM name`                           | —                                                       | —                                                 |
| Streaming read (pipeline dataset) | Read a sibling table as a streaming DataFrame.         | `spark.readStream.table("name")`               | `SELECT ... FROM STREAM(name)`                   | —                                                       | —                                                 |
| Auto Loader (cloud files)         | Incrementally ingest new files from cloud storage.     | `spark.readStream.format("cloudFiles")`        | `STREAM read_files(...)`                         | [auto-loader-python](references/auto-loader-python.md)  | [auto-loader-sql](references/auto-loader-sql.md)  |
| Kafka source                      | Streaming read from Kafka topic.                       | `spark.readStream.format("kafka")`             | `STREAM read_kafka(...)`                         | [kafka](references/kafka.md)                            | [kafka](references/kafka.md)                      |
| Kinesis source                    | Streaming read from AWS Kinesis.                       | `spark.readStream.format("kinesis")`           | `STREAM read_kinesis(...)`                       | —                                                       | —                                                 |
| Pub/Sub source                    | Streaming read from GCP Pub/Sub.                       | `spark.readStream.format("pubsub")`            | `STREAM read_pubsub(...)`                        | —                                                       | —                                                 |
| Pulsar source                     | Streaming read from Apache Pulsar.                     | `spark.readStream.format("pulsar")`            | `STREAM read_pulsar(...)`                        | —                                                       | —                                                 |
| Event Hubs source                 | Streaming read from Azure Event Hubs (Kafka protocol). | `spark.readStream.format("kafka")` + EH config | `STREAM read_kafka(...)` + EH config             | [kafka](references/kafka.md)                            | [kafka](references/kafka.md)                      |
| JDBC / Lakehouse Federation       | Batch read from external systems via federation.       | `spark.read.format("postgresql")` etc.         | Direct table ref via federation catalog          | —                                                       | —                                                 |
| Custom data source                | User-defined Python data source.                       | `spark.read[Stream].format("custom")`          | N/A — Python only                                | —                                                       | —                                                 |
| Static file read (batch)          | One-shot load of files (no incremental tracking).      | `spark.read.format("json"\|"csv"\|...).load()` | `read_files(...)` (no STREAM)                    | —                                                       | —                                                 |
| Skip upstream change commits      | Ignore CDC commits on the upstream table.              | `.option("skipChangeCommits", "true")`         | `read_stream("name", skipChangeCommits => true)` | [streaming-table-python](references/streaming-table-python.md) | [streaming-table-sql](references/streaming-table-sql.md) |

### Table/Schema Feature APIs

| Feature                      | Description                                                   | Python                                                | SQL                                     | Skill (Py)                                              | Skill (SQL)                                       |
| ---------------------------- | ------------------------------------------------------------- | ----------------------------------------------------- | --------------------------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| Liquid clustering            | Adaptive multi-column data layout; replaces PARTITION + Z-ORDER. Prefer Auto clustering when possible | `cluster_by=[...]`                                 | `CLUSTER BY (col1, col2)`               | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Auto liquid clustering       | Databricks picks clustering keys from query patterns.         | `cluster_by_auto=True`                                | `CLUSTER BY AUTO`                       | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Partition columns            | Legacy fixed partitioning. Prefer Liquid Clustering.          | `partition_cols=[...]`                                | `PARTITIONED BY (col1, col2)`           | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Table properties             | Delta table properties (auto-optimize, CDF, retention).       | `table_properties={...}`                              | `TBLPROPERTIES (...)`                   | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Explicit schema              | Declare column types up front (vs inferred).                  | `schema="col1 TYPE, ..."`                             | `(col1 TYPE, ...) AS`                   | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Generated columns            | Columns computed from other columns at write time.            | `schema="..., col TYPE GENERATED ALWAYS AS (expr)"`   | `col TYPE GENERATED ALWAYS AS (expr)`   | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Row filter (Public Preview)  | UC fine-grained access: filter rows by a function.            | `row_filter="ROW FILTER fn ON (col)"`                 | `WITH ROW FILTER fn ON (col)`           | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Column mask (Public Preview) | UC fine-grained access: mask a column with a function.        | `schema="..., col TYPE MASK fn USING COLUMNS (col2)"` | `col TYPE MASK fn USING COLUMNS (col2)` | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |
| Private dataset              | Materialized intermediate not published to UC.                | `private=True`                                        | `CREATE PRIVATE ...`                    | [materialized-view-python](references/materialized-view-python.md) | [materialized-view-sql](references/materialized-view-sql.md) |

### Legacy DLT Syntax — always migrate

The tables above show **only the modern API**. If you see any of the following in user code, it is the legacy DLT syntax — **always migrate to the modern form**, do not extend it. Read [references/dlt-migration.md](references/dlt-migration.md) before suggesting changes so the conversion is correct (especially around `apply_changes` → `create_auto_cdc_flow` semantics and `partition_cols` → `cluster_by`).

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

## Language Selection (Python vs SQL)

Decide before scaffolding — the choice picks template files (`.py` vs `.sql`) and which reference docs apply. Both can coexist, but pick a primary. When unsure, default to SQL for simplicity.

| User signal | Pick |
|-------------|------|
| "Python pipeline", UDF, pandas, ML inference, pyspark | **Python** |
| "SQL pipeline", "SQL files" | **SQL** |
| "Simple pipeline", "create a table", "an aggregation" | **SQL** (simpler, use it as default) |
| Complex parameterized logic, custom UDFs, ML | **Python** |

If ambiguous, ask. Stick with the chosen language unless the user explicitly switches.

## Choose Your Workflow

Three project shapes exist — pick before scaffolding. Default to A for production-bound work and C for exploration / demo scaffolding.

- **A: Standalone new pipeline project (DAB)** — pipeline IS the project, no existing `databricks.yml`. Scaffold with `databricks pipelines init --output-dir . --config-file init-config.json`. → [1-project-initialization-with-dab.md](references/1-project-initialization-with-dab.md)
- **B: Pipeline in an existing bundle (DAB)** — `databricks.yml` already exists. Add a `resources/<name>.pipeline.yml` pointing at `src/`. → [1-project-initialization-with-dab.md#workflow-b-pipeline-in-existing-bundle](references/1-project-initialization-with-dab.md#workflow-b-pipeline-in-existing-bundle)
- **C: Rapid CLI iteration (no bundle)** — prototyping. `databricks pipelines create / start-update / list-pipeline-events`; formalise into a bundle later if the work goes to production. → [2-rapid-iteration-with-cli.md](references/2-rapid-iteration-with-cli.md)

## Pipeline Structure

- Follow the medallion pattern (Bronze → Silver → Gold) unless the user says otherwise. Keep it simple by default — just a few tables.
- One dataset per file, named after the dataset. Transformation files live in `src/` or `transformations/`.
- **Gold layer: preserve key business dimensions.** When aggregating into Gold, keep the dimensions analysts will filter / slice by (location, department, product line, customer segment, time period). Over-aggregating loses information that can't be recovered downstream. If a dashboard is mentioned, every filter on it needs to be a column in the Gold table. Easier to aggregate further in queries than to recover lost dimensions.


## Running a Pipeline

Picking the right run command depends on the workflow chosen above.

- **Workflow A / B (DAB)** — Code changes only take effect after `databricks bundle deploy`. Always deploy before any run, dry run, or selective refresh.
  ```bash
  databricks bundle validate --profile <profile>
  databricks bundle deploy -t dev --profile <profile>
  databricks bundle run <pipeline_name> -t dev --profile <profile>
  databricks pipelines get <pipeline_id> --profile <profile>      # status
  ```
  → Full DAB run + iteration details: [references/1-project-initialization-with-dab.md#running-a-pipeline-workflow-a--b](references/1-project-initialization-with-dab.md#running-a-pipeline-workflow-a--b)

- **Workflow C (CLI, no bundle)** — Upload files to the workspace, then drive the pipeline directly. Re-upload after every code change.
  ```bash
  databricks workspace import-dir ./my_pipeline /Workspace/Users/<user>/my_pipeline --overwrite
  databricks pipelines start-update <pipeline_id>
  ```
  → Full CLI run + polling pattern: [references/2-rapid-iteration-with-cli.md](references/2-rapid-iteration-with-cli.md)

**Refresh modes (both workflows):**

- **Selective refresh** is preferred when you only need to run one table. Dependencies must already be materialized.
- **Full refresh** is the most expensive and dangerous option and **can lead to data loss** (it reprocesses streaming sources from scratch, destroying streaming state). Use only when really necessary. Always suggest it as a follow-up the user must explicitly approve.

**Always poll the update**, not top-level pipeline state — see the polling rationale in [2-rapid-iteration-with-cli.md#step-4-start-an-update-and-poll-that-update](references/2-rapid-iteration-with-cli.md#step-4-start-an-update-and-poll-that-update). Same rule applies to bundle runs.

## Reference Index

Project & lifecycle:

- [1-project-initialization-with-dab.md](references/1-project-initialization-with-dab.md) — Workflows A and B.
- [2-rapid-iteration-with-cli.md](references/2-rapid-iteration-with-cli.md) — Workflow C; start-update + polling + error-extraction.
- [pipeline-configuration.md](references/pipeline-configuration.md) — Full create/update JSON reference + variant snippets + multi-schema + platform constraints.
- [performance.md](references/performance.md) — Liquid Clustering, state management, joins, pre-aggregation, monitoring.
- [dlt-migration.md](references/dlt-migration.md) — DLT → SDP conversions.

Cross-cutting patterns:

- [streaming-patterns.md](references/streaming-patterns.md) — Dedup, windowed aggregations, late data, rescue-data quarantine, anomaly detection, lag monitoring.
- [scd-2-querying.md](references/scd-2-querying.md) — Current-state, point-in-time, joining facts with historical dims.
- [kafka.md](references/kafka.md) — Kafka / Event Hubs ingestion.

Auto Loader format-specific options: [JSON](references/options-json.md) · [CSV](references/options-csv.md) · [XML](references/options-xml.md) · [Parquet](references/options-parquet.md) · [Avro](references/options-avro.md) · [Text](references/options-text.md) · [ORC](references/options-orc.md).

Dataset, flow, CDC, expectation, Auto Loader, and sink references are listed per (feature, language) in the [API Reference tables above](#api-reference).
