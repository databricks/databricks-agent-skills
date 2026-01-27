# Jobs

Databricks Jobs provide workflow orchestration for notebooks, Python scripts, JARs, and more.

## Job Commands

### List and Get Jobs

```bash
# List jobs
databricks jobs list --profile my-workspace

# Get job details
databricks jobs get --job-id <job-id> --profile my-workspace
```

### Create Job

```bash
# Create job from JSON config
databricks jobs create --json @job-config.json --profile my-workspace
```

### Update Job

```bash
# Update job configuration
databricks jobs update --job-id <job-id> --json @updated-config.json --profile my-workspace

# Reset job configuration (replaces entire config)
databricks jobs reset --job-id <job-id> --json @new-config.json --profile my-workspace
```

### Delete Job

```bash
# Delete a job
databricks jobs delete --job-id <job-id> --profile my-workspace
```

## Running Jobs

### Run Job Now

```bash
# Run job immediately
databricks jobs run-now --job-id <job-id> --profile my-workspace

# Run with parameters
databricks jobs run-now \
  --job-id <job-id> \
  --notebook-params '{"param1": "value1", "param2": "value2"}' \
  --profile my-workspace
```

### Cancel Job Run

```bash
# Cancel a running job
databricks jobs cancel-run --run-id <run-id> --profile my-workspace
```

### Get Run Details

```bash
# Get job run details
databricks jobs get-run --run-id <run-id> --profile my-workspace

# Get job run output
databricks jobs get-run-output --run-id <run-id> --profile my-workspace
```

### List Job Runs

```bash
# List runs for a specific job
databricks jobs list-runs --job-id <job-id> --profile my-workspace

# List all runs
databricks jobs list-runs --profile my-workspace

# List active runs
databricks jobs list-runs --active-only --profile my-workspace
```

## Job Configuration Examples

### Simple Notebook Job

```json
{
  "name": "Daily ETL Job",
  "tasks": [{
    "task_key": "run_notebook",
    "notebook_task": {
      "notebook_path": "/Users/user@example.com/etl_notebook",
      "source": "WORKSPACE"
    },
    "new_cluster": {
      "spark_version": "13.3.x-scala2.12",
      "node_type_id": "i3.xlarge",
      "num_workers": 2
    }
  }],
  "schedule": {
    "quartz_cron_expression": "0 0 2 * * ?",
    "timezone_id": "UTC"
  }
}
```

### Multi-Task Job with Dependencies

```json
{
  "name": "Data Pipeline Job",
  "tasks": [
    {
      "task_key": "extract",
      "notebook_task": {
        "notebook_path": "/Workspace/notebooks/extract.py",
        "source": "WORKSPACE"
      },
      "new_cluster": {
        "spark_version": "13.3.x-scala2.12",
        "node_type_id": "i3.xlarge",
        "num_workers": 2
      }
    },
    {
      "task_key": "transform",
      "depends_on": [{"task_key": "extract"}],
      "notebook_task": {
        "notebook_path": "/Workspace/notebooks/transform.py",
        "source": "WORKSPACE"
      },
      "new_cluster": {
        "spark_version": "13.3.x-scala2.12",
        "node_type_id": "i3.xlarge",
        "num_workers": 4
      }
    },
    {
      "task_key": "load",
      "depends_on": [{"task_key": "transform"}],
      "notebook_task": {
        "notebook_path": "/Workspace/notebooks/load.py",
        "source": "WORKSPACE"
      },
      "new_cluster": {
        "spark_version": "13.3.x-scala2.12",
        "node_type_id": "i3.xlarge",
        "num_workers": 2
      }
    }
  ]
}
```

### Python Wheel Task

```json
{
  "name": "Python Package Job",
  "tasks": [{
    "task_key": "run_python_wheel",
    "python_wheel_task": {
      "package_name": "my_package",
      "entry_point": "main",
      "parameters": ["--arg1", "value1"]
    },
    "new_cluster": {
      "spark_version": "13.3.x-scala2.12",
      "node_type_id": "i3.xlarge",
      "num_workers": 2
    },
    "libraries": [{
      "whl": "dbfs:/FileStore/wheels/my_package-0.1.0-py3-none-any.whl"
    }]
  }]
}
```

### Job with Existing Cluster

```json
{
  "name": "Job on Existing Cluster",
  "tasks": [{
    "task_key": "run_task",
    "notebook_task": {
      "notebook_path": "/Workspace/notebooks/analysis.py"
    },
    "existing_cluster_id": "<cluster-id>"
  }]
}
```

