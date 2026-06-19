# Rapid Iteration with CLI (no DAB)

Use the `databricks pipelines` CLI to create, run, and iterate on a pipeline **without managing a bundle**. Fastest path for prototyping. Production-bound work belongs in a bundle — see [1-project-initialization-with-dab.md](1-project-initialization-with-dab.md).

**Default to serverless.** Only use classic clusters if the user explicitly requires R, Spark RDD APIs, or JAR libraries.

---

## Step 1: Write pipeline files locally

`.sql` or `.py` files in a folder. See [python-basics.md](python-basics.md) or [sql-basics.md](sql-basics.md) for syntax.

## Step 2: Upload to the workspace

```bash
databricks workspace import-dir ./my_pipeline /Workspace/Users/<user>/my_pipeline
```

Re-upload with `--overwrite` after every code change.

## Step 3: Create the pipeline

```bash
databricks pipelines create --json '{
  "name": "my_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": true,
  "continuous": false,
  "development": true,
  "channel": "PREVIEW",
  "configuration": {
    "pipelines.numUpdateRetryAttempts": "0",
    "pipelines.maxFlowRetryAttempts": "0"
  },
  "libraries": [{"glob": {"include": "/Workspace/Users/<user>/my_pipeline/**"}}]
}'
```

These flags are the canonical dev/iteration defaults — fail fast. **Tuned for demo / iteration.** For production pipelines, drop `"development"` and the two `pipelines.*RetryAttempts` overrides so the platform's retry defaults (5 / 2) can absorb transient infra failures. Per-field rationale in [pipeline-configuration.md#canonical-create-dev--iteration-defaults](pipeline-configuration.md#canonical-create-dev--iteration-defaults).

`libraries`: use `"glob"` for a directory (recommended for medallion folders), `"file"` for a single `.sql`/`.py` (folder paths fail with `Paths must end with .py or .sql`), or enumerated `"file"` entries when ordering matters. `"notebook"` is deprecated — never use.

```json
"libraries": [
  {"file": {"path": "/Workspace/.../bronze/ingest_orders.sql"}},
  {"file": {"path": "/Workspace/.../silver/clean_orders.sql"}}
]
```

Capture the returned `pipeline_id`.

## Step 4: Start an update and poll *that update*

```bash
UPDATE_ID=$(databricks pipelines start-update <pipeline_id> | jq -r .update_id)
# Or with full refresh (destructive on streaming state — omit for incremental):
# UPDATE_ID=$(databricks pipelines start-update <pipeline_id> --full-refresh | jq -r .update_id)

while :; do
  STATE=$(databricks pipelines get-update <pipeline_id> "$UPDATE_ID" | jq -r '.update.state')
  echo "$(date +%H:%M:%S) update=$UPDATE_ID state=$STATE"
  case "$STATE" in COMPLETED|FAILED|CANCELED) break;; esac
  sleep 30
done
```

**Why poll the update, not the pipeline.** Top-level pipeline `state` flips back to `RUNNING` on `RETRY_ON_FAILURE`, so a loop watching the pipeline (or `latest_updates[0]`) can spin past a real `FAILED` update forever. Poll the captured `update_id` and stop on the first terminal state — including `FAILED`.

**On `FAILED`**: read the events log, don't re-run. **The real error is in `error.exceptions[0].message`, not in the top-level `.message`** — that one just says "Update X is FAILED", which is useless. Extract both:

```bash
databricks pipelines list-pipeline-events <pipeline_id> \
  | jq '[.[] | select(.level=="ERROR") | {
      event_type,
      summary: (.message // "")[0:200],
      exception: ((.error.exceptions[0].message // "no exception body") | .[0:800])
    }] | .[0:5]'
```

If you only see "Update X is FAILED" in your output, you're not extracting `error.exceptions[0].message` — fix the jq and re-run.

