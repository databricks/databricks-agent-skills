# Remediation Guide

Concrete before/after patterns for fixing the antipatterns flagged by `scripts/preflight.py`. Choose the fix that matches your handoff payload size and governance requirements.

## Decision tree

```
What is the handoff?

  Small scalar or JSON (< ~48 KB total per run)
    → use dbutils.jobs.taskValues (no file at all)

  A file
    Need UC governance / large files / Delta tables?
      → /Volumes/<catalog>/<schema>/<volume>/handoff/...   (PREFERRED)
    Smaller files, no UC required, simpler permissions?
      → /Workspace/Shared/<job_name>/handoff/...           (FALLBACK)

  Same-task scratch only
    → /local_disk0/tmp/... is FINE (and recommended)
```

## Fix 1 — UC Volumes handoff (preferred)

Use a Volume for any cross-task file. Volumes are durable, cross-node, UC-governed, and work for any file size.

### Setup (one-time, per workload)

```sql
CREATE VOLUME IF NOT EXISTS main.analytics.job_handoffs;
GRANT WRITE VOLUME ON VOLUME main.analytics.job_handoffs TO `<workspace-user-or-sp>`;
GRANT READ VOLUME  ON VOLUME main.analytics.job_handoffs TO `<workspace-user-or-sp>`;
```

### Before — broken (FANOUT001 + FANOUT006)

```python
import pandas as pd

tmp = "/local_disk0/spark-abc/trustedTemp-def/handoff.parquet"
pd.DataFrame({"x": [1, 2, 3]}).to_parquet(tmp)

dbutils.notebook.run("./child", 600, {"handoff_path": tmp})
```

### After — durable Volumes handoff

```python
import pandas as pd

run_id = dbutils.notebook.entry_point.getDbutils().notebook().getContext().jobId().get()
handoff = f"/Volumes/main/analytics/job_handoffs/run_{run_id}/data.parquet"

dbutils.fs.mkdirs(f"/Volumes/main/analytics/job_handoffs/run_{run_id}")
pd.DataFrame({"x": [1, 2, 3]}).to_parquet(handoff)

dbutils.notebook.run("./child", 600, {"handoff_path": handoff})
```

### Cleanup (optional, end-of-job task)

```python
# Remove this run's handoff directory at the end of the job
import shutil
run_dir = f"/Volumes/main/analytics/job_handoffs/run_{run_id}"
shutil.rmtree(run_dir, ignore_errors=True)
```

### Permission notes

- The job's run-as identity needs `WRITE VOLUME` on the producing side and `READ VOLUME` on the consuming side.
- For ad-hoc development from a notebook, the calling user needs the same grants.
- Volume paths are accessible from Python (`open`, `pd.read_*`, `shutil.*`), Spark (`spark.read.*`), and shell commands (`cat`, `ls`).
- Lifecycle: Volumes persist until you delete them. Plan for cleanup if your job produces many handoff directories.

## Fix 2 — `/Workspace` handoff (fallback)

Use `/Workspace` files when UC is not available or when the file is small and ephemeral. Files written under `/Workspace` are durable and visible across nodes, but subject to workspace storage quotas and not designed for high-throughput I/O.

### Before — broken

```python
import json

tmp = "/tmp/config.json"
with open(tmp, "w") as f:
    json.dump({"feature_flags": ["a", "b"]}, f)

dbutils.notebook.run("./apply_config", 600, {"config_path": tmp})
```

### After — Workspace handoff

```python
import json, os

handoff_dir = "/Workspace/Shared/my_job/handoff"
os.makedirs(handoff_dir, exist_ok=True)
handoff = f"{handoff_dir}/config.json"

with open(handoff, "w") as f:
    json.dump({"feature_flags": ["a", "b"]}, f)

dbutils.notebook.run("./apply_config", 600, {"config_path": handoff})
```

### Permission notes

- The run-as identity needs **CAN_EDIT** on `/Workspace/Shared/my_job/` (or whichever folder you write to).
- `/Workspace` is workspace-scoped: the same path is **not** visible from a different workspace.
- Keep files under `/Workspace` modest in size (megabytes, not gigabytes). For large data, use Volumes.

## Fix 3 — `dbutils.jobs.taskValues` for small payloads

If the handoff is a scalar, a small dict, or a small JSON blob, skip the file entirely. Task values are designed for this and avoid all the storage concerns.

### Before — broken

```python
# In parent task
import json
status = {"records_processed": 12345, "skipped": 2}
with open("/tmp/status.json", "w") as f:
    json.dump(status, f)
```

