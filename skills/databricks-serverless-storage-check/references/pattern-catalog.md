# Pattern Catalog

All detection rules used by `scripts/preflight.py`. Each pattern has a stable ID, a severity, a description of what it matches, an example that triggers it, the recommended fix, and the underlying detection rule.

The preflight scanner is intentionally conservative — false-negatives on heavily dynamic code (paths built from many variables at runtime) are expected. False positives should be rare. If you hit one, the scanner accepts the finding being ignored at the call site; please file an issue with a minimal repro.

## Severity scale

| Severity | Meaning |
|----------|---------|
| **Blocker** | The job WILL fail on serverless under realistic execution. Must fix before deploying. Contributes to exit code `2`. |
| **Warning** | The job is likely to fail under parallel execution or fan-out. Should fix. Contributes to exit code `1`. |
| **Info** | Awareness-only or escalation routing (e.g. env-sync error). Does not affect exit code. |

## Patterns

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
shared = "/tmp/foo.parquet"
pd.DataFrame({"x": [1]}).to_parquet(shared)
```

```python
shared = "/tmp/foo.parquet"
df = pd.read_parquet(shared)
```

**Fix**: Move the shared artifact to `/Volumes/...` or `/Workspace/...` and update both notebooks.

**Detection rule**: `scan_job_yaml` resolves each task's `notebook_path`, runs the per-cell scanner on every referenced notebook, and collects the set of local-disk paths each notebook touches (writes, reads, child-call args, or bare string literals). When two or more task keys overlap on the same path, the finding fires.

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

**Example that triggers it**:

```python
tmp = "/local_disk0/spark-abc/trustedTemp-def/handoff.parquet"
```

**Fix**: Never hardcode a `trustedTemp` path. The full path is a runtime-internal Spark scratch location; if you depend on it from another task, the path will exist on a different node from where you wrote it. Use `/Volumes/...` or `/Workspace/...` for any cross-task data.

**Detection rule**: A tree-walk over every string `Constant` node in every cell tests `is_bsi_signature()` (which uses the `BSI_TRUSTED_TEMP_RE` regex). Triggers regardless of whether the string is in an assignment, a call arg, or a free expression.

### ENV001 — `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT` in run output

**Severity**: Info

**What it matches**: `--run-id` mode only. The run's error trace contains `ENVIRONMENT_SETUP_ERROR.PYTHON_NOTEBOOK_ENVIRONMENT` (often accompanied by "Virtual environment changed while syncing").

**Why this is info-only**: Per the BSI thread (Philip Nord), this error is a rare, platform-side intermittent issue. There is no customer-side fix this skill can apply. The scanner emits this finding to route the user to escalation rather than mislead them into a code change.

**Fix**:

1. Open a Databricks engineering support ticket (use `/jira-actions` or `/support-escalation`) with the run ID and error trace.
2. As a mitigation, reduce dependency setup during child notebook startup. Move heavy `%pip install` into the parent or into a job-level environment spec where possible.
3. Add task retries — the error is usually transient and the next run typically succeeds.

**Detection rule**: `--run-id` mode shells out to `databricks jobs get-run-output` and tests the combined `error` + `error_trace` text against `ENV_SYNC_RE`.

## False-positive escape hatch

If a finding is genuinely safe in your workload (rare, but possible — e.g. you have a single-task notebook where `/local_disk0` use is fine), the simplest mitigation is to wrap the path construction so the literal doesn't appear in source:

```python
# Hidden from the static scanner; only do this when you've verified the
# context is genuinely single-task.
import os
LOCAL_SCRATCH = os.environ.get("LOCAL_SCRATCH_ROOT", "/local_disk0/tmp")
```

The scanner does not resolve `os.environ.get()`, so paths constructed this way are skipped. Prefer fixing the antipattern when possible; this is an explicit opt-out, not a recommendation.

## Adding a new pattern

To add a new detection rule:

1. Add the rule logic to `_NotebookScanner` (cell-scoped) or `scan_job_yaml` (DAB-scoped) in `scripts/preflight.py`.
2. Append a new entry to this catalog with: ID (next `FANOUT###` or topical prefix), severity, what-it-matches, example, fix, detection rule.
3. Add a unit test in `scripts/test_preflight.py` that exercises a triggering fixture and asserts the expected finding.
4. Update the summary table in `SKILL.md`.
5. Run `python3 scripts/test_preflight.py` — must still pass cleanly.
