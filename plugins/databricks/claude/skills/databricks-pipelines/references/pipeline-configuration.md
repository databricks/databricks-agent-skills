# Pipeline Configuration

JSON field reference for `databricks pipelines create --json '{...}'` and `databricks pipelines update <id> --json '{...}'`, plus variant snippets for common configurations.

Defaults to **serverless + Unity Catalog**. Don't set `serverless: false` unless the user explicitly needs R, Spark RDD APIs, or JAR / Maven libraries.

## Canonical Create (dev / iteration defaults)

For dev, demo, and iteration work, always pass these fields:

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

> **Tuned for demo / iteration.** The `pipelines.*RetryAttempts: "0"` overrides disable retries so a broken update fails fast (~30s) instead of retrying for 10+ min on the same root cause. For production, **drop these overrides** so the platform's retry defaults (5 update / 2 flow) absorb transient infra failures.

Per-field rationale:

- **`continuous: false`** — triggered runs. `true` auto-restarts failed updates forever (`cause: RETRY_ON_FAILURE`), burning cost and trapping polling loops. Only `true` when the user explicitly asks for always-on streaming.
- **`development: true`** — faster startup, relaxed validation, no retry-on-failure. Required for any edit/re-run loop.
- **`pipelines.numUpdateRetryAttempts: "0"` + `maxFlowRetryAttempts: "0"`** — belt-and-suspenders against retries. Even with `development`, some configs still retry. Drop for prod.
- **`channel: "PREVIEW"`** — latest features. `"CURRENT"` (default) for production stability.

Variant snippets below show only the **deltas** to add/replace in the canonical JSON.

---

## Top-Level Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `serverless` | bool | `true` | Serverless compute. `false` requires `clusters`. |
| `continuous` | bool | `false` | `true` = always running. `false` = triggered runs. |
| `development` | bool | `false` | Dev mode: faster startup, relaxed validation, no retries. |
| `photon` | bool | `false` | Photon vectorized engine. |
| `edition` | str | `"CORE"` | `"CORE"`, `"PRO"`, `"ADVANCED"`. CDC requires `"ADVANCED"`. |
| `channel` | str | `"CURRENT"` | `"CURRENT"` (stable) or `"PREVIEW"` (latest features). |
| `clusters` | list | `[]` | Cluster configs. Required if `serverless: false`. |
| `configuration` | dict | `{}` | Spark/pipeline config key-value (all values strings). |
| `tags` | dict | `{}` | Metadata tags (max 25). |
| `event_log` | dict | auto | Custom event log table location. |
| `notifications` | list | `[]` | Email/webhook alerts. |
| `allow_duplicate_names` | bool | `false` | Allow multiple pipelines with the same name. |
| `budget_policy_id` | str | — | Budget policy for cost tracking. |
| `storage` | str | — | DBFS root (legacy — use Unity Catalog). |
| `target` | str | — | **Deprecated** — use `schema`. |
| `dry_run` | bool | `false` | Validate without creating (create only). |
| `run_as` | dict | — | Run as specific user / service principal. |
| `restart_window` | dict | — | Maintenance window for continuous-pipeline restarts. |
| `filters` | dict | — | Include/exclude specific paths. |
| `trigger` | dict | — | **Deprecated** — use `continuous`. |
| `deployment` | dict | — | `BUNDLE` (DABs) vs `DEFAULT`. |
| `environment` | dict | — | Python pip deps for serverless. |
| `gateway_definition` | dict | — | CDC gateway pipeline config. |
| `ingestion_definition` | dict | — | Managed ingestion (Salesforce, Workday, etc.). |
| `usage_policy_id` | str | — | Usage policy. |

### Edition Comparison

| Feature | CORE | PRO | ADVANCED |
|---------|------|-----|----------|
| Streaming tables | ✓ | ✓ | ✓ |
| Materialized views | ✓ | ✓ | ✓ |
| Expectations | ✓ | ✓ | ✓ |
| CDC | — | — | ✓ |
| SCD Type 1/2 | — | — | ✓ |

---

