# Serverless Storage Check — Pattern Catalog & Remediation Guide

Detection rules used by `scripts/preflight.py` and before/after fixes for every antipattern the scanner flags. Use this reference when the scanner reports a finding and you need to understand the rule or choose the right fix.

---

## Part 1 — Pattern Catalog

All detection rules. Each entry covers: what the scanner matches, an example that triggers it, the recommended fix, and the underlying detection rule.

The preflight scanner is intentionally conservative — false-negatives on heavily dynamic code (paths built from many variables at runtime) are expected. False positives should be rare. If you hit one, the scanner accepts the finding being ignored at the call site; please file an issue with a minimal repro.

### Severity scale

| Severity | Meaning |
|----------|---------|
| **Blocker** | The job WILL fail on serverless under realistic execution. Must fix before deploying. Contributes to exit code `2`. |
| **Warning** | The job is likely to fail under parallel execution or fan-out. Should fix. Contributes to exit code `1`. |
| **Info** | Awareness-only or escalation routing (e.g. env-sync error). Does not affect exit code. |

### FANOUT001 — Local-disk path passed to a child call

**Severity**: Blocker

**What it matches**: A string literal (or a variable bound to a string literal) starting with `/local_disk0`, `/tmp`, `/dbfs/tmp`, or containing `trustedTemp` is passed as an argument to one of:

- `dbutils.notebook.run(notebook, timeout, args)`
- `dbutils.jobs.taskValues.set(key=..., value=path)`
- `dbutils.task_values.set(...)` (legacy spelling)

The path may be passed directly, inside a dict literal (`{"handoff_path": tmp}`), or inside a list/tuple/set literal.

**Example that triggers it**:

```python
tmp = "/local_disk0/scratch/output.parquet"
df.write.parquet(tmp)
dbutils.notebook.run("./child", 600, {"handoff_path": tmp})
```

**Fix**:

```python
import uuid
handoff = f"/Volumes/main/analytics/handoffs/{uuid.uuid4()}.parquet"
df.write.parquet(handoff)
dbutils.notebook.run("./child", 600, {"handoff_path": handoff})
```

**Detection rule**: AST visitor on `ast.Call`. `_call_qualname` matches `dbutils.notebook.run`, `dbutils.jobs.taskValues.set`, or `dbutils.task_values.set`. `_string_args` resolves Name nodes via the cell's variable map and recurses into dict/list literals to find string values. Each resolved string is tested with `is_local_disk_path()`.

### FANOUT002 — Child notebook reads from a local-disk path

**Severity**: Blocker

