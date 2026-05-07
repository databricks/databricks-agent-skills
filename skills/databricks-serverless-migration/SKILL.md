---
name: databricks-serverless-migration
description: "Migrate Databricks workloads from classic compute to serverless compute. Scans code for serverless compatibility issues, provides concrete fixes for the serverless Spark Connect architecture, and guides the full migration to serverless environments. Use for classic-to-serverless migrations, serverless code compatibility checks, or writing new serverless-compatible notebooks and jobs. Not for classic DBR version upgrades or cluster configuration changes within classic compute."
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
├── Scala notebook cells → Category 2: port to PySpark/SQL or compile as JAR
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

**Category E: Libraries**

| Pattern | Severity | Fix |
|---------|----------|-----|
| JAR libraries in notebooks | Blocker | Compile as JAR job task (Scala 2.13, JDK 17, env version 4+) |
| Maven coordinates | Blocker | Replace with PyPI packages in Environments |
| `%pip install` without version pins | Warning | Pin versions: `%pip install numpy==2.2.2 pandas==2.2.3` |
| Custom Spark data sources (v1/v2 JARs) | Blocker | Use Lakehouse Federation, Lakeflow Connect, or PySpark custom data sources |
| LZO format files | Blocker | Convert to Parquet or Delta |

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
| `SyntaxError` after migration | Ensure comments are inside MAGIC blocks, not straddling cell delimiters |

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

When migration fails irrecoverably, generate a structured failure report to help improve the skill. This applies when:

- All retry attempts are exhausted (typically 5)
- An unknown pattern is encountered that isn't in the compatibility checks
- A fix was applied but didn't resolve the underlying issue
- The workload hits a Category 3 blocker the user wasn't aware of

### When to generate a report

Generate a report at the end of a migration attempt if **any** of:
- `retry_count >= max_retries` and final status is FAILED
- A pattern was detected but no fix is available in the skill
- The user explicitly requests a failure report (`/migration-report`)

### How to generate

Write a JSON file to `~/.databricks-migration-skill/reports/failure-<ISO-timestamp>.json`. Create the directory if it doesn't exist.

**Schema** (strictly follow — no free-text code or identifiers):

```json
{
  "report_version": "1.0",
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
  "final_error_category": "unknown_api | missing_library | data_access | permission | custom_data_source | other",
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

This is a hard requirement — the report must be safe to share publicly on GitHub Issues:

- **No code content** — only pattern IDs from this skill's catalog (e.g., `rdd_parallelize`), never actual code snippets
- **No file paths** — no notebook names, directory paths, or workspace URLs
- **No error message text** — only the error category enum and a hashed signature
- **No identifiers** — no table names, column names, catalog names, schema names, user emails, workspace IDs, or customer names
- **No credentials** — no secret scope names, API keys, or connection strings
- **No data descriptions** — no column value samples, row counts tied to specific tables, or data shape details beyond the `notebook_characteristics` fields

### After generating the report

Tell the user:

```
Migration failed after <N> attempts. A failure report has been generated at:

  ~/.databricks-migration-skill/reports/failure-<timestamp>.json

This report contains anonymized diagnostic data (detected patterns, error categories, retry count) and no code content or PII. You can:

1. Review the JSON to confirm no sensitive information is present
2. Share it via GitHub Issue to help improve the skill:
   https://github.com/databricks/databricks-agent-skills/issues/new?template=migration-feedback.md

Submission is optional and opt-in. We use reports to prioritize new patterns and fix detection gaps.
```

**Never transmit the report automatically.** The user owns their data and must review before sharing.

## Reference Guides

For detailed workarounds and code examples beyond the quick fixes above:

- [Compatibility Checks](references/compatibility-checks.md) — Full pattern detection table with all 40+ checks
- [Streaming Migration](references/streaming-migration.md) — Trigger migration, SDP continuous mode, continuous jobs
- [Networking and Security](references/networking-and-security.md) — VPC peering to NCCs, Private Link, firewall setup
- [Code Patterns](references/code-patterns.md) — Complete before/after code examples for every migration pattern
- [Configuration Guide](references/configuration-guide.md) — Supported Spark configs, Environments setup, budget policies

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
