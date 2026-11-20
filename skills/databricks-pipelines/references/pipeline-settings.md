# Pipeline Settings Reference

Field reference for pipeline settings. Any field from the Databricks Pipelines API is accepted and validated by the API itself. `databricks pipelines update` replaces the whole spec and resets omitted fields. Build the update from `databricks pipelines get <pipeline-id>`: the fields of its `spec` go at the top level of the request, together with `parameters` and `run_as` when they are set. In a bundle, edit the pipeline resource instead.

Use **serverless + Unity Catalog** by default. Don't set `serverless: false` unless the user needs R, Spark RDD APIs, or JAR / Maven libraries.

## Canonical Create (dev / iteration defaults)

For dev, demo, and iteration work, pass these fields:

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

- **`continuous: false`**: triggered runs. `true` restarts failed updates indefinitely (`cause: RETRY_ON_FAILURE`), which costs money and traps polling loops. Make a pipeline always-on with a continuous schedule instead (see [continuous-pipeline.md](continuous-pipeline.md); Real-Time Mode uses one too, see [real-time-mode-sdp.md](real-time-mode-sdp.md)).
- **`development: true`**: faster startup and no retry on failure, for an edit and re-run loop.
- **`pipelines.numUpdateRetryAttempts: "0"` + `pipelines.maxFlowRetryAttempts: "0"`**: a broken update fails fast (~30s) instead of retrying on the same root cause for 10+ minutes.
- **`channel: "PREVIEW"`**: latest features. Use `"CURRENT"` (the default) for production.

For production, remove `"development": true` and the two retry overrides so the platform's retry defaults (5 update retries, 2 flow retries) absorb transient failures, and switch to `"channel": "CURRENT"`.

## String Fields

| Field              | Description                                                                                                                                                                                                           |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`             | Friendly display name for the pipeline. Must be unique within the workspace.                                                                                                                                          |
| `channel`          | Release channel. Default: `"current"`. Values: `"current"` (current runtime version) or `"preview"` (pre-release, for testing upcoming runtime changes).                                                              |
| `catalog`          | Unity Catalog catalog to publish data to. If `schema` is also set, tables publish to `catalog.schema.table`. Note that it is not possible to switch between Hive Metastore and Unity Catalog after pipeline creation. |
| `schema`           | Default schema (database) where tables are read from or published to. Preferred over `target` for new pipelines.                                                                                                      |
| `root_path`        | Workspace root directory for the pipeline (e.g. `"/Workspace/Users/user/my-pipeline"`). Used as the base for editing and added to `sys.path` for Python execution.                                                    |
| `budget_policy_id` | ID of the serverless usage policy for this pipeline. Only applicable to serverless pipelines.                                                                                                                         |
| `edition`          | Pipeline product edition. Default: `"ADVANCED"`. Values: `"CORE"` (streaming ingest), `"PRO"` (streaming ingest + CDC), `"ADVANCED"` (streaming ingest + CDC + expectations for data quality).                        |
| `storage`          | DBFS or cloud storage location for storing output data and metadata. Only relevant for Hive Metastore pipelines. **Cannot be changed after pipeline creation — do not modify.**                                       |
| `target`           | **Legacy** — use `schema` instead. Target schema for publishing tables (Hive Metastore only).                                                                                                                         |

## Boolean Fields

| Field        | Default | Description                                                                                                                                                                                                                         |
| ------------ | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `photon`     | `false` | Enable Photon for accelerated query execution.                                                                                                                                                                                      |
| `serverless` | —       | Use serverless compute. Set `serverless: true` explicitly for a serverless pipeline rather than relying on a default. When enabled, Databricks manages cluster provisioning automatically — `clusters` cannot be set alongside `serverless: true`.                                                     |
| `continuous` | `false` | Run the pipeline continuously (always-on) vs. triggered (on-demand). Continuous mode keeps clusters running and processes data as it arrives; triggered mode shuts down after each update. Replaces the deprecated `trigger` field. **Legacy mechanism — do NOT set this to `true` to make a pipeline continuous**; create a backing continuous schedule instead (read [continuous-pipeline](continuous-pipeline.md)). Existing pipelines may still have `continuous: true`, and it remains valid — setting it back to `false` is the correct way to make such a pipeline triggered. |
| `allow_duplicate_names` | `false` | Allow this pipeline to have the same name as another pipeline. When `false`, creating or renaming it fails if the name is already taken. |
| `development` | `false` | Development mode: faster startup and no retries on failure. |
| `dry_run`    | `false` | Create only: validate the request without creating the pipeline. |

## Other Fields

| Field | Description |
| ----- | ----------- |
| `event_log` | Event log table location: `{"catalog": ..., "schema": ..., "name": ...}`. |
| `restart_window` | For legacy `continuous: true` pipelines, the 5-hour window when daily restarts may occur: `start_hour` (0–23, required), `days_of_week` (default all), `time_zone_id` (default UTC). A continuous schedule uses its job's maintenance window instead. |
| `filters` | `include` / `exclude` path lists. |
| `deployment` | `kind` (`"BUNDLE"` for bundles, or `"DEFAULT"`) and `metadata_file_path`. |
| `trigger` | **Deprecated**, use `continuous`. |
| `gateway_definition` / `ingestion_definition` | Managed ingestion (Lakeflow Connect) pipelines. |
| `usage_policy_id` | Usage policy. |

## Complex Fields.

### `clusters` (array of objects)

Cluster configuration for the pipeline. Each entry defines a cluster profile.

```yaml
clusters:
  - label: 'default'
    autoscale:
      min_workers: 1
      max_workers: 5
      mode: 'ENHANCED'
  - label: 'maintenance'
    num_workers: 1