## `clusters[]` — Classic Cluster Config

Required when `serverless: false`. Each cluster object:

| Field | Type | Description |
|-------|------|-------------|
| `label` | str | **Required**. `"default"` (main) or `"maintenance"`. |
| `num_workers` | int | Fixed workers (mutually exclusive with `autoscale`). |
| `autoscale` | dict | `{"min_workers": N, "max_workers": N, "mode": "ENHANCED"}` — `"ENHANCED"` recommended. |
| `node_type_id` | str | Instance type (e.g. `"i3.xlarge"`). |
| `driver_node_type_id` | str | Defaults to `node_type_id`. |
| `instance_pool_id` | str | Faster startup via pool. |
| `driver_instance_pool_id` | str | Pool for driver. |
| `spark_conf` | dict | Per-cluster Spark config. |
| `spark_env_vars` | dict | Env vars. |
| `custom_tags` | dict | Cloud resource tags. |
| `init_scripts` | list | Init scripts. |
| `aws_attributes` | dict | e.g. `{"availability": "SPOT", "zone_id": "us-west-2a"}`. |
| `azure_attributes` | dict | e.g. `{"availability": "SPOT_AZURE"}`. |
| `gcp_attributes` | dict | GCP-specific. |

---

## `event_log` — Custom Event Log Table

| Field | Description |
|-------|-------------|
| `catalog` | UC catalog for the event log table. |
| `schema` | Schema for the event log table. |
| `name` | Table name. |

---

## `notifications[]` — Alerts

| Field | Description |
|-------|-------------|
| `email_recipients` | List of email addresses. |
| `alerts` | `"on-update-success"`, `"on-update-failure"`, `"on-update-fatal-failure"`, `"on-flow-failure"`. |

---

## `configuration` — Spark / Pipeline Config

All values must be strings.

| Key | Description |
|-----|-------------|
| `spark.sql.shuffle.partitions` | Number of shuffle partitions. `"auto"` recommended. |
| `pipelines.numRetries` | Retries on transient failures. |
| `pipelines.trigger.interval` | Trigger interval for continuous pipelines (e.g. `"1 hour"`). |
| `spark.databricks.delta.preview.enabled` | Enable Delta preview features (`"true"`). |

Any key here is also accessible from pipeline code via `spark.conf.get("key")` — use this to parameterize transformations.

---

## `run_as` — Execution Identity

Only one of these:

| Field | Description |
|-------|-------------|
| `user_name` | Email of workspace user (can only set to your own). |
| `service_principal_name` | Application ID (requires `servicePrincipal/user` role). |

---

## `restart_window` — Continuous-Pipeline Restart Window

For continuous pipelines, the 5-hour window when daily restarts may occur:

| Field | Description |
|-------|-------------|
| `start_hour` | **Required**. Hour 0–23 when window begins. |
| `days_of_week` | `"MONDAY"`, `"TUESDAY"`, … (default: all). |
| `time_zone_id` | e.g. `"America/Los_Angeles"` (default UTC). |

---

## `filters` — Path Filtering

| Field | Description |
|-------|-------------|
| `include` | Paths to include. |
| `exclude` | Paths to exclude. |

---

## `environment` — Serverless Python Deps

| Field | Description |
|-------|-------------|
| `dependencies` | List of pip requirements, e.g. `["pandas==2.0.0", "requests"]`. |

---

## `deployment` — Deployment Method

| Field | Description |
|-------|-------------|
| `kind` | `"BUNDLE"` (DABs) or `"DEFAULT"`. |
| `metadata_file_path` | Path to deployment metadata. |

---

## Variant Snippets

Each block shows what to add to (or replace in) the canonical create JSON.

### Production mode (remove dev defaults)

The canonical create above is tuned for iteration. For production, **remove** `"development": true` and the two `pipelines.*RetryAttempts` overrides so the platform's retry defaults (5 / 2) can absorb transient infra failures. Add ownership tags:

```json
"channel": "CURRENT",
"tags": {"environment": "production", "owner": "data-team"}
```

Switch `"channel"` to `"CURRENT"` for stable runtime behavior.

