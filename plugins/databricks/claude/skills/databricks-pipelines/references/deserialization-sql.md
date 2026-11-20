# Deserialization - SQL

General-purpose deserialization of JSON and Avro payloads in Spark Declarative Pipelines (SQL). These functions work on any string or binary column regardless of the streaming source.

For Avro with Confluent Schema Registry see **[Kafka Deserialization - Python](kafka-deserialization-python.md)** (SQL `from_avro` has no Schema Registry form). Protobuf works in SQL on DBR 16.1+: `from_protobuf(data, messageName, options)`, with Schema Registry passed as options (`schema.registry.subject`, `schema.registry.address`).

---

## JSON

### With Explicit Schema

```sql
CREATE OR REFRESH STREAMING TABLE silver_events AS
SELECT
  from_json(
    event_value,
    'event_id STRING, event_type STRING, user_id STRING, timestamp TIMESTAMP, payload MAP<STRING, STRING>'
  ) AS data
FROM STREAM bronze_events;
```

### With Schema Inference and Evolution (Pipelines Only)

Pass `NULL` as the schema to enable automatic inference and evolution. Each `from_json` expression requires a unique `schemaLocationKey` per pipeline.

```sql
CREATE OR REFRESH STREAMING TABLE silver_events AS
SELECT
  from_json(
    event_value,
    NULL,
    map(
      'schemaLocationKey', 'events',
      'schemaEvolutionMode', 'addNewColumns'
    )
  ) AS data
FROM STREAM bronze_events;
```

Schema evolution modes:

| Mode               | Behavior                                                               |
| ------------------ | ---------------------------------------------------------------------- |
| `addNewColumns`    | (default) Adds new fields as they appear; existing columns keep types  |
| `rescue`           | Never evolves; unrecognized fields go to `_rescued_data`               |
| `failOnNewColumns` | Fails the pipeline when new fields appear                              |
| `none`             | Silently ignores new fields                                            |

An auto-added `_rescued_data STRING` column captures data that doesn't fit the current schema. When referencing `data.*` fields in the same query, provide `schemaHints` to avoid analysis errors:

```sql
map('schemaLocationKey', 'events', 'schemaHints', 'event_id STRING, event_type STRING')
```

**`from_json` vs `parse_json`:** `from_json` enforces schema at write time and optimizes storage. Use `parse_json` instead when schemas change rapidly and you want flexible, schema-less VARIANT storage without strict typing.

### Flatten Parsed Data

```sql
CREATE OR REFRESH STREAMING TABLE silver_events_flat AS
SELECT
  data.event_id,
  data.event_type,
  data.user_id,
  data.timestamp AS event_timestamp,
  data.payload
FROM STREAM silver_events;
```

---

## Avro

Available in Databricks Runtime 16.0 and above. Operates on a binary column — do not cast to STRING first.

```sql
CREATE OR REFRESH STREAMING TABLE silver_avro_events AS
SELECT
  from_avro(
    payload,
    '{"type":"record","name":"Event","fields":[
      {"name":"event_id","type":"string"},
      {"name":"event_type","type":"string"},
      {"name":"user_id","type":"string"}
    ]}',
    NULL
  ) AS data
FROM STREAM bronze_events;
```

`from_avro` options (pass as `MAP<STRING,STRING>` in place of `NULL`):

| Option                    | Values                                       | Description                          |
| ------------------------- | -------------------------------------------- | ------------------------------------ |
| `mode`                    | `FAILFAST`, `PERMISSIVE`                     | Error handling (default: `FAILFAST`) |
| `avroSchemaEvolutionMode` | `none`, `restart`                            | Schema evolution (default: `none`)   |
| `compression`             | `uncompressed`, `snappy`, `deflate`, `bzip2` | Compression codec                    |
