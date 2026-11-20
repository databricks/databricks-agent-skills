# Kafka Deserialization - Python

Confluent Schema Registry integration for Avro and Protobuf in Spark Declarative Pipelines (Python). For general deserialization patterns (inline schemas, descriptor files, `from_json`) see **[Deserialization - Python](deserialization-python.md)**. See also: **[Core Ingestion](kafka-streaming-python.md)** | **[Authentication](kafka-auth-python.md)**

Keep `value` as binary when reading from Kafka — do not cast to STRING before passing to `from_avro` or `from_protobuf`.

---

## Avro with Confluent Schema Registry

```python
from pyspark.sql.avro.functions import from_avro

@dp.table(name="silver_avro_events")
def silver_avro_events():
    schema_registry_options = {
        "confluent.schema.registry.basic.auth.credentials.source": "USER_INFO",
        "confluent.schema.registry.basic.auth.user.info": (
            f"{dbutils.secrets.get('schema-registry', 'api-key')}"
            f":{dbutils.secrets.get('schema-registry', 'api-secret')}"
        ),
        "avroSchemaEvolutionMode": "restart",   # Restart query when schema changes
        "mode": "FAILFAST",
    }

    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", spark.conf.get("kafka_brokers"))
        .option("subscribe", "events-topic")
        .option("databricks.serviceCredential", spark.conf.get("kafka_credential"))
        .load()
        .select(
            from_avro(
                data=F.col("value"),
                subject="events-topic-value",
                schemaRegistryAddress=spark.conf.get("schema_registry_url"),
                options=schema_registry_options
            ).alias("data"),
            F.col("timestamp").alias("kafka_timestamp")
        )
        .select("data.*", "kafka_timestamp")
    )
```

`avroSchemaEvolutionMode` values: `none` (default — ignores schema changes), `restart` (throws `UnknownFieldException` on change, enabling automatic job restart).

For Schema Registry SSL/TLS (Databricks Runtime 14.3 LTS+), add to `schema_registry_options`:

```python
{
    "confluent.schema.registry.ssl.truststore.location": "/Volumes/catalog/schema/volume/truststore.jks",
    "confluent.schema.registry.ssl.truststore.password": dbutils.secrets.get("sr", "truststore-password"),
}
```

---

## Protobuf with Confluent Schema Registry

Available in Databricks Runtime 12.2 LTS and above.

```python
from pyspark.sql.protobuf.functions import from_protobuf

@dp.table(name="silver_proto_events")
def silver_proto_events():
    schema_registry_options = {
        "schema.registry.subject": "events-topic-value",
        "schema.registry.address": spark.conf.get("schema_registry_url"),
        "confluent.schema.registry.basic.auth.credentials.source": "USER_INFO",
        "confluent.schema.registry.basic.auth.user.info": (
            f"{dbutils.secrets.get('schema-registry', 'api-key')}"
            f":{dbutils.secrets.get('schema-registry', 'api-secret')}"
        ),
    }

    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", spark.conf.get("kafka_brokers"))
        .option("subscribe", "events-topic")
        .option("databricks.serviceCredential", spark.conf.get("kafka_credential"))
        .load()
        .select(
            from_protobuf(F.col("value"), options=schema_registry_options).alias("data"),
            F.col("timestamp").alias("kafka_timestamp")
        )
        .select("data.*", "kafka_timestamp")
    )
```

Key `from_protobuf` options:

| Option                       | Default    | Description                                               |
| ---------------------------- | ---------- | --------------------------------------------------------- |
| `mode`                       | `FAILFAST` | `FAILFAST` throws on bad records; `PERMISSIVE` emits null |
| `recursive.fields.max.depth` | `-1`       | -1 = disallowed; 0 = drop recursive; 1-10 = expand depth |
| `emit.default.values`        | `false`    | Fill empty fields with proto default values               |
| `enums.as.ints`              | `false`    | Represent enums as integers instead of strings            |