### Non-serverless / dedicated cluster

Required only for R, Spark RDD APIs, or JAR/Maven libraries.

```json
"serverless": false,
"photon": true,
"edition": "ADVANCED",
"clusters": [{
  "label": "default",
  "autoscale": {"min_workers": 2, "max_workers": 8, "mode": "ENHANCED"},  // or "num_workers": 4 for fixed
  "node_type_id": "i3.xlarge",
  "spark_conf": {"spark.sql.adaptive.enabled": "true"},
  "custom_tags": {"environment": "production"}
}]
```

### Continuous streaming

```json
"continuous": true,
"configuration": {"spark.sql.shuffle.partitions": "auto"}
```

### Email notifications

```json
"notifications": [{
  "email_recipients": ["team@example.com", "oncall@example.com"],
  "alerts": ["on-update-failure", "on-update-fatal-failure", "on-flow-failure"]
}]
```

### Serverless Python dependencies

```json
"environment": {
  "dependencies": ["scikit-learn==1.3.0", "pandas>=2.0.0", "requests"]
}
```

### Continuous with restart window

Combine `"continuous": true` with:

```json
"restart_window": {
  "start_hour": 2,
  "days_of_week": ["SATURDAY", "SUNDAY"],
  "time_zone_id": "America/Los_Angeles"
}
```

### Custom event-log location

```json
"event_log": {
  "catalog": "audit_catalog",
  "schema": "pipeline_logs",
  "name": "my_pipeline_events"
}
```

---

## Updating an Existing Pipeline

`update` takes the same JSON shape as `create`:

```bash
databricks pipelines update <pipeline_id> --json '{
  "name": "updated_name",
  "development": false,
  "notifications": [{"email_recipients": ["team@example.com"], "alerts": ["on-update-failure"]}]
}'
```

Then trigger a new run with `databricks pipelines start-update <pipeline_id> [--full-refresh]`. See [2-rapid-iteration-with-cli.md](2-rapid-iteration-with-cli.md#step-4-start-an-update-and-poll-that-update) for the polling pattern — never poll top-level `pipelines get` state for run completion.

---

## Multi-Schema Patterns

**Preferred: one pipeline, multiple schemas** via fully-qualified table names. Simpler than running multiple pipelines. For trivial cases where all tables share one schema, use name prefixes (`bronze_*`, `silver_*`, `gold_*`).

Set pipeline defaults to one schema (e.g. bronze); pull the rest from `configuration`:

```python
silver_schema = spark.conf.get("silver_schema")  # add silver_catalog too for cross-catalog
gold_schema   = spark.conf.get("gold_schema")

@dp.table(name="orders_bronze")                                  # uses pipeline default schema
def orders_bronze(): ...

@dp.table(name=f"{silver_schema}.orders_clean")                  # other schema, same catalog
def orders_clean(): ...

@dp.materialized_view(name=f"{gold_schema}.orders_by_date")
def orders_by_date(): ...
```

For cross-catalog: use three-part `f"{cat}.{schema}.{table}"` in `name=`. SQL uses the same fully-qualified form in `CREATE OR REFRESH ...`.

---

## Platform Constraints

### Serverless requirements

| Requirement | Notes |
|-------------|-------|
| Unity Catalog | Required — serverless always uses UC. |
| Region | Must be serverless-enabled. |
| Terms | Workspace must accept serverless terms of use. |
| CDC | Requires serverless (or Pro/Advanced with classic). |

### Serverless limitations (force classic clusters)

| Limitation | Reason to use classic |
|------------|----------------------|
| R language | Not supported on serverless. |
| Spark RDD APIs | Not supported. |
| JAR libraries / Maven coordinates | Not supported. |
| DBFS root access | Limited — use UC external locations. |
| Global temp views | Not supported. |

### General constraints

| Constraint | Notes |
|------------|-------|
| Schema evolution | Streaming tables need full refresh for incompatible changes. |
| `PIVOT` clause | Unsupported. |
| Sinks | Python only; streaming only; append-only flows. |
