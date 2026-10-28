# Quick Fixes Reference

Before/after snippets for the most common serverless fixes. Full catalog of patterns: [Analyze Checklist](analyze-checklist.md); exhaustive before/after code: [Code Patterns](code-patterns.md).

## Replace DBFS paths with UC Volumes

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

## Replace RDD operations with DataFrames

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

## Fix streaming triggers

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

## Remove caching

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

## Other quick fixes

| Pattern | Fix | Full example |
|---------|-----|-------------|
| `sc.broadcast` / `sc.accumulator` / `sqlContext.sql` | Use SparkSession equivalents: `broadcast()` join, `df.agg()`, `spark.sql()` | [Code Patterns](code-patterns.md) |
| Init scripts | Move to Environment panel or `requirements.txt`. Do NOT install PySpark. Pin versions. | [Code Patterns](code-patterns.md) |
| Hive Metastore tables | Use HMS Federation as bridge (`CREATE FOREIGN CATALOG`) or migrate directly (`CREATE TABLE ... AS SELECT`) | [Code Patterns](code-patterns.md) |
| Custom JDBC JARs | Use Lakehouse Federation (`CREATE CONNECTION ... TYPE POSTGRESQL`) or built-in JDBC (works on serverless) | [Code Patterns](code-patterns.md) |
| Spark UI debugging | Use Query Profile: click "See performance" under cell output, or `df.explain(True)` | [Code Patterns](code-patterns.md) |

## Detect serverless at runtime

```python
import os
is_serverless = os.getenv("IS_SERVERLESS", "").lower() == "true"
```

## Parameterize catalogs for testing

```python
dbutils.widgets.text("catalog", "main")  # Default to production
catalog = dbutils.widgets.get("catalog")
df = spark.table(f"{catalog}.sales.orders")
# Pass catalog="test_catalog" as a job parameter during testing
```

See [Configuration Guide](configuration-guide.md) for mock table catalog mapping and test job creation patterns.
