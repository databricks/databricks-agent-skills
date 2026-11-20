# Kafka Streaming - SQL

Ingesting data from Apache Kafka using SQL in Spark Declarative Pipelines.

See also: **[Authentication](kafka-auth-sql.md)** | **[Deserialization (JSON, Avro)](deserialization-sql.md)**

---

## Base Reader Pattern

Use this as the starting point for SQL Kafka sources. The sections below show
only the `read_kafka` arguments that differ for topic selection, batch reads,
authentication, or payload parsing.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_kafka_events AS
SELECT
  CAST(key AS STRING) AS event_key,
  CAST(value AS STRING) AS event_value,
  topic,
  partition,
  offset,
  timestamp AS kafka_timestamp,
  current_timestamp() AS _ingested_at
FROM STREAM read_kafka(
  bootstrapServers => '${kafka_brokers}',
  subscribe => 'events-topic',
  serviceCredential => '${kafka_credential}',
  startingOffsets => 'earliest',    -- Use 'latest' to skip historical data
  failOnDataLoss => 'false'
);
```

---

## Pipeline Parameters

`${parameter_name}` substitutes pipeline configuration parameters — key-value pairs set in the pipeline settings UI or API. They are resolved at runtime, keeping environment-specific values (broker addresses, credential names) out of notebook code.

```sql
bootstrapServers => '${kafka_brokers}'
serviceCredential => '${kafka_credential}'
```

---

## Kafka Row Schema

`read_kafka` returns these columns:

| Column          | Type                                        | Notes                                                    |
| --------------- | ------------------------------------------- | -------------------------------------------------------- |
| `key`           | `BINARY`                                    | Cast to STRING if key is text                            |
| `value`         | `BINARY NOT NULL`                           | Cast to STRING for JSON; keep binary for Avro            |
| `topic`         | `STRING NOT NULL`                           | Source topic name                                        |
| `partition`     | `INT NOT NULL`                              | Partition ID                                             |
| `offset`        | `BIGINT NOT NULL`                           | Offset within partition                                  |
| `timestamp`     | `TIMESTAMP NOT NULL`                        | Record timestamp                                         |
| `timestampType` | `INTEGER NOT NULL`                          | 0 = CreateTime, 1 = LogAppendTime                        |
| `headers`       | `ARRAY<STRUCT<key: STRING, VALUE: BINARY>>` | Only present when `includeHeaders => 'true'`             |

---

## Configuration Options

| Option                                        | Description                                                             | Example                               |
| --------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------- |
| `bootstrapServers`                            | Kafka broker addresses (required)                                       | `'broker1:9092,broker2:9092'`         |
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
| `serviceCredential`                           | Unity Catalog service credential name (requires DBR 16.1+)              | `'my-credential'`                     |
| `kafka.ssl.endpoint.identification.algorithm` | SSL hostname verification (prevents MITM attacks)                       | `'https'`                             |
| `kafka.request.timeout.ms`                    | Request timeout                                                         | `'60000'`                             |
| `kafka.session.timeout.ms`                    | Consumer session timeout (controls rebalancing)                         | `'30000'`                             |
| `kafka.group.id`                              | Explicit consumer group ID (use with caution — see warning below)       | `'my-consumer-group'`                 |
| `groupIdPrefix`                               | Prefix for auto-generated consumer group IDs (default: `spark-kafka-source`) | `'my-pipeline'`                  |

> **Note:** `subscribe`, `subscribePattern`, and `assign` are mutually exclusive — choose exactly one.

> **Warning — `kafka.group.id`:** By default, each query generates a unique group ID, ensuring its own consumer group with no interference from other consumers and full access to all subscribed partitions. Only set `kafka.group.id` in specific scenarios such as Kafka group-based authorization. Concurrently running queries or sources sharing the same group ID will interfere with each other, each reading only a subset of the data — this can also occur when queries are restarted in quick succession. If you must set this option, set `kafka.session.timeout.ms` to a very small value to minimize interference. Setting `kafka.group.id` causes `groupIdPrefix` to be ignored.

---

## Topic Selection

`subscribe`, `subscribePattern`, and `assign` are mutually exclusive. Start
from the base `read_kafka` call and use exactly one of these arguments.

```sql
subscribe => 'orders,customers,products'
```

```sql
subscribePattern => 'prod-events-.*'
```

```sql
assign => '{"orders":[0,1,2],"customers":[0,1]}'
```

### Route by Topic

```sql
-- Bronze: all events
CREATE OR REFRESH STREAMING TABLE bronze_all_events AS
SELECT * FROM STREAM read_kafka(
  bootstrapServers => '${kafka_brokers}',
  subscribe => 'orders,customers',
  startingOffsets => 'earliest'
);

