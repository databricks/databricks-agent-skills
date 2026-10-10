# MQTT v5 endpoint

Read this when the user's devices, gateways, or applications already publish **MQTT v5** messages (IoT, edge, telemetry) and they want that data in a Delta table. Zerobus provides an **MQTT v5 endpoint**: each message carries one JSON object and is written directly to an existing Unity Catalog table. It isn't an MQTT broker; there are **no subscriptions** and no other broker features. Content comes from the Zerobus MQTT docs, so you don't need to fetch them.

**Status:** Beta. A workspace admin must turn on **Zerobus Ingest MQTT Endpoint** on the workspace **Previews** page.


## When to use it
| Use the MQTT endpoint | Use something else |
|---|---|
| Devices/gateways send **MQTT v5** + **JSON** | Client needs MQTT 3.1.1, QoS 2, or subscriptions |
| | Multiple consumers need to subscribe → keep MQTT broker |
| | Need PrivateLink → use SDK or REST |

## How MQTT concepts map to Zerobus
| MQTT | Zerobus |
|-----|---------|
| **Connection** | Targets **one table**; open another for another table |
| **Topic** | Full table name (`catalog.schema.table`) in every `PUBLISH` |
| **Payload** | **One UTF-8 JSON object** matching the schema |
| **QoS 1** | `PUBACK` arrives after the record is durable; treat it as acknowledged when `PUBACK` reason code is 0 |
| **QoS 0** | Best-effort; no acknowledgment or failure response |
| **QoS 2** | Not supported |
| **Durable vs queryable** | `PUBACK` = durable, rows appear ~5 sec later ([how-it-works.md#the-data-path](how-it-works.md#the-data-path)) |
| **Delivery** | At-least-once with QoS 1; retries can create duplicates ([how-it-works.md#delivery-and-duplicates](how-it-works.md#delivery-and-duplicates)) |
| **Subscriptions, retained messages, Last Will, session state** | Not supported |

## Prerequisites
- **MQTT Preview** enabled for the workspace (workspace admin → Previews → Zerobus Ingest MQTT Endpoint).
- **Existing Delta table** ([schema-management.md](schema-management.md)).
- **Service principal** with `USE CATALOG`, `USE SCHEMA`, `MODIFY`, `SELECT` on the table ([authentication.md](authentication.md)).
- **Workspace URL, ID, and region** ([authentication.md](authentication.md), Step 1).
- **Outbound TLS port 8883** to the endpoint.

## Connection settings
| Setting | Value |
|---------|-------|
| Host | `<workspace-id>.zerobus.<region>.cloud.databricks.com` (AWS); `.azuredatabricks.net` (Azure); `.gcp.databricks.com` (GCP); **no https://** |
| Port and transport | **8883**, TLS |
| Protocol | **MQTT v5 only** |
| Client ID | Required, non-empty, ≤128 bytes, unique per connection |
| Keep-alive | **5-300 seconds**; server closes after 1.5× the interval |
| Clean start | `True` (no session state retained) |

## Authentication
Send two **MQTT v5 User Properties** in `CONNECT`:

| Property | Value |
|----------|-------|
| `Authorization` | `Bearer <token>` (table-scoped token from [authentication.md](authentication.md)) |
| `x-databricks-zerobus-table-name` | Full table name, e.g., `main.default.air_quality` |

**Reconnect with a fresh token:** Connections have a bounded server lifetime. When Zerobus disconnects, mint a new token and reconnect (don't reuse cached tokens). Disable client library auto-reconnect; reconnect explicitly with the new token.

## Step 1: Table and environment
The docs' example table, plus an optional **`event_id`** column in case the user later needs to remove the occasional duplicate from a resend:
```sql
CREATE TABLE main.default.air_quality (
  event_id STRING,
  device_name STRING,
  temp INT,
  humidity INT
);
```
```bash
pip install "paho-mqtt>=2,<3" requests
```
Set the env vars from [authentication.md](authentication.md#step-5-store-credentials-local-vs-deployed) Step 5, including `DATABRICKS_WORKSPACE_ID`. The MQTT host is the `ZEROBUS_SERVER_ENDPOINT` host without `https://`. Never put the secret in code.

## Step 2: Publish without blocking (Python, paho-mqtt 2.x)
**Pattern:** Publish **QoS 1** records continuously; handle each `PUBACK` in the `on_publish` callback; call `flush()` at boundaries, not per-record.

A complete working publisher is at [`examples/mqtt_producer.py`](../examples/mqtt_producer.py). Key points:
- `publish()` sends and returns; the `on_publish` callback handles success (reason code 0) or failure. Keep callbacks fast.
- Zerobus advertises **Receive Maximum 4,096** QoS 1 messages per connection. Use a semaphore to bound in-flight records (backpressure).
- On disconnect, unacknowledged records are resent. Expect occasional duplicates; that's normal.
- One connection, one table. For more tables, create one publisher per table.

**Tuning:** `max_inflight` default 1,000; run in the workspace's region.

## Step 3: Verify
Query the table: `SELECT count(*) AS row_count FROM main.default.air_quality`. **Expected:** `row_count` rises by the number of acknowledged records about 5 seconds after `flush()`.

## Waiting on each PUBACK (advanced)
For connectivity testing only, publish one record and wait for its `PUBACK` before sending the next. This blocks throughput; use callbacks and `flush()` for production.

## Limits
| Item | Limit |
|------|-------|
| Protocol | MQTT v5 only |
| QoS | 0 and 1 only (QoS 2 not supported) |
| In-flight messages | **Receive Maximum 4,096** QoS 1 per connection |
| `CONNECT` packet | **16 KiB** (includes bearer token) |
| Packets after `CONNECT` | **64 KiB** (`CONNACK` Maximum Packet Size) |
| Keep-alive | 5-300 seconds |
| PrivateLink | Not supported (public endpoint only) |

## Networking
- **TLS port 8883** for MQTT + **HTTPS 443** for token requests.
- **Public endpoint only** (no PrivateLink for MQTT).
- Run publishers in the **workspace's region** for best throughput.

## Troubleshooting
| Symptom | Fix |
|---------|-----|
| Connection fails | Fix hostname (no `https://`), open egress on 8883, enable MQTT in workspace Previews |
| `CONNECT` rejected | Mint fresh token with correct `authorization_details` (see [authentication.md](authentication.md)) |
| Missing `PUBACK` | Doesn't mean the record failed; it may already be durable. Retry with fresh token on reconnect |
| Throughput capped at ~20 msg/s | Increase `max_inflight_messages_set()` toward 4,096 |
| Rows missing with QoS 0 | Use **QoS 1** for guaranteed delivery |

## Sources
- [Use MQTT with Zerobus Ingest](https://docs.databricks.com/ingestion/zerobus-mqtt) (connection model, authentication, acknowledgments, Python example, limitations, troubleshooting)
- [Zerobus API protocols: MQTT](https://docs.databricks.com/ingestion/zerobus-api-protocols#mqtt)
- [Zerobus Ingest quotas](https://docs.databricks.com/ingestion/zerobus-quotas) (delivery guarantees, MQTT packet sizes)
- [Zerobus networking](https://docs.databricks.com/ingestion/zerobus-networking) (no front-end PrivateLink for MQTT)
- [Use Zerobus Ingest](https://docs.databricks.com/ingestion/zerobus-ingest) (endpoint, service principal, token flow)
- paho-mqtt 2.1.0 source (`paho/mqtt/client.py`): default `max_inflight_messages` of 20, no use of the server's Receive Maximum or Server Keep Alive, and `on_publish` called under the internal message lock
