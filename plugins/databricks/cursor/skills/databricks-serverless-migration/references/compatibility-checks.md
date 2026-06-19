# Compatibility Checks Reference

Complete pattern detection table for serverless compute compatibility scanning. Each entry includes the detection pattern, severity, fix summary, and a link to authoritative documentation.

## How to Use This Reference

Scan user code for the regex/grep patterns below. When a match is found, report the severity and provide the fix. Patterns are grouped by category matching the SKILL.md analysis categories (A through G).

## Category A: Unsupported APIs

### RDD and SparkContext Operations

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| `sc.parallelize` | `sc\.parallelize\(` | Blocker | `spark.createDataFrame([(x,) for x in data], ["value"])` | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `rdd.map` | `\.map\(lambda` on RDD variables | Blocker | `df.select(F.col("col") * 2)` or `df.withColumn(...)` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.filter` | `\.filter\(lambda` on RDD variables | Blocker | `df.filter(F.col("value") > 3)` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.reduce` | `\.reduce\(lambda` | Blocker | `df.agg(F.sum("col")).collect()[0][0]` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.flatMap` | `\.flatMap\(` | Blocker | `df.select(F.explode(F.split(col, " ")))` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.groupByKey` | `\.groupByKey\(` | Blocker | `df.groupBy("key").agg(F.collect_list("value"))` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.mapPartitions` | `\.mapPartitions\(` | Blocker | `df.groupBy(F.spark_partition_id()).applyInPandas(fn, schema)` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.reduceByKey` | `\.reduceByKey\(` | Blocker | `df.groupBy("key").agg(F.sum("value"))` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.sortByKey` | `\.sortByKey\(` | Blocker | `df.orderBy("key")` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.join` | RDD `.join\(` | Blocker | `df1.join(df2, "key")` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.coalesce` / `rdd.repartition` | `\.coalesce\(\d+\)` on RDD | Blocker | `df.coalesce(n)` / `df.repartition(n)` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.foreach` | `\.foreach\(` on RDD | Blocker | `df.foreach(fn)` or rewrite with DataFrame operations | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.foreachPartition` | `\.foreachPartition\(` | Blocker | Rewrite with `applyInPandas` or DataFrame sink operations | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `rdd.toDF` | `\.toDF\(` on RDD | Blocker | Use `spark.createDataFrame()` directly | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |

### SparkContext Methods

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| `sc.textFile` | `sc\.textFile\(` | Blocker | `spark.read.text(path)` | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `sc.wholeTextFiles` | `sc\.wholeTextFiles\(` | Blocker | `spark.read.format("binaryFile").load(path)` | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `sc.broadcast` | `sc\.broadcast\(` | Blocker | `from pyspark.sql.functions import broadcast; df.join(broadcast(lookup_df), key)` | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `sc.accumulator` | `sc\.accumulator\(` | Blocker | `df.agg(F.sum("col"))` or `df.count()` | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `spark.sparkContext` | `spark\.sparkContext` | Blocker | Use `spark` (SparkSession) directly | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `sqlContext` | `sqlContext\.` | Blocker | `spark.sql(query)` or `spark.table(name)` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |
| `sc.hadoopConfiguration` | `sc\.hadoopConfiguration` or `hadoopConfiguration\.set\(` | Blocker | Use UC external locations — no credential configs needed | [UC External Locations](https://docs.databricks.com/en/connect/unity-catalog/external-locations.html) |
| `SparkContext.getOrCreate()` | `SparkContext\.getOrCreate\(\)` | Blocker | Not supported — `RuntimeError: Only remote Spark sessions using Databricks Connect are supported`. Replace with `spark.createDataFrame()` or `spark.range()` for data setup. | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `sc.setLogLevel` | `sc\.setLogLevel\(` | Info | Remove — log level is managed automatically | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `sc.getConf` | `sc\.getConf` | Warning | `spark.conf.get("config.name")` | [Spark Connect](https://docs.databricks.com/en/spark/connect-vs-classic) |

### Caching Operations

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| `df.cache()` | `\.cache\(\)` | Warning | Remove caching calls. Materialize expensive results to Delta tables. Native support coming soon. | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `df.persist()` | `\.persist\(` | Warning | Remove — or write expensive intermediate results to a Delta table | [Disk Cache](https://docs.databricks.com/en/optimizations/disk-cache) |
| `df.unpersist()` | `\.unpersist\(` | Warning | Remove along with the corresponding `cache`/`persist` call | [Disk Cache](https://docs.databricks.com/en/optimizations/disk-cache) |
| `df.checkpoint()` | `\.checkpoint\(` | Warning | Write to Delta table instead | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `spark.catalog.cacheTable` | `cacheTable\(` | Warning | Remove — not needed on serverless | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `CACHE TABLE` | `CACHE\s+TABLE` | Warning | Remove the SQL statement | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `UNCACHE TABLE` | `UNCACHE\s+TABLE` | Warning | Remove along with the corresponding `CACHE TABLE` | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |

### Language Restrictions

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| Scala cells | `%scala` | Blocker | Port to PySpark/SQL or compile as JAR for job tasks | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| R cells | `%r` | Blocker | No serverless equivalent — keep on classic or port to PySpark | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| Hive variable syntax | `\$\{[^}]+\}` in SQL | Warning | Use `DECLARE VARIABLE` / `SET VARIABLE` (SQL) or Python f-strings | [SQL Variables](https://docs.databricks.com/en/sql/language-manual/sql-ref-variables.html) |
| `CREATE GLOBAL TEMPORARY VIEW` | `CREATE\s+GLOBAL\s+TEMP` | Blocker | `CREATE OR REPLACE TEMPORARY VIEW` — global temp views use `global_temp` database which doesn't exist on serverless | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| `global_temp.` prefix in queries | `global_temp\.` | Warning | Remove prefix — session-scoped temp views are accessible without a database qualifier | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |

## Category B: Data Access

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| DBFS paths (persistent) | `dbfs:/` or `"/dbfs/` | Blocker | Replace with `/Volumes/<your_catalog>/schema/volume/path` | [Volumes](https://docs.databricks.com/en/volumes/volume-files) |
| DBFS temp paths | `dbfs:/tmp/`, `"/dbfs/tmp/`, paths with `cache`/`scratch`/`temp` | Warning | Use `/tmp/` or `/local_disk0/tmp/` (local driver disk) instead of Volumes for temp files | [Volumes](https://docs.databricks.com/en/volumes/volume-files) |
| FUSE mount paths | `file:///dbfs/` | Warning | Replace persistent paths with `/Volumes/...`; replace temp paths with `/local_disk0/tmp/` | [Volumes](https://docs.databricks.com/en/volumes/volume-files) |
| DBFS mounts (Spark) | `dbfs:/mnt/` | Blocker | Create UC external location + external volume | [External Locations](https://docs.databricks.com/en/connect/unity-catalog/external-locations.html) |
| DBFS mounts (Python) | `/dbfs/mnt/` | Blocker | Replace with `/Volumes/catalog/schema/volume/` | [Volumes](https://docs.databricks.com/en/volumes/volume-files) |
| Mount creation | `dbutils\.fs\.mount\(` | Blocker | Create UC external location + external volume | [External Locations](https://docs.databricks.com/en/connect/unity-catalog/external-locations.html) |
| Hive Metastore tables | `hive_metastore\.` | Warning | Migrate to UC or use HMS Federation | [UC Upgrade](https://docs.databricks.com/en/data-governance/unity-catalog/upgrade/) |
| Two-level namespace | `spark\.table\("[^.]+\.[^.]+"\)` (exactly 2 levels) | Warning | Add catalog prefix: `spark.table("catalog.schema.table")` | [UC Upgrade](https://docs.databricks.com/en/data-governance/unity-catalog/upgrade/) |
| `CREATE DATABASE`/`CREATE SCHEMA` without `USE CATALOG` | `CREATE\s+(DATABASE|SCHEMA)\s+(?!IF)` without preceding `USE CATALOG` or 3-level qualification | Blocker | Prepend `spark.sql("USE CATALOG <your_catalog>")` at notebook start before any CREATE statements | [UC Upgrade](https://docs.databricks.com/en/data-governance/unity-catalog/upgrade/) |
| IAM instance profiles | `instance_profile_arn` or `iam.*instance.profile` | Warning | Use UC external locations + storage credentials | [Storage Credentials](https://docs.databricks.com/en/connect/unity-catalog/storage-credentials.html) |
| Hive SerDe tables | `STORED AS` with non-Delta formats, `ROW FORMAT SERDE` | Blocker | Migrate to Delta tables in UC | [Delta Migration](https://docs.databricks.com/en/delta/migrate-from-other-formats.html) |
| Direct S3/ADLS access | `s3://` or `abfss://` in `spark.read`/`spark.write` without UC | Warning | Use UC external locations for governed access | [External Locations](https://docs.databricks.com/en/connect/unity-catalog/external-locations.html) |

## Category C: Streaming

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| ProcessingTime trigger | `\.trigger\(processingTime` | Blocker | `.trigger(availableNow=True)` + set batch size limits | [Triggers](https://docs.databricks.com/en/structured-streaming/triggers.html) |
| Continuous trigger | `\.trigger\(continuous` | Blocker | Migrate to Spark Declarative Pipelines (SDP) continuous mode | [SDP Serverless](https://docs.databricks.com/en/ldp/serverless) |
| Missing trigger | `\.writeStream` without `.trigger(` nearby | Blocker | Add `.trigger(availableNow=True)` — Spark defaults to `ProcessingTime("0 seconds")` | [Triggers](https://docs.databricks.com/en/structured-streaming/triggers.html) |
| Kafka source | `format\("kafka"\)` | Info | Works with AvailableNow; use `maxOffsetsPerTrigger` for batch size control | [Kafka](https://docs.databricks.com/en/structured-streaming/kafka.html) |
| Auto Loader | `format\("cloudFiles"\)` | Info | Works; use `cloudFiles.maxFilesPerTrigger` (note prefix) | [Auto Loader](https://docs.databricks.com/en/ingestion/cloud-files/) |
| `forEachBatch` | `\.foreachBatch\(` | Info | Works on serverless with AvailableNow trigger | [Triggers](https://docs.databricks.com/en/structured-streaming/triggers.html) |

## Category D: Configuration

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| Unsupported Spark configs | `spark\.conf\.set\(` with non-supported config key | Warning | Remove — only 6 configs are supported (see [Configuration Guide](configuration-guide.md)) | [Spark Configs](https://docs.databricks.com/en/spark/conf#serverless) |
| Init scripts (cluster/job config) | `init_scripts` in cluster/job config JSON | Blocker | Extract pip packages to Environment `dependencies`; flag OS-level packages without pip equivalents as serverless-incompatible | [Dependencies](https://docs.databricks.com/en/compute/serverless/dependencies) |
| Init scripts (bash) | `#!/bin/bash` scripts with `pip install` or `apt install` | Blocker | Convert `pip install` to Environment dependencies; convert `apt install` to pip equivalents where possible | [Dependencies](https://docs.databricks.com/en/compute/serverless/dependencies) |
| `%run` with relative paths | `%run\s+\.\/` or `%run\s+\.\.\/` | Warning | Relative `%run` paths may not resolve in serverless job tasks. Inline the notebook (<500 lines) or use `dbutils.notebook.run("<absolute_workspace_path>", timeout)` | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| Docker containers | `docker` in cluster config | Blocker | Use Environments for libraries; keep on classic if OS-level customization is required | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| Cluster policies | `cluster_policy_id` | Info | Use budget policies for cost attribution | [Budget Policies](https://docs.databricks.com/en/admin/usage/budget-policies.html) |
| Environment variables in init scripts | `export\s+\w+=` in init scripts | Warning | Use `dbutils.widgets` or job parameters | [Job Parameters](https://docs.databricks.com/en/jobs/settings.html) |
| Executor count/memory configs | `spark\.executor\.(instances|memory|cores)` | Info | Remove — serverless auto-scales and auto-tunes | [Serverless Compute](https://docs.databricks.com/en/compute/serverless/) |
| Driver memory configs | `spark\.driver\.memory` | Info | Remove — serverless REPL default is 8 GB (high-memory option available) | [Serverless Compute](https://docs.databricks.com/en/compute/serverless/) |
| AQE configs | `spark\.sql\.adaptive\.` | Info | Remove — AQE is always enabled and auto-tuned on serverless | [Serverless Best Practices](https://docs.databricks.com/en/compute/serverless/best-practices) |
| Auto-compact/optimize configs | `spark\.databricks\.(delta\.autoCompact\|delta\.optimizeWrite)` | Info | Remove — always enabled on serverless | [Serverless Best Practices](https://docs.databricks.com/en/compute/serverless/best-practices) |
| `os.environ` accessing system env vars | `os\.environ\[` or `os\.environ\.get\(` | Warning | System/Spark env vars (`SPARK_HOME`, `JAVA_HOME`) and custom cluster env vars are not available on serverless. Use `os.environ.get()` with fallback, `spark.version`, or `dbutils.widgets` for custom vars. | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |
| Hive variable substitution (`SET hivevar:`) | `SET\s+hivevar:` | Blocker | Use SQL session variables: `DECLARE OR REPLACE VARIABLE name = value` (DBR 14.1+). Reference variables by name directly, not `${hivevar:name}`. | [SQL Variables](https://docs.databricks.com/en/sql/language-manual/sql-ref-variables.html) |
| Hive variable references (`${hivevar:...}`) | `\$\{hivevar:` | Blocker | Replace with SQL session variable references (just the variable name) or Python f-strings | [SQL Variables](https://docs.databricks.com/en/sql/language-manual/sql-ref-variables.html) |

## Category E: Libraries

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| JAR libraries in notebooks | `dbutils\.library\.install\(` or JAR paths in library configs | Blocker | Compile as JAR job task (Scala 2.13, JDK 17, environment version 4+) | [JAR Jobs](https://docs.databricks.com/en/jobs/how-to/use-jars-in-workflows) |
| Maven coordinates | `maven` in library configs | Blocker | Replace with PyPI packages in Environments | [Dependencies](https://docs.databricks.com/en/compute/serverless/dependencies) |
| Unpinned pip installs | `%pip install\s+\w+` without `==` | Warning | Pin versions: `%pip install numpy==2.2.2 pandas==2.2.3` | [Dependencies](https://docs.databricks.com/en/compute/serverless/dependencies) |
| PySpark in pip install | `%pip install.*pyspark` | Blocker | Remove — installing PySpark breaks the serverless session | [Dependencies](https://docs.databricks.com/en/compute/serverless/dependencies) |
| Custom Spark data sources | `spark.read.format("custom_format")` with custom JARs | Blocker | Use Lakehouse Federation, Lakeflow Connect, or PySpark custom data sources | [Federation](https://docs.databricks.com/en/query-federation/) |
| LZO format | `\.lzo` or `format\("lzo"\)` | Blocker | Convert to Parquet or Delta | [Limitations](https://docs.databricks.com/en/compute/serverless/limitations) |

## Category F: Networking

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| VPC peering | VPC peering in workspace network config | Blocker | Create NCCs, get stable IPs, allowlist on resource firewalls | [Serverless Networking](https://docs.databricks.com/en/security/network/serverless-network-security/) |
| Direct cloud storage access | `s3://` or `abfss://` without UC | Warning | Use UC external locations for governed access | [External Locations](https://docs.databricks.com/en/connect/unity-catalog/external-locations.html) |
| Hardcoded IP addresses | IP addresses in connection strings | Warning | Verify connectivity from serverless network; use NCCs if private resources | [Serverless Networking](https://docs.databricks.com/en/security/network/serverless-network-security/) |

## Category G: Sizing and Debugging

| Pattern | Grep/Regex | Severity | Fix | Docs |
|---------|-----------|----------|-----|------|
| Large driver memory | `spark.driver.memory` set to >8g | Info | Serverless REPL default is 8 GB; high-memory option available via Environments | [Serverless Compute](https://docs.databricks.com/en/compute/serverless/) |
| Spark UI references | References to Spark UI, `spark.ui.port`, Spark History Server | Info | Use Query Profile: click "See performance" under cell output | [Query Profile](https://docs.databricks.com/en/sql/user/queries/query-profile.html) |
| Large shuffle configs | `spark.sql.shuffle.partitions` set very high (>2048) | Info | Serverless auto-tunes via AQE; consider removing or lowering | [Best Practices](https://docs.databricks.com/en/compute/serverless/best-practices) |

## Comprehensive Regex for Quick Scan

Use these combined patterns for a fast first-pass scan:

```python
# Blockers - must fix before migration
blocker_patterns = [
    r'sc\.(parallelize|textFile|wholeTextFiles|broadcast|accumulator)\(',
    r'SparkContext\.getOrCreate\(\)',
    r'spark\.sparkContext',
    r'sqlContext\.',
    r'sc\.hadoopConfiguration',
    r'\.mapPartitions\(',
    r'\.groupByKey\(',
    r'\.reduceByKey\(',
    r'\.flatMap\(',
    r'dbfs:/',
    r'"/dbfs/',
    r'dbutils\.fs\.mount\(',
    r'\.trigger\(processingTime',
    r'\.trigger\(continuous',
    r'%scala',
    r'%r\b',
    r'%pip install.*pyspark',
    r'CREATE\s+(DATABASE|SCHEMA)\s+',  # Check for missing USE CATALOG
    r'"init_scripts"',  # In job JSON
    r'CREATE\s+GLOBAL\s+TEMP',  # Global temp views not supported
    r'SET\s+hivevar:',  # Hive variable substitution not supported
    r'\$\{hivevar:',  # Hive variable references not supported
]

# Warnings - should fix for best results
warning_patterns = [
    r'\.cache\(\)',
    r'\.persist\(',
    r'\.checkpoint\(',
    r'hive_metastore\.',
    r'spark\.conf\.set\(',
    r'CACHE\s+TABLE',
    r'\$\{[^}]+\}',  # Hive variable syntax in SQL
    r'%run\s+\.\.?\/',  # Relative %run paths
    r'file:///dbfs/',  # FUSE mount paths
    r'global_temp\.',  # Global temp view references
    r'os\.environ\[',  # Direct env var access (may KeyError on serverless)
]

# Info - awareness items
info_patterns = [
    r'spark\.executor\.',
    r'spark\.driver\.memory',
    r'spark\.ui\.',
    r'format\("kafka"\)',
    r'format\("cloudFiles"\)',
]
```
