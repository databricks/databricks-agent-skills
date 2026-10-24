---
name: databricks-jobs
description: Develop and deploy Lakeflow Jobs on Databricks via DABs, Python SDK, or the CLI. Use when creating data engineering jobs with notebooks, Python wheels, SQL, dbt, or pipelines. Invoke BEFORE starting implementation. For compute (serverless, performance mode, classic), also use databricks-serverless.
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.3.0"
parent: databricks-core
---

# Lakeflow Jobs Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, profile selection, and data exploration commands.

**Compute**: jobs run on serverless by default. Before you choose compute or write any cluster setting, use the
`databricks-serverless` skill; it decides serverless or classic and the performance mode.

Lakeflow Jobs orchestrate data workflows with multi-task DAGs, flexible triggers, and comprehensive monitoring. Jobs support diverse task types and can be managed via Declarative Automation Bundles (DABs), Python SDK, or CLI.

## Reference Files

| Use Case | Reference File |
|----------|----------------|
| Configure task types (notebook, Python, SQL, dbt, pipeline, JAR, run_job, for_each) | [references/task-types.md](references/task-types.md) |
| Set up triggers and schedules (cron, periodic, file arrival, table update, continuous) | [references/triggers-schedules.md](references/triggers-schedules.md) |
| Configure notifications, health rules, retries, timeouts, queues | [references/notifications-monitoring.md](references/notifications-monitoring.md) |
| Complete worked examples (ETL, warehouse refresh, event-driven, ML training, multi-env, streaming, cross-job) | [references/examples.md](references/examples.md) |

## Scaffolding a New Job Project

Use `databricks bundle init` with a config file to scaffold non-interactively. This creates a project in the `<project_name>/` directory:

```bash
databricks bundle init default-python --config-file <(echo '{"project_name": "my_job", "include_job": "yes", "include_pipeline": "no", "include_python": "yes", "serverless": "yes"}') --profile <PROFILE> < /dev/null
```

- `project_name`: letters, numbers, underscores only

`bundle init` also creates an `AGENTS.md` in the project. Customize that file for the project
instead of creating new agent instruction files.

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

### Declarative Automation Bundles (DABs) — recommended

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
      # no cluster block = serverless; compute details: databricks-serverless
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
| `notebook_task` | Run notebooks | [references/task-types.md#notebook-task](references/task-types.md#notebook-task) |
| `spark_python_task` | Run Python scripts | [references/task-types.md#spark-python-task](references/task-types.md#spark-python-task) |
| `python_wheel_task` | Run Python wheels | [references/task-types.md#python-wheel-task](references/task-types.md#python-wheel-task) |
| `sql_task` | Run SQL queries/files/dashboards/alerts | [references/task-types.md#sql-task](references/task-types.md#sql-task) |
| `dbt_task` | Run dbt projects | [references/task-types.md#dbt-task](references/task-types.md#dbt-task) |
| `pipeline_task` | Trigger SDP (formerly DLT) pipelines | [references/task-types.md#pipeline-task](references/task-types.md#pipeline-task) |
| `spark_jar_task` | Run Spark JARs | [references/task-types.md#spark-jar-task](references/task-types.md#spark-jar-task) |
| `run_job_task` | Trigger other jobs | [references/task-types.md#run-job-task](references/task-types.md#run-job-task) |
| `for_each_task` | Loop over inputs | [references/task-types.md#for-each-task](references/task-types.md#for-each-task) |

### Trigger Types Summary

| Trigger Type | Use Case | Reference |
|--------------|----------|-----------|
| `schedule` | Cron-based scheduling | [references/triggers-schedules.md#cron-schedule](references/triggers-schedules.md#cron-schedule) |
| `trigger.periodic` | Interval-based | [references/triggers-schedules.md#periodic-trigger](references/triggers-schedules.md#periodic-trigger) |
| `trigger.file_arrival` | File arrival events | [references/triggers-schedules.md#file-arrival-trigger](references/triggers-schedules.md#file-arrival-trigger) |
| `trigger.table_update` | Unity Catalog table change events | [references/triggers-schedules.md#table-update-trigger](references/triggers-schedules.md#table-update-trigger) |
| `continuous` | Always-running jobs | [references/triggers-schedules.md#continuous-jobs](references/triggers-schedules.md#continuous-jobs) |

## Compute Configuration

Serverless is the default. Leave out cluster settings (`job_clusters`, `new_cluster`, `job_cluster_key`,
`existing_cluster_id`); a notebook, Python script, wheel or JAR task without them runs on serverless.
SQL tasks, and the SQL of dbt tasks, run on a SQL warehouse (`warehouse_id`, see
[Task Types](references/task-types.md)); a pipeline task runs on the pipeline's own compute
(`serverless: true` in the pipeline), and the job's `performance_target` sets its mode.
If creating or running the job fails because serverless is not available in the workspace, put the
whole job on classic and say so (job clusters for the tasks that run on job compute).

For everything else about compute, **use the `databricks-serverless` skill**: the performance mode
(`performance_target`), libraries (`environments`), existing code that may not run on serverless, and
the few workloads that need a classic cluster. If that skill is not installed, run
`databricks aitools install`. Either way, set `performance_target` on every job: `STANDARD` to optimize
cost, `PERFORMANCE_OPTIMIZED` when the job is time-sensitive, interactive, or other workloads depend on it.

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

### Declarative Automation Bundle Operations

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
| Serverless job startup slow | `performance_target: PERFORMANCE_OPTIMIZED`; see databricks-serverless |
| Task dependencies not working | Verify `task_key` references match exactly in `depends_on` |
| Schedule not triggering | Check `pause_status: UNPAUSED` and valid timezone |
| File arrival not detecting | Ensure path has proper permissions and uses cloud storage URL |
| Table update trigger missing events | Verify Unity Catalog table and proper grants |
| Parameter not accessible | Use `dbutils.widgets.get()` in notebooks |
| `admins` group error | Cannot modify admins permissions on jobs |
| Serverless task fails | See the Common Issues of databricks-serverless (libraries, RDD code, DBFS mounts) |

## Related Skills

- **databricks-dabs** — DABs configuration patterns shared by jobs and pipelines
- **databricks-pipelines** — SDP (formerly DLT) pipelines triggered by `pipeline_task`
- **databricks-serverless** — compute decisions: serverless, performance mode, classic fallback

## Documentation

- [Lakeflow Jobs](https://docs.databricks.com/jobs)
- [Task types](https://docs.databricks.com/jobs/configure-task)
- [Declarative Automation Bundles](https://docs.databricks.com/dev-tools/bundles/)
- [Jobs API Reference](https://docs.databricks.com/api/jobs/v2/job)
- [Bundle Examples Repository](https://github.com/databricks/bundle-examples)
