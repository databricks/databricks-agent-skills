# Configuration Guide

Supported Spark configurations, environment setup, budget policies, and performance mode selection for serverless compute.

## Supported Spark Configurations

Serverless compute supports only 6 Spark configurations. All other configurations are auto-tuned and cannot be overridden.

| Configuration | Description | Default |
|--------------|-------------|---------|
| `spark.sql.shuffle.partitions` | Number of partitions for shuffles (joins, aggregations) | Auto-tuned by AQE |
| `spark.sql.session.timeZone` | Session timezone for timestamp operations | `UTC` |
| `spark.sql.ansi.enabled` | Enable ANSI SQL mode (strict type checking, error on overflow) | `true` |
| `spark.sql.files.maxPartitionBytes` | Max bytes per partition when reading files | `128MB` |
| `spark.sql.legacy.timeParserPolicy` | Time parsing behavior: `EXCEPTION`, `LEGACY`, or `CORRECTED` | `EXCEPTION` |
| `spark.databricks.execution.timeout` | Maximum execution time for a command | Not set (no timeout) |

### Setting Supported Configurations

```python
# In Python:
spark.conf.set("spark.sql.shuffle.partitions", "200")
spark.conf.set("spark.sql.session.timeZone", "America/New_York")
spark.conf.set("spark.sql.ansi.enabled", "false")
```

```sql
-- In SQL:
SET spark.sql.shuffle.partitions = 200;
SET spark.sql.session.timeZone = 'America/New_York';
SET spark.sql.ansi.enabled = false;
```

### Important: ANSI Mode is Enabled by Default

Serverless compute enables ANSI SQL mode by default. This means:
- Integer overflow throws an error instead of wrapping
- Division by zero throws an error instead of returning NULL
- Invalid casts throw errors instead of returning NULL

If your existing code relies on non-ANSI behavior, you may need to:

```python
# Option 1: Disable ANSI mode (quick fix)
spark.conf.set("spark.sql.ansi.enabled", "false")

# Option 2: Fix code to handle edge cases (recommended)
from pyspark.sql import functions as F
# Use try_cast instead of cast for safe conversions
df.select(F.expr("try_cast(col AS INT)"))
# Use try_divide for safe division
df.select(F.expr("try_divide(a, b)"))
```

## Common Unsupported Configurations and What to Do

### Auto-Tuned (Remove — Serverless Handles Automatically)

| Configuration | Why It's Auto-Tuned |
|--------------|-------------------|
| `spark.sql.adaptive.enabled` | AQE is always on and fully managed |
| `spark.sql.adaptive.coalescePartitions.enabled` | Managed by AQE |
| `spark.sql.adaptive.skewJoin.enabled` | Managed by AQE |
| `spark.databricks.delta.autoCompact.enabled` | Always enabled on serverless |
| `spark.databricks.delta.optimizeWrite.enabled` | Always enabled on serverless |
| `spark.databricks.delta.autoOptimize.optimizeWrite` | Always enabled |
| `spark.databricks.delta.autoOptimize.autoCompact` | Always enabled |
| `spark.sql.sources.parallelPartitionDiscovery.parallelism` | Auto-tuned |
| `spark.default.parallelism` | Auto-tuned based on data size |

### Resource Configs (Remove — Serverless Auto-Scales)

| Configuration | Why to Remove |
|--------------|--------------|
| `spark.executor.instances` | Serverless auto-scales executors |
| `spark.executor.memory` | Managed by serverless |
| `spark.executor.cores` | Managed by serverless |
| `spark.driver.memory` | Fixed per environment (8 GB default) |
| `spark.driver.maxResultSize` | Managed by serverless |
| `spark.dynamicAllocation.*` | Serverless has its own autoscaling |

### Credential Configs (Remove — Use UC Instead)

| Configuration | Replacement |
|--------------|-------------|
| `fs.s3a.access.key` | UC storage credentials |
| `fs.s3a.secret.key` | UC storage credentials |
| `fs.s3a.endpoint` | UC external locations |
| `fs.azure.account.key.*` | UC storage credentials |
| `fs.azure.sas.*` | UC storage credentials |
| `hadoop.security.*` | UC governance |

### Temporary Bridge Strategy

If removing a configuration breaks your workload, check if it maps to one of the 6 supported configs. Common mappings:

```python
# BEFORE (classic — many configs):
spark.conf.set("spark.sql.shuffle.partitions", "2000")
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
spark.conf.set("spark.executor.memory", "8g")
spark.conf.set("spark.default.parallelism", "2000")

# AFTER (serverless — only the supported config):
spark.conf.set("spark.sql.shuffle.partitions", "2000")
# Everything else is auto-tuned. You can likely remove shuffle.partitions too
# since AQE will optimize it, but keep it temporarily if needed for validation.
```

