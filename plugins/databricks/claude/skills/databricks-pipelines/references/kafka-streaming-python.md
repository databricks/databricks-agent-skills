# Kafka Streaming - Python

Ingesting data from Apache Kafka using Python in Spark Declarative Pipelines.

See also: **[Authentication](kafka-auth-python.md)** | **[Payload parsing without Schema Registry](deserialization-python.md)** | **[Confluent Schema Registry](kafka-deserialization-python.md)**

---

## Base Reader Pattern

Use this as the starting point for Kafka sources. The sections below show only
the options that differ for topic selection, batch reads, authentication, or
payload parsing.

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.dataframe import DataFrame

@dp.table(name="bronze_kafka_events")
def bronze_kafka_events() -> DataFrame:
    kafka_brokers = spark.conf.get("kafka_brokers")
    kafka_credential = spark.conf.get("kafka_credential")
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", kafka_brokers)
        .option("subscribe", "events-topic")        # Or subscribePattern / assign
        .option("databricks.serviceCredential", kafka_credential)
        .option("startingOffsets", "earliest")      # Use 'latest' to skip historical data
        .option("failOnDataLoss", "false")         # Prevent failure if Kafka retention expires
        .load()
        .selectExpr(
            "CAST(key AS STRING) AS event_key",
            "CAST(value AS STRING) AS event_value",
            "topic",
            "partition",
            "offset",
            "timestamp AS kafka_timestamp",        # TimestampType (millisecond precision)
            "current_timestamp() AS _ingested_at"
        )
    )
```

---

## Pipeline Parameters

`spark.conf.get()` reads from the pipeline's configuration parameters — key-value pairs set in the pipeline settings UI or API. They are injected into the Spark session at runtime, keeping environment-specific values (broker addresses, credential names) out of notebook code.

```python
kafka_brokers = spark.conf.get("kafka_brokers")
kafka_credential = spark.conf.get("kafka_credential")
```

---

## Kafka Row Schema

The `format("kafka")` reader returns these columns:

| Column          | Type                                        | Notes                                                    |
| --------------- | ------------------------------------------- | -------------------------------------------------------- |
| `key`           | `BINARY`                                    | Cast to STRING if key is text                            |
| `value`         | `BINARY`                                    | Cast to STRING for JSON; keep binary for Avro/Protobuf   |
| `topic`         | `STRING`                                    | Source topic name                                        |
| `partition`     | `INT`                                       | Partition ID                                             |
| `offset`        | `LONG`                                      | Offset within partition                                  |
| `timestamp`     | `TIMESTAMP`                                 | Record timestamp (millisecond precision)                 |
| `timestampType` | `INT`                                       | 0 = CreateTime, 1 = LogAppendTime                        |
| `headers`       | `ARRAY<STRUCT<key: STRING, value: BINARY>>` | Only present when `includeHeaders` option is `'true'`    |

---

## Configuration Options

| Option                                        | Description                                                             | Example                               |
| --------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------- |
| `kafka.bootstrap.servers`                     | Kafka broker addresses (required)                                       | `'broker1:9092,broker2:9092'`         |
| `subscribe`                                   | Topic(s) to subscribe (comma-separated)                                 | `'topic1'` or `'topic1,topic2'`       |
| `subscribePattern`                            | Topic pattern (Java regex)                                              | `'events-.*'`                         |
| `assign`                                      | Specific topic-partitions as JSON                                       | `'{"topicA":[0,1],"topicB":[0]}'`     |
| `startingOffsets`                             | Where to start reading (`earliest` recommended; Spark streaming default is `latest`) | `'earliest'`, `'latest'` |
| `startingOffsetsByTimestamp`                  | Per-partition starting timestamps in ms as JSON                         | `'{"topicA":{"0":1620000000000}}'`    |
| `endingOffsets`                               | Stopping point for batch reads only (default: `latest`)                 | `'latest'` or JSON offset string      |
| `failOnDataLoss`                              | Default `true`. `'false'` keeps the stream running when Kafka retention expired unread offsets, skipping that data; keep `true` when gaps are not acceptable | `'false'`                             |
| `maxOffsetsPerTrigger`                        | Max offsets processed per trigger — primary throughput control knob     | `'100000'`                            |
| `minOffsetsPerTrigger`                        | Min offsets required before a trigger fires                             | `'1000'`                              |
| `maxTriggerDelay`                             | Max time to wait before firing a trigger (default: `15m`)               | `'5m'`                                |
| `includeHeaders`                              | Include Kafka `headers` column in output (default: `false`)             | `'true'`                              |
| `databricks.serviceCredential`                | Unity Catalog service credential name (requires DBR 16.1+)              | `'my-credential'`                     |
| `kafka.ssl.endpoint.identification.algorithm` | SSL hostname verification (prevents MITM attacks)                       | `'https'`                             |
| `kafka.request.timeout.ms`                    | Request timeout                                                         | `'60000'`                             |
| `kafka.session.timeout.ms`                    | Consumer session timeout (controls rebalancing)                         | `'30000'`                             |
| `kafka.group.id`                              | Explicit consumer group ID (use with caution — see warning below)       | `'my-consumer-group'`                 |
| `groupIdPrefix`                               | Prefix for auto-generated consumer group IDs (default: `spark-kafka-source`) | `'my-pipeline'`                  |
| `minPartitions`                               | Minimum Spark partitions for parallel consumption                       | `'10'`                                |

> **Note:** `subscribe`, `subscribePattern`, and `assign` are mutually exclusive — choose exactly one.

> **Warning — `kafka.group.id`:** By default, each query generates a unique group ID, ensuring its own consumer group with no interference from other consumers and full access to all subscribed partitions. Only set `kafka.group.id` in specific scenarios such as Kafka group-based authorization. Concurrently running queries or sources sharing the same group ID will interfere with each other, each reading only a subset of the data — this can also occur when queries are restarted in quick succession. If you must set this option, set `kafka.session.timeout.ms` to a very small value to minimize interference. Setting `kafka.group.id` causes `groupIdPrefix` to be ignored.

---

## Topic Selection

`subscribe`, `subscribePattern`, and `assign` are mutually exclusive. Start
from the base reader and use exactly one of these options.

```python
.option("subscribe", "orders,customers,products")
```

```python
.option("subscribePattern", "prod-events-.*")
```

```python
.option("assign", '{"orders":[0,1,2],"customers":[0,1]}')
```

### Route by Topic

```python
@dp.table(name="bronze_all_events")
def bronze_all_events():
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", spark.conf.get("kafka_brokers"))
        .option("subscribe", "orders,customers")
        .load()
    )