## Schedule Formats

### Cron Expression

```json
{
  "schedule": {
    "quartz_cron_expression": "0 0 2 * * ?",  // Daily at 2 AM
    "timezone_id": "UTC"
  }
}
```

Common cron patterns:
- `0 0 2 * * ?` - Daily at 2 AM
- `0 0 */6 * * ?` - Every 6 hours
- `0 0 2 ? * MON` - Every Monday at 2 AM
- `0 30 9 ? * MON-FRI` - Weekdays at 9:30 AM

## Managing Jobs with Asset Bundles

### Bundle Job Configuration

```yaml
# resources/jobs/daily_job.yml
resources:
  jobs:
    daily_etl:
      name: "Daily ETL Pipeline"

      tasks:
        - task_key: "extract_data"
          notebook_task:
            notebook_path: "./src/notebooks/extract.py"
            source: WORKSPACE
          new_cluster:
            spark_version: "13.3.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 2

        - task_key: "transform_data"
          depends_on:
            - task_key: "extract_data"
          notebook_task:
            notebook_path: "./src/notebooks/transform.py"
            source: WORKSPACE
          new_cluster:
            spark_version: "13.3.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 4

      schedule:
        quartz_cron_expression: "0 0 2 * * ?"
        timezone_id: "UTC"

      email_notifications:
        on_failure:
          - "team@example.com"
```

### Deploy Job with Bundle

```bash
# Validate
databricks bundle validate --profile my-workspace

# Deploy
databricks bundle deploy -t prod --profile my-workspace

# Run job
databricks bundle run daily_etl -t prod --profile my-workspace
```

## Best Practices

### 1. Use Asset Bundles

Manage jobs as code:
- Version control
- Environment management
- Reproducible deployments

### 2. Structure Multi-Task Jobs

```
extract → transform → load → validate
           ↓
        backup
```

Use dependencies to create workflows:
```json
{
  "depends_on": [{"task_key": "previous_task"}]
}
```

### 3. Use Appropriate Cluster Sizing

```json
{
  "new_cluster": {
    "spark_version": "13.3.x-scala2.12",
    "node_type_id": "i3.xlarge",
    "autoscale": {
      "min_workers": 2,
      "max_workers": 10
    }
  }
}
```

### 4. Set Up Notifications

```json
{
  "email_notifications": {
    "on_start": ["team@example.com"],
    "on_success": ["team@example.com"],
    "on_failure": ["oncall@example.com", "team@example.com"]
  }
}
```

### 5. Use Retries for Flaky Tasks

```json
{
  "max_retries": 3,
  "min_retry_interval_millis": 60000,
  "retry_on_timeout": true
}
```

### 6. Set Timeouts

```json
{
  "timeout_seconds": 3600  // 1 hour timeout
}
```

### 7. Use Parameters

Make jobs reusable:
```json
{
  "notebook_task": {
    "notebook_path": "/Workspace/notebooks/etl.py",
    "base_parameters": {
      "date": "{{job.start_time}}",
      "env": "prod"
    }
  }
}
```

## Troubleshooting

### Job Creation Fails

**Symptom**: `databricks jobs create` fails

**Solution**:
1. Validate JSON configuration
2. Check notebook paths exist
3. Verify cluster configuration
4. Ensure you have job creation permissions

### Job Run Fails

**Symptom**: Job run fails with error

**Solution**:
1. Check run output: `databricks jobs get-run-output --run-id <run-id>`
2. Review task logs in workspace UI
3. Verify notebook/script code
4. Check cluster resources
5. Verify data/file access

### Schedule Not Triggering

**Symptom**: Scheduled job doesn't run

**Solution**:
1. Verify schedule is enabled
2. Check cron expression is correct
3. Verify timezone setting
4. Check job hasn't been paused
5. Review job run history

### Cluster Fails to Start

**Symptom**: Job fails because cluster won't start

**Solution**:
1. Check workspace capacity
2. Verify cluster configuration
3. Check for permission issues
4. Try different node type
5. Review cluster initialization logs

## Related Topics

- [Asset Bundles](asset-bundles.md) - Define jobs as code
- [Clusters](clusters.md) - Manage compute resources
- [Workspace](workspace.md) - Manage notebooks and files
- [Workflows](workflows.md) - Complete job workflows