## Environment Setup

### Managing Dependencies

Serverless compute uses **Environments** instead of init scripts, cluster libraries, or `dbutils.library.install`. Dependencies can be configured via:

1. **Notebook Environment panel** — click the Environment icon in the notebook sidebar
2. **Job Environment spec** — in the job task configuration
3. **`%pip install`** — inline in notebooks (works but Environment panel is preferred for reproducibility)

### Pinning Versions

Always pin dependency versions for reproducible builds:

```
# Good — pinned versions:
numpy==2.2.2
pandas==2.2.3
scikit-learn==1.4.0
requests==2.31.0

# Bad — unpinned (may break on next run):
numpy
pandas
scikit-learn
```

### Using Private Package Repositories

```
# In workspace admin settings, configure a default PyPI mirror:
# Admin Console → Compute → Environment Settings → PyPI Repository

# Then packages resolve from your private mirror:
my-internal-package==1.0.0
```

### Installing Wheel Files

```
# From UC Volumes (recommended):
/Volumes/main/libs/packages/my_package-1.0.0-py3-none-any.whl

# From workspace files:
/Workspace/shared/packages/my_package-1.0.0-py3-none-any.whl
```

### Workspace Utility Packages

For shared utility code used across notebooks:

```
# Structure in workspace:
# /Workspace/shared/helper_utils/
#   ├── pyproject.toml
#   ├── helper_utils/
#   │   ├── __init__.py
#   │   └── transforms.py

# Add to Environment:
/Workspace/shared/helper_utils

# Use in notebook:
from helper_utils.transforms import clean_data
```

### Critical Rules

- **Never install PySpark** — this overwrites the managed PySpark installation and breaks the session
- **Never install packages that bundle their own Spark** (e.g., some older ML packages)
- **Pin all versions** — floating versions cause non-reproducible results
- **Use UC Volumes** for wheel files, not DBFS paths

## Budget Policies

Budget policies replace cluster policies for cost attribution and control on serverless.

### Creating Budget Policies

Budget policies are configured by workspace admins via the Databricks UI or API:

```bash
# List existing budget policies
databricks budget-policies list

# Assign a budget policy to a job
databricks jobs update <job-id> \
  --json '{"budget_policy_id": "<policy-id>"}'
```

### Using Budget Policies for Cost Attribution

- Each serverless workload can be tagged with a budget policy
- Cost data flows to `system.billing.usage` with the policy tag
- Use this for team-level or project-level cost tracking

```sql
-- Query cost by budget policy
SELECT
  budget_policy_id,
  SUM(usage_quantity) as total_dbus,
  SUM(usage_quantity * list_price) as estimated_cost
FROM system.billing.usage
WHERE usage_type = 'SERVERLESS_COMPUTE'
  AND usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY budget_policy_id
ORDER BY estimated_cost DESC;
```

### Monitoring Cost After Migration

```sql
-- Compare classic vs serverless cost for the same workload
SELECT
  sku_name,
  usage_type,
  SUM(usage_quantity) as total_dbus,
  MIN(usage_date) as first_seen,
  MAX(usage_date) as last_seen
FROM system.billing.usage
WHERE workspace_id = '<workspace-id>'
  AND usage_date >= current_date() - INTERVAL 90 DAYS
GROUP BY sku_name, usage_type
ORDER BY total_dbus DESC;
```

## Performance Mode Selection

Serverless compute offers two performance modes. Choose based on workload characteristics.

### Performance-Optimized

| Aspect | Detail |
|--------|--------|
| Startup time | Under 50 seconds |
| Cost | Higher per DBU |
| Available for | Notebooks, Jobs, Spark Declarative Pipelines |
| Best for | Interactive development, time-sensitive jobs, notebooks |
| Default | Yes (for both UI and API) |

### Standard

| Aspect | Detail |
|--------|--------|
| Startup time | 4-6 minutes |
| Cost | Significantly lower per DBU |
| Available for | Jobs and Spark Declarative Pipelines **only** |
| Best for | Batch ETL, scheduled pipelines, cost-sensitive workloads |
| Default | No — must be explicitly selected |

**Standard mode is NOT available for notebooks.** Notebooks always use Performance-Optimized.

### Selection Guide

```
Workload → What type?
├── Interactive notebook → Performance-Optimized (only option)
├── Job / Pipeline
│   ├── Time-sensitive (SLA < 10 min)? → Performance-Optimized
│   ├── Dev/test iteration? → Performance-Optimized
│   ├── Batch ETL, scheduled? → Standard (cost savings)
│   ├── Large-scale data processing? → Standard (cost savings)
│   └── Default for production pipelines → Standard (unless latency matters)
```

