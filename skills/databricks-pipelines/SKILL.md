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

## Schema Definition Guidelines

**Start with schema inference by default.** Always begin with automatic schema inference, even when the user requests manual schema definition. Only add explicit schemas when: (1) after successful inference if user requested it (use inferred schema as basis), or (2) when pipeline fails due to missing schema (add minimal required schema only).

## Changing Dataset Types

Changing an existing dataset's type (e.g., streaming table to materialized view, or vice versa) is NOT possible without the user first manually dropping the existing table. Full refresh does NOT help.

When a user asks to change a dataset type:

1. **Explain the limitation clearly**: you MUST explicitly tell the user that changing the type on the same name will cause the pipeline to **FAIL** unless the existing table is manually dropped first. Also state that full refresh does NOT help. Do not skip or soften this warning.
2. **Rename the dataset by default**: unless the user indicated they already dropped the existing table, create the new dataset with a different name (e.g., append a suffix or use a descriptive new name) so both the old and new datasets can coexist. The old dataset will become inactive once it is no longer defined in code. Do NOT just change the type in-place without renaming — that will fail.
3. **Update all downstream datasets**: after renaming, update every file that references the old dataset name to use the new name. Also ensure downstream datasets use the correct read semantics for the new type (e.g., `spark.read`/direct reference for materialized view sources, `spark.readStream`/`STREAM()` for streaming table sources). Do NOT change the type of downstream datasets — only update their name references and read method.
4. **Offer manual drop as a follow-up**: explicitly suggest as a follow-up action that the user can drop the old table themselves and then rename the new dataset back to the original name if they prefer.

## Running Pipelines

**You must deploy before running.** In local development, code changes only take effect after `databricks bundle deploy`. Always deploy before any run, dry run, or selective refresh.

- Selective refresh is preferred when you only need to run one table. For selective refresh it is important that dependencies are already materialized.
- **Full refresh is the most expensive and dangerous option, and can lead to data loss**, so it should be used only when really necessary. Always suggest this as a follow-up that the user explicitly needs to select.

## Development Workflow

1. **Validate**: `databricks bundle validate --profile <profile>`
2. **Deploy**: `databricks bundle deploy -t dev --profile <profile>`
3. **Run pipeline**: `databricks bundle run <pipeline_name> -t dev --profile <profile>`
4. **Check status**: `databricks pipelines get --pipeline-id <id> --profile <profile>`