-- Silver: orders only
CREATE OR REFRESH STREAMING TABLE silver_orders AS
SELECT * FROM STREAM bronze_all_events
WHERE topic = 'orders';

-- Silver: customers only
CREATE OR REFRESH STREAMING TABLE silver_customers AS
SELECT * FROM STREAM bronze_all_events
WHERE topic = 'customers';
```

---

## Batch Read

Use `read_kafka` without `STREAM` for one-time historical reads. Compared with
the base streaming reader, remove `STREAM` and set both `startingOffsets` and
`endingOffsets`.

```sql
SELECT
  CAST(key AS STRING) AS event_key,
  CAST(value AS STRING) AS event_value,
  topic, partition, offset,
  timestamp AS kafka_timestamp
FROM read_kafka(
  -- Same bootstrapServers / subscribe / serviceCredential arguments as the base reader
  startingOffsets => 'earliest',
  endingOffsets => 'latest'
);
```

`endingOffsets` accepts `'latest'` or a JSON offset string: `'{"topicA":{"0":100,"1":200}}'`. Use `-1` within JSON to mean latest for that partition.

---

## Monitoring

The Kafka source exposes streaming metrics via pipeline metrics:

| Metric                            | Description                                     |
| --------------------------------- | ----------------------------------------------- |
| `avgOffsetsBehindLatest`          | Average offset lag across subscribed partitions |
| `maxOffsetsBehindLatest`          | Maximum offset lag across partitions            |
| `minOffsetsBehindLatest`          | Minimum offset lag across partitions            |
| `estimatedTotalBytesBehindLatest` | Estimated remaining bytes to consume            |

Configure the bytes estimate window (Databricks Runtime 17.1+):

```sql
FROM STREAM read_kafka(
  bootstrapServers => '${kafka_brokers}',
  subscribe => 'events',
  bytesEstimateWindowLength => '10m'
)
```

---

## Best Practices

1. **Add ingestion metadata:**

```sql
SELECT
  *,
  current_timestamp() AS _ingested_at,
  topic AS _source_topic,
  CONCAT(topic, '-', partition, '-', offset) AS _message_id
FROM STREAM read_kafka(...)
```

2. **Parse in silver layer** — Keep bronze raw (binary `value`) for reprocessing with different schemas

3. **Use schema evolution** — Use `from_json` with `schemaLocationKey` instead of hard-coded schemas to handle field additions automatically

4. **Monitor lag** — Check offset progress in pipeline metrics; set `maxOffsetsPerTrigger` to pace high-volume topics

---

## Common Issues

| Issue                      | Solution                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| Connection refused         | Verify `bootstrapServers` and network access / VPC peering                                 |
| Authentication failed      | See `kafka-auth-sql.md`; use shaded class names (e.g., `kafkashaded.`)                     |
| No data received           | Verify topic exists and has data; check `startingOffsets`                                  |
| `Unable to find Kafka source` | Check the source is `read_kafka`; the pipeline runtime includes the Kafka client libraries |
| `from_json` returns NULL | Payload doesn't match the schema; route rows where the parsed struct IS NULL to a quarantine table |
| Lag increasing             | Set `maxOffsetsPerTrigger` to pace ingestion; check downstream processing bottlenecks      |
| `failOnDataLoss` error after a pause | Kafka retention expired the checkpointed offsets. Set `failOnDataLoss` to `'false'` to skip the gap, or full refresh the table |
| DBR version incompatibility | `serviceCredential` requires DBR 16.1+ (AWS/Azure) or 18.0+ (GCP); `from_avro` SQL requires DBR 16.0+ |

---

## Further Reading

- [`read_kafka` reference](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_kafka)
- Kinesis: [kinesis-streaming-sql.md](kinesis-streaming-sql.md). Pub/Sub and Pulsar use the `read_pubsub` / `read_pulsar` functions with the same overall shape.
- Writing to Kafka: sinks are Python only; see [sink-python.md](sink-python.md).
- [Connect to Apache Kafka — Databricks docs](https://docs.databricks.com/aws/en/connect/streaming/kafka/)
- [Kafka authentication — Databricks docs](https://docs.databricks.com/aws/en/connect/streaming/kafka/authentication)
- [Full stream reader options reference — spark/api-options#stream-reader-kafka](https://docs.databricks.com/aws/en/spark/api-options#stream-reader-kafka)
