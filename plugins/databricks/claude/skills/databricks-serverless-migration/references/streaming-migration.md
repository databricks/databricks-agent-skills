# Streaming Migration Guide

Complete guide for migrating streaming workloads from classic compute to serverless compute.

## Trigger Support Matrix

| Trigger Type | Serverless Support | Migration Action |
|-------------|-------------------|------------------|
| `availableNow=True` | Supported | No change needed |
| `once=True` | Supported (deprecated) | Migrate to `availableNow=True` |
| `processingTime="10 seconds"` | Not supported | Switch to `availableNow=True` |
| `continuous="1 second"` | Not supported | Migrate to SDP continuous mode |
| No `.trigger()` specified | Not supported | Add `.trigger(availableNow=True)` — Spark defaults to `ProcessingTime("0 seconds")` |

The most common migration surprise: **omitting `.trigger()` entirely causes failure** because Spark defaults to `ProcessingTime("0 seconds")`, which is not supported on serverless.

## Migration Hierarchy

When migrating continuous/near-real-time streaming workloads, choose the approach that best fits your requirements:

1. **Spark Declarative Pipelines (SDP) on serverless** (recommended) — native continuous streaming support with managed infrastructure
2. **Jobs with continuous schedule + AvailableNow trigger** — runs the streaming job on a recurring schedule; each run processes all available data then terminates
3. **Classic compute** (last resort) — keep ProcessingTime or Continuous triggers on classic clusters

### When to Use Each Approach

| Requirement | SDP Serverless | Jobs + AvailableNow | Classic |
|-------------|---------------|--------------------:|---------|
| Sub-second latency | No | No | Yes (Continuous trigger) |
| Minutes-level freshness | Yes | Yes (with frequent schedule) | Yes |
| Managed infrastructure | Yes | Partial | No |
| Complex multi-hop pipelines | Yes (native) | Manual orchestration | Manual orchestration |
| Cost optimization | Good | Good (pay per run) | Varies |

## Fixing the Default Trigger (Most Common Issue)

```python
# BEFORE (fails on serverless — no trigger defaults to ProcessingTime):
query = (df.writeStream
    .format("delta")
    .outputMode("append")
    .start(path))

# AFTER (serverless compatible):
query = (df.writeStream
    .format("delta")
    .outputMode("append")
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/stream1")
    .start("/Volumes/main/data/output/stream1"))
query.awaitTermination()
```

**Key points:**
- Always specify a checkpoint location (use UC Volumes, not DBFS)
- Call `.awaitTermination()` after `.start()` so the job waits for completion
- Checkpoint compatibility is maintained when switching from ProcessingTime to AvailableNow

## OOM Prevention

AvailableNow processes **all** available data in a single run. Without batch size limits, large backlogs can cause out-of-memory errors. Always set appropriate limits based on your source type.

### Delta / Parquet Sources

```python
query = (spark.readStream.format("delta")
    .option("maxFilesPerTrigger", 100)          # Max files per micro-batch
    .option("maxBytesPerTrigger", "10g")         # Max bytes per micro-batch
    .load("/Volumes/main/data/input/events")
    .writeStream
    .format("delta")
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/events")
    .start("/Volumes/main/data/output/events"))
query.awaitTermination()
```

**Defaults:** `maxFilesPerTrigger` defaults to 1000. Set `maxBytesPerTrigger` to control memory usage for large files.

### Auto Loader (cloudFiles)

```python
query = (spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.maxFilesPerTrigger", 1000)   # Note: cloudFiles. prefix
    .option("cloudFiles.maxBytesPerTrigger", "10g")   # Note: cloudFiles. prefix
    .option("cloudFiles.schemaLocation", "/Volumes/main/data/schemas/events")
    .load("/Volumes/main/data/landing/events")
    .writeStream
    .format("delta")
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/autoloader")
    .start("/Volumes/main/data/output/events"))
query.awaitTermination()
```

**Important:** Auto Loader options use the `cloudFiles.` prefix (e.g., `cloudFiles.maxFilesPerTrigger`, not `maxFilesPerTrigger`).

### Kafka Sources

```python
query = (spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", "broker1:9092,broker2:9092")
    .option("subscribe", "events-topic")
    .option("maxOffsetsPerTrigger", 100000)          # Kafka-specific batch limit
    .option("startingOffsets", "latest")              # Or "earliest" for backfill
    .load()
    .selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)", "topic", "partition", "offset")
    .writeStream
    .format("delta")
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/kafka")
    .start("/Volumes/main/data/output/kafka_events"))
query.awaitTermination()
```

**Note:** `maxOffsetsPerTrigger` controls how many offsets (messages) are read per micro-batch across all partitions. Set this based on your message size and available memory.