**What it matches**: A notebook that pulls parameters via `dbutils.widgets.get` or `dbutils.jobs.taskValues.get` (suggesting it's a child) also performs a read (`open(path)`, `pd.read_*`, `spark.read.*`) from a `/local_disk0`, `/tmp`, or `trustedTemp` path.

**Example that triggers it**:

```python
dbutils.widgets.text("handoff_path", "")
path = dbutils.widgets.get("handoff_path")
df = pd.read_parquet("/local_disk0/scratch/input.parquet")
```

**Fix**: The parent must write to durable storage (`/Volumes` or `/Workspace`), and the child must read from the same. Pass the durable path via the parameter.

**Detection rule**: The scanner flags a cell as `is_likely_child` if any cell in the notebook uses `dbutils.widgets.get`, `dbutils.jobs.taskValues.get`, or `dbutils.task_values.get`. In a likely-child notebook, any read target (resolved via `_read_targets_in_cell`) matching `is_local_disk_path()` triggers this finding.

### FANOUT003 — Sibling tasks share a local-disk path

**Severity**: Warning

**What it matches**: A DAB job YAML defines two or more sibling tasks (or a task and one of its descendants) whose referenced notebooks both touch the same `/local_disk0`, `/tmp`, or `trustedTemp` path.

**Example that triggers it**:

```yaml
resources:
  jobs:
    my_job:
      tasks:
        - task_key: producer
          notebook_task:
            notebook_path: ./producer.py
        - task_key: consumer
          depends_on: [{ task_key: producer }]
          notebook_task:
            notebook_path: ./consumer.py
```

```python
# producer.py
shared = "/tmp/foo.parquet"
pd.DataFrame({"x": [1]}).to_parquet(shared)
```

```python
# consumer.py
shared = "/tmp/foo.parquet"
df = pd.read_parquet(shared)
```

**Fix**: Move the shared artifact to `/Volumes/...` or `/Workspace/...` and update both notebooks.

**Detection rule**: `scan_job_yaml` resolves each task's `notebook_path`, runs the per-cell scanner on every referenced notebook, and collects the set of local-disk paths each notebook touches. When two or more task keys overlap on the same path, the finding fires.

### FANOUT004 — `pipeline_task` downstream of a local-temp-writing notebook

**Severity**: Warning

**What it matches**: A DAB task with `pipeline_task: ...` whose `depends_on` includes a `notebook_task` that writes to a local-disk path.

**Example that triggers it**:

```yaml
tasks:
  - task_key: prep
    notebook_task:
      notebook_path: ./prep.py    # writes to /tmp/staging.parquet
  - task_key: run_pipeline
    depends_on: [{ task_key: prep }]
    pipeline_task:
      pipeline_id: 12345
```

**Fix**: Have `prep` write to a UC Volume that the pipeline ingests via Auto Loader or a streaming table, or materialize the prep output as a table the pipeline reads from.

**Detection rule**: For each task with `is_pipeline_task == True`, if any upstream `depends_on` task's notebook contains a local-disk write (recorded in `notebook_local_paths`), the finding fires.

### FANOUT005 — `dbutils.fs.cp` from local path to local path

**Severity**: Info

**What it matches**: A `dbutils.fs.cp(src, dst)` or `dbutils.fs.mv(src, dst)` call where both arguments resolve to local-disk paths.

**Example that triggers it**:

```python
dbutils.fs.cp("/local_disk0/staging/x.parquet", "/tmp/cache/x.parquet")
```

**Fix**: Safe within a single task. If the notebook is invoked by a multi-task job, change one side to `/Volumes/...` or `/Workspace/...` so the destination is visible to other tasks.

**Detection rule**: AST visitor matches `dbutils.fs.cp` and `dbutils.fs.mv` calls with two string args that both pass `is_local_disk_path()`.

### FANOUT006 — Hardcoded BSI trustedTemp signature

**Severity**: Blocker

**What it matches**: Any string anywhere in the source that matches the regex `/local_disk0/spark-[A-Za-z0-9\-]+/trustedTemp[A-Za-z0-9\-]*`. This is the exact path family that produced the original BSI failure:

```
/local_disk0/spark-d6bae111-42bd-4f54-9136-a4e9fbdec3d6/trustedTemp-55adadbe-d9ed-4278-a751-868797c1562f/tmpc58fz4pv
```

**Fix**: Never hardcode a `trustedTemp` path. The full path is a runtime-internal Spark scratch location — it will exist on a different node from where you wrote it. Use `/Volumes/...` or `/Workspace/...` for any cross-task data.

**Detection rule**: A tree-walk over every string `Constant` node in every cell tests `is_bsi_signature()` (using the `BSI_TRUSTED_TEMP_RE` regex). Triggers regardless of whether the string is in an assignment, a call arg, or a free expression.

### ENV001 — `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT` in run output

**Severity**: Info

**What it matches**: `--run-id` mode only. The run's error trace contains `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT` (often accompanied by "Virtual environment changed while syncing").

**Why this is info-only**: This error is a rare, platform-side intermittent issue. There is no customer-side code fix. The scanner emits this finding to route the user to escalation rather than mislead them into a code change.

**Fix**:
1. Open a Databricks support ticket with the run ID and error trace.
2. As a mitigation, move heavy `%pip install` into the parent or a job-level environment spec.
3. Add task retries — the error is usually transient.

**Detection rule**: `--run-id` mode shells out to `databricks jobs get-run-output` and tests the combined `error` + `error_trace` text against `ENV_SYNC_RE`.

### False-positive escape hatch

If a finding is genuinely safe in your workload, wrap the path construction so the literal doesn't appear in source:

```python
# Hidden from the static scanner; only do this when you've verified the
# context is genuinely single-task.
import os
LOCAL_SCRATCH = os.environ.get("LOCAL_SCRATCH_ROOT", "/local_disk0/tmp")
```

The scanner does not resolve `os.environ.get()`, so paths constructed this way are skipped.

### Adding a new pattern

1. Add the rule logic to `_NotebookScanner` (cell-scoped) or `scan_job_yaml` (DAB-scoped) in `scripts/preflight.py`.
2. Append a new entry to this catalog with: ID, severity, what-it-matches, example, fix, detection rule.
3. Add a unit test in `scripts/test_preflight.py` that exercises a triggering fixture and asserts the expected finding.
4. Update the summary table in `SKILL.md`.
5. Run `python3 scripts/test_preflight.py` — must still pass cleanly.

---

## Part 2 — Remediation Guide

Concrete before/after patterns for each fix. Choose based on handoff payload size and governance requirements.

### Decision tree

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

### Fix 1 — UC Volumes handoff (preferred)

Use a Volume for any cross-task file. Volumes are durable, cross-node, UC-governed, and work for any file size.

**Setup (one-time, per workload)**:

```sql
CREATE VOLUME IF NOT EXISTS main.analytics.job_handoffs;
GRANT WRITE VOLUME ON VOLUME main.analytics.job_handoffs TO `<workspace-user-or-sp>`;
GRANT READ VOLUME  ON VOLUME main.analytics.job_handoffs TO `<workspace-user-or-sp>`;
```

**Before — broken (FANOUT001 + FANOUT006)**:

```python
import pandas as pd
tmp = "/local_disk0/spark-abc/trustedTemp-def/handoff.parquet"
pd.DataFrame({"x": [1, 2, 3]}).to_parquet(tmp)
dbutils.notebook.run("./child", 600, {"handoff_path": tmp})
```

**After**:

```python
import pandas as pd
run_id = dbutils.notebook.entry_point.getDbutils().notebook().getContext().jobId().get()
handoff = f"/Volumes/main/analytics/job_handoffs/run_{run_id}/data.parquet"
dbutils.fs.mkdirs(f"/Volumes/main/analytics/job_handoffs/run_{run_id}")
pd.DataFrame({"x": [1, 2, 3]}).to_parquet(handoff)
dbutils.notebook.run("./child", 600, {"handoff_path": handoff})
```

**Permission notes**: The job's run-as identity needs `WRITE VOLUME` on the producing side and `READ VOLUME` on the consuming side. Volume paths are accessible from Python (`open`, `pd.read_*`, `shutil.*`), Spark (`spark.read.*`), and shell commands.

### Fix 2 — `/Workspace` handoff (fallback)

Use when UC is not available or the file is small and ephemeral.

**Before — broken**:

```python
import json
tmp = "/tmp/config.json"
with open(tmp, "w") as f:
    json.dump({"feature_flags": ["a", "b"]}, f)
dbutils.notebook.run("./apply_config", 600, {"config_path": tmp})
```

**After**:

```python
import json, os
handoff_dir = "/Workspace/Shared/my_job/handoff"
os.makedirs(handoff_dir, exist_ok=True)
handoff = f"{handoff_dir}/config.json"
with open(handoff, "w") as f:
    json.dump({"feature_flags": ["a", "b"]}, f)
dbutils.notebook.run("./apply_config", 600, {"config_path": handoff})
```

**Permission notes**: The run-as identity needs **CAN_EDIT** on the target workspace folder. Keep files modest in size (megabytes, not gigabytes).

### Fix 3 — `dbutils.jobs.taskValues` for small payloads

If the handoff is a scalar, small dict, or small JSON blob, skip the file entirely.

**Before — broken**:

```python
# Parent task
import json
with open("/tmp/status.json", "w") as f:
    json.dump({"records_processed": 12345}, f)
```

```python
# Child task
import json
with open("/tmp/status.json") as f:   # FANOUT002
    status = json.load(f)
```

**After**:

```python
# Parent task
dbutils.jobs.taskValues.set(key="status", value={"records_processed": 12345, "skipped": 2})
```

```python
# Child task
status = dbutils.jobs.taskValues.get(taskKey="parent_task", key="status", debugValue={})
```

**Limits**: 48 KB per value, 5 MB per run across all task values. Types: any JSON-serializable Python value. `debugValue` is required for interactive notebook runs.

### Fix 4 — `pipeline_task` downstream of a notebook (FANOUT004)

**Before — broken**:

```yaml
tasks:
  - task_key: prep
    notebook_task:
      notebook_path: ./prep_data.py    # writes /tmp/staging.parquet
  - task_key: run_pipeline
    depends_on: [{ task_key: prep }]
    pipeline_task:
      pipeline_id: 12345
```

**After** — update the notebook to write to Volumes, update the pipeline to read from it:

```python
# prep_data.py
dest = "/Volumes/main/raw/staging/run_42/data.parquet"
df.write.format("parquet").mode("overwrite").save(dest)
```

```python
# Pipeline (DLT/SDP)
import dlt

@dlt.table
def staging():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "parquet")
        .load("/Volumes/main/raw/staging/")
    )
```

### Anti-examples — what NOT to do

```python
# Anti-pattern 1: parent writes to trustedTemp, child reads
tmp = "/local_disk0/spark-abc/trustedTemp-def/handoff.parquet"   # FANOUT006
df.write.parquet(tmp)
dbutils.notebook.run("./child", 600, {"handoff_path": tmp})       # FANOUT001
```

```yaml
# Anti-pattern 2: sibling tasks share /tmp
tasks:
  - task_key: producer
    notebook_task: { notebook_path: ./producer.py }   # writes /tmp/foo.parquet
  - task_key: consumer
    depends_on: [{ task_key: producer }]
    notebook_task: { notebook_path: ./consumer.py }   # reads /tmp/foo.parquet — FANOUT003
```

### When `/local_disk0/tmp` IS correct

```python
# Fine: per-task scratch that doesn't outlive the task
scratch = "/local_disk0/tmp/intermediate.parquet"
df.write.parquet(scratch)
post = spark.read.parquet(scratch)   # same task — OK
```

The boundary: does another task need to read this? If yes → `/Volumes` or `/Workspace`. If no → `/local_disk0/tmp` is the right choice.

## External references

- [Unity Catalog volumes](https://docs.databricks.com/en/connect/unity-catalog/volumes.html)
- [Workspace files](https://docs.databricks.com/en/files/workspace.html)
- [`dbutils.jobs.taskValues`](https://docs.databricks.com/en/dev-tools/databricks-utils.html#task-values-utility-dbutilsjobstaskvalues)
- [Serverless compute limitations](https://docs.databricks.com/en/compute/serverless/limitations)
