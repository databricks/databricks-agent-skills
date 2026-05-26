---
name: databricks-jobs
description: Develop and deploy Lakeflow Jobs on Databricks via DABs, Python SDK, or the CLI. Use when creating data engineering jobs with notebooks, Python wheels, SQL, dbt, or pipelines. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.2.0"
parent: databricks-core
---

# Lakeflow Jobs Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, profile selection, and data exploration commands.

Lakeflow Jobs orchestrate data workflows with multi-task DAGs, flexible triggers, and comprehensive monitoring. Jobs support diverse task types and can be managed via Asset Bundles (DABs), Python SDK, or CLI.

## Reference Files

| Use Case | Reference File |
|----------|----------------|
| Configure task types (notebook, Python, SQL, dbt, pipeline, JAR, run_job, for_each) | [task-types.md](task-types.md) |
| Set up triggers and schedules (cron, periodic, file arrival, table update, continuous) | [triggers-schedules.md](triggers-schedules.md) |
| Configure notifications, health rules, retries, timeouts, queues | [notifications-monitoring.md](notifications-monitoring.md) |
| Complete worked examples (ETL, warehouse refresh, event-driven, ML training, multi-env, streaming, cross-job) | [examples.md](examples.md) |

## Scaffolding a New Job Project

Use `databricks bundle init` with a config file to scaffold non-interactively. This creates a project in the `<project_name>/` directory:

```bash
databricks bundle init default-python --config-file <(echo '{"project_name": "my_job", "include_job": "yes", "include_pipeline": "no", "include_python": "yes", "serverless": "yes"}') --profile <PROFILE> < /dev/null
```

- `project_name`: letters, numbers, underscores only

After scaffolding, create `CLAUDE.md` and `AGENTS.md` in the project directory. These files are essential to provide agents with guidance on how to work with the project. Use this content:

```
# Declarative Automation Bundles Project

This project uses Declarative Automation Bundles (formerly Databricks Asset Bundles) for deployment.

## Prerequisites

Install the Databricks CLI (>= v0.288.0) if not already installed:
- macOS: `brew tap databricks/tap && brew install databricks`
- Linux: `curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh`
- Windows: `winget install Databricks.DatabricksCLI`

Verify: `databricks -v`

## For AI Agents

Read the `databricks-core` skill for CLI basics, authentication, and deployment workflow.
Read the `databricks-jobs` skill for job-specific guidance.

If skills are not available, install them: `databricks aitools install`
```

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
└── pyproject.toml              # Python project config (if using wheels)
```

## Quick Start

### Asset Bundles (DABs) — recommended

```yaml
# resources/jobs.yml
resources:
  jobs:
    my_etl_job:
      name: "[${bundle.target}] My ETL Job"
      tasks:
        - task_key: extract
          notebook_task:
            notebook_path: ../src/notebooks/extract.py
```

### Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import Task, NotebookTask, Source

w = WorkspaceClient()

job = w.jobs.create(
    name="my-etl-job",
    tasks=[
        Task(
            task_key="extract",
            notebook_task=NotebookTask(
                notebook_path="/Workspace/Shared/etl/extract",
                source=Source.WORKSPACE,
            ),
        ),
    ],
)
print(f"Created job: {job.job_id}")
```

### CLI

```bash
databricks jobs create --json '{
  "name": "my-etl-job",
  "tasks": [{
    "task_key": "extract",
    "notebook_task": {
      "notebook_path": "/Workspace/Shared/etl/extract",
      "source": "WORKSPACE"
    }
  }]
}'
```

## Core Concepts

### Multi-Task Workflows

Jobs support DAG-based task dependencies:

```yaml
tasks:
  - task_key: extract
    notebook_task:
      notebook_path: ../src/extract.py

  - task_key: transform
    depends_on:
      - task_key: extract
    notebook_task:
      notebook_path: ../src/transform.py

  - task_key: load
    depends_on:
      - task_key: transform
    run_if: ALL_SUCCESS  # Only run if all dependencies succeed
    notebook_task:
      notebook_path: ../src/load.py
```

