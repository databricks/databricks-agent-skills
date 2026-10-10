# Apache Kafka-compatible producer APIs

Read this when the user already runs a **Kafka producer** (an app, agent, or collector that emits to Kafka) and wants that data in a Delta table with minimal code changes. Zerobus **supports Apache Kafka-compatible producer APIs**. It isn't a Kafka broker: the APIs are **write-only**. Content comes from the Zerobus Kafka docs, so you don't need to fetch them. For migrating a whole pipeline from Kafka or a Kafka-compatible system, also read [migration-from-kafka-compatible-systems.md](migration-from-kafka-compatible-systems.md).

**Status:** Beta.

## When to use it
| Use the Kafka-compatible APIs | Use an SDK or keep Kafka |
|--|----|
| You already run a Kafka producer sending **JSON** | You need Protobuf, Avro, Arrow, or highest throughput |
| You want to reuse producer config and tooling | You need consumers, consumer groups, or replay |
| | You need PrivateLink ([networking.md](networking.md)) |

## How Kafka concepts map to Zerobus
| Kafka | Zerobus |
|-------|---------|
| Topic | Full table name (`catalog.schema.table`) |
| Record value | **Only** thing ingested; must be UTF-8 JSON matching the schema |
| Key, headers, partition, timestamp | Ignored and not persisted |
| Broker and partitions | Partitionless (one logical broker, partition 0) |
| `acks` | Set to `all` for durable persistence |
| APIs | `Produce`, `Metadata`, `ApiVersions`, SASL; no consumer/admin/transactional APIs |
| Delivery | At-least-once; see [how-it-works.md#delivery-and-duplicates](how-it-works.md#delivery-and-duplicates) |

## Connection settings
| Setting | Value |
|---------|-------|
| Bootstrap server (AWS) | `<workspace-id>.zerobus.<region>.cloud.databricks.com:9092` |
| Bootstrap server (Azure) | `<workspace-id>.zerobus.<region>.azuredatabricks.net:9092` |
| Bootstrap server (GCP) | `<workspace-id>.zerobus.<region>.gcp.databricks.com:9092` |
| `security.protocol` | `SASL_SSL` |
| `sasl.mechanism` | `OAUTHBEARER`, with a **token-provider callback** (see Authentication) |
| `acks` | `all` |
| `compression.type` | `none`. Compressed batches (`gzip`, `snappy`, `lz4`, `zstd`) are rejected with `UNSUPPORTED_COMPRESSION_TYPE` |
| `enable.idempotence` | **`false`**. Zerobus doesn't implement the transactional APIs and rejects `InitProducerId`. **Java clients enable idempotence by default (Kafka 3.0+), so set it explicitly** (Debezium docs) |
| `linger.ms`, `batch.size` | Tune up to batch records. "Batching is the single biggest lever for throughput" |

## Authentication
Use a table-scoped OAuth token minted per [authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc](authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc). Supply it through the client's **token-provider callback** (not static), so the client refreshes it every hour and re-fetches on reconnect. Built-in OIDC settings (librdkafka, Java) don't send `resource` and `authorization_details`, so use a **custom callback** (example below).

**Grants:** Grant `USE CATALOG`, `USE SCHEMA`, `MODIFY`, `SELECT` **directly on the table** ([authentication.md](authentication.md), Step 4). `ALL PRIVILEGES` is not sufficient.

## Step 1: Token provider (Python, kafka-python)
Uses `fetch_zerobus_token()` from [authentication.md](authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc) (paste it above this code). kafka-python calls `token()` whenever it needs a fresh token, which covers the 1-hour expiry.
```python
from kafka.sasl.oauth import AbstractTokenProvider

class ZerobusTokenProvider(AbstractTokenProvider):
    def token(self):
        access_token, _ = fetch_zerobus_token()  # noqa: F821 (defined in authentication.md)
        return access_token
```
For other clients, implement the same token request in that client's OAUTHBEARER callback (for example `oauth_cb` in confluent-kafka-python, or a custom `AuthenticateCallbackHandler` in Java). The token request is the same one.

## Step 2: Produce without blocking
```python
import json, os
from kafka import KafkaProducer

TABLE_NAME = os.environ["ZEROBUS_TABLE_NAME"]
producer = KafkaProducer(
    # Same host as the Zerobus endpoint, on port 9092
    bootstrap_servers=os.environ["ZEROBUS_SERVER_ENDPOINT"].removeprefix("https://") + ":9092",
    security_protocol="SASL_SSL",
    sasl_mechanism="OAUTHBEARER",
    sasl_oauth_token_provider=ZerobusTokenProvider(),
    acks="all",                 # durable acknowledgment per batch
    compression_type=None,      # compression isn't supported
)

def on_error(exc):              # surface failures without blocking the send loop
    print(f"send failed: {exc}")

for i in range(1000):
    producer.send(
        topic=TABLE_NAME,       # the topic is the full table name
        value=json.dumps({"device_name": f"sensor-{i}", "temp": 20 + i % 15}).encode("utf-8"),
    ).add_errback(on_error)

producer.flush()                # durability boundary: wait once for outstanding sends
producer.close()
```
**Keep the producer long-lived.** Send without waiting per-record; use errbacks or callbacks to surface failures. The non-blocking pattern (ingest without waiting, `flush()` only at boundaries) matches the SDK pattern.

**Verify:** Query the table: `SELECT count(*) FROM <catalog.schema.table>`. **Expected:** the count rises by 1,000 about 5 seconds after `flush()` returns.

## Quotas and limits
| Limit | Value |
|-------|-------|
| Kafka-compatible APIs (Beta) | 50,000 messages/s per workspace by default ([performance.md](performance.md#quotas)) |
| Record size | 10 MB per record (`MESSAGE_TOO_LARGE` above that) |
| Other limits | Same latency, record-size, and partitioned-table characteristics as the rest of Zerobus ([performance.md](performance.md)) |

## Networking
- Outbound **TCP 9092** to the bootstrap server, over TLS (`SASL_SSL`).
- **Front-end PrivateLink isn't supported.** Connect over the public endpoint.
- Run the producer in the **same cloud region** as the endpoint for the best throughput.

## Errors
| Error | Cause | Fix |
|-------|-------|-----|
| `SASL_AUTHENTICATION_FAILED` | Bad token or missing grants | Check callback (resource, `authorization_details`), grants |
| `UNKNOWN_TOPIC_OR_PARTITION` | Table doesn't exist or token unauthorized | Create table, check table name and grants |
| `INVALID_RECORD` | Schema mismatch or not UTF-8 JSON | Match schema or add rescue column ([schema-management.md](schema-management.md)) |
| `MESSAGE_TOO_LARGE` | Record > 10 MB | Split record |
| `UNSUPPORTED_COMPRESSION_TYPE` | Batch compressed | Set `compression.type=none` |
| `InitProducerId` | Idempotence enabled | Set `enable.idempotence=false` |

After a failed `Produce`, Zerobus closes the connection. Producers reconnect automatically; surface failures (errbacks/callbacks) so records aren't silently dropped.

**Debezium:** Debezium Server supports the Kafka route with `debezium.sink.type=kafka` here, but Debezium recommends its built-in Zerobus sink (Path C in [migration-from-kafka-compatible-systems.md](migration-from-kafka-compatible-systems.md)).

## Sources
- [Zerobus: Apache Kafka-compatible producer APIs](https://docs.databricks.com/ingestion/zerobus-kafka)
- [Zerobus Ingest quotas](https://docs.databricks.com/ingestion/zerobus-quotas) (50,000 messages/s per workspace, Beta)
- [Use Zerobus Ingest](https://docs.databricks.com/ingestion/zerobus-ingest) (token flow)
- [Debezium Server 3.7: Databricks Zerobus sink](https://debezium.io/documentation/reference/3.7/operations/debezium-server.html) (`enable.idempotence=false`, Kafka route notes)
