---
name: databricks-jobs
description: "Develop and deploy Lakeflow Jobs on Databricks: create notebook, Python wheel, and SQL tasks, configure schedules and task dependencies, and manage job parameters. Use when creating data engineering jobs with notebooks, Python wheels, or SQL tasks. Invoke BEFORE starting implementation."
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.1.0"
  parent: databricks-core
---

# Lakeflow Jobs Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, profile selection, and data exploration commands.

Lakeflow Jobs are scheduled workflows that run notebooks, Python scripts, SQL queries, and other tasks on Databricks.

## Scaffolding a New Job Project

Use `databricks bundle init` with a config file to scaffold non-interactively. This creates a project in the `<project_name>/` directory:

```bash
databricks bundle init default-python --config-file <(echo '{"project_name": "my_job", "include_job": "yes", "include_pipeline": "no", "include_python": "yes", "serverless": "yes"}') --profile <PROFILE> < /dev/null
```

- `project_name`: letters, numbers, underscores only

After scaffolding, create `CLAUDE.md` and `AGENTS.md` pointing agents to the `databricks-core` and `databricks-jobs` skills.

## Project Structure

```
my-job-project/
├── databricks.yml              # Bundle configuration
├── resources/
│   └── my_job.job.yml          # Job definition
├── src/
│   ├── my_notebook.ipynb       # Notebook tasks
│   └── my_module/              # Python wheel package
│       ├── __init__.py
│       └── main.py
├── tests/
│   └── test_main.py
└── pyproject.toml               # Python project config (if using wheels)
```

## Configuring Tasks

Edit `resources/<job_name>.job.yml`. Task types: `notebook_task`, `python_wheel_task`, `spark_python_task`, `pipeline_task`, `sql_task`. Use `depends_on` for multi-task DAGs. Job-level `parameters` are passed to ALL tasks (access in notebooks via `dbutils.widgets.get("catalog")`).

```yaml
resources:
  jobs:
    my_job:
      name: my_job
      parameters:
        - name: catalog
          default: ${var.catalog}
        - name: schema
          default: ${var.schema}
      trigger:
        periodic:
          interval: 1
          unit: DAYS
      # Or use cron: schedule: { quartz_cron_expression: "0 0 2 * * ?", timezone_id: "UTC" }

      tasks:
        - task_key: extract
          notebook_task:
            notebook_path: ../src/extract.ipynb

        - task_key: transform
          depends_on:
            - task_key: extract
          notebook_task:
            notebook_path: ../src/transform.ipynb

        - task_key: load_wheel
          depends_on:
            - task_key: transform
          python_wheel_task:
            package_name: my_package
            entry_point: main
```

## Unit Testing

Run unit tests locally:

```bash
uv run pytest
```

## Development Workflow

1. **Validate**: `databricks bundle validate --profile <profile>` -- fix any YAML or schema errors before proceeding
2. **Deploy**: `databricks bundle deploy -t dev --profile <profile>` -- if `PERMISSION_DENIED`, check workspace permissions and profile
3. **Run**: `databricks bundle run <job_name> -t dev --profile <profile>`
4. **Check run status**: `databricks jobs get-run --run-id <id> --profile <profile>` -- if `FAILED`, check `run_page_url` for task-level errors

## Documentation

- Lakeflow Jobs: https://docs.databricks.com/jobs
- Task types: https://docs.databricks.com/jobs/configure-task
- Declarative Automation Bundles: https://docs.databricks.com/dev-tools/bundles/
