# Authentication, endpoints, and permissions

Read this to set up credentials, find the endpoint, grant permissions, decide where credentials live (local vs deployed), or debug auth errors. Content comes from the Zerobus docs ("Use Zerobus Ingest") and the SDK READMEs, so you don't need to fetch them.

## Auth methods
| Method | Status | Use it when |
|--------|--------|-------------|
| **OAuth machine-to-machine with a Databricks service principal** (client ID + client secret) | **Official, documented.** The default for every SDK, REST, OTLP, the Apache Kafka-compatible producer APIs, and MQTT | Always, unless the user's organization requires identity federation |
| **The Databricks App's own service principal** | Same OAuth M2M; credentials are injected into the app | The producer runs inside a Databricks App ([databricks-apps.md](databricks-apps.md)) |
| **External IdP federation (for example Microsoft Entra ID)**: account-level or workload identity federation | **Supported in the Python and Rust SDKs** (documented in their READMEs). **Not yet in the official Zerobus docs** | The organization forbids long-lived Databricks secrets and already issues IdP tokens to workloads. Confirm the SDK version supports it |

Personal access tokens aren't documented for Zerobus. Don't recommend them.

## Step 1: Find the workspace URL, workspace ID, region, and endpoint
Endpoint = workspace ID + region + cloud. **CLI:** `databricks metastores summary --profile <PROFILE>` gives cloud and region. **UI:** workspace URL is before `/?o=`; workspace ID is after `o=` (or after `adb-` on Azure); region is in the workspace switcher.

Alternatives: SQL `SELECT current_metastore()` returns `<cloud>:<region>:<uuid>`; Python SDK `WorkspaceClient().metastores.summary().region`.

| Cloud | Workspace URL | Zerobus server endpoint |
|-------|---------------|-------------------------|
| **AWS** | `https://<instance>.cloud.databricks.com` | `<workspace-id>.zerobus.<region>.cloud.databricks.com` |
| **Azure** | `https://<instance>.azuredatabricks.net` | `<workspace-id>.zerobus.<region>.azuredatabricks.net` |
| **GCP** | `https://<instance>.gcp.databricks.com` | `<workspace-id>.zerobus.<region>.gcp.databricks.com` |

Example (AWS): full URL `https://company-workspace.cloud.databricks.com/?o=1111111111111111`, so the workspace URL is `https://company-workspace.cloud.databricks.com`, the workspace ID is `1111111111111111`, and the endpoint is `1111111111111111.zerobus.us-west-2.cloud.databricks.com`.

