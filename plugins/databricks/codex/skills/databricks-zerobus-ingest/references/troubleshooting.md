# Troubleshooting

Read this when **anything fails or data is missing**. Match the symptom to a row, apply the fix, and re-run the verification query in SKILL.md Step 6.

## Connection and Authentication

| Error | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Wrong endpoint/port | Verify: `<workspace-id>.zerobus.<region>.cloud.databricks.com:443` |
| `401 Unauthorized` | Bad credentials | Regenerate SP OAuth secret; verify client ID/secret |
| `Error 4024 / authorization_details` | SP missing grants | Grant `USE CATALOG`, `USE SCHEMA`, `MODIFY` + `SELECT` on table (not inherited) |
| `TLS handshake failed` | TLS issue | Use TLS on 443; firewall allows HTTPS |

## Schema and Data

| Error | Cause | Solution |
|-------|-------|----------|
| `Schema mismatch / unknown field` | Record field not in table | Add the field to the table, or for JSON enable a rescue column (Beta) ([schema-management.md](schema-management.md)). Regenerate the `.proto` for Protobuf |
| `Type mismatch` | Record field type doesn't match column | Ensure type matches exactly (e.g., INT vs BIGINT). See [protobuf-schema.md](protobuf-schema.md) for type mappings. |
| `NOT NULL constraint violated` | Record missing a required field | Update producer to include the field, or remove NOT NULL from the table. |
| `Records not appearing after a schema change` | Schema mismatch occurred after durability | Records that were already durable but couldn't be written to the table after a schema change are held in the fallback location ([recovery.md](recovery.md#advanced-recover-data-from-the-durable-fallback-location)). Ingest errors surface; they are not silently rejected. |

## Throughput and Performance

| Issue | Cause | Solution |
|-------|-------|----------|
| **Throughput plateau** | Hit per-stream quota | Open more streams; throughput scales with stream count ([performance.md#quotas](performance.md#quotas)). |
| **Throughput plateau at 10 GB/s** | Hit the default per-table quota | Contact your Databricks account team to raise it. |
| **Ingest calls stall or block** | The in-flight buffer is full: acks aren't keeping up (network, per-stream quota) | Expected backpressure. Check connectivity and quota, then add streams. Don't add waits ([how-it-works.md](how-it-works.md#how-the-sdk-processes-records)) |
| **Throughput far below the per-stream quota** | Per-record `wait_for_offset()` or per-record `flush()` | Use batching: `ingest_record_offset()` in a loop, then `flush()` once. |
| **Memory usage growing** | The in-flight buffer holds unacknowledged records in memory | Lower the in-flight limit (`max_inflight_records` in Python; `max_inflight_requests` on the Rust builder), and check that acks keep up ([how-it-works.md](how-it-works.md#how-the-sdk-processes-records)) |

## Data Visibility

| Issue | Cause | Solution |
|-------|-------|----------|
| **Ack received but no rows in table** | Durable is not queryable | Wait about 5 seconds after the ack, then query the table. This is expected behavior. |
| **No rows after 30 seconds** | Ingestion may have failed | Verify the table schema matches the records, then check `errors` in `system.lakeflow.zerobus_ingest` ([observability.md](observability.md)). |
| **Duplicate rows** | At-least-once delivery with retries | Usually fine to keep. If the use case needs unique rows, see [how-it-works.md#delivery-and-duplicates](how-it-works.md#delivery-and-duplicates). |

## SDK-Specific Issues

### Python

| Error | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: zerobus` | SDK not installed | `pip install databricks-zerobus-ingest-sdk` locally. On Databricks, add it as a cluster library (classic) or an environment dependency (serverless). |
| `Cannot import from zerobus.sdk.sync` | Wrong import path | Use `from zerobus.sdk.sync import ZerobusSdk` for sync; `from zerobus.sdk.aio import ZerobusSdk` for async. |

### Java

| Error | Cause | Solution |
|-------|-------|----------|
| `ClassNotFoundException: ZerobusSdk` | JAR not on classpath | Add `com.databricks:zerobus-ingest-sdk` to pom.xml or build.gradle. |
| `Unsupported platform` | Platform not supported (e.g., macOS) | Use a supported platform (Linux x86_64/aarch64, Windows x86_64) or build from source. |

### TypeScript

| Error | Cause | Solution |
|-------|-------|----------|
| `Cannot find module '@databricks/zerobus-ingest-sdk'` | Package not installed | `npm install @databricks/zerobus-ingest-sdk` |
| `Module uses native binary, but native binaries are forbidden` | Edge runtime (Cloudflare Workers, Deno Deploy, etc.) | Use REST API instead |

### Go

| Error | Cause | Solution |
|-------|-------|----------|
| `missing Rust library` | Pre-built binary not for your platform | CGO: install Rust and C, rebuild. Purego (Go 1.25+): use pure Go variant |

## Advanced Debugging

**Python logging:** `import logging; logging.basicConfig(level=logging.DEBUG)`.

**Test connectivity:** Endpoint per cloud: AWS `.cloud.databricks.com`, Azure `.azuredatabricks.net`, GCP `.gcp.databricks.com`.
```bash
openssl s_client -connect <endpoint>:443 -brief </dev/null      # gRPC, REST, OTLP
openssl s_client -connect <endpoint>:9092 -brief </dev/null     # Kafka TLS
```
**Expected:** `CONNECTION ESTABLISHED` on each test.

### Verify Service Principal

```bash
databricks service-principals get --service-principal-id <id> --profile <PROFILE>
```

## Escalate
Collect logs, timestamps, then check [Zerobus overview](https://docs.databricks.com/ingestion/zerobus-overview) and [deep dives](https://docs.databricks.com/ingestion/zerobus-deep-dives). Contact Databricks support with details.

## Sources

- [Zerobus Concepts](https://docs.databricks.com/ingestion/zerobus-concepts)
- [Databricks Support](https://docs.databricks.com/en/support/index.html)
