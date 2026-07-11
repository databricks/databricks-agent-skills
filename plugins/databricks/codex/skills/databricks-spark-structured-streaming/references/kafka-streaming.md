---
name: kafka-streaming
description: Comprehensive Kafka streaming patterns including Kafka-to-Delta ingestion, Kafka-to-Kafka pipelines, and Real-Time Mode for sub-second latency. Use when building Kafka ingestion pipelines, implementing event enrichment, format transformation, or low-latency streaming workloads.
---

# Kafka Streaming Patterns

Comprehensive guide to Kafka streaming with Spark Structured Streaming: ingestion to Delta, Kafka-to-Kafka pipelines, and Real-Time Mode for sub-second latency.

## Quick Start

### Kafka to Delta

```python
from pyspark.sql.functions import col, from_json
from pyspark.sql.types import StructType, StructField, StringType, TimestampType

# Schema for the JSON payload carried in the Kafka value column.
# Reused across the patterns below as `event_schema`.
event_schema = StructType([
    StructField("event_id", StringType()),
    StructField("user_id", StringType()),
    StructField("event_type", StringType()),
    StructField("timestamp", TimestampType()),
])

# Read from Kafka
df = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker1:9092,broker2:9092")
    .option("subscribe", "topic_name")
    .option("startingOffsets", "earliest")
    .option("minPartitions", "6")  # Match Kafka partitions
    .load()
)

# Parse JSON value
df_parsed = df.select(
    col("key").cast("string"),
    from_json(col("value").cast("string"), event_schema).alias("data"),
    col("topic"), col("partition"), col("offset"),
    col("timestamp").alias("kafka_timestamp")
).select("key", "data.*", "topic", "partition", "offset", "kafka_timestamp")

# Write to Delta
df_parsed.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/kafka_stream") \
    .trigger(processingTime="30 seconds") \
    .start("/delta/bronze_events")
```

### Kafka to Kafka

```python
from pyspark.sql.functions import col, from_json, to_json, struct, current_timestamp

# Read from source Kafka
source_df = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker1:9092")
    .option("subscribe", "input-events")
    .option("startingOffsets", "latest")
    .load()
)

# Parse and transform
parsed_df = source_df.select(
    col("key").cast("string"),
    from_json(col("value").cast("string"), event_schema).alias("data"),
    col("topic").alias("source_topic")
).select("key", "data.*", "source_topic")

# Transform events
enriched_df = parsed_df.withColumn(
    "processed_at", current_timestamp()
).withColumn(
    "value", to_json(struct("event_id", "user_id", "event_type", "processed_at"))
)

# Write to output Kafka topic
enriched_df.select("key", "value").writeStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "broker1:9092") \
    .option("topic", "output-events") \
    .option("checkpointLocation", "/checkpoints/kafka-to-kafka") \
    .trigger(processingTime="30 seconds") \
    .start()
```

## Common Patterns

### Pattern 1: Bronze Layer Ingestion (Kafka to Delta)

Minimal transformation, preserve original columns:

```python
# Best practice: Minimal transformation, preserve original columns
# Why: Kafka retention is expensive (default 7 days)
# Delta provides permanent storage with full history

df_bronze = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", servers)
    .option("subscribe", topic)
    .option("startingOffsets", "earliest")
    .option("maxOffsetsPerTrigger", 10000)  # Control batch size
    .load()
    .select(
        col("key").cast("string"),
        col("value").cast("string"),
        col("topic"), col("partition"), col("offset"),
        col("timestamp").alias("kafka_timestamp"),
        current_timestamp().alias("ingestion_timestamp")
    )
)

df_bronze.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/bronze_events") \
    .trigger(processingTime="30 seconds") \
    .start("/delta/bronze_events")
```

### Pattern 2: Scheduled Streaming (Cost-Optimized)

Run periodically instead of continuously:

```python
# Run every 4 hours, not continuously
# Same code, just change trigger in job scheduler

df_bronze.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/bronze_events") \
    .trigger(availableNow=True) \
    .start("/delta/bronze_events")  # Process all available, then stop

# In Databricks Jobs:
# - Schedule: Every 4 hours
# - Cluster: Fixed size (no autoscaling for streaming)
# - Same streaming code, batch-style execution
```

### Pattern 3: Real-Time Mode (Sub-Second Latency)

RTM is GA and is the default for any kafka→kafka pipeline with sub-second SLAs. DBR 16.4 LTS minimum, DBR 18.1+ recommended. Full setup, slot math, supported operations, and error classes in [real-time-mode.md](real-time-mode.md).

```python
query = (enriched_df
    .select(col("key"), col("value"))
    .writeStream
    .format("kafka")
    .option("kafka.bootstrap.servers", brokers)
    .option("topic", "output-events")
    .outputMode("update")         # RTM only supports update mode
    .trigger(realTime="5 minutes")  # long-running batch duration; see real-time-mode.md
    .option("checkpointLocation", checkpoint_path)
    .start()
)
```

### Pattern 4: Event Enrichment (Kafka to Kafka with Delta)

Enrich events with dimension data:

