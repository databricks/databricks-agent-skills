# Kafka Ingestion

Ingest from Apache Kafka into streaming tables. Examples in both Python (`spark.readStream.format("kafka")`) and SQL (`read_kafka()`). Same pattern works for Azure Event Hubs via the Kafka protocol — see [Event Hubs](#event-hubs) below.

For Kinesis, Pub/Sub, and Pulsar, use the analogous `read_kinesis`, `read_pubsub`, `read_pulsar` functions / Spark formats — same overall shape as below.

---

## Basic Read

Kafka returns rows with binary `key` and `value` columns plus `topic`, `partition`, `offset`, `timestamp`. Cast to strings (or `from_json` / `from_avro`) downstream.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_kafka_events AS
SELECT CAST(key AS STRING)   AS event_key,
       CAST(value AS STRING) AS event_value,
       topic, partition, offset,
       timestamp                  AS kafka_timestamp,
       current_timestamp()        AS _ingested_at
FROM read_kafka(
  bootstrapServers => '${kafka_brokers}',
  subscribe        => 'events-topic',
  startingOffsets  => 'latest'
);
```

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(name="bronze_kafka_events")
def bronze_kafka_events():
    kafka_brokers = spark.conf.get("kafka_brokers")
    return (
        spark.readStream.format("kafka")
             .option("kafka.bootstrap.servers", kafka_brokers)
             .option("subscribe", "events-topic")
             .option("startingOffsets", "latest")
             .load()
             .selectExpr(
                 "CAST(key AS STRING) AS event_key",
                 "CAST(value AS STRING) AS event_value",
                 "topic", "partition", "offset",
                 "timestamp AS kafka_timestamp")
             .withColumn("_ingested_at", F.current_timestamp())
    )
```

**Documentation**: [`read_kafka` function reference](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_kafka).

### Common options

| Option | Purpose |
|--------|---------|
| `bootstrapServers` / `kafka.bootstrap.servers` | Broker list. Use a pipeline config var, not a literal. |
| `subscribe` | Topic name or comma-separated list. |
| `subscribePattern` | Regex over topic names (alternative to `subscribe`). |
| `startingOffsets` | `"latest"`, `"earliest"`, or JSON per-partition offsets. |
| `endingOffsets` | Only for batch reads — ignored in streaming. |
| `maxOffsetsPerTrigger` | Throttle per micro-batch. |
| `failOnDataLoss` | Default `true`. Set `false` only when you accept gaps. |

---

## Parse JSON Payloads

`value` is a binary/string blob. Extract structured columns with `from_json` (SQL/Python) against an explicit schema.

```sql
CREATE OR REFRESH STREAMING TABLE silver_events AS
SELECT data.*, kafka_timestamp, _ingested_at
FROM (
  SELECT from_json(event_value,
                   'event_id STRING, event_type STRING, timestamp TIMESTAMP') AS data,
         kafka_timestamp, _ingested_at
  FROM STREAM bronze_kafka_events
);
```

```python
from pyspark.sql.types import StructType, StructField, StringType, TimestampType

event_schema = StructType([
    StructField("event_id",   StringType()),
    StructField("event_type", StringType()),
    StructField("timestamp",  TimestampType()),
])

@dp.table(name="silver_events")
def silver_events():
    return (
        spark.readStream.table("bronze_kafka_events")
             .withColumn("data", F.from_json("event_value", event_schema))
             .select("data.*", "kafka_timestamp", "_ingested_at")
    )
```

**Schema hygiene**: keep the schema in code (Python `StructType` or SQL string), versioned alongside the pipeline. Inferring JSON schema from a streaming Kafka source is not supported — the schema must be explicit.

For Avro / Protobuf payloads, swap `from_json` for `from_avro` / `from_protobuf` (with Schema Registry config). Same overall pattern.

---

## Authentication

### Databricks Secrets

Don't put credentials in code or pipeline config literally. Use `{{secrets/scope/key}}` interpolation.

```sql
-- SASL/PLAIN
FROM read_kafka(
  bootstrapServers          => '${kafka_brokers}',
  subscribe                 => 'events-topic',
  `kafka.security.protocol` => 'SASL_SSL',
  `kafka.sasl.mechanism`    => 'PLAIN',
  `kafka.sasl.jaas.config`  =>
    'org.apache.kafka.common.security.plain.PlainLoginModule required ' ||
    'username="{{secrets/kafka/username}}" ' ||
    'password="{{secrets/kafka/password}}";'
);
```

```python
@dp.table(name="bronze_kafka_authenticated")
def bronze_kafka_authenticated():
    username = dbutils.secrets.get(scope="kafka", key="username")
    password = dbutils.secrets.get(scope="kafka", key="password")
    return (
        spark.readStream.format("kafka")
             .option("kafka.bootstrap.servers", spark.conf.get("kafka_brokers"))
             .option("subscribe", "events-topic")
             .option("kafka.security.protocol", "SASL_SSL")
             .option("kafka.sasl.mechanism", "PLAIN")
             .option("kafka.sasl.jaas.config",
                 f'org.apache.kafka.common.security.plain.PlainLoginModule required '
                 f'username="{username}" password="{password}";')
             .load()
    )
```

### TLS / mTLS

For mTLS, additional `kafka.ssl.truststore.*` and `kafka.ssl.keystore.*` options are required. Truststore/keystore files typically come from Unity Catalog volumes; pass file paths via pipeline config.

---

## Event Hubs (via Kafka protocol)

Azure Event Hubs speaks the Kafka protocol on port 9093. Use the same Kafka source — only the connection string changes.

```sql
FROM read_kafka(
  bootstrapServers          => '<namespace>.servicebus.windows.net:9093',
  subscribe                 => '<event-hub-name>',
  `kafka.security.protocol` => 'SASL_SSL',
  `kafka.sasl.mechanism`    => 'PLAIN',
  `kafka.sasl.jaas.config`  =>
    'org.apache.kafka.common.security.plain.PlainLoginModule required ' ||
    'username="$ConnectionString" ' ||
    'password="{{secrets/eventhub/connection-string}}";'
);
```

```python
@dp.table(name="bronze_eventhub_events")
def bronze_eventhub_events():
    conn_str = dbutils.secrets.get(scope="eventhub", key="connection-string")
    return (
        spark.readStream.format("kafka")
             .option("kafka.bootstrap.servers", "<namespace>.servicebus.windows.net:9093")
             .option("subscribe", "<event-hub-name>")
             .option("kafka.security.protocol", "SASL_SSL")
             .option("kafka.sasl.mechanism", "PLAIN")
             .option("kafka.sasl.jaas.config",
                 'org.apache.kafka.common.security.plain.PlainLoginModule required '
                 f'username="$ConnectionString" password="{conn_str}";')
             .load()
    )
```

The username is the literal string `$ConnectionString` and the password is the namespace-level or entity-level connection string (with `SharedAccessKey=…`).

---

## Pipeline Configuration

Pass Kafka brokers, topics, and consumer-group identity through pipeline configuration so dev/prod can differ without code changes.

```yaml
# In resources/<name>.pipeline.yml
resources:
  pipelines:
    my_pipeline:
      ...
      configuration:
        kafka_brokers: "broker-1:9092,broker-2:9092,broker-3:9092"
        kafka_topic:   "events-topic"
```

Read in code with `spark.conf.get("kafka_brokers")` (Python) or `${kafka_brokers}` (SQL).

---

## Writing to Kafka (Sinks)

Sinks are Python-only. Write a payload to Kafka by creating a sink with `format="kafka"` and appending via `@dp.append_flow`. The `value` column is mandatory — use `to_json(struct(*))` to serialize the row. See [sink.md](sink.md) and [sink-python.md](sink-python.md).

---

## Best Practices

1. **Always cast `value` to a usable type** (`STRING`, `BINARY`) and parse with `from_json` / `from_avro` against an explicit schema. Don't carry `value` as bytes downstream.
2. **Add `_ingested_at`** for lag monitoring — see [streaming-patterns.md](streaming-patterns.md#monitoring-lag).
3. **Tune `maxOffsetsPerTrigger`** if downstream operations are bottlenecking.
4. **Don't set `failOnDataLoss = false`** unless you genuinely accept gaps. The default protects against retention-window data loss.
5. **Use the parent `databricks-core` skill** for secret-scope management.

---

## Common Issues

| Issue | Fix |
|-------|-----|
| `Unable to find Kafka source` | Confirm `format("kafka")` (Python) / `read_kafka` (SQL) and that the cluster has Kafka client libraries (default on serverless / DBR ML / standard runtimes). |
| `Connection refused` / SSL handshake | Verify `bootstrapServers` reachability and `kafka.security.protocol`. |
| Schema for `value` doesn't match | `from_json` returns `NULL` on parse failure — add a quarantine fanout on `data IS NULL` similar to [rescue-data quarantine](streaming-patterns.md#rescue-data-quarantine). |
| Increasing consumer lag | Bottleneck downstream — see [streaming-patterns.md](streaming-patterns.md#monitoring-lag) for lag table; tune cluster size / `maxOffsetsPerTrigger`. |
| `failOnDataLoss` error after a long pause | Kafka topic retention expired the offset checkpoint. Reset the pipeline (full refresh) or start from `earliest`. |