**run_if conditions:**

- `ALL_SUCCESS` (default) — run when all dependencies succeed
- `ALL_DONE` — run when all dependencies complete (success or failure)
- `AT_LEAST_ONE_SUCCESS` — run when at least one dependency succeeds
- `NONE_FAILED` — run when no dependencies failed
- `ALL_FAILED` — run when all dependencies failed
- `AT_LEAST_ONE_FAILED` — run when at least one dependency failed

### Task Types Summary

| Task Type | Use Case | Reference |
|-----------|----------|-----------|
| `notebook_task` | Run notebooks | [task-types.md#notebook-task](task-types.md#notebook-task) |
| `spark_python_task` | Run Python scripts | [task-types.md#spark-python-task](task-types.md#spark-python-task) |
| `python_wheel_task` | Run Python wheels | [task-types.md#python-wheel-task](task-types.md#python-wheel-task) |
| `sql_task` | Run SQL queries/files/dashboards/alerts | [task-types.md#sql-task](task-types.md#sql-task) |
| `dbt_task` | Run dbt projects | [task-types.md#dbt-task](task-types.md#dbt-task) |
| `pipeline_task` | Trigger SDP (formerly DLT) pipelines | [task-types.md#pipeline-task](task-types.md#pipeline-task) |
| `spark_jar_task` | Run Spark JARs | [task-types.md#spark-jar-task](task-types.md#spark-jar-task) |
| `run_job_task` | Trigger other jobs | [task-types.md#run-job-task](task-types.md#run-job-task) |
| `for_each_task` | Loop over inputs | [task-types.md#for-each-task](task-types.md#for-each-task) |

### Trigger Types Summary

| Trigger Type | Use Case | Reference |
|--------------|----------|-----------|
| `schedule` | Cron-based scheduling | [triggers-schedules.md#cron-schedule](triggers-schedules.md#cron-schedule) |
| `trigger.periodic` | Interval-based | [triggers-schedules.md#periodic-trigger](triggers-schedules.md#periodic-trigger) |
| `trigger.file_arrival` | File arrival events | [triggers-schedules.md#file-arrival-trigger](triggers-schedules.md#file-arrival-trigger) |
| `trigger.table_update` | Unity Catalog table change events | [triggers-schedules.md#table-update-trigger](triggers-schedules.md#table-update-trigger) |
| `continuous` | Always-running jobs | [triggers-schedules.md#continuous-jobs](triggers-schedules.md#continuous-jobs) |

## Compute Configuration

### Job Clusters (recommended)

Define reusable cluster configurations shared across tasks:

```yaml
job_clusters:
  - job_cluster_key: shared_cluster
    new_cluster:
      spark_version: "15.4.x-scala2.12"
      node_type_id: "i3.xlarge"
      num_workers: 2
      spark_conf:
        spark.speculation: "true"

tasks:
  - task_key: my_task
    job_cluster_key: shared_cluster
    notebook_task:
      notebook_path: ../src/notebook.py
```

### Autoscaling Clusters

```yaml
new_cluster:
  spark_version: "15.4.x-scala2.12"
  node_type_id: "i3.xlarge"
  autoscale:
    min_workers: 2
    max_workers: 8
```

### Existing Cluster

```yaml
tasks:
  - task_key: my_task
    existing_cluster_id: "0123-456789-abcdef12"
    notebook_task:
      notebook_path: ../src/notebook.py
```

### Serverless Compute

For notebook and Python tasks, omit cluster configuration to use serverless:

```yaml
tasks:
  - task_key: serverless_task
    notebook_task:
      notebook_path: ../src/notebook.py
    # No cluster config = serverless
```

## Job Parameters

Parameters defined at job level are passed to ALL tasks (no need to repeat per task):

```yaml
parameters:
  - name: env
    default: "dev"
  - name: date
    default: "{{start_date}}"  # Dynamic value reference
```

Access in notebooks:

```python
catalog = dbutils.widgets.get("env")
load_date = dbutils.widgets.get("date")
```

Pass to specific tasks:

```yaml
tasks:
  - task_key: my_task
    notebook_task:
      notebook_path: ../src/notebook.py
      base_parameters:
        env: "{{job.parameters.env}}"
        custom_param: "value"
```

## Common Operations

### Python SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# List jobs
jobs = w.jobs.list()

# Get job details
job = w.jobs.get(job_id=12345)

# Run job now
run = w.jobs.run_now(job_id=12345)

# Run with parameters
run = w.jobs.run_now(
    job_id=12345,
    job_parameters={"env": "prod", "date": "2024-01-15"},
)

# Cancel run
w.jobs.cancel_run(run_id=run.run_id)

# Delete job
w.jobs.delete(job_id=12345)
```

### CLI

```bash
# List jobs
databricks jobs list

# Get job details
databricks jobs get 12345

# Run job
databricks jobs run-now 12345

# Run with parameters (must use --json with job_id inside)
databricks jobs run-now --json '{"job_id": 12345, "job_parameters": {"env": "prod"}}'

# Cancel run
databricks jobs cancel-run 67890

# Delete job
databricks jobs delete 12345
```

### Asset Bundle Operations

```bash
# Validate configuration
databricks bundle validate --profile <profile>

# Deploy to a target
databricks bundle deploy -t dev --profile <profile>

# Run a job
databricks bundle run <job_name> -t dev --profile <profile>

# Check run status
databricks jobs get-run --run-id <id> --profile <profile>

# Destroy resources
databricks bundle destroy --auto-approve
```

## Permissions (DABs)

```yaml
resources:
  jobs:
    my_job:
      name: "My Job"
      permissions:
        - level: CAN_VIEW
          group_name: "data-analysts"
        - level: CAN_MANAGE_RUN
          group_name: "data-engineers"
        - level: CAN_MANAGE
          user_name: "admin@example.com"
```

**Permission levels:**

- `CAN_VIEW` — view job and run history
- `CAN_MANAGE_RUN` — view, trigger, and cancel runs
- `CAN_MANAGE` — full control including edit and delete

## Unit Testing

Run unit tests locally:

```bash
uv run pytest
```

## Development Workflow

1. **Validate**: `databricks bundle validate --profile <profile>`
2. **Deploy**: `databricks bundle deploy -t dev --profile <profile>`
3. **Run**: `databricks bundle run <job_name> -t dev --profile <profile>`
4. **Check run status**: `databricks jobs get-run --run-id <id> --profile <profile>`

## Common Issues

| Issue | Solution |
|-------|----------|
| Job cluster startup slow | Use job clusters with `job_cluster_key` for reuse across tasks |
| Task dependencies not working | Verify `task_key` references match exactly in `depends_on` |
| Schedule not triggering | Check `pause_status: UNPAUSED` and valid timezone |
| File arrival not detecting | Ensure path has proper permissions and uses cloud storage URL |
| Table update trigger missing events | Verify Unity Catalog table and proper grants |
| Parameter not accessible | Use `dbutils.widgets.get()` in notebooks |
| `admins` group error | Cannot modify admins permissions on jobs |
| Serverless task fails | Ensure task type supports serverless (notebook, Python) |

## Related Skills

- **databricks-dabs** — DABs configuration patterns shared by jobs and pipelines
- **databricks-pipelines** — SDP (formerly DLT) pipelines triggered by `pipeline_task`

## Documentation

- [Lakeflow Jobs](https://docs.databricks.com/jobs)
- [Task types](https://docs.databricks.com/jobs/configure-task)
- [Declarative Automation Bundles](https://docs.databricks.com/dev-tools/bundles/)
- [Jobs API Reference](https://docs.databricks.com/api/workspace/jobs)
- [Bundle Examples Repository](https://github.com/databricks/bundle-examples)
