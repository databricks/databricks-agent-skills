# Pipeline Project Workflows

Three workflows for building Spark Declarative Pipelines, depending on what already exists in the project and how much DAB scaffolding the user wants.

## Choose Your Workflow

| Situation | Workflow |
|-----------|----------|
| New, standalone pipeline project with its own bundle | **A. Standalone bundle** |
| Pipeline added to an existing DAB project | **B. Existing bundle** |
| Quick prototyping, no bundle (yet) | **C. Rapid CLI iteration** |

If the user is unsure, default to A for production-bound work and C for exploration.

---

## Language Selection (Python vs SQL)

Decide before scaffolding — the choice picks the template files (`.py` vs `.sql`) and pulls in different reference docs. Both languages can coexist in the same project, but pick one primary.

| User signal | Pick |
|-------------|------|
| "Python pipeline", "use Python", UDF, pandas, ML inference, pyspark | **Python** |
| "SQL pipeline", "SQL files", "use SQL" | **SQL** |
| "Create a simple pipeline", "create a table", "an aggregation" | **SQL** (simpler) |
| Complex parameterized logic, custom UDFs, ML, advanced processing | **Python** |

If the request is ambiguous, ask. Stick with the chosen language unless the user explicitly switches.

---

## Workflow A: Standalone Bundle (`pipelines init`)

Use when the user wants a new project where the pipeline *is* the project.

### Non-interactive (recommended for agents)

```bash
databricks pipelines init --output-dir . --config-file init-config.json
```

`init-config.json`:

```json
{
  "project_name": "customer_pipeline",
  "initial_catalog": "prod_catalog",
  "use_personal_schema": "no",
  "initial_language": "sql"
}
```

| Field | Notes |
|-------|-------|
| `project_name` | Letters, numbers, underscores only. Used for bundle name + folder. |
| `initial_catalog` | Must exist in Unity Catalog. |
| `use_personal_schema` | `"yes"` → `${workspace.current_user.short_name}` (dev). `"no"` → fixed value (prod). |
| `initial_language` | `"sql"` or `"python"` (lowercase). |

### Interactive

```bash
databricks pipelines init --output-dir .
```

Prompts for the same fields.

### Generated structure

```
project_root/
├── databricks.yml                     # Bundle config
├── pyproject.toml                     # Python only
├── resources/
│   ├── <name>_etl.pipeline.yml        # Pipeline resource
│   └── sample_job.job.yml             # Optional scheduled job
└── src/
    └── <name>_etl/
        ├── explorations/              # Ad-hoc notebooks (NOT pipeline code)
        └── transformations/           # Pipeline transformations
            ├── sample_*.sql           # or .py
            └── ...
```

**Key rule**: Pipeline transformations are raw `.sql` / `.py` files. Notebooks go in `explorations/` for ad-hoc work only.

### Customize and deploy

1. Replace `sample_*` files in `transformations/` with real datasets (1 dataset per file).
2. Edit `databricks.yml` to set per-target catalog/schema variables and workspace host.
3. Edit `resources/<name>_etl.pipeline.yml` for pipeline-level settings (serverless on by default).
4. `databricks bundle validate` → `databricks bundle deploy [-t <target>]` → `databricks bundle run <pipeline_name>`.

### Alternative: `databricks bundle init lakeflow-pipelines`

The older template-based scaffolding also works:

```bash
databricks bundle init lakeflow-pipelines \
  --config-file <(echo '{"project_name": "my_pipeline", "language": "python", "serverless": "yes"}') \
  --profile <PROFILE> < /dev/null
```

Both produce DAB-shaped projects; `pipelines init` is the newer, more focused command.

### `databricks.yml` essentials

```yaml
bundle:
  name: customer_pipeline

include:
  - resources/*.yml
  - resources/*/*.yml

variables:
  catalog: { description: The catalog to use }
  schema:  { description: The schema to use }

targets:
  dev:
    mode: development           # prefixes resources with [dev <user>], pauses schedules
    default: true
    workspace:
      host: https://<workspace>.cloud.databricks.com
    variables:
      catalog: dev_catalog
      schema: ${workspace.current_user.short_name}

  prod:
    mode: production            # no prefix, schedules active
    workspace:
      host: https://<workspace>.cloud.databricks.com
      root_path: /Workspace/Users/<owner>/.bundle/${bundle.name}/${bundle.target}
    variables:
      catalog: prod_catalog
      schema: production
    permissions:
      - user_name: <owner>
        level: CAN_MANAGE
```

### Pipeline resource (`resources/<name>.pipeline.yml`)

```yaml
resources:
  pipelines:
    customer_pipeline_etl:
      name: customer_pipeline_etl
      catalog: ${var.catalog}
      schema: ${var.schema}
      serverless: true
      continuous: false          # explicit — true auto-retries failed updates forever
      root_path: "../src/customer_pipeline_etl"
      libraries:
        - glob:
            include: ../src/customer_pipeline_etl/transformations/**
      environment:                # serverless Python deps (optional)
        dependencies:
          - --editable ${workspace.file_path}
```

### Python project dependencies

