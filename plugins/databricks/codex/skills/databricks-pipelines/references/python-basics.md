# Python Basics

## Setup

- `from pyspark import pipelines as dp` — required at the top. Legacy `import dlt` still parses but should be migrated (see [SKILL.md Legacy DLT Syntax](../SKILL.md#legacy-dlt-syntax--always-migrate)).
- `spark` (SparkSession) is pre-imported in pipeline files. In utility modules, import it normally.

## Core decorators

- `@dp.materialized_view()` — batch table. See [materialized-view-python.md](materialized-view-python.md).
- `@dp.table()` — streaming table when the function returns a streaming DataFrame. (Returns-batch-DataFrame is legacy DLT shape — use `@dp.materialized_view` instead.) See [streaming-table-python.md](streaming-table-python.md).
- `@dp.temporary_view()` — pipeline-scoped view. See [temporary-view-python.md](temporary-view-python.md).
- `@dp.expect*()` — quality constraints. See [expectations-python.md](expectations-python.md).
- `@dp.append_flow(target=..., once=...)` — fan multiple sources into one target. See [streaming-table-python.md](streaming-table-python.md).
- `@dp.foreach_batch_sink()` — custom per-batch Python sink (Public Preview). See [foreach-batch-sink-python.md](foreach-batch-sink-python.md).

## Core functions

- `dp.create_streaming_table()` — empty target for `@dp.append_flow` / `dp.create_auto_cdc_flow`. See [streaming-table-python.md](streaming-table-python.md).
- `dp.create_auto_cdc_flow()` / `dp.create_auto_cdc_from_snapshot_flow()` — CDC. See [auto-cdc-python.md](auto-cdc-python.md).
- `dp.create_sink()` — external Delta / Kafka / Event Hubs sinks. See [sink-python.md](sink-python.md).

## Reading datasets

- Batch sibling table: `spark.read.table("name")`.
- Streaming sibling table: `spark.readStream.table("name")`.
- **Never** use the `LIVE.` prefix — fully deprecated, errors in modern pipelines.
- `dp.read()` / `dp.read_stream()` are legacy — always use `spark.read.table(...)` / `spark.readStream.table(...)`.

## Critical rules

- ✅ Dataset functions return a Spark DataFrame.
- ✅ Use the modern `auto_cdc` API, not `apply_changes`.
- ✅ Look up parameter docs when unsure — many decorators have nuanced options.
- ❌ Never call `.collect()`, `.count()`, `.toPandas()`, `.save()`, `.saveAsTable()`, `.start()`, `.toTable()` inside a dataset function. The pipeline owns the write side.
- ❌ No custom monitoring or side effects in dataset functions — they may be evaluated multiple times. Keep them pure DataFrame definitions.
- ❌ No star imports.

## `skipChangeCommits`

When a downstream streaming table reads from an upstream streaming table that has updates/deletes (GDPR purges, Auto CDC targets), set `skipChangeCommits` to ignore the change commits — without it, they cause errors:

```python
@dp.table()
def downstream():
    return spark.readStream.option("skipChangeCommits", "true").table("upstream_table")
```