### Setting Performance Mode

```bash
# Via Databricks CLI for a job:
databricks jobs update <job-id> \
  --json '{"tasks": [{"task_key": "etl", "environment_key": "default", "compute": {"serverless": {"performance_mode": "STANDARD"}}}]}'
```

In the Databricks UI:
1. Open the Job configuration
2. Under Compute, select "Serverless"
3. Choose "Performance-Optimized" or "Standard"

## Serverless Compute Defaults

| Setting | Value |
|---------|-------|
| Driver memory (REPL) | 8 GB default (high-memory option available) |
| Max executors | 32 (Premium), 64 (Enterprise) — can request increase via support |
| Auto-scaling | Always enabled, fully managed |
| AQE | Always enabled |
| Delta auto-compact | Always enabled |
| Delta optimize write | Always enabled |
| ANSI SQL mode | Enabled by default (can disable) |
| Debugging | Query Profile (no Spark UI) |

## Job Configuration Transformation

### Before (Classic Compute)

```json
{
  "job_clusters": [{
    "job_cluster_key": "my_cluster",
    "new_cluster": {
      "spark_version": "15.4.x-scala2.12",
      "num_workers": 2,
      "node_type_id": "Standard_DS3_v2",
      "init_scripts": [{ "dbfs": { "destination": "dbfs:/init/setup.sh" } }]
    }
  }],
  "tasks": [{
    "task_key": "main_task",
    "job_cluster_key": "my_cluster",
    "notebook_task": { "notebook_path": "/path/to/notebook" }
  }]
}
```

### After (Serverless)

```json
{
  "environments": [{
    "environment_key": "serverless_env",
    "spec": {
      "client": "2",
      "dependencies": ["pandas==2.2.3", "numpy==2.2.2"]
    }
  }],
  "tasks": [{
    "task_key": "main_task",
    "environment_key": "serverless_env",
    "notebook_task": { "notebook_path": "/path/to/notebook" }
  }]
}
```

### Key Changes

- **Remove** `job_clusters` / `new_cluster` — serverless manages infrastructure
- **Add** `environments` with serverless spec
- **Replace** `job_cluster_key` with `environment_key` in each task
- **Remove** `init_scripts` — move to environment `dependencies`
- **Remove** `num_workers`, `node_type_id`, `spark_version` — all auto-managed

## Job Definition Migration (Complete Example)

This section shows the full transformation from a classic job with init scripts, cluster libraries, and spark_conf to a serverless job with Environments.

### Before (Classic Job with Init Scripts, Libraries, and spark_conf)

```json
{
  "name": "daily_etl_pipeline",
  "job_clusters": [{
    "job_cluster_key": "etl_cluster",
    "new_cluster": {
      "spark_version": "15.4.x-ml-scala2.12",
      "num_workers": 4,
      "node_type_id": "i3.xlarge",
      "init_scripts": [
        { "dbfs": { "destination": "dbfs:/init/install_packages.sh" } },
        { "dbfs": { "destination": "dbfs:/init/setup_env.sh" } }
      ],
      "spark_conf": {
        "spark.sql.shuffle.partitions": "400",
        "spark.sql.adaptive.enabled": "true",
        "spark.executor.memory": "8g",
        "spark.databricks.delta.autoCompact.enabled": "true",
        "fs.s3a.access.key": "{{secrets/scope/s3-key}}"
      },
      "custom_tags": { "team": "data-eng" }
    }
  }],
  "tasks": [{
    "task_key": "etl_main",
    "job_cluster_key": "etl_cluster",
    "notebook_task": { "notebook_path": "/Repos/team/project/etl_main" },
    "libraries": [
      { "maven": { "coordinates": "com.example:connector:1.0" } },
      { "jar": "dbfs:/libs/custom_udf.jar" }
    ]
  }]
}
```

Suppose the init scripts contain:

```bash
# install_packages.sh
#!/bin/bash
pip install mlflow==2.12.1 scikit-learn==1.3.0 xgboost==2.0.3
pip install /dbfs/libs/internal_utils-1.0.0.whl

# setup_env.sh
#!/bin/bash
apt-get install -y libgomp1
export MODEL_ENV=production
```

### After (Serverless Job with Environments)