@dp.table(name="silver_orders")
def silver_orders():
    return spark.readStream.table("bronze_all_events").filter(F.col("topic") == "orders")

@dp.table(name="silver_customers")
def silver_customers():
    return spark.readStream.table("bronze_all_events").filter(F.col("topic") == "customers")
```

---

## Batch Read

Use `spark.read` (not `readStream`) for one-time historical reads. Compared
with the base streaming reader, switch to `spark.read` and set both
`startingOffsets` and `endingOffsets`.

```python
# Differences from the base reader:
spark.read                                    # not spark.readStream
.option("startingOffsets", "earliest")
.option("endingOffsets", "latest")           # Required for batch reads
```

`endingOffsets` accepts `'latest'` or a JSON offset string: `'{"topicA":{"0":100,"1":200}}'`. Use `-1` within JSON to mean latest for that partition.

---

## Monitoring / Kafka Lag Metrics

The Kafka source exposes streaming metrics accessible via `StreamingQuery.lastProgress["sources"][0]["metrics"]`:

| Metric                            | Description                                     |
| --------------------------------- | ----------------------------------------------- |
| `avgOffsetsBehindLatest`          | Average offset lag across subscribed partitions |
| `maxOffsetsBehindLatest`          | Maximum offset lag across partitions            |
| `minOffsetsBehindLatest`          | Minimum offset lag across partitions            |
| `estimatedTotalBytesBehindLatest` | Estimated remaining bytes to consume            |

Configure the bytes estimate window (Databricks Runtime 17.1+):

```python
.option("bytesEstimateWindowLength", "10m")
```

---

## Common Issues

| Issue                      | Solution                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| Connection refused         | Verify `kafka.bootstrap.servers` and network access / VPC peering                          |
| Authentication failed      | See `kafka-auth-python.md`; use shaded class names (e.g., `kafkashaded.`)                  |
| No data received           | Verify topic exists; check `startingOffsets`                                               |
| `Unable to find Kafka source` | Check the source is `format("kafka")`; the pipeline runtime includes the Kafka client libraries |
| `from_json` returns NULL | Payload doesn't match the schema; route rows where the parsed struct IS NULL to a quarantine table |
| Schema mismatch            | See `deserialization-python.md` for JSON/Avro/Protobuf parsing; use `kafka-deserialization-python.md` for Confluent Schema Registry |
| Lag increasing             | Set `maxOffsetsPerTrigger` to pace ingestion; check downstream processing bottlenecks      |
| `failOnDataLoss` error after a pause | Kafka retention expired the checkpointed offsets. Set `failOnDataLoss` to `'false'` to skip the gap, or full refresh the table |
| Idempotent write error     | Set `kafka.enable.idempotence=false` for Kafka ≤ 2.8.0 without `IDEMPOTENT_WRITE` ACL     |
| DBR version incompatibility | Service credentials: DBR 16.1+ (AWS/Azure) or 18.0+ (GCP); Protobuf: DBR 12.2+; Avro SQL: DBR 16.0+ |

---

## Further Reading

- Kinesis: [kinesis-streaming-python.md](kinesis-streaming-python.md). Pub/Sub and Pulsar use `spark.readStream.format("pubsub")` / `format("pulsar")` with the same overall shape.
- Writing to Kafka: sinks are Python only; see [sink-python.md](sink-python.md).
- [Connect to Apache Kafka — Databricks docs](https://docs.databricks.com/aws/en/connect/streaming/kafka/)
- [Kafka authentication — Databricks docs](https://docs.databricks.com/aws/en/connect/streaming/kafka/authentication)
- [Full stream reader options reference — spark/api-options#stream-reader-kafka](https://docs.databricks.com/aws/en/spark/api-options#stream-reader-kafka)
