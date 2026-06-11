# Project Initialization with DAB

Two DAB-based workflows for creating Spark Declarative Pipelines:

- **Workflow A**: Standalone new project (the pipeline *is* the project).
- **Workflow B**: Adding a pipeline to an existing bundle (the pipeline is part of a larger app + jobs + dashboards).

For prototyping without a bundle, see [2-rapid-iteration-with-cli.md](2-rapid-iteration-with-cli.md).

---

## Workflow A: Standalone Bundle (`pipelines init`)

Use when the user wants a new project where the pipeline *is* the project (no existing `databricks.yml`).

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

### Alternative: `databricks bundle init lakeflow-pipelines`

The older template-based scaffolding also works:

```bash
databricks bundle init lakeflow-pipelines \
  --config-file <(echo '{"project_name": "my_pipeline", "language": "python", "serverless": "yes"}') \
  --profile <PROFILE> < /dev/null
```

Both produce DAB-shaped projects; `pipelines init` is the newer, more focused command.

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

### Scheduling Pipelines

To schedule a pipeline, add a job that triggers it in `resources/<name>.job.yml`:

```yaml
resources:
  jobs:
    my_pipeline_job:
      trigger:
        periodic:
          interval: 1
          unit: DAYS
      tasks:
        - task_key: refresh_pipeline
          pipeline_task:
            pipeline_id: ${resources.pipelines.my_pipeline.id}
```


### Python project dependencies

Python projects ship a standard `pyproject.toml`. Runtime deps in `[project].dependencies`, dev-only in `[project.optional-dependencies].dev` (e.g. `databricks-connect>=15.4,<15.5`, `pytest`, `ruff`). The `--editable ${workspace.file_path}` line in the pipeline resource installs the package on serverless compute at deploy time.

### Multi-environment workflow

```bash
databricks bundle deploy                          # dev (default target) — resources prefixed [dev <user>]
databricks bundle deploy --target prod            # prod — no prefix, schedules active
databricks bundle run customer_pipeline_etl [--target prod]
```

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

## Running a Pipeline (Workflow A / B)

**You must deploy before running.** In local development, code changes only take effect after `databricks bundle deploy`. Always deploy before any run, dry run, or selective refresh.

### Development workflow

```bash
# 1. Validate the bundle config
databricks bundle validate --profile <profile>

# 2. Deploy to a target (dev is default)
databricks bundle deploy -t dev --profile <profile>

# 3. Trigger the pipeline
databricks bundle run <pipeline_name> -t dev --profile <profile>

# 4. Check status (capture the update_id from step 3 and poll it — not top-level state)
databricks pipelines get <pipeline_id> --profile <profile>
databricks pipelines get-update <pipeline_id> <update_id> --profile <profile>
```

For the rationale on polling the update (not the pipeline) and the FAILED-extraction `jq` pattern, see [2-rapid-iteration-with-cli.md#step-4-start-an-update-and-poll-that-update](2-rapid-iteration-with-cli.md#step-4-start-an-update-and-poll-that-update). It applies to bundle runs too.

### Refresh modes

- **Selective refresh** is preferred when only one table needs to run. Dependencies must already be materialized.
- **Full refresh** is the most expensive option and **can lead to data loss** — it reprocesses streaming sources from scratch and destroys streaming state. Use only when necessary, and always surface it as a follow-up the user must explicitly approve. CLI: `databricks bundle run <pipeline_name> --full-refresh-all` or `--refresh <table>` for selective.

### Editing pipeline code

Edit `.sql` / `.py` files under `src/`, then re-run `databricks bundle deploy` + `databricks bundle run`. Bundle deploy uploads changed files as raw `FILE` entries. Don't mix `databricks workspace import --format SOURCE` into a bundle-managed pipeline — that creates a NOTEBOOK entry and subsequent bundle deploys fail with `type mismatch (asked: FILE, actual: NOTEBOOK)`.

---

## Migrating from a Manual Folder Structure

If the user already has `bronze/`, `silver/`, `gold/` folders without a bundle, migrate to Workflow A by wrapping them in a `databricks.yml` and a pipeline resource pointing at the existing folders via a `glob`. No file moves required — the medallion folders work as-is under `transformations/**`.

For detailed pipeline configuration options (development mode, continuous, custom event log, notifications, Python deps, classic clusters), see [pipeline-configuration.md](pipeline-configuration.md).

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
| `Authentication error` on deploy | `databricks configure --host https://<workspace>.cloud.databricks.com` or set `DATABRICKS_HOST` / `DATABRICKS_TOKEN` |
