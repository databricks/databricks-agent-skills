---
name: databricks-serverless-migration
description: "Migrate Databricks workloads from classic compute to serverless compute. Use when migrating notebooks, jobs, pipelines, or Scala JARs (`spark_jar_task`) from classic clusters to serverless, checking if existing code is serverless-compatible, or writing new serverless-compatible code. Provides concrete fixes for the serverless Spark Connect architecture and guides the full migration. Not for classic DBR version upgrades or cluster configuration changes within classic compute."
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Serverless Compute Migration

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Analyze existing Databricks code for serverless compute compatibility and guide migration from classic clusters. The skill follows a 4-step migration lifecycle: **Ingest** the workload → **Analyze** for compatibility → **Test** via A/B comparison → **Validate** and iterate.

## When to Use This Skill

- Migrating notebooks, jobs, or pipelines from classic compute to serverless
- Checking if existing code is serverless-compatible
- Writing new code that targets serverless compute
- Troubleshooting serverless-specific errors after migration
- Choosing between Performance-Optimized and Standard mode

## Where to Run This Skill

This skill is published as an Agent Skill (agentskills.io) and runs in any compatible client:

- **Claude Code, Cursor, or any agentskills.io client on your laptop** — the default. Install via `databricks aitools install` or follow the per-client docs.
- **Inside a Databricks workspace via Genie Code Agent mode** — drop the skill into `/Workspace/Users/<you>/.assistant/skills/databricks-serverless-migration/` (per-user) or `/Workspace/.assistant/skills/databricks-serverless-migration/` (workspace-wide, admin only). See [Install in Databricks Genie Code](references/install-in-databricks-genie-code.md) for the three install methods and the **important serverless-compute caveat** (the Databricks CLI isn't pre-installed on serverless, so some deploy steps need adjustment).

If you finish a migration analysis for a user who's currently running you from a laptop client, mention the Genie Code option once at the end — many users prefer iterating on migrations inside the workspace where the workload lives.

## Input to get from the user
Ask the user for explicit input parameters for the following items, providing reasonable defaults:
- Which workspace contains the source workloads?
- Which workspace will contain the migrated workloads?
- What is the catalog and schema where output from the test migrated jobs should go?
- How should the test jobs be prefixed or tagged?
- Where in the workspace should the converted code go?
- What compute should be used for reading output produced by classic jobs for comparison (if serverless is not available)?

Prior to presenting these questions, make sure there are 6 questions (so you don't miss any of the above).

## Understanding Migration Blockers

Migration blockers fall into three categories. Focus your effort on category 2 — that's where this skill helps most.

| Category | Description | Action |
|----------|-------------|--------|
| **1. Feature expanding** | Databricks is actively expanding support (e.g., SparkML, custom JDBC) | Use the workaround now and revisit later |
| **2. Code/config change needed** | Your code uses patterns that need updating for serverless (e.g., RDDs, DBFS, streaming triggers) | **This skill helps here** — it detects these patterns and provides fixes |
| **3. Classic-only** | Workload requires capabilities not available on serverless (e.g., root OS access, R language) | Keep on classic compute |

## Decision Tree: Is My Workload Ready?

```
Workload → Check language
├── R code → Category 3: keep on classic
├── Scala notebook cells → Category 2: port to PySpark/SQL, or compile as a JAR job task
├── Compiled Scala JAR (spark_jar_task, build.sbt/pom.xml/build.gradle) → see references/jar-migration.md
│     ├── Scala 2.12 build?             → recompile against 2.13.16
│     ├── Bundles spark-core/spark-sql? → use databricks-connect % Provided
│     └── Bundles libs on the kernel classpath? → mark % Provided (see the classpath table in references/jar-migration.md)
├── Python / SQL → Continue
    ├── Uses RDD APIs? → Category 2: rewrite to DataFrame API (see fixes below)
    ├── Uses DBFS paths? → Category 2: migrate to UC Volumes
    ├── Uses Hive Metastore? → Category 2: migrate to Unity Catalog (or use HMS Federation)
    ├── Uses df.cache/persist? → Category 1: remove and materialize to Delta (native support coming soon)
    ├── Uses streaming?
    │   ├── ProcessingTime trigger → Category 2: use AvailableNow or migrate to SDP
    │   ├── Continuous trigger → Category 2: use SDP continuous mode
    │   ├── No trigger specified → Category 2: add explicit .trigger(availableNow=True)
    │   └── AvailableNow / Once → Ready ✓
    ├── Uses init scripts? → Category 2: use Environments
    ├── Uses VPC peering? → Category 2: use NCCs / Private Link
    ├── Uses unsupported Spark configs? → Category 2: remove (serverless auto-tunes)
    ├── Uses custom JDBC drivers? → Category 2: use Lakehouse Federation or built-in JDBC
    ├── Uses Docker containers? → Category 3: use Environments for libs, or keep on classic
    └── All clear → Ready for serverless ✓
```

## Migration Workflow

### Step 1: Ingest — Gather Workload Context

**Confirm the migration target is serverless compute.** This skill is purpose-built for classic → serverless migrations. The checks, fixes, and workflow all target the serverless compute architecture (Spark Connect, Environments, NCCs). If the user wants to upgrade between classic DBR versions instead, this skill does not apply — classic DBR upgrades have a different compatibility surface and should follow the standard DBR upgrade guide.

Collect the full picture of what needs to migrate to serverless:
- Read the user's notebook/script files
- Identify the classic cluster configuration (instance type, DBR version, Spark configs, init scripts, libraries)
- Note the networking setup (VPC peering, instance profiles, mounts)
- Understand the workload type: batch job, streaming, interactive notebook, pipeline
- Determine the target: the output is always a **serverless compute** configuration, not a classic cluster with a newer DBR

### Step 1.5: Handle Multi-Notebook Workloads

If the workload spans more than one user notebook (exclude `_resources/` setup notebooks from the count), process them **one at a time** rather than all at once. The agent's context window is finite, and trying to hold the full source of an 8-notebook job in active context while doing analysis, fixes, and migration triggers autocompact thrashing (Claude Code) or equivalent context-overflow failures in other clients.

**Procedure**:

1. **Enumerate first.** List every user notebook with its path. Do not read the bodies in full yet beyond a few lines for orientation.
   - **Check for `bundle_config.py` (H4).** If the source tree contains a `bundle_config.py`, parse it and follow any upstream-source declarations (git URLs, S3 paths, `init_scripts`, `git_source`, or custom upstream-repo declarations). Clone or fetch each referenced repo into a sibling location and include its notebooks in the enumeration. List "external sources" as a first-class artifact category in the migration plan. Without this step, multi-source demos (e.g., `dbt-on-databricks` references the upstream `dbt-databricks-c360` repo) get mis-enumerated and the real task notebooks are missed.
2. **For each notebook, in order**:
   a. Read its full source.
   b. Run the Step 2 Analyze checklist scoped to this notebook only.
   c. Record a structured summary in your response or to a scratch file, then drop the raw source from active working memory. The summary must include:
      - `notebook_path` (relative)
      - `detected_patterns[]` (pattern IDs from this skill's catalog)
      - `blockers[]` (Category-3 patterns this notebook hits, if any)
      - `migration_steps[]` (concrete fixes ordered)
      - `unmigratable` (bool — true if any blocker has no workaround)
   d. If you have a writable scratch directory (`~/.databricks-migration-skill/scratch/<run-id>/findings/`), persist the summary as `<notebook-basename>.json`. This frees the source from context safely. If not, keep the summary compact in conversation history.
3. **Synthesize.** After all notebooks have a summary, produce the unified migration plan from the summaries alone. Apply fixes notebook-by-notebook, never re-reading the original source unless required to resolve an ambiguity in a summary.
4. **Failure Reporting.** Trigger the Failure Reporting Protocol exactly once per workload, not once per notebook. The `detected_patterns` array in the report aggregates across all notebooks; `notebook_characteristics` uses summed line counts and the union of language/streaming/ML flags.

**Threshold guidance**: apply this procedure when the user notebook count is ≥ 3, or when individual notebooks exceed ~5KB of source. For 1–2 small notebooks the single-pass workflow in Steps 2–4 is fine.

**Anti-pattern**: do NOT attempt a "merge all notebooks into one big file" or "read all notebooks, then act in one mega-turn" strategy. Both defeat the purpose by reintroducing the original context-pressure problem.

### Step 2: Analyze — Scan for Serverless Readiness

**Read notebooks before running them — do not rely on failed job runs to discover issues.** A pre-run scan surfaces incompatibilities faster than iterating on error traces, and many serverless failures (hardcoded catalog references, init scripts, missing dependencies) are easy to spot statically but expensive to debug after a failed run.

Before creating or running any test job:
1. Read every notebook and source file referenced by the job
2. Scan for all hardcoded catalog/schema references (e.g., `spark.table("main.schema.table")`, `spark.sql("... FROM main...")`, `catalog = "main"`)
3. Check for dependency patterns: init scripts, local wheel files, custom install functions, `%pip install` lines
4. Locate any `requirements.txt` or equivalent and resolve the full dependency set
5. Flag OS-level installs (`apt install`, `yum install`) for conversion or escalation

Scan the code for patterns that are incompatible with the serverless compute architecture. These checks are serverless-specific — most of these patterns work fine on classic compute regardless of DBR version. For each issue found, report:
- **Category**: Which of the 3 blocker categories it falls into
- **Severity**: Blocker (must fix for serverless) / Warning (should fix) / Info (awareness)
- **Pattern**: What was detected and where
- **Fix**: Specific remediation targeting serverless compute

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

**Category A: Unsupported APIs**

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
| Builtin `max(..., key=)` / `min(..., key=)` / `sorted(..., key=)` with `from pyspark.sql.functions import *` (A2) | Blocker | `pyspark.sql.functions.max` shadows the builtin and rejects `key=` (raises `TypeError: max() got an unexpected keyword argument 'key'`). Use sort+index: `xs.sort(key=...); top = xs[0]`. See [MLflow on UC](references/mlflow-uc-patterns.md). |
| `from databricks import automl` / `automl.classify()` / `automl.regress()` / `automl.forecast()` (A3) | Blocker | AutoML not available on serverless and the `DBDemos.create_mockup_automl_run` fallback hits `PlanMetrics not JSON serializable` on Spark Connect. Rewrite as inline scikit-learn `Pipeline` with `mlflow.sklearn.log_model` + `mlflow.register_model` + UC alias. See [MLflow on UC](references/mlflow-uc-patterns.md). |
| `mlflow.pyfunc.spark_udf(...)` followed by `df.withColumn("prediction", loaded_model(struct(*features)))` (A4) | Blocker on mlflow 2.19.0 | Closure bug on Spark Connect: `batch_predict_fn` captures `loaded_model` as a free variable; workers fail with `NameError: cannot access free variable 'loaded_model'`. **Root cause is Spark Connect serialization.** Preferred fix (portable, any mlflow), driver-side pandas inference: `mlflow.pyfunc.load_model(uri).predict(df.toPandas())` then `spark.createDataFrame(...)`. Fallback fix: pin `mlflow>=2.20.0` in the environment spec. |
| `AutoCaptureConfigInput(enabled=...)` in model-serving endpoint creation (A5) | Warning | Deprecated arg, breaks first-time endpoint deploy. Remove the `auto_capture_config=AutoCaptureConfigInput(...)` parameter entirely from `EndpointCoreConfigInput(...)`. |
| `mlflow.<flavor>.log_model(..., registered_model_name=...)` with `mlflow.set_registry_uri("databricks-uc")` in scope (M1) | Blocker | Under UC, `registered_model_name=` triggers an internal `get_model_version_by_alias(..., 'Champion')` call that raises `RESOURCE_DOES_NOT_EXIST` for brand-new models. Drop the kwarg from `log_model`; after the run, call `mlflow.register_model(model_uri=f"runs:/{run.info.run_id}/model", name=<full_name>)` and `MlflowClient().set_registered_model_alias(...)`. See [MLflow on UC](references/mlflow-uc-patterns.md). |
| `.latest_versions` access on UC-registered models (e.g., `client.get_registered_model(name).latest_versions`) (M2) | Blocker | `RegisteredModel.latest_versions` is always `None` on UC; `max(None, key=...)` raises `TypeError: 'NoneType' object is not iterable`. Use `client.search_model_versions(f"name='{name}'")` + sort+index (per A2 above). See [MLflow on UC](references/mlflow-uc-patterns.md). |
| `mlflow.<flavor>.log_model(...)` without `signature=` kwarg, with `mlflow.set_registry_uri("databricks-uc")` in scope (M3) | Blocker | UC requires a model signature on every registered model. Without `signature=`, `log_model` raises `MlflowException: Model signature is required for registering a model to Unity Catalog`. Infer from a sample: `signature = infer_signature(X_sample, model.predict(X_sample))` then pass as `signature=signature` to `log_model`. See [MLflow on UC](references/mlflow-uc-patterns.md). |
| Binary-classifier prediction column written as `float64` (`Double`) when downstream Delta table expects `Integer` (M4) | Blocker on first write | sklearn binary classifiers (e.g. the AutoML → sklearn rewrite from A3) emit `predict()` results as `float64`. Writing to a Delta table whose `prediction` column is `IntegerType` fails with `DELTA_FAILED_TO_MERGE_FIELDS: prediction (Double) vs prediction (Integer)`. Cast before writing: `df.withColumn("prediction", col("prediction").cast("integer"))`. See [MLflow on UC](references/mlflow-uc-patterns.md). |

**Category B: Data Access**

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

**Category C: Streaming**

| Pattern | Severity | Fix |
|---------|----------|-----|
| `.trigger(processingTime=...)` | Blocker | `.trigger(availableNow=True)` + set `maxFilesPerTrigger` or `maxBytesPerTrigger` to prevent OOM |
| `.trigger(continuous=...)` | Blocker | Migrate to SDP continuous mode |
| No `.trigger()` call on writeStream | Blocker | **Must** add `.trigger(availableNow=True)` — Spark defaults to `ProcessingTime("0 seconds")` which is not supported |
| Kafka source | Info | Works with AvailableNow; use `maxOffsetsPerTrigger` to control batch size |
| Auto Loader | Info | Works; use `cloudFiles.maxFilesPerTrigger` (note the `cloudFiles.` prefix) |

**Category D: Configuration**

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

**Category E: Libraries**

| Pattern | Severity | Fix |
|---------|----------|-----|
| JAR libraries in notebooks | Blocker | Compile as JAR job task (Scala 2.13, JDK 17, env version 4+) |
| Compiled Scala JAR migration (version + dependency conflicts) | Blocker | Recompile against Scala 2.13.16; depend on `databricks-connect` % Provided; mark kernel-bundled deps % Provided. Full procedure + env-4 classpath in [JAR Migration](references/jar-migration.md) |
| Maven coordinates | Blocker | Replace with PyPI packages in Environments |
| `%pip install` without version pins | Warning | Pin versions: `%pip install numpy==2.2.2 pandas==2.2.3` |
| Custom Spark data sources (v1/v2 JARs) | Blocker | Use Lakehouse Federation, Lakeflow Connect, or PySpark custom data sources |
| LZO format files | Blocker | Convert to Parquet or Delta |
| AutoML-trained model loaded via `mlflow.pyfunc.spark_udf(..., env_manager='local')` inside an SDP `.py` library file (E1) | Blocker | The SDP serverless image does not ship `databricks-automl-runtime`; cloudpickle.load raises `ModuleNotFoundError: No module named 'databricks.automl_runtime'`. Auto-emit `%pip install -q databricks-automl-runtime` as the first non-comment line of the SDP `.py` library file. `%pip install` is supported in SDP `.py` library files and runs once per update before SQL flows are planned. Same fix works for non-SDP notebooks loading AutoML-trained models. |
| AutoML → sklearn rewrite (A3) with pre-existing model-serving endpoint (E2) | Blocker on first redeploy | The rewrite changes model signature (e.g., drops `id` from inputs). A pre-existing endpoint pinned to the old AutoML signature fails create/update with HTTP 400 `Failed to enforce schema of data ... Model is missing inputs ['id']`. In the downstream serving notebook for the **migrated test endpoint** (not a live production endpoint serving real traffic), flip `force_update = False` → `force_update = True` so the endpoint re-binds to the current `prod` (or `Champion`) alias. Before flipping, confirm the endpoint name matches the migrated copy. |

**Category F: Networking**

| Pattern | Severity | Fix |
|---------|----------|-----|
| VPC peering configuration | Blocker | Create NCCs, get stable IPs, allowlist on resource firewalls. S3 same-region access works without changes. |
| Direct S3/ADLS access without UC | Warning | Use UC external locations |

**Category G: Sizing & Debugging**

| Pattern | Severity | Fix |
|---------|----------|-----|
| Large driver memory configs | Info | Serverless REPL default is 8GB (high-memory option for 16GB+ via Environments) |
| Spark UI references | Info | Use Query Profile instead: click "See performance" under cell output |

**Category H: Job-level config (dbt_task, SDP, multi-source, deploy preconditions)**

These checks operate on the job/pipeline spec JSON and on deploy preconditions, not on notebook bodies. Apply them alongside the per-notebook checks in Categories A–G.

| Pattern | Severity | Fix |
|---------|----------|-----|
| `dbt_task` block in job spec (H1) | Blocker for dbt workloads | Three sub-checks: (1) **`warehouse_id`**: swap known-busy or non-serverless warehouses to a Stable/dedicated DBSQL serverless warehouse. (2) **`project_directory`**: rewrite to the migrated workspace location (e.g., `/Workspace/Users/<me>/<demo>-skill-migrated/...`). (3) **`libraries[]`**: replace classic-only Python wheels with pinned serverless-compatible versions; flag `dbt-databricks` < 1.7.x. |
| SDP pipeline spec deployed alongside the original demo with the same `schema` (H2) | Blocker | UC rejects parallel deploy with `Table is already managed by pipeline <orig-id>`. When the target path includes a migration suffix (e.g., `-skill-migrated/`), automatically suffix the pipeline's target `schema` (e.g., `dbdemos_retail_c360` → `dbdemos_retail_c360_skill_migrated`). Apply the same rewrite to any `LIVE` / `STREAMING TABLE` references in transformation files that hard-code the schema. Lint the pipeline spec before deploy: if any target table already exists and belongs to another pipeline, fail with a clear message. |
| Workspace `import` 10 MB cap (H3) | Advisory (foreseeable) | Pre-deploy precondition: walk the migrated tree before `databricks workspace import` and flag any file > 10 MB. Reroute large files (sample CSVs, `dbt seed` data, sample datasets, etc.) to UC Volumes (`databricks fs cp`) instead of workspace import. Emit a UC Volumes upload command alongside the workspace import command, with a manifest of what went where. Not blocking in most workloads but blocks any demo using `dbt seed` or large sample CSVs. |
| Multi-source workloads with `bundle_config.py` declaring upstream git URLs (H4) | Diagnostic | Without this, the skill mis-enumerates user notebooks. Parse `bundle_config.py` and follow any upstream-source declarations (git URLs, S3 paths). Clone or fetch the referenced repos before per-notebook enumeration. List "external sources" as a first-class artifact category in the migration plan. See [Multi-source enumeration](references/multi-source-enumeration.md). Concrete example: `dbt-on-databricks`'s `bundle_config.py` references the upstream `dbt-databricks-c360` repo; the real task notebooks live there, not in the local `dbdemos-notebooks/` tree. |

### Required Output: Serverless Environment Specification

The migration output MUST include a Serverless Environment specification alongside migrated code. Generate this by:

1. Scanning all `import` statements and `%pip install` lines to detect required packages
2. Extracting init script `pip install` commands from the job configuration
3. Producing a JSON block suitable for the Jobs API `environments` field:

```json
{
  "environment_key": "Default",
  "spec": {
    "client": "2",
    "dependencies": ["mlflow==2.12.1", "scikit-learn==1.3.0", "xgboost==2.0.3"]
  }
}
```

**Important**: ML runtime libraries (mlflow, scikit-learn, hyperopt, xgboost, tensorflow, torch, etc.) are NOT pre-installed on serverless compute. They MUST be listed explicitly in the environment spec `dependencies`. ML runtime is NOT available on serverless — always use Serverless Environments with explicit package dependencies instead.

### Step 3: Test — Two-Branch Strategy

Use separate branches for testing and production to keep test-only workarounds out of the code that ships. The test branch is a safe sandbox for experimentation; the production branch contains only changes that production actually needs.

| Aspect               | Test branch                                    | Production branch                  |
|----------------------|------------------------------------------------|------------------------------------|
| Name pattern         | `serverless-test-{job_name}-{timestamp}`        | `serverless-prod-{job_name}`       |
| Base branch          | Any working branch                              | Must be master                     |
| Purpose              | Verify serverless compatibility                 | Deploy to production               |
| Test-only workarounds | Yes (catalog overrides, sampled data, date limits) | **No**                         |
| Compatibility fixes  | Yes (discover them here)                        | Yes (apply the validated ones)     |
| Job config changes   | Yes (for the test job)                          | Yes (for the prod job)             |
| Catalog              | Test catalog                                    | Production catalog                 |
| PR required          | No                                              | Yes                                |
| Merged to master     | No                                              | Yes                                |

**Test branch** (`serverless-test-{job_name}-{timestamp}`): Temporary, no PR needed.
1. Create a branch from your current working branch
2. Set up test data: create sampled copies of upstream tables in a test catalog using job lineage (see test data setup below)
3. Parameterize the catalog so the notebook works with both test and production data (see catalog parameterization pattern below)
4. Apply all compatibility fixes discovered in Step 2
5. Create a serverless test job and run it
6. If it fails, get the error output, debug, fix, and retry
7. Document which changes are **test workarounds** vs. **real compatibility fixes**

**Production branch** (`serverless-prod-{job_name}`): PR required, created from master.
1. Create a new branch from master (NOT from the test branch)
2. Apply ONLY the real compatibility fixes — no test workarounds
3. Apply job config changes (see job config transformation below)
4. Commit and create a PR

### Test Data Setup

When the job reads from production tables, do not point the test job at production data. Instead, create sampled copies of upstream tables in a dedicated test catalog and run the test job against those.

The recommended pattern:
1. Resolve the job's upstream tables from its lineage (or from a static scan of the notebook)
2. For each upstream table, run `CREATE TABLE IF NOT EXISTS <test_catalog>.<schema>.<table> AS SELECT * FROM <prod_catalog>.<schema>.<table> LIMIT N` (typical N: 10–1000 rows)
3. Keep the schema names identical to production — only the catalog changes
4. Make the operation idempotent: skip tables that already exist, so the setup step is safe to re-run
5. Require a running SQL warehouse and `CREATE TABLE` permission on the test catalog

With schema names preserved, the same notebook code runs in both environments — only the `catalog` widget value changes.

### Decision Tree: Should This Change Go to Production?

| Change type | Production? | Reason |
|-------------|-------------|--------|
| Remove incompatible Spark configs | **Yes** | Serverless compatibility fix |
| Update library versions | **Yes** | Serverless compatibility fix |
| Replace DBFS paths with UC Volumes | **Yes** | Serverless compatibility fix |
| Remove init scripts, add Environments | **Yes** | Serverless compatibility fix |
| Fix hardcoded cluster settings | **Yes** | Serverless compatibility fix |
| Catalog override to test catalog | **No** | Test workaround only |
| Empty DataFrame handling for missing test data | **No** | Test workaround only |
| Date range limiting for faster tests | **No** | Test workaround only |

**Simple test**: Would production fail without this change on serverless? If yes → include. If no → test branch only.

### A/B Comparison

After both branches are ready, compare outputs:

```python
# Compare outputs between classic and serverless runs
classic_df = spark.read.table("main.output.classic_results")
serverless_df = spark.read.table("main.output.serverless_results")

assert classic_df.count() == serverless_df.count(), "Row count mismatch"
assert classic_df.schema == serverless_df.schema, "Schema mismatch"
diff = classic_df.exceptAll(serverless_df)
assert diff.count() == 0, f"Found {diff.count()} differing rows"
```

**Temporary bridge configs**: If the serverless run fails, you may temporarily set supported Spark configs (like `spark.sql.shuffle.partitions`) to bridge gaps. Mark these as temporary — remove once the workload stabilizes.

### Step 4: Validate — Confirm and Monitor

Once the A/B comparison passes:
1. Merge the production branch PR
2. Switch the production job to serverless compute
3. Monitor cost via system tables (`system.billing.usage`) and budget policies
4. Remove any temporary bridge configurations
5. Set up budget alerts for cost visibility

### Migration Deliverables

At the end of a successful migration run, surface these artifacts so the user can verify the work and inspect the results:

| Deliverable | What it is | Why it matters |
|-------------|------------|----------------|
| Test branch name/URL | The `serverless-test-{job_name}-{timestamp}` branch with all compatibility fixes and test workarounds | Lets the user see what changed during experimentation, including test-only adjustments |
| Production branch name/URL | The `serverless-prod-{job_name}` branch containing only the validated compatibility fixes | This is what ships — the user reviews and merges the PR from here |
| Test job ID and run URL | The serverless test job that validated the migration | Proves the notebook runs successfully on serverless against sampled data |
| Classic vs serverless comparison | A/B result summary (row counts, schema check, row-level diff) | Confidence that serverless output matches classic output |
| Serverless environment spec | The `environments` JSON block (client version + pinned dependencies) | Ready to paste into the production job config |
| Change summary | List of what went to production vs test-only (with reasons) | Audit trail for the PR reviewer |

If any deliverable is missing, the migration is incomplete — do not mark it as done.

### Stopping Conditions

Do not attempt workarounds for these — surface them to the user and stop:
- Permission failures on source tables, the test catalog, or the workspace
- Category 3 blockers (R code, custom Spark data source JARs, features that require classic compute)
- SQL warehouse or test catalog not available
- Repeated failures (typically 5+) with no new information in the error trace — generate a failure report instead (see Failure Reporting Protocol)

## Quick Fixes Reference

### Replace DBFS paths with UC Volumes

```python
# BEFORE (classic)
df = spark.read.csv("dbfs:/mnt/datalake/sales/data.csv", header=True)
df.write.parquet("dbfs:/mnt/output/results")

# AFTER (serverless)
df = spark.read.csv("/Volumes/main/sales/raw_data/data.csv", header=True)
df.write.parquet("/Volumes/main/analytics/output/results")

# Replace mounts with external volumes (SQL):
# CREATE EXTERNAL VOLUME main.data.raw_files LOCATION 's3://my-bucket/data/';
# Then use: /Volumes/main/data/raw_files/

# Pandas paths too:
# BEFORE: pd.read_csv("/dbfs/mnt/data/file.csv")
# AFTER:  pd.read_csv("/Volumes/main/data/volume/file.csv")
```

### Replace RDD operations with DataFrames

```python
from pyspark.sql import functions as F

# parallelize + map
# BEFORE:
rdd = sc.parallelize([1, 2, 3])
result = rdd.map(lambda x: x * 2).collect()
# AFTER:
df = spark.createDataFrame([(1,), (2,), (3,)], ["value"])
result = df.select((F.col("value") * 2).alias("value")).collect()

# flatMap (word splitting)
# BEFORE:
words = sc.parallelize(["hello world"]).flatMap(lambda l: l.split(" ")).collect()
# AFTER:
df = spark.createDataFrame([("hello world",)], ["line"])
words = df.select(F.explode(F.split("line", " ")).alias("word")).collect()

# groupByKey
# BEFORE:
rdd = sc.parallelize([("a", 1), ("b", 2), ("a", 3)])
grouped = rdd.groupByKey().mapValues(list).collect()
# AFTER:
df = spark.createDataFrame([("a", 1), ("b", 2), ("a", 3)], ["key", "value"])
grouped = df.groupBy("key").agg(F.collect_list("value").alias("values")).collect()

# mapPartitions → applyInPandas
# BEFORE:
def process_partition(iterator):
    yield sum(iterator)
result = sc.parallelize(range(100), 4).mapPartitions(process_partition).collect()
# AFTER:
import pandas as pd
def process_group(pdf: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"total": [pdf["id"].sum()]})
result = (spark.range(100).repartition(4)
    .groupBy(F.spark_partition_id())
    .applyInPandas(process_group, schema="total long")
    .collect())

# textFile
# BEFORE: rdd = sc.textFile("/mnt/data/file.txt")
# AFTER:  df = spark.read.text("/Volumes/catalog/schema/volume/file.txt")

# wholeTextFiles
# BEFORE: rdd = sc.wholeTextFiles("/mnt/data/dir/")
# AFTER:  df = spark.read.format("binaryFile").load("/Volumes/catalog/schema/volume/dir/")
```

### Fix streaming triggers

```python
# CRITICAL: Omitting .trigger() defaults to ProcessingTime(0) — not supported on serverless

# BEFORE (fails on serverless — no trigger = ProcessingTime default):
query = df.writeStream.format("delta").outputMode("append").start(path)

# BEFORE (fails — explicit ProcessingTime):
query = df.writeStream.trigger(processingTime="10 seconds").start(path)

# AFTER (serverless compatible):
query = (df.writeStream
    .format("delta")
    .outputMode("append")
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/stream1")
    .start("/Volumes/main/data/output/stream1"))
query.awaitTermination()

# With OOM prevention (recommended for large sources):
query = (spark.readStream.format("delta")
    .option("maxFilesPerTrigger", 100)          # Delta/Parquet sources
    .option("maxBytesPerTrigger", "10g")         # Limit data per micro-batch
    .load(input_path)
    .writeStream
    .trigger(availableNow=True)
    .option("checkpointLocation", checkpoint_path)
    .start(output_path))

# Kafka: use maxOffsetsPerTrigger
query = (spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "topic1")
    .option("maxOffsetsPerTrigger", 100000)      # Kafka-specific
    .load()
    .writeStream.trigger(availableNow=True).start(output_path))

# Auto Loader: use cloudFiles.maxFilesPerTrigger (note the prefix)
query = (spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.maxFilesPerTrigger", 1000)  # cloudFiles. prefix
    .load(landing_path)
    .writeStream.trigger(availableNow=True).start(output_path))
```

### Remove caching

```python
# BEFORE (classic):
df = spark.read.parquet(path)
df.cache()
df.count()  # materialize cache
result1 = df.filter("status = 'active'")
result2 = df.groupBy("region").agg(F.sum("revenue"))

# AFTER (serverless — remove .cache(); native support coming soon):
df = spark.read.parquet(path)
result1 = df.filter("status = 'active'")
result2 = df.groupBy("region").agg(F.sum("revenue"))

# For truly expensive intermediate results, materialize to Delta:
expensive_df.write.format("delta").mode("overwrite").saveAsTable("main.scratch.intermediate")
result = spark.table("main.scratch.intermediate")

# SQL equivalent:
# BEFORE: CACHE TABLE my_table
# AFTER:  (just remove the CACHE TABLE statement)
```

### Other quick fixes

| Pattern | Fix | Full example |
|---------|-----|-------------|
| `sc.broadcast` / `sc.accumulator` / `sqlContext.sql` | Use SparkSession equivalents: `broadcast()` join, `df.agg()`, `spark.sql()` | [Code Patterns](references/code-patterns.md) |
| Init scripts | Move to Environment panel or `requirements.txt`. Do NOT install PySpark. Pin versions. | [Code Patterns](references/code-patterns.md) |
| Hive Metastore tables | Use HMS Federation as bridge (`CREATE FOREIGN CATALOG`) or migrate directly (`CREATE TABLE ... AS SELECT`) | [Code Patterns](references/code-patterns.md) |
| Custom JDBC JARs | Use Lakehouse Federation (`CREATE CONNECTION ... TYPE POSTGRESQL`) or built-in JDBC (works on serverless) | [Code Patterns](references/code-patterns.md) |
| Spark UI debugging | Use Query Profile: click "See performance" under cell output, or `df.explain(True)` | [Code Patterns](references/code-patterns.md) |

### Detect serverless at runtime

```python
import os
is_serverless = os.getenv("IS_SERVERLESS", "").lower() == "true"
```

### Transform job config from classic to serverless

Remove `job_clusters`/`new_cluster`, add `environments` with serverless spec, replace `job_cluster_key` with `environment_key`, remove `init_scripts`. See [Configuration Guide](references/configuration-guide.md) for full before/after JSON and environment version mapping.

**Environment version mapping** (match to the DBR version the workload was on):

| Classic DBR | Serverless `spec.client` | Python |
|-------------|--------------------------|--------|
| 13.x, 14.x | `"1"` | 3.10 |
| 15.x | `"2"` | 3.11 |
| 16.x+ | `"3"` | 3.12 |

### Job Definition Migration

When migrating a job, the **job configuration JSON** must be transformed alongside notebook code. The agent should perform all of the following:

**Init scripts to Serverless Environments**: Detect `init_scripts` in the job JSON. Extract all `pip install` commands and convert them to Environment `dependencies`. For OS-level packages (`apt install`/`yum install`) that have pip equivalents (e.g., `apt install python3-opencv` becomes `opencv-python`), convert them. Flag OS-level packages without pip equivalents as serverless-incompatible (Category 3).

**Cluster libraries (Maven/JAR) to Environment or Volumes**: Maven coordinates for Python-wrapping JARs should be replaced with their PyPI equivalent in the Environment spec. Custom JARs on DBFS need to be moved to `/Volumes/<your_catalog>/schema/volume/` and referenced there. Custom Spark data source JARs (v1/v2) are a Category 3 blocker — flag them for classic retention.

**job_clusters to serverless compute**: Remove `job_clusters` / `new_cluster` blocks entirely. Add an `environments` array with the serverless spec. Replace `job_cluster_key` in each task with `environment_key`. Remove `init_scripts`, `num_workers`, `node_type_id`, `spark_version`. See [Configuration Guide](references/configuration-guide.md) for a complete before/after example.

**spark_conf migration**: Scan all `spark.conf.set(...)` calls in the notebook and `spark_conf` entries in the job JSON. For each:
- **Supported** (keep): `spark.sql.shuffle.partitions`, `spark.sql.session.timeZone`, `spark.sql.ansi.enabled`, `spark.sql.files.maxPartitionBytes`, `spark.sql.legacy.timeParserPolicy`, `spark.databricks.execution.timeout`
- **Auto-tuned** (remove with comment): AQE configs, Delta auto-compact, executor/driver sizing, parallelism configs
- **Credential configs** (remove): `fs.s3a.*`, `fs.azure.*` — replaced by UC external locations
- Add a code comment at each removal explaining why: `# Removed: auto-tuned on serverless` or `# Removed: use UC external locations instead`

### Parameterize catalogs for testing

```python
dbutils.widgets.text("catalog", "main")  # Default to production
catalog = dbutils.widgets.get("catalog")
df = spark.table(f"{catalog}.sales.orders")
# Pass catalog="test_catalog" as a job parameter during testing
```

See [Configuration Guide](references/configuration-guide.md) for mock table catalog mapping and test job creation patterns.

### Debug failed serverless runs

Always get the actual error with `w.jobs.get_run_output(run_id=...)` before guessing. Common errors:

| Error | Fix |
|-------|-----|
| `INFINITE_STREAMING_TRIGGER_NOT_SUPPORTED` | Add `.trigger(availableNow=True)` |
| `UNRESOLVED_COLUMN` | Temp view name collision — use unique names |
| `TABLE_OR_VIEW_NOT_FOUND` | DBFS/HMS table not accessible — migrate to UC |
| `Py4JError: ... is not available` | SparkContext/RDD used — rewrite to DataFrame |
| Package installation timeout | Pin versions; do NOT install PySpark as a dependency |
| `ModuleNotFoundError: No module named 'mlflow'` | Add to environment spec `dependencies` — ML runtime is NOT available on serverless |
| `SparkContext.getOrCreate() is NOT supported` / `RuntimeError: Only remote Spark sessions` | Replace with `spark.createDataFrame()` or `spark.range()` |
| `UC_FILE_SCHEME_FOR_TABLE_CREATION_NOT_SUPPORTED` | Use managed tables or `/Volumes/...` paths |
| `PERMISSION_DENIED: CREATE SCHEMA on Catalog 'main'` | Add `spark.sql("USE CATALOG <your_catalog>")` before CREATE statements |
| `DATA_SOURCE_NOT_FOUND: Failed to find data source` | Category 3 blocker — custom JAR data source needs classic compute |
| `NoSuchMethodError: scala.Predef$.wrapRefArray` / `NoClassDefFoundError: scala/Serializable` on a JAR run | Scala version mismatch — JAR compiled against 2.12; serverless is 2.13.16. Recompile against 2.13.16. See [JAR Migration](references/jar-migration.md) |
| `NoClassDefFoundError` for `org/apache/spark/...` on a JAR run | Spark bundled instead of provided. Mark `databricks-connect % Provided` (and rewrite any `SparkContext`/RDD source). See [JAR Migration](references/jar-migration.md) |
| `SyntaxError` after migration | Ensure comments are inside MAGIC blocks, not straddling cell delimiters |
| `File './<name>' not found` from `%run` (or `%run` fires as IPython line magic) | A1: a plain-Python comment is preceding `# MAGIC %run` in the same cell. Move the comment to its own `# MAGIC %md` cell above. |
| `TypeError: max() got an unexpected keyword argument 'key'` | A2: `from pyspark.sql.functions import *` shadowed builtin `max`. Use sort+index instead of `max(..., key=)`. |
| `TypeError: Object of type PlanMetrics is not JSON serializable` | A3: `automl.classify/regress/forecast` not supported; the `DBDemos.create_mockup_automl_run` fallback hits this on Spark Connect. Rewrite as inline sklearn Pipeline. |
| `NameError: cannot access free variable 'loaded_model'` | A4: mlflow 2.19.0 `pyfunc.spark_udf` closure bug on Spark Connect. Use driver-side `pyfunc.load_model` + `toPandas()` + `spark.createDataFrame`, or pin `mlflow>=2.20.0`. |
| `ModuleNotFoundError: No module named 'databricks.automl_runtime'` | E1: SDP image missing `databricks-automl-runtime`. Emit `%pip install -q databricks-automl-runtime` at top of the SDP `.py` library file. |
| `HTTP 400: Failed to enforce schema of data ... Model is missing inputs ['id']` | E2: AutoML → sklearn rewrite changed model signature; flip downstream `force_update = False` → `True`. |
| `RESOURCE_DOES_NOT_EXIST` from `get_model_version_by_alias(..., 'Champion')` during `log_model` | M1: drop `registered_model_name=` from `log_model` under UC; call `mlflow.register_model(...)` after the run. |
| `TypeError: 'NoneType' object is not iterable` from `.latest_versions` | M2: `RegisteredModel.latest_versions` is always `None` on UC. Use `client.search_model_versions(...)` + sort+index. |
| `MlflowException: Model signature is required for registering a model to Unity Catalog` | M3: UC requires `signature=` on `log_model`. Infer via `infer_signature(X_sample, model.predict(X_sample))` and pass to `log_model(..., signature=signature)`. See [MLflow on UC](references/mlflow-uc-patterns.md). |
| 404 on `ai_query(endpoint => 'databricks-meta-llama-3-1-405b-instruct')` | D1: retired Foundation Model endpoint. Replace with `databricks-meta-llama-3-3-70b-instruct` via content scan across all migrated files. |
| `PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore` (even when catalog exists) | B2: priv check fires before `IF NOT EXISTS` short-circuits. Guard with `SHOW CATALOGS LIKE '...'` probe. Apply recursively, including `_resources/` and `config*` files. |
| `Table is already managed by pipeline <pipeline-id>` on SDP parallel deploy | H2: suffix the migrated pipeline's target `schema` (e.g., `<orig>_skill_migrated`). |
| `DELTA_FAILED_TO_MERGE_FIELDS: prediction (Double) vs prediction (Integer)` | M4: AutoML → sklearn rewrite emits `float64` predictions; cast to `IntegerType` for binary classifiers before writing. See [MLflow on UC](references/mlflow-uc-patterns.md). |

See [Configuration Guide](references/configuration-guide.md) for the full error reference and SDK code examples.

## Performance Mode Selection

| Criteria | Performance-Optimized | Standard |
|----------|-----------------------|----------|
| Startup time | <50 seconds | 4-6 minutes |
| Cost | Higher | Significantly lower |
| Available for | Notebooks, Jobs, SDP | Jobs and SDP only |
| Best for | Interactive work, dev, time-sensitive | Batch ETL, scheduled pipelines |
| Default | Yes (UI and API) | Must be explicitly selected |

**Standard mode is NOT available for notebooks.** Notebooks always use Performance-Optimized.

## Serverless Defaults to Know

| Setting | Value |
|---------|-------|
| REPL VM memory | 8GB default (high-memory option available) |
| Max executors | 32 (Premium), 64 (Enterprise) — raise via support |
| Supported Spark configs | 6 only (see Category D above) |
| Debugging | Query Profile (no Spark UI) |
| ANSI SQL | Enabled by default (configurable) |

## Failure Reporting Protocol

When migration fails or hits an unmigratable pattern, generate a structured failure report and offer the user a one-step path to file it as a GitHub issue. This feedback loop is how the skill learns — without it, gaps go undiscovered.

See [Failure Reporting](references/failure-reporting.md) for the full redaction checklist, URL-encoding recipe, and example pre-filled link.

### Decision tree: when to offer to file an issue

**Offer to file a GitHub issue any time the workload cannot be fully migrated to serverless as-is.** Reports from "known" patterns (R, Scala, custom JAR data sources, JVM access, third-party connectors) are just as valuable as reports from unknown patterns — they tell maintainers which gaps users hit most often, which drives prioritization.

Concretely, ALWAYS offer if **any** of these is true:

1. **Workload contains any Category 3 (classic-only) blocker** — R, Scala notebook cells, custom JAR data sources, JVM/Py4J access, third-party connectors without serverless equivalents, native binary dependencies, etc. The fact that the pattern is "documented as Cat 3" is not a reason to skip the offer.
2. **Retries exhausted** — `retry_count >= max_retries` (typically 5) and final status is FAILED
3. **Unknown pattern** — a classic-compute construct was detected that isn't in the skill's catalog
4. **Fix didn't resolve** — a known fix was applied but the workload still fails on serverless
5. **Explicit request** — the user invokes `/migration-report`

**Do NOT offer to file** only when:

- The migration succeeded fully (even after retries), or
- The workload is already serverless-compatible and required no changes.

### How to generate the report

Write a JSON file to `~/.databricks-migration-skill/reports/failure-<ISO-timestamp>.json`. Create the directory if it doesn't exist.

**Schema** (strictly follow — no free-text code or identifiers):

```json
{
  "report_version": "1.1",
  "report_id": "<uuid-v4>",
  "skill_version": "<from SKILL.md frontmatter metadata.version>",
  "timestamp": "<ISO 8601 UTC>",
  "failure_phase": "analyze | migrate | test | validate",
  "detected_patterns": [
    {"category": "A", "pattern_id": "rdd_parallelize", "count": 3}
  ],
  "attempted_fixes": [
    {"pattern_id": "rdd_parallelize", "fix_applied": "<fix_id>", "attempt_number": 1, "outcome": "failed"}
  ],
  "final_error_category": "unknown_api | missing_library | data_access | permission | custom_data_source | jvm_access | unsupported_language | other",
  "final_error_signature": "<SHA256 of top 3 stack frames, NOT the frames themselves>",
  "retry_count": 5,
  "total_duration_seconds": 245,
  "notebook_characteristics": {
    "lines_of_code": 180,
    "language": "python | sql | scala | r",
    "uses_streaming": false,
    "uses_ml_libraries": true,
    "databricks_runtime_source": "<DBR version only, no cluster identifiers>"
  }
}
```

### What the report MUST NOT contain

Hard requirement — the report must be safe to share publicly on GitHub Issues:

- **No code content** — pattern IDs only (e.g., `rdd_parallelize`), never code snippets, function bodies, or even single-line examples
- **No file paths** — no notebook names, directory paths, workspace URLs, or DBFS paths
- **No error message text** — only the error category enum and a hashed signature
- **No identifiers** — no table names, column names, catalog names, schema names, secret scope names, user emails, workspace IDs, or account IDs
- **No internal Databricks references** — no Databricks employee names, internal codenames (e.g., product code names not in public docs), `go/` links, Confluence page IDs, Google Doc IDs, Slack user or channel IDs (`U…`, `C…`), PROD-* / SEV-* / SC-* ticket numbers
- **No customer references** — no company names, product names of customer systems, or anything that would identify the workspace's owning organization
- **No credentials** — no tokens, API keys, connection strings, JDBC URLs, or service principal IDs
- **No data descriptions** — no column value samples, row counts tied to specific tables, or schema fingerprints beyond the `notebook_characteristics` fields

### Anonymization safety pass

Before writing the report, scan every string field against this pattern checklist. If any pattern matches, **drop the offending field** (do not redact partially — empty string is safer than risking leakage):

| Pattern | What to scrub |
|---------|---------------|
| `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}` | Email addresses |
| `dbfs:/`, `/dbfs/`, `s3://`, `abfss://`, `gs://`, `wasbs://` | Cloud storage paths |
| `https?://[a-z0-9-]+\.cloud\.databricks\.com`, `https?://adb-\d+\.\d+\.azuredatabricks\.net` | Workspace URLs |
| `U[A-Z0-9]{8,}`, `C[A-Z0-9]{8,}` | Slack user / channel IDs |
| `\bgo/[a-z0-9-]+\b` | go/ links |
| `\b(PROD|SEV|SC|JIRA)-\d+\b` | Internal ticket IDs |
| `[0-9a-f]{20,}` (heuristic) | Likely doc/file/workspace IDs |
| Catalog/schema/table name literals from the analyzed notebook | Drop and replace with `"<redacted>"` |

The `notebook_characteristics` fields are the only safe surface for workload metadata. Do not add new fields without expanding this checklist.

### Deterministic post-serialization scrub (required)

The redaction above happens at generation time and depends on the model applying every rule. That is not enough on a path that ends in a public GitHub issue. After serializing the report to JSON:

1. **Re-run the MUST-NOT-CONTAIN regex set as a literal text search over the final JSON file**. Match the same patterns from the table above, plus any catalog/schema/table names that were referenced in the analyzed notebook.
2. **If any pattern matches, refuse to display the pre-filled URL or the `gh issue create` command**. Print the local file path, list the patterns that matched, and tell the user to redact the file manually before sharing.
3. Only when the post-serialization scrub is clean may the pre-filled URL be shown.

This deterministic check is non-negotiable; do not skip it even when you are confident the generation-time redaction was applied.

### After generating the report — output template

When the decision tree above says "offer to file", the **default output is local-only**. The pre-filled URL and `gh` command are shown only after the user has acknowledged the local file and the post-serialization scrub (see above) is clean.

Default response — always include:

1. The local report file path (`~/.databricks-migration-skill/reports/failure-<timestamp>.json`, with `<timestamp>` filled in).
2. A one-line note that the report contains pattern IDs and notebook characteristics only, no code or identifiers.
3. A prompt: *"This is a draft. Open the file, confirm the redaction looks right, then tell me to share it. I'll generate the pre-filled GitHub issue URL once you've confirmed."*

Only after the user explicitly confirms (e.g. *"share it"*, *"file the issue"*, *"looks good"*) AND the deterministic post-serialization scrub above returned clean, then produce:

- **Option A** — a complete pre-filled `https://github.com/databricks/databricks-agent-skills/issues/new?template=migration-feedback.md&title=<…>&body=<…>` URL, both parameters URL-encoded.
- **Option B** — the literal `gh issue create --repo databricks/databricks-agent-skills …` command, body-file pointing at the local report.

Do not produce the URL or `gh` command in the same turn as the file write. Two turns: write + offer review, then publish after explicit confirmation.

Use this exact wrap-up template, replacing `<…>` placeholders:

```
Migration could not complete. A failure report has been generated at:

  ~/.databricks-migration-skill/reports/failure-<timestamp>.json

The report contains anonymized diagnostic data (detected pattern IDs, error
category, retry count, notebook characteristics) and no code content or PII.
Submission is optional and opt-in.

To help improve this skill, file the report as a GitHub issue:

  Option A — One-click in browser (pre-filled):
    <PREFILLED_ISSUE_URL>

  Option B — From the terminal (if you have the GitHub CLI installed):
    gh issue create \
      --repo databricks/databricks-agent-skills \
      --title "<TITLE>" \
      --body-file ~/.databricks-migration-skill/reports/failure-<timestamp>.json \
      --label migration-skill

Before submitting, please open the JSON and confirm nothing sensitive
slipped through. We never transmit reports automatically.
```

Build `<PREFILLED_ISSUE_URL>` like this:

1. **Title**: `[migration-skill] <final_error_category> in <failure_phase> phase`
   Example: `[migration-skill] custom_data_source in migrate phase`
2. **Body**: the issue template's markdown skeleton (Category, Environment, Description, Failure report JSON fenced in ` ```json `) with the report JSON inlined.
3. **URL-encode** both title and body (`%20` for spaces, `%23` for `#`, `%0A` for newline, etc.).
4. **Final URL**:
   `https://github.com/databricks/databricks-agent-skills/issues/new?template=migration-feedback.md&title=<URL-encoded title>&body=<URL-encoded body>`

If your runtime cannot actually write the file (sandboxed, no filesystem write), still show the path the file WOULD be at and produce Options A and B. The user can write the JSON to disk themselves.

The full recipe with a worked example is in [Failure Reporting](references/failure-reporting.md).

**Never transmit the report automatically.** The user owns their data and must review before sharing. If the user declines, do not press them — log the local report path and move on.

## Success report

When migration succeeds, generate a per-workload report with the same structure as the failure report (minus the redaction-to-publish step), listing the patterns detected and the fixes applied for each workload. Write to `~/.databricks-migration-skill/reports/success-<timestamp>.json` and tell the user the file path.

## Multiple workload migration

When several independent workloads are in scope, migrate them in parallel (e.g. one subagent per workload). Keep the per-notebook steps within a single workload sequential, as in Step 1.5.

## Reference Guides

For detailed workarounds and code examples beyond the quick fixes above:

- [Compatibility Checks](references/compatibility-checks.md) — Full pattern detection table with all 40+ checks
- [Streaming Migration](references/streaming-migration.md) — Trigger migration, SDP continuous mode, continuous jobs
- [Networking and Security](references/networking-and-security.md) — VPC peering to NCCs, Private Link, firewall setup
- [Code Patterns](references/code-patterns.md) — Complete before/after code examples for every migration pattern
- [Configuration Guide](references/configuration-guide.md) — Supported Spark configs, Environments setup, budget policies
- [MLflow on UC](references/mlflow-uc-patterns.md) — AutoML rewrite to sklearn, UC-aware registration, `latest_versions` replacement, `spark_udf` closure-bug fix, prediction-column dtype alignment
- [Multi-source enumeration](references/multi-source-enumeration.md) — Parsing `bundle_config.py` and fetching upstream git sources before per-notebook analysis
- [Failure Reporting](references/failure-reporting.md) — Redaction checklist + pre-filled GitHub issue URL recipe (for when migration cannot complete)
- [Install in Databricks Genie Code](references/install-in-databricks-genie-code.md) — Run this skill inside a Databricks workspace
- [JAR Migration](references/jar-migration.md) — Migrating a compiled Scala JAR (spark_jar_task): Scala 2.13.16, Databricks Connect, dependency conflicts vs the serverless kernel classpath, sbt fixes, build/test/deploy

## Documentation

- Serverless compute overview: https://docs.databricks.com/en/compute/serverless/
- **Migration guide**: https://docs.databricks.com/en/compute/serverless/migration
- Limitations: https://docs.databricks.com/en/compute/serverless/limitations
- Best practices: https://docs.databricks.com/en/compute/serverless/best-practices
- Serverless notebooks: https://docs.databricks.com/en/compute/serverless/notebooks
- Serverless jobs: https://docs.databricks.com/en/jobs/run-serverless-jobs
- Serverless SDP: https://docs.databricks.com/en/ldp/serverless
- Spark Connect vs. classic: https://docs.databricks.com/en/spark/connect-vs-classic
- Unity Catalog upgrade: https://docs.databricks.com/en/data-governance/unity-catalog/upgrade/
- Supported Spark configs: https://docs.databricks.com/en/spark/conf#serverless
