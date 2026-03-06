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
│   └── sample_job.job.yml                # Scheduling job (optional)
└── src/
    └── my_pipeline/
        └── transformations/
            ├── my_table.py (or .sql)     # One dataset per file
            ├── another_table.py (or .sql)
            └── ...
```

By convention, each dataset definition should be in a file named like the dataset, e.g. `transformations/my_table.py`. Resource files use the naming convention `<resource_key>.pipeline.yml`.

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

To schedule a pipeline, add a job that triggers it in `resources/sample_job.job.yml`:

```yaml
resources:
  jobs:
    sample_job:
      name: sample_job

      trigger:
        periodic:
          interval: 1
          unit: DAYS

      parameters:
        - name: catalog
          default: ${var.catalog}
        - name: schema
          default: ${var.schema}

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

- **MANDATORY** [Write Spark Declarative Pipelines](references/write-spark-declarative-pipelines.md) - Core syntax and rules ([Python](references/python-basics.md), [SQL](references/sql-basics.md)). **Always read before writing any pipeline code.**
- [Streaming Tables](references/streaming-table.md) - Continuous data stream processing with exactly-once semantics
- [Materialized Views](references/materialized-view.md) - Physically stored query results with incremental refresh
- [Views](references/view.md) - Reusable query logic published to Unity Catalog (SQL only)
- [Temporary Views](references/temporary-view.md) - Pipeline-private views not published to Unity Catalog
- [Auto Loader](references/auto-loader.md) - Incrementally ingest files from cloud storage into Delta Lake
- [Auto CDC](references/auto-cdc.md) - Process Change Data Capture feeds (SCD Type 1 & 2)
- [Expectations](references/expectations.md) - Define and enforce data quality constraints
- [Sinks](references/sink.md) - Write to Kafka, Event Hubs, external Delta tables (Python only)
