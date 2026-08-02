# Analysis Output Examples

Worked output of the Step 2 serverless-readiness scan: the post-rewrite cell-magic lint, the full finding catalogue by category, and the deployment-blocker table. Read this while writing or reviewing a scan report.

## Contents

  - [Post-rewrite lint: Cell-magic boundary check (A1)](#post-rewrite-lint-cell-magic-boundary-check-a1)
- [Category A: Unsupported APIs](#category-a-unsupported-apis)
- [Category B: Data Access](#category-b-data-access)
- [Category C: Streaming](#category-c-streaming)
- [Category D: Configuration](#category-d-configuration)
- [Category E: Libraries](#category-e-libraries)
- [Category F: Networking](#category-f-networking)
- [Category G: Sizing & Debugging](#category-g-sizing--debugging)
- [Category H: Job-level config (dbt_task, SDP, multi-source, deploy preconditions)](#category-h-job-level-config-dbt_task-sdp-multi-source-deploy-preconditions)

---

#### Post-rewrite lint: Cell-magic boundary check (A1)

**HIGH IMPACT.** Before declaring a migrated notebook ready, run this lint pass on every output cell. Caused 3/7 demos to fail in the dbdemos E2E sweep (hls-readmission, fsi-fraud, retail-c360).

**Detect**: any cell that contains a `# MAGIC %<word>` line (e.g., `# MAGIC %run`, `# MAGIC %sql`, `# MAGIC %md`, `# MAGIC %pip`, `# MAGIC %fs`). Within that cell, every non-blank line must either start with `# MAGIC ` or be a blank line. If a plain-Python comment (or any other Python code) precedes the `# MAGIC %...` directive in the same cell, the cell is corrupted: Databricks parses it as Python and `%run` falls back to IPython line magic, producing errors like `File './00-global-setup-v2' not found`.

**Fix**: never prepend plain-Python comments above a `# MAGIC %...` line within the same cell. Two valid options:

1. **Preferred**: put migration notes in a separate `# MAGIC %md` cell above (its own `# COMMAND ----------` block).
2. **Acceptable**: drop the migration note entirely and rely on git/file history.

**Example before** (corrupted; `%run` fails with `File not found`):

```python
# COMMAND ----------

# Migration: relative '%run ../../../_resources/00-global-setup-v2' may not
# resolve under serverless job tasks. Replaced with sibling reference.
# MAGIC %run ./00-global-setup-v2
```

**Example after** (clean; `%run` fires as cell magic):

```python
# COMMAND ----------

# MAGIC %md
# MAGIC Migration: relative %run path replaced with sibling reference.

# COMMAND ----------

# MAGIC %run ./00-global-setup-v2
```

### Category A: Unsupported APIs

| Pattern | Severity | Fix |
|---------|----------|-----|
| `sc.parallelize(data)` | Blocker | `spark.createDataFrame([(x,) for x in data], ["value"])` |
| `rdd.map(fn)` | Blocker | `df.select(F.col("value") * 2)` or `df.withColumn(...)` |
| `rdd.filter(fn)` | Blocker | `df.filter(F.col("value") > 3)` |
| `rdd.reduce(fn)` | Blocker | `df.agg(F.sum("col")).collect()[0][0]` |
| `rdd.flatMap(fn)` | Blocker | `df.select(F.explode(F.split(col, " ")))` |
| `rdd.groupByKey()` | Blocker | `df.groupBy("key").agg(F.collect_list("value"))` |
| `rdd.mapPartitions(fn)` | Blocker | `df.groupBy(F.spark_partition_id()).applyInPandas(fn, schema)` |
| `sc.textFile(path)` | Blocker | `spark.read.text(path)` |
| `sc.wholeTextFiles(path)` | Blocker | `spark.read.format("binaryFile").load(path)` |
| `sc.broadcast(data)` | Blocker | `from pyspark.sql.functions import broadcast; df.join(broadcast(lookup_df), key)` |
| `sc.accumulator(init)` | Blocker | `df.agg(F.sum("col"))` or `df.count()` |
| `spark.sparkContext` | Blocker | Use `spark` (SparkSession) directly |
| `SparkContext.getOrCreate()` | Blocker | Not supported — raises `RuntimeError: Only remote Spark sessions using Databricks Connect are supported`. Replace with `spark.createDataFrame()` or `spark.range()` for data setup. |
| `sqlContext.sql(query)` | Blocker | `spark.sql(query)` |
| `sc.hadoopConfiguration.set(...)` | Blocker | Use UC external locations — no credential configs needed |
| `df.cache()` / `df.persist()` | Warning | Remove caching calls. For expensive intermediate results, materialize to a Delta table. Native support coming soon. |
| `df.checkpoint()` | Warning | Write to Delta table instead |
| `spark.catalog.cacheTable(t)` / `CACHE TABLE` | Warning | Remove — not needed on serverless |
| `%scala` cells in notebook | Blocker | Port to PySpark/SQL or compile as JAR for job tasks |
| `%r` cells in notebook | Blocker | No serverless equivalent — keep on classic or port to PySpark |
| Hive variable syntax `${var}` | Warning | Use `DECLARE VARIABLE` / `SET VARIABLE` (SQL) or Python f-strings |
| `CREATE GLOBAL TEMPORARY VIEW` | Blocker | Use `CREATE OR REPLACE TEMPORARY VIEW` — `global_temp` database doesn't exist on serverless |
| `global_temp.` prefix in queries | Warning | Remove prefix — session-scoped temp views are accessible without qualifier |
| Builtin `max(..., key=)` / `min(..., key=)` / `sorted(..., key=)` with `from pyspark.sql.functions import *` (A2) | Blocker | `pyspark.sql.functions.max` shadows the builtin and rejects `key=` (raises `TypeError: max() got an unexpected keyword argument 'key'`). Use sort+index: `xs.sort(key=...); top = xs[0]`. See mlflow-uc-patterns. |
| `from databricks import automl` / `automl.classify()` / `automl.regress()` / `automl.forecast()` (A3) | Blocker | AutoML not available on serverless and the `DBDemos.create_mockup_automl_run` fallback hits `PlanMetrics not JSON serializable` on Spark Connect. Rewrite as inline scikit-learn `Pipeline` with `mlflow.sklearn.log_model` + `mlflow.register_model` + UC alias. See mlflow-uc-patterns. |
| `mlflow.pyfunc.spark_udf(...)` followed by `df.withColumn("prediction", loaded_model(struct(*features)))` (A4) | Blocker on mlflow 2.19.0 | Closure bug on Spark Connect: `batch_predict_fn` captures `loaded_model` as a free variable; workers fail with `NameError: cannot access free variable 'loaded_model'`. **Root cause is Spark Connect serialization.** Preferred fix (portable, any mlflow), driver-side pandas inference: `mlflow.pyfunc.load_model(uri).predict(df.toPandas())` then `spark.createDataFrame(...)`. Fallback fix: pin `mlflow>=2.20.0` in the environment spec. |
| `AutoCaptureConfigInput(enabled=...)` in model-serving endpoint creation (A5) | Warning | Deprecated arg, breaks first-time endpoint deploy. Remove the `auto_capture_config=AutoCaptureConfigInput(...)` parameter entirely from `EndpointCoreConfigInput(...)`. |
| `mlflow.<flavor>.log_model(..., registered_model_name=...)` with `mlflow.set_registry_uri("databricks-uc")` in scope (M1) | Blocker | Under UC, `registered_model_name=` triggers an internal `get_model_version_by_alias(..., 'Champion')` call that raises `RESOURCE_DOES_NOT_EXIST` for brand-new models. Drop the kwarg from `log_model`; after the run, call `mlflow.register_model(model_uri=f"runs:/{run.info.run_id}/model", name=<full_name>)` and `MlflowClient().set_registered_model_alias(...)`. See mlflow-uc-patterns. |
| `.latest_versions` access on UC-registered models (e.g., `client.get_registered_model(name).latest_versions`) (M2) | Blocker | `RegisteredModel.latest_versions` is always `None` on UC; `max(None, key=...)` raises `TypeError: 'NoneType' object is not iterable`. Use `client.search_model_versions(f"name='{name}'")` + sort+index (per A2 above). See mlflow-uc-patterns. |
| `mlflow.<flavor>.log_model(...)` without `signature=` kwarg, with `mlflow.set_registry_uri("databricks-uc")` in scope (M3) | Blocker | UC requires a model signature on every registered model. Without `signature=`, `log_model` raises `MlflowException: Model signature is required for registering a model to Unity Catalog`. Infer from a sample: `signature = infer_signature(X_sample, model.predict(X_sample))` then pass as `signature=signature` to `log_model`. See mlflow-uc-patterns. |
| Binary-classifier prediction column written as `float64` (`Double`) when downstream Delta table expects `Integer` (M4) | Blocker on first write | sklearn binary classifiers (e.g. the AutoML → sklearn rewrite from A3) emit `predict()` results as `float64`. Writing to a Delta table whose `prediction` column is `IntegerType` fails with `DELTA_FAILED_TO_MERGE_FIELDS: prediction (Double) vs prediction (Integer)`. Cast before writing: `df.withColumn("prediction", col("prediction").cast("integer"))`. See mlflow-uc-patterns. |

### Category B: Data Access

| Pattern | Severity | Fix |
|---------|----------|-----|
| `dbfs:/` or `/dbfs/` paths (persistent data) | Blocker | Replace with `/Volumes/<your_catalog>/schema/volume/path` |
| `dbfs:/tmp/`, `/dbfs/tmp/`, paths with `cache`/`scratch`/`temp` | Warning | Use `/tmp/` or `/local_disk0/tmp/` (local driver disk) — do not use Volumes for temp files due to performance |
| `file:///dbfs/` FUSE mount paths | Warning | Replace persistent paths with `/Volumes/...`; replace temp paths with `/local_disk0/tmp/` |
| `dbutils.fs.mount(...)` | Blocker | Create UC external location + external volume |
| `hive_metastore.db.table` | Warning | Migrate to UC or use HMS Federation: `CREATE FOREIGN CATALOG ... USING CONNECTION hms_connection` |
| `CREATE DATABASE`/`CREATE SCHEMA` without `USE CATALOG` or 3-level name | Blocker | Prepend `spark.sql("USE CATALOG <your_catalog>")` at notebook start before any CREATE statements. Detect target catalog from existing table references, or ask the user. |
| IAM instance profile references | Warning | Use UC external locations + storage credentials |
| Hive SerDe tables | Blocker | Migrate to Delta tables in UC |
| Bare `catalog = "<value>"` / `schema = "<value>"` assignment in `config.py`, `config/__init__.py`, `_config*.py`, or any Python file referenced via `%run` (B1) | Blocker | Catalog rewrite must scan **all** config files, not just notebook bodies that contain `spark.table(...)`. Replace literals like `"main"`, `"main__build"`, `"hive_metastore"` with the user's target catalog (typically `home_<user>`). Post-rewrite, grep the entire migrated tree for residual literal catalog refs. |
| `spark.sql("CREATE CATALOG IF NOT EXISTS ...")` (B2) | Blocker | Privilege check fires before `IF NOT EXISTS` short-circuits, so non-admin users hit `PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore` even when the catalog already exists. Guard with `SHOW CATALOGS LIKE '...'` probe first; only emit `CREATE CATALOG` if the probe returns empty. **Apply recursively across the entire migrated tree, including `_resources/00-global-setup-v2.py` and `config*` files.** Same pattern applies to `CREATE SCHEMA IF NOT EXISTS` and `CREATE VOLUME IF NOT EXISTS` in catalogs the user doesn't own. |

### Category C: Streaming

| Pattern | Severity | Fix |
|---------|----------|-----|
| `.trigger(processingTime=...)` | Blocker | `.trigger(availableNow=True)` + set `maxFilesPerTrigger` or `maxBytesPerTrigger` to prevent OOM |
| `.trigger(continuous=...)` | Blocker | Migrate to SDP continuous mode |
| No `.trigger()` call on writeStream | Blocker | **Must** add `.trigger(availableNow=True)` — Spark defaults to `ProcessingTime("0 seconds")` which is not supported |
| Kafka source | Info | Works with AvailableNow; use `maxOffsetsPerTrigger` to control batch size |
| Auto Loader | Info | Works; use `cloudFiles.maxFilesPerTrigger` (note the `cloudFiles.` prefix) |

### Category D: Configuration

| Pattern | Severity | Fix |
|---------|----------|-----|
| Unsupported `spark.conf.set(...)` | Warning | Remove — only 6 configs supported: `spark.sql.shuffle.partitions`, `spark.sql.session.timeZone`, `spark.sql.ansi.enabled`, `spark.sql.files.maxPartitionBytes`, `spark.sql.legacy.timeParserPolicy`, `spark.databricks.execution.timeout`. Serverless auto-tunes everything else. |
| Init scripts | Blocker | Use Environments: add dependencies via notebook Environment panel or `requirements.txt`. Pin specific versions. |
| Cluster policies | Info | Use budget policies for cost attribution |
| Docker containers | Blocker | Use Environments for library management. Keep on classic only if Docker is needed for OS-level customization. |
| `%run ./relative/path` or `%run ../path` | Warning | Relative `%run` paths may not resolve correctly in serverless job tasks. Fix: (1) Inline the referenced notebook's code if <500 lines (preferred), (2) Convert to `dbutils.notebook.run("<absolute_workspace_path>", timeout)` with absolute path. Found in ~19% of repos. |
| `os.environ["VAR"]` (system/custom env vars) | Warning | Use `os.environ.get()` with fallback, `spark.version` for Spark info, or `dbutils.widgets` for custom vars |
| `SET hivevar:` / `${hivevar:...}` (Hive variable substitution) | Blocker | Use SQL session variables: `DECLARE OR REPLACE VARIABLE name = value` (DBR 14.1+) |
| Environment variables (in init scripts) | Warning | Use `dbutils.widgets` or job parameters |
| Explicit executor count/memory configs | Info | Remove — serverless auto-scales and auto-tunes |
| Retired Foundation Model endpoint references, e.g., `databricks-meta-llama-3-1-405b-instruct` and similar (D1) | Blocker | Detect by **content scan across every migrated file** (not by filename pattern). Common refs in `ai_query(endpoint => '...')`, `ChatDatabricks(endpoint=...)`, model-serving config, and Genie/AI-Functions SQL. Replace with the current default `databricks-meta-llama-3-3-70b-instruct`. Verify the replacement endpoint exists in the target workspace before final deploy. |

### Category E: Libraries

| Pattern | Severity | Fix |
|---------|----------|-----|
| JAR libraries in notebooks | Blocker | Compile as JAR job task (Scala 2.13, JDK 17, env version 4+) |
| Compiled Scala JAR migration (version + dependency conflicts) | Blocker | Recompile against Scala 2.13.16; depend on `databricks-connect` % Provided; mark kernel-bundled deps % Provided. Full procedure + env-4 classpath in jar-migration |
| Maven coordinates | Blocker | Replace with PyPI packages in Environments |
| `%pip install` without version pins | Warning | Pin versions: `%pip install numpy==2.2.2 pandas==2.2.3` |
| Custom Spark data sources (v1/v2 JARs) | Blocker | Use Lakehouse Federation, Lakeflow Connect, or PySpark custom data sources |
| LZO format files | Blocker | Convert to Parquet or Delta |
| AutoML-trained model loaded via `mlflow.pyfunc.spark_udf(..., env_manager='local')` inside an SDP `.py` library file (E1) | Blocker | The SDP serverless image does not ship `databricks-automl-runtime`; cloudpickle.load raises `ModuleNotFoundError: No module named 'databricks.automl_runtime'`. Auto-emit `%pip install -q databricks-automl-runtime` as the first non-comment line of the SDP `.py` library file. `%pip install` is supported in SDP `.py` library files and runs once per update before SQL flows are planned. Same fix works for non-SDP notebooks loading AutoML-trained models. |
| AutoML → sklearn rewrite (A3) with pre-existing model-serving endpoint (E2) | Blocker on first redeploy | The rewrite changes model signature (e.g., drops `id` from inputs). A pre-existing endpoint pinned to the old AutoML signature fails create/update with HTTP 400 `Failed to enforce schema of data ... Model is missing inputs ['id']`. In the downstream serving notebook for the **migrated test endpoint** (not a live production endpoint serving real traffic), flip `force_update = False` → `force_update = True` so the endpoint re-binds to the current `prod` (or `Champion`) alias. Before flipping, confirm the endpoint name matches the migrated copy. |

### Category F: Networking

| Pattern | Severity | Fix |
|---------|----------|-----|
| VPC peering configuration | Blocker | Create NCCs, get stable IPs, allowlist on resource firewalls. S3 same-region access works without changes. |
| Direct S3/ADLS access without UC | Warning | Use UC external locations |

### Category G: Sizing & Debugging

| Pattern | Severity | Fix |
|---------|----------|-----|
| Large driver memory configs | Info | Serverless REPL default is 8GB (high-memory option for 16GB+ via Environments) |
| Spark UI references | Info | Use Query Profile instead: click "See performance" under cell output |

### Category H: Job-level config (dbt_task, SDP, multi-source, deploy preconditions)

These checks operate on the job/pipeline spec JSON and on deploy preconditions, not on notebook bodies. Apply them alongside the per-notebook checks in Categories A–G.

| Pattern | Severity | Fix |
|---------|----------|-----|
| `dbt_task` block in job spec (H1) | Blocker for dbt workloads | Three sub-checks: (1) **`warehouse_id`**: swap known-busy or non-serverless warehouses to a Stable/dedicated DBSQL serverless warehouse. (2) **`project_directory`**: rewrite to the migrated workspace location (e.g., `/Workspace/Users/<me>/<demo>-skill-migrated/...`). (3) **`libraries[]`**: replace classic-only Python wheels with pinned serverless-compatible versions; flag `dbt-databricks` < 1.7.x. |
| SDP pipeline spec deployed alongside the original demo with the same `schema` (H2) | Blocker | UC rejects parallel deploy with `Table is already managed by pipeline <orig-id>`. When the target path includes a migration suffix (e.g., `-skill-migrated/`), automatically suffix the pipeline's target `schema` (e.g., `dbdemos_retail_c360` → `dbdemos_retail_c360_skill_migrated`). Apply the same rewrite to any `LIVE` / `STREAMING TABLE` references in transformation files that hard-code the schema. Lint the pipeline spec before deploy: if any target table already exists and belongs to another pipeline, fail with a clear message. |
| Workspace `import` 10 MB cap (H3) | Advisory (foreseeable) | Pre-deploy precondition: walk the migrated tree before `databricks workspace import` and flag any file > 10 MB. Reroute large files (sample CSVs, `dbt seed` data, sample datasets, etc.) to UC Volumes (`databricks fs cp`) instead of workspace import. Emit a UC Volumes upload command alongside the workspace import command, with a manifest of what went where. Not blocking in most workloads but blocks any demo using `dbt seed` or large sample CSVs. |
| Multi-source workloads with `bundle_config.py` declaring upstream git URLs (H4) | Diagnostic | Without this, the skill mis-enumerates user notebooks. Parse `bundle_config.py` and follow any upstream-source declarations (git URLs, S3 paths). Clone or fetch the referenced repos before per-notebook enumeration. List "external sources" as a first-class artifact category in the migration plan. See multi-source-enumeration. Concrete example: `dbt-on-databricks`'s `bundle_config.py` references the upstream `dbt-databricks-c360` repo; the real task notebooks live there, not in the local `dbdemos-notebooks/` tree. |
