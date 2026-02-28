---
name: databricks-pipelines
description: Develop Lakeflow Spark Declarative Pipelines (formerly Delta Live Tables) on Databricks. Use when building batch or streaming data pipelines with Python or SQL. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= v0.288.0)
metadata:
  version: "0.1.0"
parent: databricks
---

# Lakeflow Spark Declarative Pipelines Development

**FIRST**: Use the parent `databricks` skill for CLI basics, authentication, profile selection, and data exploration commands.

Lakeflow Spark Declarative Pipelines (formerly Delta Live Tables / DLT) is a framework for building batch and streaming data pipelines.

## Project Structure

```
my-pipeline-project/
├── databricks.yml                        # Bundle configuration
├── resources/
│   ├── my_pipeline.pipeline.yml          # Pipeline definition
│   └── my_pipeline_job.job.yml           # Scheduling job (optional)
└── src/
    ├── my_table.py (or .sql)             # One dataset per file
    ├── another_table.py (or .sql)
    └── ...
```

By convention, each dataset definition should be in a file named like the dataset, e.g. `src/my_table.py`.

## Adding Transformations

**Python** — Create `.py` files in `src/`:

```python
from pyspark import pipelines as dp

@dp.table
def my_table():
    return spark.read.table("catalog.schema.source")
```

Note: `from pyspark import pipelines as dp` is the preferred import. `import dlt` also works but is deprecated.

**SQL** — Create `.sql` files in `src/`:

```sql
CREATE MATERIALIZED VIEW my_view AS
SELECT * FROM catalog.schema.source
```

Use `CREATE STREAMING TABLE` for incremental ingestion, `CREATE MATERIALIZED VIEW` for batch transformations.

## Key Concepts

| Concept | Python | SQL | Use Case |
|---------|--------|-----|----------|
| Materialized View | `@dp.materialized_view()` | `CREATE MATERIALIZED VIEW` | Batch transformations |
| Streaming Table | `@dp.table()` (streaming DF) | `CREATE STREAMING TABLE` | Incremental ingestion |
| Temporary View | `@dp.view()` | `CREATE TEMPORARY VIEW` | Intermediate logic (pipeline-private) |
| View | — | `CREATE VIEW` | Reusable logic (published to UC) |
| Auto Loader | `spark.readStream.format("cloudFiles")` | `read_files()` | Ingest from cloud storage |
| Auto CDC | `dp.create_auto_cdc_flow()` | `AUTO CDC INTO` | Change data capture |
| Expectations | `@dp.expect()` | `CONSTRAINT ... EXPECT` | Data quality |
| Sink | `dp.create_sink()` | — | Write to Kafka, Event Hubs, external Delta |

## Critical Rules

### Python
- Functions MUST return Spark DataFrames — never call `.collect()`, `.count()`, `.toPandas()`, `.save()`, `.saveAsTable()`, `.start()`, `.toTable()`
- Use `spark.read.table()` / `spark.readStream.table()` to read other datasets
- Never use `LIVE.` prefix (deprecated)

### SQL
- Use `CREATE OR REFRESH` syntax
- Use `STREAM` keyword for streaming reads
- Use `read_files()` for Auto Loader
- Never use `LIVE.` prefix or `CREATE LIVE TABLE` (deprecated)

## Scheduling Pipelines

To schedule a pipeline, add a job that triggers it in `resources/<name>.job.yml`:

```yaml
resources:
  jobs:
    my_pipeline_job:
      trigger:
        periodic:
          interval: 1
          unit: DAYS
      tasks:
        - task_key: refresh_pipeline
          pipeline_task:
            pipeline_id: ${resources.pipelines.my_pipeline.id}
```

## Development Workflow

1. **Validate**: `databricks bundle validate --profile <profile>`
2. **Deploy**: `databricks bundle deploy -t dev --profile <profile>`
3. **Run pipeline**: `databricks bundle run <pipeline_name> -t dev --profile <profile>`
4. **Check status**: `databricks pipelines get --pipeline-id <id> --profile <profile>`

## Documentation

- Lakeflow Spark Declarative Pipelines: https://docs.databricks.com/ldp
- Databricks Asset Bundles: https://docs.databricks.com/dev-tools/bundles/examples

## Pipeline API Reference

Detailed reference guides for each pipeline API:

- [Write Spark Declarative Pipelines](references/write-spark-declarative-pipelines.md) - Core syntax and rules
- [Python basics](references/python-basics.md) - Python decorators, functions, and critical rules
- [SQL basics](references/sql-basics.md) - SQL statements and critical rules
- [Streaming Tables (Python)](references/streaming-table-python.md) - `@dp.table()`, `dp.create_streaming_table()`, `@dp.append_flow()`
- [Streaming Tables (SQL)](references/streaming-table-sql.md) - `CREATE STREAMING TABLE`, `CREATE FLOW`
- [Materialized Views (Python)](references/materialized-view-python.md) - `@dp.materialized_view()`
- [Materialized Views (SQL)](references/materialized-view-sql.md) - `CREATE MATERIALIZED VIEW`
- [Views (SQL)](references/view-sql.md) - `CREATE VIEW` (published to Unity Catalog)
- [Temporary Views (Python)](references/temporary-view-python.md) - `@dp.view()`
- [Temporary Views (SQL)](references/temporary-view-sql.md) - `CREATE TEMPORARY VIEW`
- [Auto Loader (Python)](references/auto-loader-python.md) - `cloudFiles` format for file ingestion
- [Auto Loader (SQL)](references/auto-loader-sql.md) - `read_files()` for file ingestion
- [Auto Loader options: JSON](references/options-json.md), [CSV](references/options-csv.md), [XML](references/options-xml.md), [Parquet](references/options-parquet.md), [Avro](references/options-avro.md), [Text](references/options-text.md), [ORC](references/options-orc.md)
- [Auto CDC (Python)](references/auto-cdc-python.md) - `dp.create_auto_cdc_flow()`
- [Auto CDC (SQL)](references/auto-cdc-sql.md) - `AUTO CDC INTO`
- [Expectations (Python)](references/expectations-python.md) - Data quality decorators
- [Expectations (SQL)](references/expectations-sql.md) - Data quality constraints
- [Sinks (Python)](references/sink-python.md) - `dp.create_sink()` for Kafka, Event Hubs, external Delta
