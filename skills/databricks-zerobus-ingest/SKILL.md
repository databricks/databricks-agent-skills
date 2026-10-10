---
name: databricks-zerobus-ingest
description: "Push records from apps, services, devices, or scripts directly into Unity Catalog Delta tables with Zerobus Ingest: SDKs (Python, TypeScript, Go, Java, Rust, C++, .NET), REST, OTLP, MQTT, Arrow Flight, or Apache Kafka-compatible producer APIs, with no message bus to run. Use to stream events, telemetry, logs, IoT data, CDC, or columnar batches into Databricks in near real time; connect existing collectors and log shippers (OpenTelemetry, Debezium, Vector, Telegraf, Cribl); replace a message bus that only feeds the lakehouse; or debug Zerobus auth, schema, throughput, or delivery issues."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.2.0"
parent: databricks-core
---

# Zerobus Ingest

**Zerobus Ingest** (part of Lakeflow Connect) is a managed, **push-based** ingestion service: a producer sends records and they land in a **Unity Catalog managed Delta table**, with no broker or ingestion cluster to run. The SDKs do real work for you: **OAuth**, **buffering**, **offset tracking**, **durability acknowledgments**, and **automatic recovery** that replays unacknowledged records after transient failures.

**FIRST**: Use the parent `databricks-core` skill for CLI install, authentication, and profile selection.

## Decide before you build

**Recommend Zerobus** when data is pushed from an app, service, or device; the destination is a Delta table; the workload is continuous or event-driven and needs a shock absorber (Zerobus lands data in about 5 seconds, and it still fits when minutes are acceptable); and there is one main downstream consumer (or a message bus such as Apache Kafka, Amazon Kinesis, Azure Event Hubs, or Google Cloud Pub/Sub is just a pipe to the lakehouse).

**Don't recommend Zerobus** when many independent consumers outside the lakehouse need the data (use a message bus such as Apache Kafka, Amazon Kinesis, Azure Event Hubs, or Google Cloud Pub/Sub), or when the data is already in Kafka or another bus and must be pulled into the lakehouse (use the Lakeflow Connect managed Kafka connector or Spark Structured Streaming). Explain why and name the alternative. **Before ruling Zerobus out** for files, SaaS apps, or databases, check [references/choose-an-interface.md](references/choose-an-interface.md): batches of columnar data can go through Arrow Flight, and a SaaS app that can push to a Zerobus-compatible API can use Zerobus.

**Prefer an off-the-shelf path.** If the source already speaks **OpenTelemetry**, **Kafka**, or **MQTT**, or runs **Debezium, Vector, Telegraf, or Cribl**, point the user to that path instead of writing SDK code. All of these, plus the full decision tree, are in [references/choose-an-interface.md](references/choose-an-interface.md). For existing **Kafka producers**, read [references/kafka.md](references/kafka.md); for **MQTT v5** devices, [references/mqtt.md](references/mqtt.md); for **columnar batches** (Parquet, Arrow, DataFrames), [references/arrow-flight.md](references/arrow-flight.md); for migrating a pipeline from Kafka or a Kafka-compatible system, read [references/migration-from-kafka-compatible-systems.md](references/migration-from-kafka-compatible-systems.md).

## Workflow

Treat the request as a conversation: ask **one question at a time**, use a multiple-choice question tool if one is available, and always offer **"Not sure, help me decide"**. Skip any question the user has already answered.

**Many users won't know Databricks.** If the user is an app, DevOps, or platform engineer who's new to Databricks, explain each Databricks term in plain language the first time you use it, map it to something they know (a table name is like `database.schema.table` in Postgres; a service principal is like a service account), and **offer to set up what's missing for them**. Read [references/new-to-databricks.md](references/new-to-databricks.md).

### Step 0: Show your plan
List the steps you'll run and what you'll create (table, grants, producer file). Ask before creating any catalog, schema, table, or service principal; never assume the user wants a new one.