```

- `label`: Cluster profile name. Standard values: `"default"` (applies to both update and maintenance clusters), `"updates"` (update cluster only), `"maintenance"` (maintenance cluster only). Custom labels are also supported.
- `autoscale`: Auto-scaling config with `min_workers`, `max_workers`, and optional `mode`.
- `num_workers`: Fixed worker count (mutually exclusive with `autoscale`).
- Additional cluster attributes can be nested per cluster: `node_type_id`, `driver_node_type_id`, `instance_pool_id`, `driver_instance_pool_id`, `spark_conf`, `spark_env_vars`, `custom_tags`, `init_scripts`, and `aws_attributes` / `azure_attributes` / `gcp_attributes` (for example `{"availability": "SPOT"}`). Use `mode: 'ENHANCED'` for autoscaling.

### `configuration` (object — string-to-string map)

Spark and pipeline configuration key-value pairs.

```yaml
configuration:
  spark.databricks.delta.preview.enabled: 'true'
  pipelines.trigger.interval: '1 hour'
```

All keys and values must be strings. Pipeline code reads any key with `spark.conf.get("key")`, so use it to parameterize transformations.

| Key | Description |
| --- | ----------- |
| `spark.sql.shuffle.partitions` | Number of shuffle partitions. `"auto"` recommended. |
| `pipelines.numUpdateRetryAttempts` | Retries of the whole update after a retryable failure (default 5 for triggered pipelines). |
| `pipelines.maxFlowRetryAttempts` | Retries of a single flow before the update fails (default 2). |
| `pipelines.trigger.interval` | Trigger interval for continuous pipelines (e.g. `"1 hour"`). In a Real-Time Mode flow the same key sets the checkpoint interval instead (see [real-time-mode-sdp.md](real-time-mode-sdp.md)). |
| `spark.databricks.delta.preview.enabled` | Enable Delta preview features (`"true"`). |

### `notifications` (array of objects)

Alert notifications for pipeline events.

```yaml
notifications:
  - alerts:
      - 'on-update-failure'
      - 'on-update-fatal-failure'
    email_recipients:
      - 'team@example.com'
  - alerts:
      - 'on-update-success'
    email_recipients:
      - 'alerts@example.com'
```

- `alerts`: List of event types (`"on-update-failure"`, `"on-update-fatal-failure"`, `"on-update-success"`, `"on-flow-failure"`).
- `email_recipients`: List of email addresses to notify.

### `tags` (object — string-to-string map)

Key-value tags for the pipeline, visible in the Jobs & Pipelines list. Pipeline tags are not associated with billing and are not forwarded to clusters as cluster tags.

```yaml
tags:
  team: 'data-engineering'
  env: 'production'
```

### `environment` (object)

Environment specification for installing Python dependencies.

```yaml
environment:
  dependencies:
    - 'scikit-learn==1.3.0'
    - 'pandas>=2.0'
