---
name: databricks-pipelines
description: Develop Lakeflow Spark Declarative Pipelines (formerly Delta Live Tables) on Databricks. Use when building batch or streaming data pipelines with Python or SQL. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= v0.288.0)
metadata:
  version: "0.1.0"
parent: databricks
---

# Lakeflow Spark Declarative Pipelines Development

**FIRST**: Use the parent `databricks` skill for CLI basics, authentication, profile selection, and data discovery commands.

Lakeflow Spark Declarative Pipelines (formerly Delta Live Tables / DLT) is a framework for building batch and streaming data pipelines.

## Scaffolding a New Pipeline Project

Use `databricks bundle init` with a config file to scaffold non-interactively. This creates a project in the `<project_name>/` directory:

```bash
databricks bundle init lakeflow-pipelines --config-file <(echo '{"project_name": "my_pipeline", "language": "python", "serverless": "yes"}') --profile <PROFILE> < /dev/null
```

- `project_name`: letters, numbers, underscores only
- `language`: `python` or `sql`. Ask the user which they prefer:
  - SQL: Recommended for straightforward transformations (filters, joins, aggregations)
  - Python: Recommended for complex logic (custom UDFs, ML, advanced processing)

After scaffolding, create `CLAUDE.md` and `AGENTS.md` in the project directory. These files are essential to provide agents with guidance on how to work with the project. Use this content:

```
# Databricks Asset Bundles Project

This project uses Databricks Asset Bundles for deployment.

## Prerequisites

Install the Databricks CLI (>= v0.288.0) if not already installed:
- macOS: `brew tap databricks/tap && brew install databricks`
- Linux: `curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh`
- Windows: `winget install Databricks.DatabricksCLI`

Verify: `databricks -v`

## For AI Agents

Read the `databricks` skill for CLI basics, authentication, and deployment workflow.
Read the `databricks-pipelines` skill for pipeline-specific guidance.

If skills are not available, install them: `databricks experimental aitools skills install`
```

## Pipeline Structure

- Follow the medallion architecture pattern (Bronze → Silver → Gold) unless the user specifies otherwise
- Use the convention of 1 dataset per file, named after the dataset
- Place transformation files in a `src/` or `transformations/` folder

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

## Running Pipelines

**You must deploy before running.** In local development, code changes only take effect after `databricks bundle deploy`. Always deploy before any run, dry run, or selective refresh.

- Selective refresh is preferred when you only need to run one table. For selective refresh it is important that dependencies are already materialized.
- **Full refresh is the most expensive and dangerous option, and can lead to data loss**, so it should be used only when really necessary. Always suggest this as a follow-up that the user explicitly needs to select.

## Development Workflow

1. **Validate**: `databricks bundle validate --profile <profile>`
2. **Deploy**: `databricks bundle deploy -t dev --profile <profile>`
3. **Run pipeline**: `databricks bundle run <pipeline_name> -t dev --profile <profile>`
4. **Check status**: `databricks pipelines get --pipeline-id <id> --profile <profile>`

## Pipeline API Reference

Detailed reference guides for each pipeline API. **Read the relevant guide before writing pipeline code.**

- [Write Spark Declarative Pipelines](references/write-spark-declarative-pipelines.md) — Core syntax and rules ([Python](references/python-basics.md), [SQL](references/sql-basics.md))
- [Streaming Tables](references/streaming-table.md) — Continuous data stream processing ([Python](references/streaming-table-python.md), [SQL](references/streaming-table-sql.md))
- [Materialized Views](references/materialized-view.md) — Physically stored query results with incremental refresh ([Python](references/materialized-view-python.md), [SQL](references/materialized-view-sql.md))
- [Views](references/view.md) — Reusable query logic published to Unity Catalog ([SQL](references/view-sql.md))
- [Temporary Views](references/temporary-view.md) — Pipeline-private views ([Python](references/temporary-view-python.md), [SQL](references/temporary-view-sql.md))
- [Auto Loader](references/auto-loader.md) — Incrementally ingest files from cloud storage ([Python](references/auto-loader-python.md), [SQL](references/auto-loader-sql.md))
- [Auto CDC](references/auto-cdc.md) — Process Change Data Capture feeds, SCD Type 1 & 2 ([Python](references/auto-cdc-python.md), [SQL](references/auto-cdc-sql.md))
- [Expectations](references/expectations.md) — Define and enforce data quality constraints ([Python](references/expectations-python.md), [SQL](references/expectations-sql.md))
- [Sinks](references/sink.md) — Write to Kafka, Event Hubs, external Delta tables ([Python](references/sink-python.md))