SDKs accept the endpoint with the `https://` scheme (current READMEs show it; the Rust README notes the scheme is optional). Region availability changes; check the availability section of the [quotas page](https://docs.databricks.com/ingestion/zerobus-quotas) before promising a region.

**Verify:** the workspace ID and region in the endpoint match what the CLI (or the UI) returned. **Expected:** both match.

## Step 2: Create or identify the target table
**Create before producers run.** Zerobus writes to **managed Delta** and **streaming tables** (same limits, quotas); tables on default storage are Public Preview. Design with [schema-management.md](schema-management.md). **OpenTelemetry:** predefined schema per signal; use `CREATE TABLE` statements in [docs](https://docs.databricks.com/ingestion/opentelemetry/configure#create-tables).

## Step 3: Create a service principal and secret
**UI** (from the docs):
1. **Settings** > **Identity and Access** > **Service principals** > **Manage** > **Add service principal** > **Add new**.
2. Generate and save the **client ID** and **client secret**.
3. On the **Configurations** tab, make sure the **Workspace access** entitlement is selected. **Zerobus requires it.**
4. Copy the **Application Id** (UUID) for the grants.

**CLI:**
```bash
databricks service-principals create --display-name "zerobus-producer" --profile <PROFILE>
# note the numeric "id" and the "applicationId" in the output
databricks service-principal-secrets-proxy create <service-principal-numeric-id> --profile <PROFILE>
# returns the OAuth secret; store it immediately, it isn't shown again
```
Then confirm the **Workspace access** entitlement in the UI.

**Ask before creating.** If the user is new to Databricks, explain that a service principal is a non-human identity for their producer, and offer to create it.

## Step 4: Grant permissions on the table
```sql
GRANT USE CATALOG ON CATALOG <catalog> TO `<application-id>`;
GRANT USE SCHEMA ON SCHEMA <catalog.schema> TO `<application-id>`;
GRANT MODIFY, SELECT ON TABLE <catalog.schema.table> TO `<application-id>`;
```
**`ALL PRIVILEGES` is not sufficient for Zerobus.** Even if the service principal already has `ALL PRIVILEGES`, grant these four explicitly: `USE CATALOG`, `USE SCHEMA`, `MODIFY`, and `SELECT`.

Grant `MODIFY` and `SELECT` **directly on the table**. Inherited schema-level grants may not satisfy the table-scoped OAuth token Zerobus uses (`authorization_details`), which shows up as **error 4024**.

**Verify:** `SHOW GRANTS ON TABLE <catalog.schema.table>`. **Expected:** the application ID has `MODIFY` and `SELECT` listed explicitly, not only `ALL PRIVILEGES`.

## Step 5: Store credentials (local vs deployed)
**Never hard-code secrets.** The SDKs need five values; use these environment variable names across the skill:
```bash
export ZEROBUS_SERVER_ENDPOINT="https://<workspace-id>.zerobus.<region>.cloud.databricks.com"
export DATABRICKS_WORKSPACE_URL="https://<instance>.cloud.databricks.com"
export ZEROBUS_TABLE_NAME="<catalog.schema.table>"
export DATABRICKS_CLIENT_ID="<application-id>"
export DATABRICKS_CLIENT_SECRET="<client-secret>"
export DATABRICKS_WORKSPACE_ID="<workspace-id>"   # REST and the Kafka-compatible APIs need it for the token request
```

| Where the producer runs | Where credentials live |
|-------------------------|------------------------|
| **Laptop / local development** | Shell environment variables or an untracked `.env` file (add it to `.gitignore`) |
| **Your service, container, or Kubernetes** | Your platform's secret manager, injected as environment variables at runtime |
| **Databricks Lakeflow Job** | A Databricks **secret scope**, referenced as `{{secrets/<scope>/<key>}}` in the job's environment variables ([databricks-apps.md](databricks-apps.md)) |
| **Databricks App** | Nothing to store: use the app's injected `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET` and grant that service principal on the table ([databricks-apps.md](databricks-apps.md)) |
| **Edge or serverless function using REST** | The platform's secret store; mint a token per the REST flow ([rest.md](rest.md)) |

## How tokens work
- **SDKs:** The SDK obtains and **auto-refreshes** table-scoped OAuth tokens. Don't manage tokens yourself.
- **REST / Kafka / MQTT / gRPC:** Request tokens yourself (see [Table-scoped tokens](#table-scoped-tokens-rest-kafka-mqtt-grpc) below). Tokens **expire in about 1 hour**; refresh before expiry.

## Table-scoped tokens (REST, Kafka, MQTT, gRPC)

The SDKs mint and refresh tokens for you. For REST, the Kafka-compatible APIs, MQTT, or a raw gRPC client, request a **table-scoped token** from the workspace's OAuth endpoint. It uses the env vars from Step 5, including `DATABRICKS_WORKSPACE_ID`.

**Shell** (from the docs):
```bash
IFS=. read -r CATALOG SCHEMA TABLE <<< "$ZEROBUS_TABLE_NAME"
authorization_details=$(cat <<EOF
[{"type": "unity_catalog_privileges", "privileges": ["USE CATALOG"], "object_type": "CATALOG", "object_full_path": "$CATALOG"},
 {"type": "unity_catalog_privileges", "privileges": ["USE SCHEMA"], "object_type": "SCHEMA", "object_full_path": "$CATALOG.$SCHEMA"},
 {"type": "unity_catalog_privileges", "privileges": ["SELECT", "MODIFY"], "object_type": "TABLE", "object_full_path": "$CATALOG.$SCHEMA.$TABLE"}]
EOF
)
export OAUTH_TOKEN=$(curl -s -X POST \
  -u "$DATABRICKS_CLIENT_ID:$DATABRICKS_CLIENT_SECRET" \
  -d "grant_type=client_credentials" \
  -d "scope=all-apis" \
  -d "resource=api://databricks/workspaces/$DATABRICKS_WORKSPACE_ID/zerobusDirectWriteApi" \
  --data-urlencode "authorization_details=$authorization_details" \
  "$DATABRICKS_WORKSPACE_URL/oidc/v1/token" | jq -r '.access_token')
```
**Verify:** `echo "${OAUTH_TOKEN:0:10}"` prints the start of a token, not `null`. **Expected:** a `null` means the client ID, secret, workspace ID, or grants are wrong ([Auth errors](#auth-errors)).

**Python** (the same request; rest.md and kafka.md reuse this function):
```python
import json, os
import requests

def fetch_zerobus_token() -> tuple[str, int]:
    """Return (access_token, expires_in_seconds) for the table in ZEROBUS_TABLE_NAME."""
    table = os.environ["ZEROBUS_TABLE_NAME"]
    catalog, schema, _ = table.split(".")
    authorization_details = [
        {"type": "unity_catalog_privileges", "privileges": ["USE CATALOG"],
         "object_type": "CATALOG", "object_full_path": catalog},
        {"type": "unity_catalog_privileges", "privileges": ["USE SCHEMA"],
         "object_type": "SCHEMA", "object_full_path": f"{catalog}.{schema}"},
        {"type": "unity_catalog_privileges", "privileges": ["SELECT", "MODIFY"],
         "object_type": "TABLE", "object_full_path": table},
    ]
    resp = requests.post(
        f"{os.environ['DATABRICKS_WORKSPACE_URL']}/oidc/v1/token",
        auth=(os.environ["DATABRICKS_CLIENT_ID"], os.environ["DATABRICKS_CLIENT_SECRET"]),
        data={
            "grant_type": "client_credentials",
            "scope": "all-apis",
            "resource": f"api://databricks/workspaces/{os.environ['DATABRICKS_WORKSPACE_ID']}/zerobusDirectWriteApi",
            "authorization_details": json.dumps(authorization_details),
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    return body["access_token"], int(body.get("expires_in", 3600))
```

**SDK difference:** the SDKs' own token request also adds `"operations": ["zerobuswrite"]` to the table entry (`rust/sdk/src/default_token_factory.rs`). The documented request above doesn't need it for REST, Kafka, or MQTT; the raw gRPC example ([../examples/grpc_client.py](../examples/grpc_client.py)) sends it, matching the SDK.

**Refresh rule.** Tokens expire after about **1 hour**. Cache the token, fetch a new one a few minutes before `expires_in` runs out, and on HTTP 401 fetch a new token and retry once. MQTT checks the token only at CONNECT, so use a fresh token on every reconnect ([mqtt.md](mqtt.md)).

## Identity federation (Entra ID): SDK-supported, docs pending
**Status:** Supported in Python and Rust SDKs; not yet in official docs. Ask users to confirm their SDK version includes it.

Two modes: **account-level** (synced identity, no Databricks SP) or **workload** (SP client ID, no secret). The SDK swaps the external IdP token for a Databricks token (RFC 8693 token exchange). For examples and caveats (keep callbacks fast; use async for network I/O), see the Python SDK README and the Rust README ("External-IdP federation").

Other SDKs: use OAuth with a service principal.

## Auth errors
| Symptom | Cause | Fix |
|---------|-------|-----|
| `401 Unauthorized`, or stream creation fails with an auth error | Wrong client ID or secret, or the secret was revoked | Check the env vars; create a new secret if needed |
| REST calls start failing after about an hour | The REST OAuth token expired (1-hour lifetime) | Fetch a new token before expiry ([rest.md](rest.md)) |
| **Error 4024** / `authorization_details` | Missing table-level grants | Grant `MODIFY`, `SELECT` directly on the table (Step 4) |
| Permission or 4024 errors, and the service principal has `ALL PRIVILEGES` | `ALL PRIVILEGES` doesn't satisfy Zerobus | Grant `USE CATALOG`, `USE SCHEMA`, `MODIFY`, and `SELECT` explicitly (Step 4) |
| Permission errors despite correct grants | The **Workspace access** entitlement is missing | Enable it on the service principal's Configurations tab |
| Auth fails against the endpoint | The endpoint's workspace ID or region doesn't match the workspace URL | Recheck Step 1 |
| Federation: token exchange fails | Identity not synced (account-level) or no federation policy (workload) | Fix the prerequisite; confirm the SDK version supports federation |

## Install the SDK
| Language | Install | Reference |
|----------|---------|-----------|
| Python 3.9+ | `pip install databricks-zerobus-ingest-sdk` (on Databricks: a cluster library on classic compute, or an environment dependency on serverless) | [python-sdk.md](python-sdk.md) |
| TypeScript (Node.js 16+) | `npm install @databricks/zerobus-ingest-sdk` | [typescript-sdk.md](typescript-sdk.md) |
| Go | see the Go reference (`go/` with cgo, or `purego/`) | [go-sdk.md](go-sdk.md) |
| Java 8+ | Maven `com.databricks:zerobus-ingest-sdk` | [java-sdk.md](java-sdk.md) |
| Rust, C++, .NET | see the reference | [other-sdks.md](other-sdks.md) |

## Verification checklist
- [ ] Endpoint matches the workspace ID, region, and cloud
- [ ] Target table exists ([schema-management.md](schema-management.md))
- [ ] Service principal has the **Workspace access** entitlement
- [ ] `SHOW GRANTS ON TABLE` shows `MODIFY` and `SELECT` for the service principal, granted explicitly (`ALL PRIVILEGES` alone isn't enough)
- [ ] Credentials come from environment variables or a secret store, not code
- [ ] Outbound HTTPS (443) to the endpoint and workspace URL ([networking.md](networking.md))

## Sources
- [Use Zerobus Ingest](https://docs.databricks.com/ingestion/zerobus-ingest) (endpoints, service principal, grants, REST token)
- [Zerobus recovery](https://docs.databricks.com/ingestion/zerobus-recovery) (token refresh during recovery)
- [OAuth M2M for service principals](https://docs.databricks.com/dev-tools/auth/oauth-m2m)
- [Python SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md) ("Authentication", "External-IdP federation")
- [Rust SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/rust/README.md) ("External-IdP federation")