### Step 1: Ask where the producer runs
> Where will the producer that sends data to Zerobus run?
> - **Outside Databricks**: a service, app, device or gateway, or my laptop
> - **Inside Databricks**: a Lakeflow Job or a Databricks App
> - **Not sure, help me decide**

- **Outside Databricks** (most common): write the producer as a local file the user keeps; read credentials from environment variables.
- **Inside Databricks**: read [references/databricks-apps.md](references/databricks-apps.md). The Python SDK runs on classic and **serverless** compute; install it as a job, cluster, or environment dependency.
- **Not sure**: ask what generates the data. Data almost always originates outside Databricks, so default there.

### Step 2: Ask only the questions you still need
Questions come in three groups. **Ask the required ones first**: they're all you need to build a first client. Ask the advanced ones only when the user raises the topic, or when the answer would change your recommendation or the deployment.

**Required to build a client:**
1. **What is the data, and where does it come from?** Application events, logs, metrics, traces, CDC from a database, IoT or sensor readings, clickstream? This decides the route: traces, logs, and metrics often fit **OTLP**, database changes fit **Debezium**, and an existing Kafka producer fits the **Kafka-compatible APIs** ([references/choose-an-interface.md](references/choose-an-interface.md)).
2. **Target table**: the three-part name, whether it exists yet, and what shape the records have (a sample event helps). Must any fields always be present, and will the shape change over time ([references/schema-management.md](references/schema-management.md))?
3. **Language and runtime**: and **can the environment use precompiled binaries / native libraries?** The Python, TypeScript, Java, Go (cgo), C++, and .NET SDKs load a prebuilt Rust core. **If the user doesn't know, assume precompiled binaries are allowed**, and change course only if the SDK fails to install or load. **If the platform has no prebuilt binary** (Alpine, glibc older than 2.34 for Python), **or the user wants to build the SDK themselves**, **build it from source** following that SDK README's build steps ([references/build-from-source.md](references/build-from-source.md)). **If precompiled binaries aren't allowed, use a pure SDK: Rust or pure Go** (pure C doesn't send data yet). **Edge runtimes such as Cloudflare Workers or Deno Deploy can't load native code, so use REST there** ([references/rest.md](references/rest.md)).

If the user doesn't name a language, default to **Python**.

