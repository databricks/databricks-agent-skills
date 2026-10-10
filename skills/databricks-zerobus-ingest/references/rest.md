# REST API

Read this when the producer **can't run an SDK**, for example an **edge runtime** (Cloudflare Workers, Deno Deploy) that can't load native libraries, a language without an SDK, or a fleet of lightweight devices that **send infrequently**. Content comes from the Zerobus docs ("Use Zerobus Ingest" REST tab, API protocols, quotas), so you don't need to fetch them.

**Status:** GA.

## When to use REST (and when not)
"The REST interface is **stateless**: each request completes on its own without holding an open connection," a fit for "large fleets of lightweight or intermittent producers."

| Use REST | Use an SDK instead |
|----------|--------------------|
| Edge runtimes and serverless functions outside Databricks that can't load the SDK's native library | Sustained or high-volume producers. "The SDKs over gRPC will sustain higher throughput than issuing many individual REST requests" |
| Devices that report occasionally and can't hold a connection | You need ack callbacks, an in-flight buffer, built-in recovery, or Protobuf |
| Languages without an SDK | |

## How the API works
| Item | Value |
|------|-------|
| **Method and URL** | `POST <zerobus-endpoint>/zerobus/v1/tables/<catalog>.<schema>.<table>/insert` |
| **Endpoint** | `https://<workspace-id>.zerobus.<region>.cloud.databricks.com` (AWS), `.azuredatabricks.net` (Azure), `.gcp.databricks.com` (GCP) |
| **Headers** | `Content-Type: application/json` (JSON is the only format) and `Authorization: Bearer <token>` |
| **Body** | A **JSON array** of record objects that match the table schema. One request can carry several records |
| **Success** | **HTTP 200** with an **empty JSON** response |
| **Quota** | **10,000 REST requests per second** (default, adjustable). Batch records into arrays to stay under it |
| **Record size** | 10 MB per record (10,485,760 bytes) |
| **Auth** | A **table-scoped OAuth token** that **expires every hour** (see below) |
| **Delivery** | At-least-once. See [how-it-works.md#delivery-and-duplicates](how-it-works.md#delivery-and-duplicates) |
| **Ordering** | Ordering across separate REST requests isn't documented. If order matters, include a sequence number or event time |

## Authentication
Every request needs a **table-scoped OAuth token** in the `Authorization: Bearer` header. Get it with the shell request or the `fetch_zerobus_token()` function in [authentication.md](authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc).

**Token lifetime:** about 1 hour. Long-running producers follow the refresh rule in [authentication.md](authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc): cache, refresh before expiry, and on HTTP 401 refresh once and retry.

Prerequisites: the grants in [authentication.md](authentication.md#step-4-grant-permissions-on-the-table) Step 4 and the env vars in Step 5.

## Step 1: Smoke test with curl
Export `OAUTH_TOKEN` with the shell request in [authentication.md](authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc), then send records. For long-running producers, use Step 2.

```bash
# OAUTH_TOKEN comes from the shell request in authentication.md (Table-scoped tokens)
curl -X POST "$ZEROBUS_SERVER_ENDPOINT/zerobus/v1/tables/$ZEROBUS_TABLE_NAME/insert" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OAUTH_TOKEN" \
  -d '[{"device_name": "device_1", "temp": 28}]'
```
**Verify:** the response is `{}` with HTTP 200. **Expected:** rows appear in the table about 5 seconds later.

## Step 2: Long-running producer with token refresh (Python)
Uses `fetch_zerobus_token()` from [authentication.md](authentication.md#table-scoped-tokens-rest-kafka-mqtt-grpc) (paste it above this code).
```python
import os, time
import requests

_token, _expires_at = None, 0.0

def get_token(force: bool = False) -> str:
    global _token, _expires_at
    if force or _token is None or time.time() > _expires_at - 300:  # refresh 5 minutes early
        _token, expires_in = fetch_zerobus_token()  # noqa: F821 (defined in authentication.md)
        _expires_at = time.time() + expires_in
    return _token

def send(records: list[dict]) -> None:
    url = f"{os.environ['ZEROBUS_SERVER_ENDPOINT']}/zerobus/v1/tables/{os.environ['ZEROBUS_TABLE_NAME']}/insert"
    for attempt in range(2):  # retry once on 401 with a fresh token
        resp = requests.post(url, headers={"Authorization": f"Bearer {get_token(force=attempt > 0)}"},
                             json=records, timeout=30)
        if resp.status_code != 401:
            resp.raise_for_status()
            return
    resp.raise_for_status()

send([{"device_name": "sensor-1", "temp": 20}])
```
**Verify:** let it run past 60 minutes; token auto-refreshes. **Expected:** HTTP 200 with no 401s.

## Step 3: Edge runtime (TypeScript: Cloudflare Workers, Deno Deploy)
Edge runtimes can't load the SDK's native library, so use REST with `fetch`. Apply the same token-refresh pattern as Step 2. Store the secret in the environment (Cloudflare Workers) or `Deno.env.get(...)` (Deno Deploy). For a complete example, see the SDK repo's `typescript/examples/` directory.

## Errors
| Code | Cause | Fix |
|------|-------|-----|
| **401** (after ~1 hour) | Token expired | Refresh it; don't reuse a one-shot token |
| **401** (right away) | Wrong credentials, `resource`, or `authorization_details` | Check env vars and the token request |
| **4024** (authorization error) | Missing table-level grants | Grant `USE CATALOG`, `USE SCHEMA`, `MODIFY`, `SELECT` ([authentication.md](authentication.md)) |
| **Other 4xx** | Schema mismatch or bad JSON | Fix the payload or add a rescue column ([schema-management.md](schema-management.md)) |
| **429** (throttled) | Over the 10,000 requests/sec quota | Batch records, or move to an SDK |

## Networking
Outbound **HTTPS (443)** to the Zerobus endpoint and to the workspace URL (for the token). **Front-end PrivateLink is supported** for REST ([networking.md](networking.md)).

## Sources
- [Use Zerobus Ingest: Write a client (REST API)](https://docs.databricks.com/ingestion/zerobus-ingest#write-a-client)
- [Zerobus API protocols: REST](https://docs.databricks.com/ingestion/zerobus-api-protocols)
- [Zerobus Ingest quotas](https://docs.databricks.com/ingestion/zerobus-quotas)