```python
from pyspark.sql.functions import broadcast, col, to_json, struct

# Read reference data (Delta table - auto-refreshed each microbatch)
user_dim = spark.table("users.dimension")

# Stream-static join for enrichment
enriched = (parsed_df
    .join(broadcast(user_dim), "user_id", "left")     # broadcast() required: RTM only supports broadcast stream-static joins
    .withColumn("enriched_value", to_json(struct(
        col("event_id"),
        col("user_id"),
        col("user_name"),  # From dimension table
        col("user_segment"),  # From dimension table
        col("event_type"),
        col("timestamp")
    )))
)

# Write enriched events to Kafka
enriched.select(col("key"), col("enriched_value").alias("value")).writeStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", brokers) \
    .option("topic", "enriched-events") \
    .outputMode("update") \
    .trigger(realTime="5 minutes") \
    .option("checkpointLocation", "/checkpoints/enrichment") \
    .start()
```

### Pattern 5: Multi-Topic Routing

Route events to different Kafka topics. This uses `foreachBatch`, which is **not available in RTM** (`STREAMING_REAL_TIME_MODE.OPERATOR_OR_SINK_NOT_IN_ALLOWLIST` if you try). Use `processingTime` triggers and accept the micro-batch latency floor; if you need sub-second routing, see the RTM-compatible alternatives below the example.

```python
def route_events(batch_df, batch_id):
    """Route events to different Kafka topics"""
    
    # High priority → urgent topic
    high_priority = batch_df.filter(col("priority") == "high")
    if high_priority.count() > 0:
        high_priority.select("key", "value").write \
            .format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("topic", "urgent-events") \
            .save()
    
    # Errors → DLQ topic
    errors = batch_df.filter(col("event_type") == "error")
    if errors.count() > 0:
        errors.select("key", "value").write \
            .format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("topic", "error-events-dlq") \
            .save()
    
    # All events → standard topic
    batch_df.select("key", "value").write \
        .format("kafka") \
        .option("kafka.bootstrap.servers", brokers) \
        .option("topic", "standard-events") \
        .save()

parsed_df.writeStream \
    .foreachBatch(route_events) \
    .trigger(processingTime="30 seconds") \
    .option("checkpointLocation", "/checkpoints/routing") \
    .start()
```

**RTM-compatible alternative for sub-second routing:** run one RTM query per output topic, each with its own filter and Kafka sink. Costs more cluster slots (one set of source partitions per query) but stays in RTM. See [multi-sink-writes.md](multi-sink-writes.md) for the multi-sink trade-offs.

### Pattern 6: Schema Validation with DLQ

Validate schema and route invalid records. Like Pattern 5, this uses `foreachBatch` and is therefore **not RTM-compatible**. For an RTM equivalent, replace the `foreachBatch` with two parallel `writeStream`s — one filtering to valid rows and writing to the main topic, one filtering to invalid rows and writing to the DLQ topic — both with `trigger(realTime="...")`.

```python
from pyspark.sql.functions import from_json, col, lit, to_json, struct, current_timestamp
from pyspark.sql.types import StructType, StructField, StringType

# Strict schema used to validate the payload; from_json returns null for records
# that don't conform, which lets us split valid vs invalid below.
validated_schema = StructType([
    StructField("event_id", StringType(), nullable=False),
    StructField("event_type", StringType(), nullable=False),
])

def validate_and_route(batch_df, batch_id):
    """Validate schema, route bad records to DLQ"""
    
    # Try to parse with strict schema
    parsed = batch_df.withColumn(
        "parsed",
        from_json(col("value").cast("string"), validated_schema)
    )
    
    # Valid records
    valid = parsed.filter(col("parsed").isNotNull()).select("key", "value")
    
    # Invalid records → DLQ
    invalid = parsed.filter(col("parsed").isNull()).select(
        col("key"),
        to_json(struct(
            col("value"),
            lit("SCHEMA_VALIDATION_FAILED").alias("dlq_reason"),
            current_timestamp().alias("dlq_timestamp")
        )).alias("value")
    )
    
    # Write valid to main topic
    if valid.count() > 0:
        valid.write.format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("topic", "valid-events") \
            .save()
    
    # Write invalid to DLQ
    if invalid.count() > 0:
        invalid.write.format("kafka") \
            .option("kafka.bootstrap.servers", brokers) \
            .option("topic", "dlq-events") \
            .save()

source_df.writeStream \
    .foreachBatch(validate_and_route) \
    .trigger(processingTime="30 seconds") \
    .option("checkpointLocation", "/checkpoints/validation") \
    .start()
```

## Configuration

### Consumer Options (Reading from Kafka)

```python
(spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "host1:9092,host2:9092")
    .option("subscribe", "source-topic")
    .option("startingOffsets", "latest")  # latest, earliest, or specific JSON
    .option("maxOffsetsPerTrigger", "10000")  # Control batch size
    .option("minPartitions", "6")  # Match Kafka partitions
    .option("kafka.auto.offset.reset", "latest")
    .option("kafka.enable.auto.commit", "false")  # Spark manages offsets
    .load()
)
```

