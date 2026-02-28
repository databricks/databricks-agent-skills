#### Setup

- `from pyspark import pipelines as dp` (preferred) or `import dlt` (deprecated but still works) is always required on top when doing Python. Prefer `dp` import style unless `dlt` was already imported, don't change existing imports unless explicitly asked.
- The SparkSession object is already available (no need to import it again) - unless in a utility file

#### Core Decorators

- `@dp.materialized_view()` - Materialized views (batch processing, recommended for materialized views)
- `@dp.table()` - Streaming tables (when returning streaming DataFrame) or materialized views (legacy, when returning batch DataFrame)
- `@dp.view()` - Temporary views (non-materialized, private to pipeline)
- `@dp.expect*()` - Data quality constraints (expect, expect_or_drop, expect_or_fail, expect_all, expect_all_or_drop, expect_all_or_fail)

#### Core Functions

- `dp.create_streaming_table()` - Continuous processing
- `dp.create_auto_cdc_flow()` - Change data capture
- `dp.create_auto_cdc_from_snapshot_flow()` - Change data capture from database snapshots
- `dp.create_sink()` - Write to alternative targets (Kafka, Event Hubs, external Delta tables)
- `dp.append_flow()` - Append-only patterns
- `dp.read()`/`dp.read_stream()` - Read from other pipeline datasets (deprecated - always use `spark.read.table()` or `spark.readStream.table()` instead)

#### Critical Rules

- ✅ Dataset functions MUST return Spark DataFrames
- ✅ Use `spark.read.table`/`spark.readStream.table` (NOT dp.read* and NOT dlt.read*)
- ✅ Use `auto_cdc` API (NOT apply_changes)
- ✅ Look up documentation for decorator/function parameters when unsure
- ❌ Do not use star imports
- ❌ NEVER use .collect(), .count(), .toPandas(), .save(), .saveAsTable(), .start(), .toTable()
- ❌ AVOID custom monitoring in dataset definitions
- ❌ Keep functions pure (evaluated multiple times)
- ❌ NEVER use the "LIVE." prefix when reading other datasets (deprecated)
- ❌ No arbitrary Python logic in dataset definitions - focus on DataFrame operations only

#### Python-Specific Considerations

**Reading Pipeline Datasets:**

When reading from other datasets defined in the pipeline, use the dataset's **dataset name directly** - NEVER use the `LIVE.` prefix:

```python
# ✅ CORRECT - use the function name directly
customers = spark.read.table("bronze_customers")
transactions = spark.readStream.table("bronze_transactions")

# ❌ WRONG - do NOT use "LIVE." prefix (deprecated)
customers = spark.read.table("LIVE.bronze_customers")
transactions = spark.readStream.table("LIVE.bronze_transactions")
```

The `LIVE.` prefix is deprecated and should never be used. The pipeline automatically resolves dataset references by dataset name.

**Streaming vs. Batch Semantics:**

- Use `spark.read.table()` (or deprecated `dp.read()`/`dlt.read()`) for batch processing (materialized views with full refresh or incremental computation)
- Use `spark.readStream.table()` (or deprecated `dp.read_stream()`/`dlt.read_stream()`) for streaming tables to enable continuous incremental processing
- **Materialized views**: Use `@dp.materialized_view()` decorator (recommended) with batch DataFrame (`spark.read`)
- **Streaming tables**: Use `@dp.table()` decorator with streaming DataFrame (`spark.readStream`)
- Note: The `@dp.table()` decorator can create both batch and streaming tables based on return type, but `@dp.materialized_view()` is preferred for materialized views

#### Auto Loader Rules

Auto Loader (`cloudFiles`) is recommended for ingesting from cloud storage.
**Relevant APIs:**

- `spark.readStream.format("cloudFiles")`
- `cloudFiles.*` options (format, schemaLocation, etc.)

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read ALL the following reference files:

1. [auto-loader-python.md](auto-loader-python.md)
2. Always look up format-specific options for the format being loaded
3. [streaming-table-python.md](streaming-table-python.md) (when Auto Loader is used with streaming tables)

NO exceptions — always read these reference files first.

#### Materialized View Rules

Materialized Views in Spark Declarative Pipelines enable batch processing with full refresh or incremental computation on serverless pipelines.

**Relevant APIs:**

- `@dp.materialized_view()` - **Recommended** for creating materialized views
- `@dp.table()` or `@dlt.table()` that return batch DataFrames (using `spark.read` or deprecated `dp.read()`/`dlt.read()`) - Legacy approach, still works but `@dp.materialized_view()` is preferred

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read the following reference file:

1. [materialized-view-python.md](materialized-view-python.md)

NO exceptions — always read this reference file first.

#### Streaming Table Rules

Streaming Tables in Spark Declarative Pipelines enable incremental processing of continuously arriving data.
Backfilling allows retroactively processing historical data using append flows with `once=True` - see "streamingTable" API guide for details.

**Relevant APIs:**

- `@dp.table()` or `@dlt.table()` that return streaming DataFrames (using `spark.readStream` or deprecated `dp.read_stream()`/`dlt.read_stream()`)
- `dp.create_streaming_table()` or `dlt.create_streaming_table()`
- `@dp.append_flow` or `@dlt.append_flow`

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read the following reference file:

1. [streaming-table-python.md](streaming-table-python.md)

NO exceptions — always read this reference file first.

#### Temporary View Rules

Temporary views in Spark Declarative Pipelines are non-materialized views that exist only during the execution of a pipeline and are private to the pipeline.

**Relevant APIs:**

- `@dp.view()` or `@dlt.view()`

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read the following reference file:

1. [temporary-view-python.md](temporary-view-python.md)

NO exceptions — always read this reference file first.

**NOTE:** Python only supports temporary views (private to pipeline). Persistent views published to Unity Catalog are NOT supported in Python - use SQL `CREATE VIEW` syntax instead, more details are available in [view-sql.md](view-sql.md).

#### Auto CDC/Apply Changes Rules

Auto CDC in Spark Declarative Pipelines processes change data capture (CDC) events from streaming sources or snapshots. Use Auto CDC when:

- Tracking changes over time or maintaining current/latest state of records
- Processing updates, upserts, or modifications based on a sequence column (timestamp, version)
- Need to "replace old records" or "keep only current/latest version"
- Handling change events, database changes, or CDC feeds
- Working with out-of-sequence records or slowly changing dimensions (SCD Type 1/2)

**Relevant APIs:**

- `dp.create_auto_cdc_flow()` or `dlt.create_auto_cdc_flow()`
- `dp.apply_changes()` or `dlt.apply_changes()`
- `dp.create_auto_cdc_from_snapshot_flow()` or `dlt.create_auto_cdc_from_snapshot_flow()`
- `dp.apply_changes_from_snapshot()` or `dlt.apply_changes_from_snapshot()`

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read ALL the following reference files:

1. [auto-cdc-python.md](auto-cdc-python.md)
2. [streaming-table-python.md](streaming-table-python.md) (since Auto CDC always requires a streaming table as a target)

NO exceptions — always read these reference files first.

#### Data Quality Expectations Rules

Expectations in Spark Declarative Pipelines apply data quality constraints using SQL Boolean expressions. Use them to validate records in tables and views.

**Relevant APIs:**

- `@dp.expect` or `@dlt.expect`
- `@dp.expect_or_drop` or `@dlt.expect_or_drop`
- `@dp.expect_or_fail` or `@dlt.expect_or_fail`
- `@dp.expect_all` or `@dlt.expect_all`
- `@dp.expect_all_or_drop` or `@dlt.expect_all_or_drop`
- `@dp.expect_all_or_fail` or `@dlt.expect_all_or_fail`

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read the following reference file:

1. [expectations-python.md](expectations-python.md)

NO exceptions — always read this reference file first.

#### Sink Rules

Sinks in Spark Declarative Pipelines enable writing data to alternative targets like event streaming services (Apache Kafka, Azure Event Hubs), external Delta tables, or custom data sources. Use sinks when:

- Writing to event streaming services for real-time operational scenarios (fraud detection, analytics, recommendations)
- Exporting to externally-managed Delta tables in Unity Catalog
- Performing reverse ETL into systems outside Databricks
- Streaming data to custom destinations using Python code

**Relevant APIs:**

- `dp.create_sink()` or `dlt.create_sink()`
- `@dp.append_flow()` or `@dlt.append_flow()` with `target` parameter

**MANDATORY:** Before implementing, editing, or suggesting any code involving the above relevant APIs, you MUST read ALL the following reference files:

1. [sink-python.md](sink-python.md)
2. [streaming-table-python.md](streaming-table-python.md) (since sinks work exclusively with streaming append flows)

NO exceptions — always read these reference files first.

**NOTE:** Sinks are Python-only in Spark Declarative Pipelines. SQL does not support sinks.