Python projects ship a `pyproject.toml`. Runtime deps go in `[project].dependencies`; dev-only in `[project.optional-dependencies].dev`. The `--editable ${workspace.file_path}` line in the pipeline resource installs the package on serverless compute at deploy time.

---

## Workflow B: Pipeline in Existing Bundle

Use when `databricks.yml` already exists for a larger project (app + jobs + dashboards) and a pipeline is being added to it.

### Step 1: Add a pipeline resource file

`resources/my_pipeline.pipeline.yml`:

```yaml
resources:
  pipelines:
    my_pipeline:
      name: my_pipeline
      catalog: ${var.catalog}
      schema: ${var.schema}
      serverless: true
      continuous: false
      libraries:
        - glob:
            include: ../src/pipelines/my_pipeline/**
```

### Step 2: Add source files

```
src/pipelines/my_pipeline/
├── bronze_ingest.sql
├── silver_clean.sql
└── gold_summary.sql
```

### Step 3: Deploy

```bash
databricks bundle deploy
databricks bundle run my_pipeline
```

The pipeline picks up the bundle's existing targets / variables / permissions.

---

## Workflow C: Rapid CLI Iteration (no bundle)

Use for prototyping when bundle scaffolding would slow the user down. Skip when the work is production-bound — workflow A or B is better long-term.

### Step 1: Write files locally

`.sql` or `.py` files in a folder. See [python-basics.md](python-basics.md) or [sql-basics.md](sql-basics.md) for syntax.

### Step 2: Upload to workspace

```bash
databricks workspace import-dir ./my_pipeline /Workspace/Users/<user>/my_pipeline
```

Re-upload with `--overwrite` after every code change.

### Step 3: Create the pipeline

```bash
databricks pipelines create --json '{
  "name": "my_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": true,
  "continuous": false,
  "channel": "PREVIEW",
  "libraries": [{"glob": {"include": "/Workspace/Users/<user>/my_pipeline/**"}}]
}'
```

`libraries` field notes:

- `"glob"` — directory of files. Recommended.
- `"file"` — single `.sql` / `.py`. A `"file"` pointing at a folder fails with `Paths must end with .py or .sql`.
- `"notebook"` — **deprecated**, never use.

Use enumerated `"file"` entries instead of `"glob"` only when explicit ordering matters.

Capture the returned `pipeline_id`.

### Step 4: Start an update and poll *that update*

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

**On `FAILED`**: read the events log, don't re-run.

```bash
databricks pipelines list-pipeline-events <pipeline_id> \
  | jq '[.[] | select(.level=="ERROR") | {event_type, message: (.message // "")[0:300]}] | .[0:5]'
```

If the pipeline is already `RUNNING`, `start-update` queues the new update. Force-stop with `databricks pipelines stop <pipeline_id>` first if needed.

### Step 5: Edit → re-upload → restart

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

### Step 6: Validate output data

Even on `COMPLETED`, verify the data:

```bash
databricks experimental aitools tools discover-schema \
  my_catalog.my_schema.bronze_orders \
  my_catalog.my_schema.silver_orders \
  my_catalog.my_schema.gold_summary
```

Returns columns/types, 5 sample rows, total row count, and null counts per column per table.

Check for: empty tables (ingestion or filter problems), unexpected row counts (broken joins), missing columns (schema mismatch), nulls in key columns (data quality).

### Python SDK alternative

```python
from databricks.sdk import WorkspaceClient
import time

w = WorkspaceClient()

pipeline = w.pipelines.create(
    name="my_pipeline",
    catalog="my_catalog",
    schema="my_schema",
    serverless=True,
    continuous=False,
    libraries=[{"glob": {"include": "/Workspace/Users/<user>/my_pipeline/**"}}],
    development=True,
)

update = w.pipelines.start_update(
    pipeline_id=pipeline.pipeline_id,
    full_refresh=True,
)

while True:
    u = w.pipelines.get_update(pipeline_id=pipeline.pipeline_id,
                               update_id=update.update_id).update
    if str(u.state) in ("COMPLETED", "FAILED", "CANCELED"):
        print(f"Update {u.update_id}: {u.state}")
        break
    time.sleep(10)
```

---

## Migrating from a Manual Folder Structure

If the user already has `bronze/`, `silver/`, `gold/` folders without a bundle, migrate to workflow A by wrapping them in a `databricks.yml` and a pipeline resource pointing at the existing folders via a `glob`. No file moves required — the medallion folders work as-is under `transformations/**`.

---

## Common Initialization Issues

| Issue | Fix |
|-------|-----|
| `Command not found: databricks` | Install the Databricks CLI — see the parent `databricks-core` skill (CLI installation reference) |
| `Invalid catalog name` | `databricks catalogs list` and verify; create with `databricks catalogs create --json '{"name": "..."}'` |
| `Language option not recognized` | Use lowercase `"sql"` / `"python"`, not `"SQL"` / `"Python"` |
| Files deploy but pipeline doesn't pick them up | Glob pattern in `libraries` doesn't match — re-check `include` path relative to the resource file |
| `Bundle validation failed: Invalid schema` | `databricks bundle validate`, check YAML indentation (spaces, not tabs) |
| Files deploy but pipeline config stale | `databricks bundle deploy --force` |
