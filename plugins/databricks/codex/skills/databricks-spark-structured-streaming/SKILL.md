---
name: databricks-spark-structured-streaming
description: "Comprehensive guide to Spark Structured Streaming for production workloads. Use when building streaming pipelines, working with Kafka ingestion, implementing Real-Time Mode (RTM), configuring triggers (processingTime, availableNow), handling stateful operations with watermarks, optimizing checkpoints, performing stream-stream or stream-static joins, writing to multiple sinks, or tuning streaming cost and performance."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Spark Structured Streaming

Production-ready streaming pipelines with Spark Structured Streaming. This skill provides navigation to detailed patterns and best practices.

## Quick Start

```python
from pyspark.sql.functions import col, from_json

# Basic Kafka to Delta streaming
df = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "topic")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
)

df.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/stream") \
    .trigger(processingTime="30 seconds") \
    .start("/delta/target_table")
```

## Core Patterns

| Pattern | Description | Reference |
|---------|-------------|-----------|
| **Kafka Streaming** | Kafka to Delta, Kafka to Kafka, Real-Time Mode | See [references/kafka-streaming.md](references/kafka-streaming.md) |
| **Stream Joins** | Stream-stream joins, stream-static joins | See [references/stream-stream-joins.md](references/stream-stream-joins.md), [references/stream-static-joins.md](references/stream-static-joins.md) |
| **Multi-Sink Writes** | Write to multiple tables, parallel merges | See [references/multi-sink-writes.md](references/multi-sink-writes.md) |
| **Merge Operations** | MERGE performance, parallel merges, optimizations | See [references/merge-operations.md](references/merge-operations.md) |

## Configuration

| Topic | Description | Reference |
|-------|-------------|-----------|
| **Checkpoints** | Checkpoint management and best practices | See [references/checkpoint-best-practices.md](references/checkpoint-best-practices.md) |
| **Stateful Operations** | Watermarks, state stores, RocksDB configuration | See [references/stateful-operations.md](references/stateful-operations.md) |
| **Trigger & Cost** | Trigger selection, cost optimization, RTM | See [references/trigger-and-cost-optimization.md](references/trigger-and-cost-optimization.md) |

## Best Practices

| Topic | Description | Reference |
|-------|-------------|-----------|
| **Production Checklist** | Comprehensive best practices | See [references/streaming-best-practices.md](references/streaming-best-practices.md) |

## Production Checklist

- [ ] Checkpoint location is persistent (UC volumes, not DBFS)
- [ ] Unique checkpoint per stream
- [ ] Fixed-size cluster (no autoscaling for streaming)
- [ ] Monitoring configured (input rate, lag, batch duration)
- [ ] Exactly-once verified (txnVersion/txnAppId)
- [ ] Watermark configured for stateful operations
- [ ] Left joins for stream-static (not inner)