```

- `dependencies`: List of PyPI package specifiers. Databricks recommends pinning versions with `==` (e.g. `'scikit-learn==1.3.0'`) for reproducibility.

### `libraries` (array of objects)

Source code files included in the pipeline. Three entry formats are supported: `glob`, `file`, and `notebook`.

When **adding** libraries, first walk the complete directory tree under the pipeline's `root_path` (NOT just the `transformations` folder) to locate the file or directory the user wants to add. If the file is not found there, search the user's workspace. Once the path is known, match the existing library format — if the pipeline uses `glob`, add new entries as `glob`. If it uses `file`/`notebook`, add new entries as `file` or `notebook`. Keep every existing entry exactly as-is and append the new ones.

**IMPORTANT — no mixing types**: A pipeline's libraries must use either ALL `glob` entries OR ALL `notebook`/`file` entries. You cannot mix `glob` with `notebook` or `file` in the same pipeline — the API will reject it with an error. `notebook` and `file` entries can be mixed with each other.

**IMPORTANT — glob syntax**: `libraries.glob.include` only supports two forms: (1) an exact file path (e.g. `.../utils.py`) or (2) a directory path ending with `/**` for recursive matching (e.g. `.../src/**`). Wildcards like `*`, `?`, or `\` are **not allowed** anywhere else in the path. Patterns like `src/*` or `src/**/*.py` will fail with an API error. To include all files under a directory, use `path/to/dir/**`.

```yaml
libraries:
  - glob:
      include: '/Workspace/Users/user/my-pipeline/transformations/**'
  - glob:
      include: '/Workspace/Users/user/my-pipeline/utils.py'
```

### `run_as` (object)

The identity the pipeline runs as. It is a top-level field, NOT part of `configuration`. Set exactly one key:

- `user_name`: a user's email.
- `service_principal_name`: a service principal's application ID.
- `group_name`: an account group's name.


Changing `run_as` requires **CAN_MANAGE** on the pipeline, plus **CAN_USE** on the service principal when setting one. The new identity applies from the next update. In Unity Catalog pipelines, changing `run_as` makes the new identity the owner of the tables the pipeline publishes. Call this out before changing it. Once set, `run_as` cannot be cleared, only changed to another identity.

#### Run as a group

A pipeline can run as an account group. When the user wants a team rather than a person to run the pipeline or own its tables, set `group_name`. Do not say a pipeline cannot run as a group, and do not substitute a service principal.

- The group must be an account group assigned to the workspace. Workspace-local groups and the built-in `account users`, `admins`, and `users` groups are rejected.
- The caller must be able to assume the group: be a member, or hold can-assume on an exclusive group. Otherwise the edit fails with `PERMISSION_DENIED`.
- The group needs every permission the pipeline uses: compute, read access to the source files, and the Unity Catalog grants on the target catalog and schema.
- The group owns the published tables. It does not become the pipeline's owner.
- In a bundle, set `group_name` in the pipeline resource's `run_as` mapping.

## Variant Snippets

Each block shows what to add to (or replace in) the canonical create JSON.

### Non-serverless / dedicated cluster

Only for R, Spark RDD APIs, or JAR/Maven libraries.

```json
"serverless": false,
"photon": true,
"clusters": [{
  "label": "default",
  "autoscale": {"min_workers": 2, "max_workers": 8, "mode": "ENHANCED"},
  "node_type_id": "i3.xlarge"
}]
```

### Email notifications

```json
"notifications": [{
  "email_recipients": ["team@example.com", "oncall@example.com"],
  "alerts": ["on-update-failure", "on-update-fatal-failure", "on-flow-failure"]
}]
```

### Custom event-log location

```json
"event_log": {
  "catalog": "audit_catalog",
  "schema": "pipeline_logs",
  "name": "my_pipeline_events"
}
```

## Updating an Existing Pipeline

`update` takes the same JSON shape as `create` and replaces the whole spec: omitted fields are reset. Start from `databricks pipelines get <pipeline_id>`, take the fields of its `spec` (plus `parameters` and `run_as` when set), change only what you need, and send the full body:

```bash
databricks pipelines update <pipeline_id> --json @updated_spec.json
```

Then start a run with `databricks pipelines start-update <pipeline_id> [--full-refresh]`. See [2-rapid-iteration-with-cli.md](2-rapid-iteration-with-cli.md#step-4-start-an-update-and-poll-that-update) for the polling pattern; don't poll the top-level `pipelines get` state for run completion.

## Multi-Schema Patterns

Prefer **one pipeline writing to several schemas** through fully qualified table names over several pipelines. When all tables share one schema, name prefixes (`bronze_*`, `silver_*`, `gold_*`) are enough.

Set the pipeline default to one schema (e.g. bronze) and pass the others through `configuration`:

```python
silver_schema = spark.conf.get("silver_schema")
gold_schema   = spark.conf.get("gold_schema")

@dp.table(name="orders_bronze")                      # pipeline default schema
def orders_bronze(): ...

@dp.table(name=f"{silver_schema}.orders_clean")      # other schema, same catalog
def orders_clean(): ...

@dp.materialized_view(name=f"{gold_schema}.orders_by_date")
def orders_by_date(): ...
```

For another catalog, use a three-part name (`f"{cat}.{schema}.{table}"`). SQL uses the same fully qualified form in `CREATE OR REFRESH ...`.

## Platform Constraints

### Serverless requirements

Serverless pipelines always use Unity Catalog, and the workspace must be in a serverless-enabled region with serverless terms accepted.

### Serverless limitations (force classic clusters)

| Limitation | Notes |
| ---------- | ----- |
| R language | Not supported on serverless. |
| Spark RDD APIs | Not supported. |
| JAR libraries / Maven coordinates | Not supported. |
| DBFS root access | Limited; use Unity Catalog volumes or external locations. |
| Global temp views | Not supported. |

### General constraints

| Constraint | Notes |
| ---------- | ----- |
| Schema evolution | Streaming tables need a full refresh for incompatible changes. |
| `PIVOT` clause | Not supported in pipelines. |
| Sinks | Python only, streaming only, append flows only. |
