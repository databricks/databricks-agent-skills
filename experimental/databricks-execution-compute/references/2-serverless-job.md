# Serverless Job Execution

**Use when:** Running intensive Python code remotely (ML training, heavy processing) that doesn't need Spark, or when code shouldn't depend on the local machine staying connected.

## When to Choose Serverless Job

- ML model training (runs independently of local machine)
- Heavy non-Spark Python processing
- Code that takes > 5 minutes (local connection can drop)
- Production/scheduled runs

## Trade-offs

| Pro | Con |
|-----|-----|
| No cluster to manage | ~25-50s cold start each invocation |
| Up to 30 min timeout | No state preserved between calls |
| Independent execution | `print()` unreliable — use `dbutils.notebook.exit()` |

## Pure CLI flow

`databricks jobs submit` is the "create + run" primitive for ephemeral runs (no Jobs UI entry, no retry). The local file must be a Databricks source notebook — first line `# Databricks notebook source` (Python) or `-- Databricks notebook source` (SQL).

### 1. Upload the local file as a workspace notebook

`TARGET_PATH` is positional; `--file` is the local path; `--language` is required when `--format SOURCE`.

`databricks workspace import /Workspace/Users/<user>/.ai_dev_kit/train --file /local/path/to/train.py --format SOURCE --language PYTHON --overwrite`

### 2. Submit the run

`--no-wait` returns `{"run_id": N}` immediately. Drop it to block until terminated. **`"client": "4"` is required** for `dependencies` to install — `"1"` silently ignores them.

`databricks jobs submit --no-wait --json @submit.json`

Where `submit.json`:

```json
{
  "run_name": "train-run",
  "tasks": [{
    "task_key": "main",
    "notebook_task": {"notebook_path": "/Workspace/Users/<user>/.ai_dev_kit/train"},
    "environment_key": "ml_env"
  }],
  "environments": [{
    "environment_key": "ml_env",
    "spec": {"client": "4", "dependencies": ["scikit-learn==1.5.2", "mlflow==2.22.0"]}
  }]
}
```

### 3. Check status

One-shot trim to the fields that matter:

`databricks jobs get-run <RUN_ID> | jq '{state: .state.life_cycle_state, result: .state.result_state, duration_ms: .execution_duration, url: .run_page_url}'`

Life-cycle states: `PENDING` → `RUNNING` → `TERMINATED` (or `SKIPPED` / `INTERNAL_ERROR`). Only read `.state.result_state` (`SUCCESS` / `FAILED` / `CANCELED`) once `life_cycle_state == TERMINATED`.

### 4. Fetch the output / error

**Gotcha:** `get-run-output` takes the **task** run_id (`.tasks[0].run_id`), not the parent `run_id` from submit.

`databricks jobs get-run-output <TASK_RUN_ID> | jq '{result: .notebook_output.result, error, error_trace}'`

`notebook_output.result` is whatever `dbutils.notebook.exit()` passed. `error` / `error_trace` populate on failure.

### 5. (Optional) Delete the temp notebook

`databricks workspace delete /Workspace/Users/<user>/.ai_dev_kit/train`

## Output handling in the notebook

```python
# BAD — print() output isn't returned by get-run-output
print("Training complete!")

# GOOD — dbutils.notebook.exit() populates notebook_output.result
import json
dbutils.notebook.exit(json.dumps({"accuracy": 0.95, "model_path": "/Volumes/..."}))
```

Max output size is 5 MB. Larger results should be written to a Volume/object store and referenced by path.

## Common Issues

| Issue | Solution |
|-------|----------|
| `print()` output missing | Use `dbutils.notebook.exit()` — `print` isn't captured by `get-run-output` |
| `ModuleNotFoundError` | Add the package to the environments spec with `"client": "4"` |
| Dependencies listed but not installed | `"client": "1"` silently drops `dependencies`; use `"client": "4"` |
| `get-run-output` returns empty `notebook_output` | You passed the parent run_id, not `.tasks[0].run_id` |
| Job times out | Use `databricks jobs submit --no-wait` and poll `get-run` yourself, or set `tasks[].timeout_seconds` in the submit JSON to extend the per-task limit |

## When NOT to Use

Switch to **[Databricks Connect](1-databricks-connect.md)** when:
- Iterating on Spark code and want instant feedback
- Need local debugging with breakpoints

Switch to **[Interactive Cluster](3-interactive-cluster.md)** when:
- Need state across multiple tool calls
- Need Scala or R support