If the pipeline is already `RUNNING`, `start-update` queues the new update. Force-stop with `databricks pipelines stop <pipeline_id>` first if needed.

## Step 5: Edit → re-upload → restart

```bash
# Re-upload (whole dir)
databricks workspace import-dir ./my_pipeline /Workspace/Users/<user>/my_pipeline --overwrite

# Or a single file
databricks workspace import /Workspace/Users/<user>/my_pipeline/gold.sql \
  --file ./my_pipeline/gold.sql --format RAW --overwrite

# Restart
databricks pipelines start-update <pipeline_id>
```

**Use `--format RAW`** for raw `.sql` / `.py` FILE entries. `--format SOURCE --language SQL|PYTHON` uploads a workspace *notebook* — and **notebooks are deprecated for pipelines**. Mixing the two on the same path fails with `Cannot overwrite the asset ... due to type mismatch (asked: NOTEBOOK, actual: FILE)`.

## Step 6: Validate output data

Even on `COMPLETED`, verify the data:

```bash
databricks experimental aitools tools discover-schema \
  my_catalog.my_schema.bronze_orders \
  my_catalog.my_schema.silver_orders \
  my_catalog.my_schema.gold_summary
```

Returns columns/types, 5 sample rows, total row count, and null counts per column per table.

Check for: empty tables (ingestion or filter problems), unexpected row counts (broken joins), missing columns (schema mismatch), nulls in key columns (data quality).

**If validation reveals problems**, trace upstream: run `discover-schema` on the source table of the problematic dataset, then *its* source, until you hit the layer where the issue originates. Bronze empty = source path wrong or files missing; silver empty = filter too aggressive or join condition mismatched; gold wrong counts = aggregation/grouping bug or duplicate keys in source.

---

## Quick reference: CLI commands

### Pipeline lifecycle

| Command | Description |
|---------|-------------|
| `databricks pipelines create --json '{...}'` | Create a new pipeline. |
| `databricks pipelines get <pipeline_id>` | Pipeline details and current status. |
| `databricks pipelines update <pipeline_id> --json '{...}'` | Update pipeline config. |
| `databricks pipelines delete <pipeline_id>` | Delete the pipeline. |
| `databricks pipelines list-pipelines` | List all pipelines. |

### Run management

| Command | Description |
|---------|-------------|
| `databricks pipelines start-update <pipeline_id>` | Start a triggered update. |
| `databricks pipelines start-update <pipeline_id> --full-refresh` | Start with full refresh (destructive on streaming state). |
| `databricks pipelines stop <pipeline_id>` | Stop a running pipeline. |
| `databricks pipelines list-pipeline-events <pipeline_id>` | Event log (errors live here). |
| `databricks pipelines list-updates <pipeline_id>` | Recent runs. |
| `databricks pipelines get-update <pipeline_id> <update_id>` | Status of a specific update (use this for polling). |

### Supporting commands

| Command | Description |
|---------|-------------|
| `databricks workspace import-dir` | Upload files/folders to the workspace. |
| `databricks workspace import` | Upload a single file. |
| `databricks workspace list` | List workspace files. |
| `databricks experimental aitools tools discover-schema` | Schema + row counts + sample data + null counts. |
| `databricks experimental aitools tools query` | Run ad-hoc SQL. |

---

## Python SDK alternative

Same JSON shape via `databricks.sdk.WorkspaceClient`: `w.pipelines.create(name=..., catalog=..., schema=..., serverless=True, continuous=False, development=True, channel="PREVIEW", configuration={...}, libraries=[...])`. Capture `pipeline.pipeline_id`. Trigger with `w.pipelines.start_update(pipeline_id=..., full_refresh=...)` and poll `w.pipelines.get_update(pipeline_id=..., update_id=update.update_id).update.state` until it hits `COMPLETED`/`FAILED`/`CANCELED`. Prefer the CLI for interactive setup; the SDK is for programmatic / scripted workflows.
