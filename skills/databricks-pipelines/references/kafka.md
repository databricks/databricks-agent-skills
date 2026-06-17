# Kafka Ingestion

Ingest from Apache Kafka into a streaming table. Same shape works for Azure Event Hubs (Kafka protocol on port 9093) — only the connection string and SASL config differ.

For Kinesis, Pub/Sub, and Pulsar, use the analogous `read_kinesis` / `read_pubsub` / `read_pulsar` SQL functions or `spark.readStream.format("kinesis|pubsub|pulsar")` — same overall shape as below.

## Basic Read

Kafka returns rows with binary `key` and `value` columns plus `topic`, `partition`, `offset`, `timestamp`. Cast to `STRING`/`BINARY` and parse downstream — don't carry raw bytes.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_kafka_events AS
SELECT CAST(key AS STRING)   AS event_key,
       CAST(value AS STRING) AS event_value,
       topic, partition, offset,
       timestamp           AS kafka_timestamp,
       current_timestamp() AS _ingested_at
FROM read_kafka(
  bootstrapServers => '${kafka_brokers}',
  subscribe        => 'events-topic',
  startingOffsets  => 'latest'
);
```

Python equivalent: `spark.readStream.format("kafka").option("kafka.bootstrap.servers", spark.conf.get("kafka_brokers")).option("subscribe", "events-topic").option("startingOffsets", "latest").load().selectExpr(...)` + `.withColumn("_ingested_at", F.current_timestamp())`.

[`read_kafka` reference](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_kafka).

### Common options

| Option | Purpose |
|--------|---------|
| `bootstrapServers` / `kafka.bootstrap.servers` | Broker list. Use a pipeline config var, not a literal. |
| `subscribe` | Topic name or comma-separated list. |
| `subscribePattern` | Regex over topic names (alternative to `subscribe`). |
| `startingOffsets` | `"latest"`, `"earliest"`, or JSON per-partition offsets. |
| `endingOffsets` | Batch reads only; ignored in streaming. |
| `maxOffsetsPerTrigger` | Throttle per micro-batch. |
| `failOnDataLoss` | Default `true`. `false` only when you accept gaps. |

## Parse JSON Payloads

`value` is a blob. Extract structured columns with `from_json` against an explicit schema — JSON-schema inference from a streaming Kafka source is not supported.

```sql
CREATE OR REFRESH STREAMING TABLE silver_events AS
SELECT data.*, kafka_timestamp, _ingested_at
FROM (
  SELECT from_json(event_value,
                   'event_id STRING, event_type STRING, timestamp TIMESTAMP') AS data,
         kafka_timestamp, _ingested_at
  FROM STREAM(bronze_kafka_events)
);
```

Python: build a `StructType` and `.withColumn("data", F.from_json("event_value", event_schema)).select("data.*", ...)`. Keep the schema in code, versioned alongside the pipeline.

For Avro / Protobuf payloads, swap `from_json` for `from_avro` / `from_protobuf` (with Schema Registry config). Same overall pattern.

## Authentication

Use `{{secrets/scope/key}}` interpolation in SQL or `dbutils.secrets.get(scope, key)` in Python. Never hard-code credentials.

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

For mTLS, add `kafka.ssl.truststore.*` and `kafka.ssl.keystore.*` options pointing at files in a UC volume; pass paths via pipeline config.

## Event Hubs (via Kafka protocol)

Same Kafka source — change the connection target and auth:

```sql
bootstrapServers          => '<namespace>.servicebus.windows.net:9093',
subscribe                 => '<event-hub-name>',
`kafka.security.protocol` => 'SASL_SSL',
`kafka.sasl.mechanism`    => 'PLAIN',
`kafka.sasl.jaas.config`  =>
    'org.apache.kafka.common.security.plain.PlainLoginModule required '
    'username="$ConnectionString" '
    'password="{{secrets/eventhub/connection-string}}";'
```

The username is the literal `$ConnectionString`; the password is the namespace- or entity-level connection string (with `SharedAccessKey=...`).

## Pipeline Configuration

Pass brokers, topics, consumer-group identity through pipeline config so dev/prod differ without code changes.

```yaml
# resources/<name>.pipeline.yml
resources:
  pipelines:
    my_pipeline:
      configuration:
        kafka_brokers: "broker-1:9092,broker-2:9092,broker-3:9092"
        kafka_topic:   "events-topic"
```

Read with `spark.conf.get("kafka_brokers")` (Python) or `${kafka_brokers}` (SQL).

## Writing to Kafka (sinks)

Sinks are Python-only. Create a sink with `format="kafka"` and write via `@dp.append_flow`. The `value` column is mandatory — use `to_json(struct(*))` to serialize the row. See [sink-python.md](sink-python.md).

## Best Practices

1. Cast `value` to `STRING` / `BINARY` and parse with `from_json` / `from_avro` against an explicit schema.
2. Add `_ingested_at` — see [streaming-patterns.md#monitoring-lag](streaming-patterns.md#monitoring-lag).
3. Tune `maxOffsetsPerTrigger` if downstream operations bottleneck.
4. Don't set `failOnDataLoss = false` unless you accept retention-window gaps.

## Common Issues

| Issue | Fix |
|-------|-----|
| `Unable to find Kafka source` | Confirm `format("kafka")` / `read_kafka`; default runtimes have Kafka client libs. |
| `Connection refused` / SSL handshake | Verify `bootstrapServers` reachability and `kafka.security.protocol`. |
| `from_json` returns NULL | Schema mismatch — quarantine on `data IS NULL` (see [rescue-data quarantine](streaming-patterns.md#rescue-data-quarantine)). |
| Growing consumer lag | Downstream bottleneck — see [streaming-patterns.md#monitoring-lag](streaming-patterns.md#monitoring-lag); tune cluster size / `maxOffsetsPerTrigger`. |
| `failOnDataLoss` error after a pause | Kafka retention expired the offset checkpoint. Full refresh, or start from `earliest`. |
