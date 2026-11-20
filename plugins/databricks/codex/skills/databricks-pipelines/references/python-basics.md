#### Setup

- `from pyspark import pipelines as dp` (preferred) or `import dlt` (deprecated but still works) is always required on top when doing Python. Use `dp` for new code; don't change existing `dlt` usages unless explicitly asked.
- The SparkSession object is already available (no need to import it again) - unless in a utility file

#### Core Decorators

- `@dp.materialized_view()` - Materialized views (batch processing, recommended for materialized views). See [materialized-view-python.md](materialized-view-python.md).
- `@dp.table()` - Streaming tables (when returning streaming DataFrame) or materialized views (legacy, when returning batch DataFrame). See [streaming-table-python.md](streaming-table-python.md).
- `@dp.temporary_view()` - Temporary views (non-materialized, private to pipeline). See [temporary-view-python.md](temporary-view-python.md).
- `@dp.expect*()` - Data quality constraints (expect, expect_or_drop, expect_or_fail, expect_all, expect_all_or_drop, expect_all_or_fail). See [expectations-python.md](expectations-python.md).

#### Core Functions

- `dp.create_streaming_table()` - Continuous processing; also creates the empty target for `dp.append_flow()` / `dp.create_auto_cdc_flow()`. See [streaming-table-python.md](streaming-table-python.md).
- `dp.create_auto_cdc_flow()` - Change data capture. See [auto-cdc-python.md](auto-cdc-python.md).
- `dp.create_auto_cdc_from_snapshot_flow()` - Change data capture from database snapshots. See [auto-cdc-from-snapshot.md](auto-cdc-from-snapshot.md).
- `dp.create_sink()` - Write to alternative targets (Kafka, Event Hubs, external Delta tables). See [sink-python.md](sink-python.md).
- `@dp.foreach_batch_sink()` - Custom streaming sink with per-batch Python logic (Public Preview). See [foreach-batch-sink-python.md](foreach-batch-sink-python.md).
- `dp.append_flow()` - Append-only patterns; fan multiple sources into one target (`target=`), or run a one-time backfill (`once=True`). See [streaming-table-python.md](streaming-table-python.md).
- `dp.read()`/`dp.read_stream()` - Read from other pipeline datasets (legacy, still supported - prefer `spark.read.table()` or `spark.readStream.table()`)

#### Critical Rules

- ✅ Dataset functions MUST return Spark DataFrames
- ✅ Use `spark.read.table`/`spark.readStream.table` (NOT dp.read* and NOT dlt.read*)
- ✅ Use `auto_cdc` API (NOT apply_changes)
- ✅ Look up documentation for decorator/function parameters when unsure
- ❌ Do not use star imports
- ❌ NEVER use .collect(), .count(), .toPandas(), .save(), .saveAsTable(), .start(), .toTable()
  - The pipeline owns the write side; dataset functions only define the DataFrame.
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

#### skipChangeCommits

When a downstream streaming table reads from an upstream streaming table that has updates or deletes (e.g., GDPR compliance, Auto CDC targets), use `skipChangeCommits` to ignore those change commits. Without it, the change commits cause the downstream stream to fail:

```python
@dp.table()
def downstream():
    return spark.readStream.option("skipChangeCommits", "true").table("upstream_table")
```
