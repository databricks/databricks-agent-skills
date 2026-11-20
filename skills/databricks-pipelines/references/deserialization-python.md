# Deserialization - Python

General-purpose deserialization of JSON, Avro, and Protobuf payloads in Spark Declarative Pipelines (Python). These functions work on any binary or string column regardless of the streaming source.

For Confluent Schema Registry integration (Avro or Protobuf) see **[Kafka Deserialization](kafka-deserialization-python.md)**.

---

## JSON

### With Explicit Schema

```python
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, MapType

event_schema = StructType([
    StructField("event_id", StringType()),
    StructField("event_type", StringType()),
    StructField("user_id", StringType()),
    StructField("timestamp", TimestampType()),
    StructField("payload", MapType(StringType(), StringType()))
])

@dp.table(name="silver_events")
def silver_events():
    return (
        spark.readStream.table("bronze_events")
        .withColumn("data", F.from_json("event_value", event_schema))
        .select(
            "data.event_id",
            "data.event_type",
            "data.user_id",
            F.col("data.timestamp").alias("event_timestamp"),
            "data.payload",
        )
    )
```

### With Schema Inference and Evolution (Pipelines Only)

Passing `None` as the schema enables automatic schema inference and evolution. Each `from_json` expression requires a unique `schemaLocationKey` per pipeline.

```python
@dp.table(name="silver_events")
def silver_events():
    return (
        spark.readStream.table("bronze_events")
        .withColumn(
            "data",
            F.from_json(
                F.col("event_value"),
                None,
                {"schemaLocationKey": "events", "schemaEvolutionMode": "addNewColumns"}
            )
        )
        .select("data.*")
    )
```

Schema evolution modes:

| Mode               | Behavior                                                               |
| ------------------ | ---------------------------------------------------------------------- |
| `addNewColumns`    | (default) Adds new fields as they appear; existing columns keep types  |
| `rescue`           | Never evolves; unrecognized fields go to `_rescued_data`               |
| `failOnNewColumns` | Fails the pipeline when new fields appear                              |
| `none`             | Silently ignores new fields                                            |

An auto-added `_rescued_data STRING` column captures data that doesn't fit the current schema. Rename it with the `rescuedDataColumn` option.

---

## Avro

`from_avro` operates on a binary column — do not cast to STRING first. Available via `from pyspark.sql.avro.functions import from_avro`.

```python
from pyspark.sql.avro.functions import from_avro

avro_schema = open("/Volumes/catalog/schema/volume/event.avsc").read()

@dp.table(name="silver_avro_events")
def silver_avro_events():
    return (
        spark.readStream.table("bronze_events")
        .select(
            from_avro(F.col("payload"), avro_schema).alias("data")
        )
        .select("data.*")
    )
```

`from_avro` options (pass as a dict to the `options` parameter):

| Option                    | Values                                       | Description                          |
| ------------------------- | -------------------------------------------- | ------------------------------------ |
| `mode`                    | `FAILFAST`, `PERMISSIVE`                     | Error handling (default: `FAILFAST`) |
| `avroSchemaEvolutionMode` | `none`, `restart`                            | Schema evolution (default: `none`)   |
| `compression`             | `uncompressed`, `snappy`, `deflate`, `bzip2` | Compression codec                    |

---

## Protobuf

`from_protobuf` operates on a binary column — do not cast to STRING first. Available via `from pyspark.sql.protobuf.functions import from_protobuf`. Requires Databricks Runtime 12.2 LTS+.

```python
from pyspark.sql.protobuf.functions import from_protobuf

@dp.table(name="silver_proto_events")
def silver_proto_events():
    return (
        spark.readStream.table("bronze_events")
        .select(
            from_protobuf(
                F.col("payload"),
                "EventMessage",
                descFilePath="/Volumes/catalog/schema/volume/event.desc"
            ).alias("data")
        )
        .select("data.*")
    )
```

Key `from_protobuf` options:

| Option                       | Default    | Description                                               |
| ---------------------------- | ---------- | --------------------------------------------------------- |
| `mode`                       | `FAILFAST` | `FAILFAST` throws on bad records; `PERMISSIVE` emits null |
| `recursive.fields.max.depth` | `-1`       | -1 = disallowed; 0 = drop recursive; 1-10 = expand depth |
| `emit.default.values`        | `false`    | Fill empty fields with proto default values               |
| `enums.as.ints`              | `false`    | Represent enums as integers instead of strings            |