**Advanced: is Zerobus the right service?** Ask when the fit is in doubt, for example when other systems also read the data or the user mentions strict volume or freshness needs ([references/choose-an-interface.md](references/choose-an-interface.md)):
- **Who consumes it?** Is the lakehouse the **one main destination**, or do several independent systems read the same data? Many consumers outside the lakehouse, replay, or consumer groups mean **keep the message bus** (don't recommend Zerobus as its replacement).
- **Volume and latency**: rough records per second and how fresh the data must be. Zerobus makes records durable in about 150 ms and queryable in about 5 seconds, and it still fits when minutes are acceptable. Volume decides how many streams to open later ([references/performance.md](references/performance.md)); it doesn't change how you build the first client.

**Advanced setup: what it takes to run in the user's environment.** Ask before deploying beyond a laptop, or when a connection or auth step fails:
- **Network**: public internet, front-end PrivateLink, an HTTP proxy, or on-prem ([references/networking.md](references/networking.md)).
- **Identity**: does the organization require identity federation (for example Entra ID) instead of a service principal secret ([references/authentication.md](references/authentication.md))?

### Step 3: Confirm prerequisites
Details are in [references/authentication.md](references/authentication.md). Don't run a producer until every row passes. **If something is missing, offer to create it**: design the table from a sample event, create the service principal, and grant it, one approved step at a time ([references/new-to-databricks.md](references/new-to-databricks.md)).

| # | Prerequisite | Verify |
|---|--------------|--------|
| 1 | Workspace in a **supported region** | Region is listed under availability on the [quotas page](https://docs.databricks.com/ingestion/zerobus-quotas) |
| 2 | **Zerobus endpoint**, e.g. `https://<workspace-id>.zerobus.<region>.cloud.databricks.com` (AWS) | Uses the numeric workspace ID and the workspace's region |
| 3 | A pre-created **managed Delta table**. Zerobus never creates or alters tables | `databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>` shows the expected columns |
| 4 | A **service principal** with an OAuth client ID and secret | `databricks service-principals list --profile <PROFILE>` lists it |
| 5 | Grants: `USE CATALOG`, `USE SCHEMA`, and `MODIFY` + `SELECT` **directly on the table**. `ALL PRIVILEGES` is not sufficient; grant these four explicitly | `SHOW GRANTS ON TABLE <catalog.schema.table>` lists the service principal with `MODIFY` and `SELECT` |
| 6 | **Outbound HTTPS (443)** from the producer to the endpoint and the workspace | Connectivity check in [references/networking.md](references/networking.md) |

### Step 4: Build the producer
Read the SDK reference for the chosen language. For production, prefer **Protobuf** over JSON ([references/protobuf-schema.md](references/protobuf-schema.md)). **Never hard-code secrets.**

**Always write a non-blocking producer.** Use this ladder, and only go further down when the user needs it:

| Need | Use | Blocks? |
|------|-----|---------|
| **Send records (the default)** | `ingest_record_offset()` / `ingest_records_offset()`: queues and returns; the SDK sends and tracks acks in the background | No |
| **Act while ingestion runs**: metrics, logging, progress, errors, checkpoints | An **ack callback** (`on_ack` / `on_error`) | No |
| **Durability boundary**: end of a bounded batch, before shutdown | `flush()` once, then `close()` | Yes, once |
| **Advanced: must not continue until one specific record is durable** | `wait_for_offset(offset)` | Yes. **Never** per record or in a loop |

Ack callbacks exist in **Python, Java, Rust, C++, and pure Go**. The TypeScript, CGO Go, and .NET SDKs don't document one; there, call `flush()` on an interval for progress. Method names differ by language; use the SDK reference.

Minimal Python producer (APIs from the SDK README), with an ack callback for progress and errors:
```python
import os
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import AckCallback, StreamConfigurationOptions, TableProperties

class Progress(AckCallback):
    def on_ack(self, offset: int):  # runs on an SDK background thread; keep it fast
        print(f"durable through offset {offset}")

    def on_error(self, offset: int, error_message: str):
        print(f"error at offset {offset}: {error_message}")

sdk = ZerobusSdk(os.environ["ZEROBUS_SERVER_ENDPOINT"], os.environ["DATABRICKS_WORKSPACE_URL"])
stream = sdk.create_stream(
    os.environ["DATABRICKS_CLIENT_ID"],
    os.environ["DATABRICKS_CLIENT_SECRET"],
    TableProperties(os.environ["ZEROBUS_TABLE_NAME"]),
    StreamConfigurationOptions(ack_callback=Progress()),
)
try:
    for i in range(100):
        stream.ingest_record_offset({"device_name": f"sensor-{i % 10}", "temp": 20 + (i % 15)})  # queues, returns
    stream.flush()  # durability boundary: blocks once until everything queued is acknowledged
finally:
    stream.close()
```

### Step 5: Send a small test batch
Send 10 to 100 records first. A **durability acknowledgment** (an `on_ack` callback, or `flush()` returning) means Zerobus stored the records safely. It does **not** mean they are queryable yet.

### Step 6: Verify the rows landed
Wait about 5 seconds after the acknowledgment (rows become queryable about 5 seconds after they're sent), then run:
```bash
databricks experimental aitools tools query \
  "SELECT count(*) AS row_count, max(<timestamp_column>) AS latest FROM <catalog.schema.table>" \
  --profile <PROFILE>
```
**Expected:** `row_count` went up by the number of records you sent, and `latest` is close to the send time. If not, read [references/troubleshooting.md](references/troubleshooting.md).

### Step 7: Harden for production
Before the user scales up, cover schema evolution, duplicates, throughput, networking, and monitoring using the reference map below.

## Key facts

- **Table first.** Update the table schema before you update producers. Fields that don't fit can go to a **rescue column** (Beta, JSON only).
- **Durable is not queryable.** Zerobus materializes acknowledged data into the Delta table as a separate step: durable in about 150 ms, queryable in about 5 seconds ([how-it-works.md](references/how-it-works.md#the-data-path)).
- **At-least-once delivery.** Recovery or a client retry can resend records, so a few duplicates are possible. Most workloads accept them; don't add deduplication by default, and **never claim exactly-once**. If the user needs unique rows, see [how-it-works.md](references/how-it-works.md#delivery-and-duplicates).
- **Ordering is per stream only.** No global ordering across streams ([how-it-works.md](references/how-it-works.md#ordering)).
- **Non-blocking by default.** Ingest calls queue and return. Use **ack callbacks** to act on acks and errors while ingestion runs, `flush()` only at boundaries, and `wait_for_offset()` only in the advanced case where code must block on one record.
- **Ingest blocks only on backpressure.** Records wait in an in-memory in-flight buffer until acked; ingest calls block only when that buffer is full ([references/how-it-works.md](references/how-it-works.md#how-the-sdk-processes-records)).
- **Recovery is built in.** The SDK reconnects and replays unacked records. Don't hand-roll a retry loop; custom recovery is advanced ([references/recovery.md](references/recovery.md)).
- **TIMESTAMP columns take epoch microseconds** (an integer), not strings.
- **Quotas are adjustable defaults**, set per stream and per table. Add streams before asking for an increase ([performance.md](references/performance.md#quotas)).

## Common issues

| Symptom | Fix |
|---------|-----|
| Connection refused or timeout | Check the endpoint's cloud, region, and workspace ID, then the egress firewall on 443 ([networking.md](references/networking.md)) |
| Error 4024 / `authorization_details` | Grant `MODIFY` and `SELECT` **directly on the table**; inherited schema grants and `ALL PRIVILEGES` aren't enough |
| Auth failed or token errors | Check the client ID and secret, and that the workspace URL's OAuth endpoint is reachable ([authentication.md](references/authentication.md)) |
| Records rejected / schema mismatch | Match field names and types to the table, or add a rescue column ([schema-management.md](references/schema-management.md)) |
| Ack received but no rows | Wait about 5 seconds and re-query; durable isn't queryable yet |
| Ingest calls stall | Backpressure: the in-flight buffer is full. Check network and quota, then add streams ([how-it-works.md](references/how-it-works.md#how-the-sdk-processes-records)) |
| Stream failed permanently | Rescue unacked records and recreate the stream ([recovery.md](references/recovery.md)) |
| Duplicate rows | Expected occasionally after retries (at-least-once delivery). Usually fine; if the use case needs unique rows, build a deduplicated table downstream ([how-it-works.md](references/how-it-works.md#delivery-and-duplicates)) |
| Throughput plateau or slow producer | Remove any per-record `wait_for_offset()` or per-request `flush()`; ingest without blocking and observe acks with a callback; then add streams ([performance.md](references/performance.md)) |
| `pip install` builds from a `.tar.gz` and fails (Alpine, glibc older than 2.34) | No wheel for the platform. Build from source with a Rust toolchain ([build-from-source.md](references/build-from-source.md)), or use a pure SDK |
| Precompiled binaries not allowed (policy, platform, cgo disabled) | Use a pure SDK: **Rust** or **pure Go** (`purego`). Pure C doesn't send data yet ([choose-an-interface.md](references/choose-an-interface.md)) |
| SDK fails to load on an edge runtime | The runtime can't load native libraries; switch to REST ([rest.md](references/rest.md)) |
| REST calls fail with 401 after about an hour | The OAuth token expired. Cache it and refresh before expiry, and retry once on 401 ([authentication.md](references/authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc)) |

## SDKs: record formats and working examples

Which record formats each SDK supports, from the SDK repo's [Ingestion APIs table](https://github.com/databricks/zerobus-sdk/tree/main#ingestion-apis) (the source of truth; check it for newer releases). Don't attach a release status to an SDK; use this table. **When the user asks how to do something specific in one language** (Protobuf, Arrow, batching, async, a particular API), open that SDK's examples folder for a working program before writing code. Most folders split by record format (`json/`, `proto/`, `arrow/`).

| SDK | JSON / Protobuf | Avro (Beta) | Arrow Flight | Working examples |
|-----|-----------------|-------------|--------------|------------------|
| Python | Available | Beta | Available since 1.8.0 | [python/examples](https://github.com/databricks/zerobus-sdk/tree/main/python/examples) (sync and async: JSON, Protobuf, Arrow, Avro, identity federation) |
| Rust | Available | Beta | Available since 2.8.0 | [rust/examples](https://github.com/databricks/zerobus-sdk/tree/main/rust/examples) |
| Go (cgo) | Available | In development | Available since 1.6.0 | [go/examples](https://github.com/databricks/zerobus-sdk/tree/main/go/examples) |
| Pure Go | Available | In development | Not available | [purego/examples](https://github.com/databricks/zerobus-sdk/tree/main/purego/examples) |
| TypeScript | Available | In development | Available since 1.3.0 | [typescript/examples](https://github.com/databricks/zerobus-sdk/tree/main/typescript/examples) |
| Java | Available | In development | Available since 1.6.0 | [java/examples](https://github.com/databricks/zerobus-sdk/tree/main/java/examples) (`legacy/` uses the deprecated factory methods; prefer the others) |
| C++ | Available | In development | Available since 0.3.0 | [cpp/examples](https://github.com/databricks/zerobus-sdk/tree/main/cpp/examples) |
| .NET (C#) | Available | In development | Not available | [dotnet/examples](https://github.com/databricks/zerobus-sdk/tree/main/dotnet/examples) |

Pure C isn't in the table: it doesn't send data yet (its [example](https://github.com/databricks/zerobus-sdk/tree/main/purec/examples) validates inputs only), so don't use it to deliver data.

## Reference map: read only what the task needs

These references hold the decisions, gotchas, and tested minimal samples for each route. For the full API surface, other record types, and the latest SDK versions, **fetch the SDK README** linked in each file's Sources (raw Markdown); for working code, use the examples folders in the table above. docs.databricks.com pages are HTML. Long runnable programs for MQTT and the raw gRPC API are in [examples/](examples/).

| Read | When |
|------|------|
| [new-to-databricks.md](references/new-to-databricks.md) | **The user doesn't know Databricks**: plain-language glossary, and a guided first-time setup (pick a catalog and schema, design the table from a sample event, create the service principal, grant, save settings) |
| [choose-an-interface.md](references/choose-an-interface.md) | Unsure whether to use Zerobus, the SDK, REST, or a protocol/tool path; checking runtime compatibility |
| [how-it-works.md](references/how-it-works.md) | **How Zerobus works**: streams, the data path (the async ack loop, then batch commits to Delta), durable vs queryable, how the SDK processes records (in-flight buffer, cumulative acks, backpressure), ordering, delivery and duplicates, scaling |
| [recovery.md](references/recovery.md) | Stream failures, retryable vs fatal errors, **advanced custom recovery** (`get_unacked_records`, `recreate_stream`), durable-fallback reprocessing |
| [authentication.md](references/authentication.md) | Endpoints per cloud, service principal OAuth (official), **Entra ID / identity federation** (SDK-supported, docs pending), grants, env vars, local vs deployed credentials, **table-scoped tokens** for REST, Kafka, MQTT, and gRPC (mint and refresh), auth errors |
| [python-sdk.md](references/python-sdk.md) | Python producers: install and platforms, a Protobuf producer, ack callbacks; links to the README for async and other APIs |
| [typescript-sdk.md](references/typescript-sdk.md) | Node.js producers and native-binary requirements |
| [go-sdk.md](references/go-sdk.md) | Go producers with cgo (`go/`) or pure Go (`purego/`) |
| [java-sdk.md](references/java-sdk.md) | JVM producers |
| [other-sdks.md](references/other-sdks.md) | Rust, C++, C#/.NET |
| [kafka.md](references/kafka.md) | Existing Kafka producers: Apache Kafka-compatible producer APIs (Beta), connection settings, token callback, limits, errors |
| [mqtt.md](references/mqtt.md) | MQTT v5 devices and gateways: connection settings, CONNECT auth, limits, errors; a runnable **non-blocking QoS 1 publisher** with token refresh on reconnect in [examples/mqtt_producer.py](examples/mqtt_producer.py) |
| [arrow-flight.md](references/arrow-flight.md) | **Columnar batches** (Parquet files, Arrow, pandas or Polars DataFrames): schema matching, a non-blocking Python producer, links for other languages, tuning, recovery |
| [migration-from-kafka-compatible-systems.md](references/migration-from-kafka-compatible-systems.md) | Migrating a pipeline from Kafka or a Kafka-compatible system into Delta: when to migrate, the four pathways, step-by-step cutover, rollback |
| [build-from-source.md](references/build-from-source.md) | **The user wants to build the SDK themselves, or there's no prebuilt binary** (Alpine/musl, older glibc, other CPUs): which platforms each SDK ships, each SDK README's source-build steps (Python wheel via `make build`, TypeScript, Java with JNI, Go, .NET, C++, Rust), an Alpine Dockerfile, build errors |
| [grpc-api.md](references/grpc-api.md) | **Building a client from scratch** against the gRPC API: the `.proto`, stub generation, the `EphemeralStream` messages, auth headers, the async ack loop, recovery; a runnable Python client in [examples/grpc_client.py](examples/grpc_client.py) |
| [rest.md](references/rest.md) | Edge runtimes and serverless functions outside Databricks (Cloudflare Workers, Deno Deploy), languages without an SDK, low-volume senders. Uses a table-scoped token from [authentication.md](references/authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc) (tokens expire after about an hour) |
| [protobuf-schema.md](references/protobuf-schema.md) | Generating `.proto` from a table, type mappings |
| [schema-management.md](references/schema-management.md) | The table as the contract: how records are matched, the three strictness scenarios, the **rescue column** (setup, tag, routing rules), safe schema evolution, Protobuf rules |
| [performance.md](references/performance.md) | Batching, stream count, quotas, table layout |
| [networking.md](references/networking.md) | Ports and TLS per interface, front-end PrivateLink, **on-prem producers and HTTP proxies**, firewalled storage, cross-region, connectivity checks |
| [observability.md](references/observability.md) | The **monitoring dashboard bundle** (install), ack callbacks, system tables, **latency** (ack and end-to-end freshness), errors, alerts |
| [troubleshooting.md](references/troubleshooting.md) | Any error or missing data |
| [databricks-apps.md](references/databricks-apps.md) | Running the producer in a Databricks App or Lakeflow Job |

## Related skills

- **databricks-core**: CLI, profiles, auth, and ad hoc SQL for verification
- **databricks-unity-catalog**: catalogs, schemas, tables, and grants
- **databricks-pipelines**: downstream processing of ingested data, including a deduplicated table built with AUTO CDC
- **databricks-lakeflow-connect**: managed connectors when Databricks should **pull** from a source
- **databricks-apps** / **databricks-apps-python**: building the Databricks App that hosts a producer
- **databricks-dabs**: deploying a producer job with Declarative Automation Bundles
- **databricks-aibi-dashboards**: building a dashboard over the ingested events or telemetry
