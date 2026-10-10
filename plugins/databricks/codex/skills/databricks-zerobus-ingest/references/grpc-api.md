# Build a client directly against the Zerobus gRPC API

Read this only when you must **build a raw gRPC client** in a language with no SDK or when REST isn't enough. Try the **SDKs first** (all languages on the [SDK repo](https://github.com/databricks/zerobus-sdk)); they save you from rebuilding the async ack loop, recovery, and token handling. Build on raw gRPC when none fit. The SDKs are the reference implementation.

## What you're building
A raw gRPC client must reproduce: token minting + caching, TLS channel, stream management, record sender with wire offsets, ack reader, backpressure, recovery on reconnect, and flush/close. The **SDKs are your reference implementation**. The Rust core (`rust/sdk/src/stream/grpc/`) has every component; pure Go (`purego/`) is a secondary reference. The pure C SDK (`purec/`) is still in development.

## Step 1: Generate stubs from the schema
The canonical schema is **`rust/sdk/zerobus_service.proto`** in the [SDK repo](https://github.com/databricks/zerobus-sdk) (proto2, package `databricks.zerobus`, marked STABLE). It imports `google/protobuf/duration.proto` (vendored).

Python example:
```bash
pip install grpcio grpcio-tools protobuf requests
python -m grpc_tools.protoc -I rust/sdk -I purego/internal/zerobuspb/third_party \
  --python_out=. --grpc_python_out=. rust/sdk/zerobus_service.proto
```

Verify the generated module has: `EphemeralStreamRequest`, `EphemeralStreamResponse`, `CreateIngestStreamRequest`, `IngestRecordRequest`, `IngestRecordBatchRequest`, `IngestRecordResponse`.

## Step 2: Service and message reference (excerpt)
**Service:** `databricks.zerobus.Zerobus` → **use the `EphemeralStream` RPC** (bidirectional streaming). Other RPCs (`PersistentStream`, `RetireStream`) are marked IN DEVELOPMENT.

**Method path:** `/databricks.zerobus.Zerobus/EphemeralStream`

For the complete schema (requests, responses, enum values), see `rust/sdk/zerobus_service.proto` at the SDK commit. Key patterns:
- **First message:** `CreateIngestStreamRequest` with `table_name`, `record_type`, and (for Protobuf) `descriptor_proto`.
- **Subsequent messages:** `IngestRecordRequest` or `IngestRecordBatchRequest`, each with an `offset_id`.
- **Responses:** `CreateIngestStreamResponse` (once), then `IngestRecordResponse` with `durability_ack_up_to_offset` (cumulative), and `CloseStreamSignal` if the server rotates.

**Record formats:**
- **JSON:** `record_type = JSON`; records are UTF-8 JSON strings matching the table schema.
- **Protobuf:** `record_type = PROTO`; `descriptor_proto` is a serialized `google.protobuf.DescriptorProto` (see [protobuf-schema.md](protobuf-schema.md)).

## Step 3: Authenticate
**Token:** Use the same table-scoped flow as REST and Kafka ([authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc](authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc)).

**Metadata headers on the stream RPC:**

| Header | Value |
|--------|-------|
| `authorization` | `Bearer <token>` |
| `x-databricks-zerobus-table-name` | Full table name |

**Token caching:** Cache the token, refresh 5 minutes before expiry, and fetch fresh headers for every stream open (including recovery). On `UNAUTHENTICATED`, retry once with a new token.

## Step 4: Connect
- **Endpoint:** `<workspace-id>.zerobus.<region>.cloud.databricks.com:443` (AWS); `.azuredatabricks.net` (Azure); `.gcp.databricks.com` (GCP).
- **TLS:** Required (verify server certificate).
- **Message size:** Max 10 MB per message. Cap payloads at 10 MB minus headroom.
- **Keepalive:** No HTTP/2 pings needed; SDKs detect dead streams with a 60-second no-ack timeout.
- **Proxy:** Standard gRPC environment variables (`grpc_proxy`, `https_proxy`, etc.).

## Step 5: The async ack loop
**Never wait per-record; run a background ack reader:**

1. **Open:** Call `EphemeralStream` with headers. Send `create_stream` first. Read `create_stream_response` (save `stream_id` for logs).
2. **Send:** Assign sequential **wire offsets** starting at 0 (restart per stream). Keep payloads in an in-flight buffer keyed by offset. Send without waiting.
3. **Read acks:** Each `ingest_record_response` carries `durability_ack_up_to_offset` (cumulative). Purge buffered entries ≤ that offset.
4. **Backpressure:** Bound the buffer. Block ingest when it's full. SDK default: `max_inflight_requests` 1,000,000.
5. **Rotation:** On `close_stream_signal`, stop sending, wait for `duration`, then replay unsent records on a new stream.
6. **Flush/close:** Flush waits for the last offset to be acked. Close flushes, then half-closes the request stream.

Ack = durable (~5 sec to queryable; see [how-it-works.md#the-data-path](how-it-works.md#the-data-path)).

## Step 6: Recover and replay
On transient errors, reconnect and replay. Terminal codes (no retry): `INVALID_ARGUMENT`, `PERMISSION_DENIED`, `UNAUTHENTICATED` (retry once), `NOT_FOUND`, `UNIMPLEMENTED`, `OUT_OF_RANGE`. For others: reopen with fresh headers (4 retries, 2-sec backoff, 15-sec timeout per attempt). Re-send unacked records in order with new wire offsets starting at 0. If retries exhaust, keep unacked records for the application to persist or replay (see [recovery.md](recovery.md)).

**Delivery is at-least-once.** See [how-it-works.md#delivery-and-duplicates](how-it-works.md#delivery-and-duplicates).

## Example: Python, JSON, non-blocking
A complete working producer is at [`examples/grpc_client.py`](../examples/grpc_client.py). It demonstrates: sender queues records, background ack reader processes cumulative acks, `flush()` waits once, and failures/rotations reopen and replay.

**Customization:** For Protobuf, set `record_type=PROTO` and `descriptor_proto`. For throughput, send batches. For metrics, hook the ack reader.

**Verify:** `SELECT count(*) FROM <catalog.schema.table>` should match or slightly exceed what you sent (duplicates from replays are normal).

## Errors
| Code | Meaning | Action |
|------|---------|--------|
| `INVALID_ARGUMENT` | Bad record or stream setup | Fix and reopen; don't retry |
| `PERMISSION_DENIED` | Missing grants | Grant `USE CATALOG`, `USE SCHEMA`, `MODIFY`, `SELECT` ([authentication.md](authentication.md)); don't retry |
| `NOT_FOUND` | Table missing | Create table; don't retry |
| `UNAUTHENTICATED` | Bad token | Get new token; retry once |
| `UNIMPLEMENTED`, `OUT_OF_RANGE` | Unsupported | Don't retry |
| `UNAVAILABLE`, `INTERNAL`, others | Transient | Reopen and replay (backoff recommended) |

See [Zerobus error reference](https://docs.databricks.com/ingestion/zerobus-errors) for details.

## Arrow Flight (columnar batches)
Arrow uses the standard **Arrow Flight `DoPut`** RPC from Apache Arrow's `Flight.proto` on the same endpoint, with the same two headers. Metadata lives in JSON `app_metadata`: client sends `{"offset_id": N}` (0 per connection), server responds with `{"ack_up_to_offset": N, ...}`. The SDK splits large batches and tracks completion via `ack_up_to_records`, not wire offsets.

**Use the Python or Rust SDK for Arrow** ([arrow-flight.md](arrow-flight.md)) unless you truly can't.

## Verification checklist
- [ ] Stubs from `rust/sdk/zerobus_service.proto` at recorded commit
- [ ] Token minted per [authentication.md](authentication.md); refreshed before expiry and per-stream
- [ ] Headers: `authorization: Bearer <token>`, `x-databricks-zerobus-table-name`
- [ ] `record_type` explicit; Protobuf includes `descriptor_proto`
- [ ] Wire offsets 0→N per stream with no gaps; one per batch
- [ ] Ingest non-blocking; buffer bounded; acks cumulative
- [ ] `close_stream_signal` → drain acks, reopen, replay
- [ ] Retryable errors reopen+replay; non-retryable ones stop (keep unacked for persistence)

## Sources
- **SDK:** [databricks/zerobus-sdk](https://github.com/databricks/zerobus-sdk) at commit `41762d8` - schema in `rust/sdk/zerobus_service.proto`; Rust core in `rust/sdk/src/stream/grpc/` and `errors.rs`; pure Go in `purego/`
- **Docs:** [Async communication](https://docs.databricks.com/ingestion/zerobus-async-communication), [Errors](https://docs.databricks.com/ingestion/zerobus-errors), [API protocols](https://docs.databricks.com/ingestion/zerobus-api-protocols)