```json
{
  "name": "daily_etl_pipeline",
  "environments": [{
    "environment_key": "etl_env",
    "spec": {
      "client": "2",
      "dependencies": [
        "mlflow==2.12.1",
        "scikit-learn==1.3.0",
        "xgboost==2.0.3",
        "/Volumes/<your_catalog>/libs/packages/internal_utils-1.0.0.whl"
      ]
    }
  }],
  "tasks": [{
    "task_key": "etl_main",
    "environment_key": "etl_env",
    "notebook_task": {
      "notebook_path": "/Repos/team/project/etl_main",
      "base_parameters": { "model_env": "production" }
    }
  }]
}
```

### Transformation Notes

| Classic element | Serverless equivalent | Notes |
|----------------|----------------------|-------|
| `job_clusters` / `new_cluster` | Removed entirely | Serverless manages infrastructure |
| `init_scripts` (pip install) | `environments[].spec.dependencies` | Extract pip packages to dependencies list |
| `init_scripts` (apt install) | Convert to pip equivalent or flag | `apt install libgomp1` — usually bundled with pip packages (xgboost includes it); flag if no pip equivalent exists |
| `init_scripts` (export env vars) | `notebook_task.base_parameters` | Pass as job parameters, read with `dbutils.widgets.get()` |
| `libraries` (Maven) | PyPI equivalent in `dependencies` | Replace Maven coordinate with its pip package name |
| `libraries` (JAR on DBFS) | Move JAR to Volumes or flag | Custom Spark data source JARs = Category 3 blocker; UDF JARs can be moved to Volumes |
| `spark_conf` (supported) | Keep in notebook code | `spark.sql.shuffle.partitions` is supported — set in notebook |
| `spark_conf` (auto-tuned) | Remove with comment | AQE, auto-compact, executor sizing — add `# Removed: auto-tuned on serverless` |
| `spark_conf` (credentials) | Remove — use UC | `fs.s3a.*` replaced by UC external locations |
| `spark_version` (ML runtime) | Add ML libs to `dependencies` | ML runtime is NOT available on serverless — list mlflow, sklearn, etc. explicitly |
| `num_workers` / `node_type_id` | Removed | Serverless auto-scales |
| `custom_tags` | Use budget policies | Cost attribution via budget policies instead |

## Environment Version Mapping

Match the serverless environment version to the DBR version the workload was running on:

| Classic DBR Version | Serverless `spec.client` | Python |
|---------------------|--------------------------|--------|
| 13.x, 14.x | `"1"` | 3.10 |
| 15.x | `"2"` | 3.11 |
| 16.x+ | `"3"` | 3.12 |

Example environment configuration:

```json
{
  "environments": [{
    "environment_key": "serverless_env",
    "spec": {
      "client": "2",
      "dependencies": ["pandas==2.2.3"]
    }
  }]
}
```

For test jobs, disable auto optimization for faster feedback:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs

w = WorkspaceClient()
w.jobs.create(
    name="serverless-test-job",
    tasks=[jobs.Task(
        task_key="test_task",
        notebook_task=jobs.NotebookTask(notebook_path="/path/to/notebook"),
        environment_key="serverless_env",
        disable_auto_optimization=True,  # Faster startup for testing
        max_retries=0,  # No retries — surface failures immediately
    )],
    environments=[jobs.JobEnvironment(
        environment_key="serverless_env",
        spec=jobs.JobEnvironmentSpec(client="2", dependencies=[]),
    )],
)
```

## Catalog Parameterization

Make notebooks work with both production and test catalogs during migration:

```python
# Add at the top of the notebook
dbutils.widgets.text("catalog", "main")  # Default to production
catalog = dbutils.widgets.get("catalog")