### Producer Options (Writing to Kafka)

```python
(df
    .select("key", "value")
    .writeStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "host1:9092,host2:9092")
    .option("topic", "target-topic")
    .option("kafka.acks", "all")  # Durability: all, 1, 0
    .option("kafka.retries", "3")
    .option("kafka.batch.size", "16384")
    .option("kafka.linger.ms", "5")
    .option("kafka.compression.type", "lz4")  # lz4, snappy, gzip
    .option("checkpointLocation", checkpoint_path)
    .start()
)
```

### Security (SASL/SSL)

**Recommended: Unity Catalog service credentials (DBR 16.1+).** Databricks
recommends authenticating to Kafka with a Unity Catalog service credential —
no credentials or JAAS strings in code at all:

```python
kafka_options = {
    "kafka.bootstrap.servers": brokers,
    "subscribe": source_topic,
    "databricks.serviceCredential": "<service-credential-name>",
}

df = spark.readStream.format("kafka").options(**kafka_options).load()
```

When using a service credential, do NOT set `kafka.sasl.mechanism`,
`kafka.sasl.jaas.config`, or `kafka.security.protocol` — Databricks
configures these for you.

**SASL/PLAIN** — store credentials in Databricks secrets rather than including
them directly in your code. Note the `kafkashaded.` class-name prefix:
Databricks bundles shaded Kafka client libraries, and unshaded class names in
`kafka.sasl.jaas.config` fail with `RESTRICTED_STREAMING_OPTION_PERMISSION_ENFORCED`.

```python
# Source credentials from Databricks secrets, never hardcode them.
kafka_username = dbutils.secrets.get("kafka-scope", "username")
kafka_password = dbutils.secrets.get("kafka-scope", "password")

df.writeStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", brokers) \
    .option("topic", target_topic) \
    .option("kafka.security.protocol", "SASL_SSL") \
    .option("kafka.sasl.mechanism", "PLAIN") \
    .option("kafka.sasl.jaas.config",
            f'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required username="{kafka_username}" password="{kafka_password}";') \
    .option("checkpointLocation", checkpoint_path) \
    .start()
```

## Performance Tuning

| Parameter | Recommendation | Why |
|-----------|---------------|-----|
| minPartitions | Match Kafka partitions | Optimal parallelism |
| maxOffsetsPerTrigger | 10,000-100,000 | Balance latency vs throughput |
| trigger interval | Business SLA / 3 | Recovery time buffer |
| RTM | Default for kafka→kafka pipelines; required when sub-second E2E latency matters | Micro-batch is more cost-effective for second-or-longer SLAs and for stateful workloads RTM doesn't support |

## Monitoring

### Key Metrics

```python
# Programmatic monitoring
for stream in spark.streams.active:
    progress = stream.lastProgress
    if progress:
        print(f"Input rate: {progress.get('inputRowsPerSecond', 0)} rows/sec")
        print(f"Processing rate: {progress.get('processedRowsPerSecond', 0)} rows/sec")
        
        # Kafka-specific metrics
        sources = progress.get("sources", [])
        for source in sources:
            end_offset = source.get("endOffset", {})
            latest_offset = source.get("latestOffset", {})
            
            # Calculate lag per partition
            for topic, partitions in end_offset.items():
                for partition, end in partitions.items():
                    latest = latest_offset.get(topic, {}).get(partition, end)
                    lag = int(latest) - int(end)
                    print(f"Topic {topic}, Partition {partition}: Lag = {lag}")
```

### Spark UI Checks

- **Input Rate vs Processing Rate**: Processing must be > Input
- **Max Offsets Behind Latest**: Should be consistent or dropping
- **Batch Duration**: Should be < trigger interval

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **No data being read** | `startingOffsets` default is "latest" | Use "earliest" for existing data |
| **High latency** | Micro-batch overhead | Use RTM (`trigger(realTime="5 minutes")`) — see [real-time-mode.md](real-time-mode.md) |
| **Consumer lag** | Processing < Input rate | Scale cluster; reduce maxOffsetsPerTrigger |
| **Duplicate messages** | Exactly-once not configured | Enable idempotent producer (acks=all) |
| **Falling behind** | Processing < Input rate | Increase cluster size |
| **Can't use autoscaling** | Streaming requirement | Use fixed-size clusters |

## Production Checklist

- [ ] Checkpoint location is persistent (UC volumes, not DBFS)
- [ ] Unique checkpoint per pipeline
- [ ] Fixed-size cluster (no autoscaling for streaming/RTM)
- [ ] RTM enabled for kafka→kafka pipelines and any workload needing sub-second E2E latency
- [ ] Consumer lag monitored and alerts configured
- [ ] Producer acks=all for durability
- [ ] Schema validation with DLQ configured
- [ ] Security (SASL/SSL) configured for production
- [ ] Exactly-once semantics verified

## Related Skills

- `stream-static-joins` - Enrichment patterns with Delta tables
- `stream-stream-joins` - Event correlation across Kafka topics
- `checkpoint-best-practices` - Checkpoint configuration
- `trigger-tuning` - Trigger configuration and RTM setup
