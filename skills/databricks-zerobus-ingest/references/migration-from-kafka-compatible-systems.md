# Migrating from Kafka-compatible systems to Zerobus

Read this when the user has a pipeline that moves data into Delta through **Kafka or a Kafka-compatible system** and wants to move it onto Zerobus. First decide whether to migrate at all (Section 1); then pick a pathway and follow the steps. For the Kafka-compatible endpoint itself, read [kafka.md](kafka.md).

## 1. Decide: Is Zerobus Right for You?

Zerobus suits **producer-to-lake pipelines** with one primary consumer. Migration is straightforward if Kafka is mainly a data-transport layer.

| Signal | Use Zerobus | Keep Kafka |
|--------|--|--|
| Producer → Kafka → Delta (single consumer) | ✓ |  |
| Multiple consumers / stream processing |  | ✓ |
| Long replay windows / retention |  | ✓ |

## 2. Choose a Migration Pathway

| Pathway | Code change | Throughput | Ordering | Status | Use when |
|---------|-------------|-----------|----------|--------|----------|
| **A: Repoint Kafka producers** to the Apache Kafka-compatible endpoint | Producer config + a token callback | Good; tune batching. Default Beta quota 50,000 messages/s per workspace | Kafka partition ordering doesn't carry over (the endpoint is one logical partition) | Beta | Producers use stock Kafka clients and send JSON |
| **B: Move producers to a Zerobus SDK** | Replace the Kafka client with the SDK | Highest (gRPC, per-stream quotas) | Per stream | Every SDK ([SKILL.md](../SKILL.md#sdks-record-formats-and-working-examples)) | You control the producer code and want throughput, callbacks, and built-in recovery |
| **C: Debezium Server** | Config only | High | Per stream | Debezium 3.7+ | CDC via Kafka |
| **D: Keep Kafka** | - | - | - | - | Multi-consumer / stream processing |

### Path A: Repoint Kafka producers
**Change in the producer:**
| Setting | Before | After |
|---------|--------|-------|
| `bootstrap.servers` | your brokers | `<workspace-id>.zerobus.<region>.cloud.databricks.com:9092` (Azure/GCP formats in [kafka.md](kafka.md)) |
| Topic | `events-topic` | the target table, `catalog.schema.table` |
| `security.protocol` / `sasl.mechanism` | as before | `SASL_SSL` / `OAUTHBEARER` with a **token callback** that requests the table-scoped token ([kafka.md](kafka.md)) |
| `acks` | any | `all` |
| `compression.type` | often `lz4`/`zstd` | `none` (compressed batches are rejected) |
| `enable.idempotence` | often `true` (Java default) | `false` |
| Record value | any bytes | a **UTF-8 JSON object** matching the table schema |

Keys, headers, partitions, and timestamps are dropped. Move anything you need (event ID, source, event time) **into the JSON value**. One table per topic: each topic name must be a full table name.

### Path B: Move to a Zerobus SDK
Replace the Kafka client with the SDK for the producer's language: [python-sdk.md](python-sdk.md), [java-sdk.md](java-sdk.md), [go-sdk.md](go-sdk.md), [typescript-sdk.md](typescript-sdk.md), [other-sdks.md](other-sdks.md). **Ingest without blocking** (use a queue with `ingest_*_offset`, an **ack callback** for progress, and `flush()` only at boundaries; see [SKILL.md](../SKILL.md) Step 4). Protobuf gives the best throughput ([protobuf-schema.md](protobuf-schema.md)).

### Path C: Debezium Server with Zerobus sink
Use Debezium's built-in Zerobus sink: set `debezium.sink.type=zerobus` with the endpoint, workspace URL, and service principal credentials. Target a Unity Catalog Delta table (with CDC and column mapping disabled). Build current-state tables downstream with AUTO CDC in Lakeflow Spark Declarative Pipelines (see the `databricks-pipelines` skill).

### Path D: Keep Kafka
Don't replace a multi-consumer bus. To land a lakehouse copy, have **Databricks read from Kafka**: Lakeflow Spark Declarative Pipelines with `read_kafka` (the `databricks-pipelines` skill), Spark Structured Streaming (the `databricks-spark-structured-streaming` skill), or the managed Kafka connector in Lakeflow Connect (the `databricks-lakeflow-connect` skill). Zerobus isn't involved on this path.

## 3. Pre-Migration Inventory

Document: all producers and topics, consumers per topic, record schemas (JSON/Avro/Protobuf), SLAs (volume, latency, ordering), and current Kafka setup (brokers, retention, replication).

## 4. Map Topics to Target Tables

For each topic: map to a `catalog.schema.table` (3-level name). Move keys, headers, timestamps into the JSON value. **Create tables first** (Zerobus requires existing tables). Use [schema-management.md](schema-management.md) for schema design:
```sql
CREATE TABLE main.ingest.events (
    event_id STRING NOT NULL,      -- stable event ID
    event_time TIMESTAMP,
    data STRING
);
```

## 5. Set Up Service Principal and Grants

Create a service principal and grant `USE CATALOG`, `USE SCHEMA`, `MODIFY`, `SELECT` on target tables ([authentication.md](authentication.md)).

## 6. Parallel Shadow Write (Optional)

Deploy a new producer that sends to **both** systems in parallel for 1-2 hours. Validate: Compare row counts, timestamps, sample data between tables. Check for duplicates (at-least-once delivery may cause them during cutover).

## 7. Cutover

Stop old producers. Start Zerobus producers (Path A or B). Monitor throughput and errors. Records appear in the table ~5 seconds after acknowledgment.

## 8. Validate

Query the table: `SELECT count(*) FROM <table>`. Check for duplicates: `SELECT event_id, count(*) FROM <table> GROUP BY 1 HAVING count(*) > 1`. See [observability.md](observability.md) for dashboards.

## 9. Decommission Kafka (Optional)

Drain consumers, stop the cluster, archive data as needed.

## Common Gotchas

| Gotcha | Fix |
|--------|-----|
| Table must exist first | Create tables before cutover ([schema-management.md](schema-management.md)) |
| No auto-evolution | Evolve the table first; for JSON, add a rescue column (Beta) ([schema-management.md](schema-management.md)) |
| Compression rejected | Set `compression.type=none` |
| Idempotence rejected | Set `enable.idempotence=false` |
| Keys/headers/timestamps dropped | Put them in the JSON value |
| No PrivateLink on Kafka-compatible APIs | Use SDK Path B or REST over PrivateLink |
| Partition ordering lost | Use event time or sequence number; sort downstream if needed |
| Duplicates from at-least-once | Expected occasionally; see [how-it-works.md](how-it-works.md#delivery-and-duplicates) |
| No consumer groups | Track progress via table queries or ack callbacks |

## Rollback

Keep Kafka running the first week. If issues, revert producers to Kafka brokers, investigate with [troubleshooting.md](troubleshooting.md), then decommission.

---

## Related

- [kafka.md](kafka.md) for Kafka-compatible endpoint details
- [python-sdk.md](python-sdk.md), [java-sdk.md](java-sdk.md) for SDK-based paths
- [schema-management.md](schema-management.md) for table setup
- [authentication.md](authentication.md) for service principal setup
- [observability.md](observability.md) for monitoring post-migration