```python
# In child task
import json
with open("/tmp/status.json") as f:   # FANOUT002: child reads from /tmp
    status = json.load(f)
```

### After — taskValues handoff

```python
# In parent task
dbutils.jobs.taskValues.set(key="records_processed", value=12345)
dbutils.jobs.taskValues.set(key="status", value={"records_processed": 12345, "skipped": 2})
```

```python
# In child task — referencing the parent task by key
records = dbutils.jobs.taskValues.get(
    taskKey="parent_task",
    key="records_processed",
    debugValue=0,
)
status = dbutils.jobs.taskValues.get(
    taskKey="parent_task",
    key="status",
    debugValue={},
)
```

### Limits

- Per-task-value: 48 KB serialized JSON
- Per-run total across all task values: 5 MB
- Types: any JSON-serializable Python value (str, int, float, bool, list, dict, None)
- The `debugValue` is required and is used when running the notebook interactively (outside a job)

## Fix 4 — `pipeline_task` downstream of a notebook (FANOUT004)

When a pipeline task depends on a notebook task, don't try to hand off via a local-disk path. The pipeline runs in its own context.

### Before — broken

```yaml
tasks:
  - task_key: prep
    notebook_task:
      notebook_path: ./prep_data.py    # writes /tmp/staging.parquet
  - task_key: run_pipeline
    depends_on: [{ task_key: prep }]
    pipeline_task:
      pipeline_id: 12345               # tries to read /tmp/staging.parquet
```

### After — Volumes-based handoff

Update the notebook:

```python
# prep_data.py
dest = "/Volumes/main/raw/staging/run_42/data.parquet"
df.write.format("parquet").mode("overwrite").save(dest)
```

Update the pipeline to read from the volume:

```python
# In the pipeline notebook (DLT / SDP)
import dlt

@dlt.table
def staging():
    return spark.read.format("parquet").load("/Volumes/main/raw/staging/run_42/data.parquet")
```

For incremental ingest, prefer Auto Loader over a single-path read:

```python
@dlt.table
def staging():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .load("/Volumes/main/raw/staging/")
    )
```

## What NOT to do — anti-examples

These are the exact patterns the scanner exists to catch. Do not use any of them for cross-task data.

### Anti-pattern 1: parent writes to trustedTemp, child reads

```python
# Parent
tmp = "/local_disk0/spark-abc/trustedTemp-def/handoff.parquet"   # FANOUT006
df.write.parquet(tmp)                                             # writes to local node only
dbutils.notebook.run("./child", 600, {"handoff_path": tmp})       # FANOUT001
```

```python
# Child
path = dbutils.widgets.get("handoff_path")
df = pd.read_parquet(path)   # FANOUT002 — child likely runs on a different node
```

### Anti-pattern 2: sibling tasks share `/tmp`

```yaml
tasks:
  - task_key: producer
    notebook_task: { notebook_path: ./producer.py }   # writes /tmp/foo.parquet
  - task_key: consumer
    depends_on: [{ task_key: producer }]
    notebook_task: { notebook_path: ./consumer.py }   # reads /tmp/foo.parquet — FANOUT003
```

### Anti-pattern 3: cleanup that depends on local state across tasks

```python
# Final cleanup task
import shutil
shutil.rmtree("/local_disk0/scratch/")   # only cleans this node; other nodes are untouched
```

The "cleanup" task may run on a node that never saw the scratch directory. Either move scratch to `/Volumes` and clean that, or skip the cleanup task entirely (local disk is reclaimed when the task ends).

## When `/local_disk0/tmp` IS fine

For completeness: local-disk paths are correct, and recommended, for **per-task scratch** that doesn't outlive the task.

```python
# OK on serverless: temporary intermediate inside a single task
scratch = "/local_disk0/tmp/intermediate.parquet"
df.write.parquet(scratch)
# ... use scratch later in the SAME task ...
post = spark.read.parquet(scratch)
```

The boundary is: does another task — child notebook, sibling task, pipeline — need to read this file? If yes, it must live on `/Volumes` or `/Workspace`. If no, `/local_disk0/tmp` is the right answer.

## Reference

- [Unity Catalog volumes overview](https://docs.databricks.com/en/connect/unity-catalog/volumes.html)
- [Workspace files](https://docs.databricks.com/en/files/workspace.html)
- [`dbutils.jobs.taskValues`](https://docs.databricks.com/en/dev-tools/databricks-utils.html#task-values-utility-dbutilsjobstaskvalues)
- [Serverless compute limitations](https://docs.databricks.com/en/compute/serverless/limitations)