# Use the parameter in all table references
df = spark.table(f"{catalog}.sales.orders")
df_accounts = spark.table(f"{catalog}.sfdc_bronze.account")
```

When creating mock tables for testing, the schema names stay the same — only the catalog changes:
- `main.sfdc_bronze.case` → `test_catalog.sfdc_bronze.case`
- `main.sales.orders` → `test_catalog.sales.orders`

Pass `catalog="test_catalog"` as a job parameter during testing. In production, the default `"main"` is used.

## Test Data Setup Pattern

When migrating jobs that read from production tables, do not run the test job against production. Create sampled copies in a dedicated test catalog instead — this keeps the test loop fast, safe, and idempotent.

### Prerequisites

- A running SQL warehouse (needed to execute the `CREATE TABLE AS SELECT` statements)
- A test catalog that already exists, with `CREATE TABLE` and `CREATE SCHEMA` permissions granted to the user
- `SELECT` permission on each source table — flag any permission gaps early, do not silently skip tables

### Setup Steps

1. Discover upstream tables from the job — either from the job's lineage (if available) or by static scan of the notebook
2. For each upstream table, run:

```sql
CREATE SCHEMA IF NOT EXISTS <test_catalog>.<schema>;
CREATE TABLE IF NOT EXISTS <test_catalog>.<schema>.<table>
AS SELECT * FROM <prod_catalog>.<schema>.<table> LIMIT <N>;
```

3. Typical `N` is 10 rows for smoke tests, up to 1000 for more realistic validation
4. Keep schema names identical between prod and test — only the catalog changes. This lets the same notebook code run in both environments via the `catalog` widget

### Idempotency

Use `CREATE TABLE IF NOT EXISTS` so the setup is safe to re-run. Skip tables that already exist rather than recreating them — this keeps test data stable across migration iterations.

### Post-Setup

Once mock tables exist, update the notebook's catalog references (or set the `catalog` job parameter) to point to the test catalog before creating the test job. Do not hardcode the test catalog into the notebook — use the widget parameter so the same file ships to production unchanged.

### Test Job Settings

For the test job, disable auto-optimization and retries to surface failures quickly:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs

w = WorkspaceClient()
w.jobs.create(
    name="serverless-test-<job_name>",
    tasks=[jobs.Task(
        task_key="test_task",
        notebook_task=jobs.NotebookTask(
            notebook_path="/path/to/notebook",
            base_parameters={"catalog": "<test_catalog>"},
        ),
        environment_key="serverless_env",
        disable_auto_optimization=True,  # Faster startup while iterating
        max_retries=0,                    # Surface failures immediately — no retries during testing
    )],
    environments=[jobs.JobEnvironment(
        environment_key="serverless_env",
        spec=jobs.JobEnvironmentSpec(client="2", dependencies=[]),
    )],
)
```

- `disable_auto_optimization=True` — skip auto-optimization for faster test-loop feedback
- `max_retries=0` — any failure surfaces immediately instead of being masked by retries
- Do not carry these settings into the production job config — they are test-only

## Debugging Failed Serverless Runs

Always get the actual error before guessing:

```python
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()

run_id = 12345  # replace with the failed run_id from the Jobs UI
run_output = w.jobs.get_run_output(run_id=run_id)
print(run_output.error)        # Error message
print(run_output.error_trace)  # Full stack trace
```

### Common Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `INFINITE_STREAMING_TRIGGER_NOT_SUPPORTED` | Time-based or default streaming trigger | Add `.trigger(availableNow=True)` |
| `SparkConnectGrpcException: UNRESOLVED_COLUMN` | Temp view name collision (Spark Connect lazy eval) | Use unique temp view names |
| `TABLE_OR_VIEW_NOT_FOUND` | DBFS or HMS table not accessible on serverless | Migrate to Unity Catalog |
| `Py4JError: ... is not available` | SparkContext/RDD API used | Rewrite to DataFrame API |
| Package installation timeout | Version not pinned or PySpark dependency conflict | Pin versions; do NOT install PySpark as a dependency |
| `PERMISSION_DENIED` on table access | UC permissions not granted | Grant appropriate UC permissions |
| `ModuleNotFoundError: No module named 'mlflow'` | ML library not in serverless environment | Add to environment spec `dependencies` — ML runtime is NOT available on serverless |
| `SparkContext.getOrCreate() is NOT supported` / `RuntimeError: Only remote Spark sessions` | Direct SparkContext usage | Replace with `spark.createDataFrame()` or `spark.range()` |
| `UC_FILE_SCHEME_FOR_TABLE_CREATION_NOT_SUPPORTED` | DBFS path used as table location | Use managed tables or `/Volumes/...` paths |
| `PERMISSION_DENIED: CREATE SCHEMA on Catalog 'main'` | No catalog specified before CREATE | Add `spark.sql("USE CATALOG <your_catalog>")` before CREATE statements |
| `DATA_SOURCE_NOT_FOUND: Failed to find data source` | Custom JAR data source not available | Category 3 blocker — needs JAR on classic compute |
| `SyntaxError` after migration | Comment placement broke cell boundaries | Ensure comments are inside MAGIC blocks, not straddling cell delimiters |

## Documentation

- Supported Spark configs: https://docs.databricks.com/en/spark/conf#serverless
- Serverless environments/dependencies: https://docs.databricks.com/en/compute/serverless/dependencies
- Budget policies: https://docs.databricks.com/en/admin/usage/budget-policies.html
- System billing tables: https://docs.databricks.com/en/admin/system-tables/billing.html
- Serverless best practices: https://docs.databricks.com/en/compute/serverless/best-practices
- Serverless compute overview: https://docs.databricks.com/en/compute/serverless/
- Databricks SDK: https://docs.databricks.com/en/dev-tools/sdk-python.html
