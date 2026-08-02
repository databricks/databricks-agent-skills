# Quick Fixes Reference

Concrete rewrites for the patterns a serverless-readiness scan flags. Read this when a scan has named a pattern and you need the code change.

## Contents

  - [Replace DBFS paths with UC Volumes](#replace-dbfs-paths-with-uc-volumes)
  - [Replace RDD operations with DataFrames](#replace-rdd-operations-with-dataframes)
  - [Fix streaming triggers](#fix-streaming-triggers)
  - [Remove caching](#remove-caching)
  - [Other quick fixes](#other-quick-fixes)
  - [Detect serverless at runtime](#detect-serverless-at-runtime)
  - [Transform job config from classic to serverless](#transform-job-config-from-classic-to-serverless)
  - [Job Definition Migration](#job-definition-migration)
  - [Parameterize catalogs for testing](#parameterize-catalogs-for-testing)
  - [Debug failed serverless runs](#debug-failed-serverless-runs)

---

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
| `sc.broadcast` / `sc.accumulator` / `sqlContext.sql` | Use SparkSession equivalents: `broadcast()` join, `df.agg()`, `spark.sql()` | code-patterns |
| Init scripts | Move to Environment panel or `requirements.txt`. Do NOT install PySpark. Pin versions. | code-patterns |
| Hive Metastore tables | Use HMS Federation as bridge (`CREATE FOREIGN CATALOG`) or migrate directly (`CREATE TABLE ... AS SELECT`) | code-patterns |
| Custom JDBC JARs | Use Lakehouse Federation (`CREATE CONNECTION ... TYPE POSTGRESQL`) or built-in JDBC (works on serverless) | code-patterns |
| Spark UI debugging | Use Query Profile: click "See performance" under cell output, or `df.explain(True)` | code-patterns |

### Detect serverless at runtime

```python
import os
is_serverless = os.getenv("IS_SERVERLESS", "").lower() == "true"
```

### Transform job config from classic to serverless

Remove `job_clusters`/`new_cluster`, add `environments` with serverless spec, replace `job_cluster_key` with `environment_key`, remove `init_scripts`. See configuration-guide for full before/after JSON and environment version mapping.

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

**job_clusters to serverless compute**: Remove `job_clusters` / `new_cluster` blocks entirely. Add an `environments` array with the serverless spec. Replace `job_cluster_key` in each task with `environment_key`. Remove `init_scripts`, `num_workers`, `node_type_id`, `spark_version`. See configuration-guide for a complete before/after example.

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

See configuration-guide for mock table catalog mapping and test job creation patterns.

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
| `NoSuchMethodError: scala.Predef$.wrapRefArray` / `NoClassDefFoundError: scala/Serializable` on a JAR run | Scala version mismatch — JAR compiled against 2.12; serverless is 2.13.16. Recompile against 2.13.16. See jar-migration |
| `NoClassDefFoundError` for `org/apache/spark/...` on a JAR run | Spark bundled instead of provided. Mark `databricks-connect % Provided` (and rewrite any `SparkContext`/RDD source). See jar-migration |
| `SyntaxError` after migration | Ensure comments are inside MAGIC blocks, not straddling cell delimiters |
| `File './<name>' not found` from `%run` (or `%run` fires as IPython line magic) | A1: a plain-Python comment is preceding `# MAGIC %run` in the same cell. Move the comment to its own `# MAGIC %md` cell above. |
| `TypeError: max() got an unexpected keyword argument 'key'` | A2: `from pyspark.sql.functions import *` shadowed builtin `max`. Use sort+index instead of `max(..., key=)`. |
| `TypeError: Object of type PlanMetrics is not JSON serializable` | A3: `automl.classify/regress/forecast` not supported; the `DBDemos.create_mockup_automl_run` fallback hits this on Spark Connect. Rewrite as inline sklearn Pipeline. |
| `NameError: cannot access free variable 'loaded_model'` | A4: mlflow 2.19.0 `pyfunc.spark_udf` closure bug on Spark Connect. Use driver-side `pyfunc.load_model` + `toPandas()` + `spark.createDataFrame`, or pin `mlflow>=2.20.0`. |
| `ModuleNotFoundError: No module named 'databricks.automl_runtime'` | E1: SDP image missing `databricks-automl-runtime`. Emit `%pip install -q databricks-automl-runtime` at top of the SDP `.py` library file. |
| `HTTP 400: Failed to enforce schema of data ... Model is missing inputs ['id']` | E2: AutoML → sklearn rewrite changed model signature; flip downstream `force_update = False` → `True`. |
| `RESOURCE_DOES_NOT_EXIST` from `get_model_version_by_alias(..., 'Champion')` during `log_model` | M1: drop `registered_model_name=` from `log_model` under UC; call `mlflow.register_model(...)` after the run. |
| `TypeError: 'NoneType' object is not iterable` from `.latest_versions` | M2: `RegisteredModel.latest_versions` is always `None` on UC. Use `client.search_model_versions(...)` + sort+index. |
| `MlflowException: Model signature is required for registering a model to Unity Catalog` | M3: UC requires `signature=` on `log_model`. Infer via `infer_signature(X_sample, model.predict(X_sample))` and pass to `log_model(..., signature=signature)`. See mlflow-uc-patterns. |
| 404 on `ai_query(endpoint => 'databricks-meta-llama-3-1-405b-instruct')` | D1: retired Foundation Model endpoint. Replace with `databricks-meta-llama-3-3-70b-instruct` via content scan across all migrated files. |
| `PERMISSION_DENIED: User does not have CREATE CATALOG on Metastore` (even when catalog exists) | B2: priv check fires before `IF NOT EXISTS` short-circuits. Guard with `SHOW CATALOGS LIKE '...'` probe. Apply recursively, including `_resources/` and `config*` files. |
| `Table is already managed by pipeline <pipeline-id>` on SDP parallel deploy | H2: suffix the migrated pipeline's target `schema` (e.g., `<orig>_skill_migrated`). |
| `DELTA_FAILED_TO_MERGE_FIELDS: prediction (Double) vs prediction (Integer)` | M4: AutoML → sklearn rewrite emits `float64` predictions; cast to `IntegerType` for binary classifiers before writing. See mlflow-uc-patterns. |

See configuration-guide for the full error reference and SDK code examples.