### Kinesis Sources

```python
query = (spark.readStream.format("kinesis")
    .option("streamName", "my-stream")
    .option("region", "us-east-1")
    .option("initialPosition", "latest")
    .load()
    .writeStream
    .format("delta")
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/kinesis")
    .start("/Volumes/main/data/output/kinesis_events"))
query.awaitTermination()
```

## Multi-Stream Patterns

When a notebook or job has multiple streaming queries, each must have its own checkpoint and use AvailableNow:

```python
# Stream 1: Raw events
raw_stream = (spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.maxFilesPerTrigger", 500)
    .load("/Volumes/main/data/landing/raw")
    .writeStream
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/raw")
    .toTable("main.bronze.raw_events"))

# Stream 2: Enriched events (reads from bronze)
enriched_stream = (spark.readStream
    .option("maxFilesPerTrigger", 100)
    .table("main.bronze.raw_events")
    .writeStream
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/enriched")
    .toTable("main.silver.enriched_events"))

# Wait for both
raw_stream.awaitTermination()
enriched_stream.awaitTermination()
```

## forEachBatch Pattern

`forEachBatch` works on serverless with AvailableNow trigger:

```python
def process_batch(batch_df, batch_id):
    # Upsert into target table
    from delta.tables import DeltaTable
    target = DeltaTable.forName(spark, "main.silver.customers")
    (target.alias("t")
        .merge(batch_df.alias("s"), "t.id = s.id")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute())

query = (spark.readStream
    .table("main.bronze.customer_events")
    .writeStream
    .trigger(availableNow=True)
    .option("checkpointLocation", "/Volumes/main/data/checkpoints/customers")
    .foreachBatch(process_batch)
    .start())
query.awaitTermination()
```

## Migrating to Spark Declarative Pipelines (SDP)

For continuous or near-real-time streaming, SDP on serverless is the recommended approach.

### Before: ProcessingTime Streaming Job

```python
# Classic notebook with ProcessingTime trigger
query = (spark.readStream.format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "orders")
    .load()
    .selectExpr("CAST(value AS STRING) as raw")
    .writeStream
    .trigger(processingTime="30 seconds")
    .format("delta")
    .option("checkpointLocation", "/dbfs/checkpoints/orders")
    .start("/dbfs/output/orders"))
```

### After: SDP Pipeline

```python
import dlt
from pyspark.sql import functions as F

@dlt.table(comment="Raw orders from Kafka")
def bronze_orders():
    return (spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", "broker:9092")
        .option("subscribe", "orders")
        .load()
        .selectExpr("CAST(value AS STRING) as raw",
                     "timestamp as kafka_timestamp"))

@dlt.table(comment="Parsed and validated orders")
@dlt.expect_or_drop("valid_order_id", "order_id IS NOT NULL")
def silver_orders():
    return (dlt.read_stream("bronze_orders")
        .select(
            F.get_json_object("raw", "$.order_id").alias("order_id"),
            F.get_json_object("raw", "$.amount").cast("double").alias("amount"),
            "kafka_timestamp"))
```

### SDP Advantages for Streaming
- Managed checkpoints and state
- Built-in data quality expectations
- Automatic retry and recovery
- Multi-hop pipelines as a single unit
- Continuous mode for low-latency requirements

## Jobs Continuous Schedule + AvailableNow

For workloads that need frequent updates but not continuous processing:

1. Convert `processingTime` to `availableNow=True` in your notebook/script
2. Create a Databricks Job with a **continuous** trigger type (or a cron schedule like `*/5 * * * *` for every 5 minutes)
3. Each run processes all available data since the last checkpoint, then terminates
4. The job scheduler automatically starts the next run

This approach provides:
- Near-real-time freshness (configurable via schedule frequency)
- Cost savings (no idle compute between runs)
- Automatic retries on failure

## Continuous Streaming Disambiguation

The term "continuous" has different meanings in different contexts:

| Context | Meaning | Serverless Support |
|---------|---------|-------------------|
| `.trigger(continuous="1s")` | Spark Continuous Processing mode (low-latency, experimental) | Not supported |
| Jobs "continuous" trigger | Job scheduler restarts the task immediately after completion | Supported |
| SDP continuous mode | Pipeline runs continuously, processing new data as it arrives | Supported on serverless |

## Documentation

- Structured Streaming triggers: https://docs.databricks.com/en/structured-streaming/triggers.html
- Serverless streaming: https://docs.databricks.com/en/compute/serverless/
- Auto Loader: https://docs.databricks.com/en/ingestion/cloud-files/
- Kafka integration: https://docs.databricks.com/en/structured-streaming/kafka.html
- Spark Declarative Pipelines: https://docs.databricks.com/en/ldp/serverless
