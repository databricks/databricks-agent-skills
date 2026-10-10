# Run a Zerobus producer in a Databricks App or Lakeflow Job

Read this when the producer runs **inside Databricks**. Most producers run outside; use a Job only as a test harness unless data originates inside (e.g., App receiving HTTP events).

## Databricks Apps

- **Runtime:** Ubuntu 22.04, Python 3.11, Node 22. Python SDK supports 3.9 to 3.14.
- **Credentials injected:** `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`, `DATABRICKS_HOST` (workspace URL), `DATABRICKS_WORKSPACE_ID`. Each app has its own service principal.
- **Stream:** long-lived web process. Open once, reuse. Shutdown: SIGTERM allows 15 seconds.

For app build/deploy, use **databricks-apps** / **databricks-apps-python** skills. This section covers Zerobus only.

### Step 1: Grant the app's service principal
Find the app's SP (in app details or `databricks apps get <app-name>`), then grant it: [authentication.md Step 4](authentication.md#step-4-grant-permissions-on-the-table). **Verify:** `SHOW GRANTS ON TABLE ...` shows app's SP with `MODIFY` and `SELECT`.

### Step 2: Configure `app.yaml`
Non-secret values go in `env` with `value`. The credentials are already injected, so don't add them.
```yaml
env:
  - name: ZEROBUS_SERVER_ENDPOINT
    value: "https://<workspace-id>.zerobus.<region>.cloud.databricks.com"
  - name: ZEROBUS_TABLE_NAME
    value: "<catalog.schema.table>"
```
If you use a **different** service principal than the app's own, store its secret in a secret scope, declare it as a `secret` resource, and bind it with `valueFrom` (DevHub Apps configuration docs, "Secrets"). **Never put secrets in `value`.**

Add `databricks-zerobus-ingest-sdk` to `requirements.txt`.

### Step 3: Open one stream for the life of the app
```python
import os
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import TableProperties

sdk = ZerobusSdk(os.environ["ZEROBUS_SERVER_ENDPOINT"], os.environ["DATABRICKS_HOST"])
stream = sdk.create_stream(
    os.environ["DATABRICKS_CLIENT_ID"],
    os.environ["DATABRICKS_CLIENT_SECRET"],
    TableProperties(os.environ["ZEROBUS_TABLE_NAME"]),
)

def handle_event(event: dict):
    stream.ingest_record_offset(event)  # queue only; SDK sends in background
```
**Don't create per request.** Streams are long-lived. Use an **ack callback** ([python-sdk.md](python-sdk.md)) for logging; call `stream.flush()` then `stream.close()` from shutdown handler (SIGTERM allows 15 seconds). Use injected `DATABRICKS_HOST` as workspace URL (prefix `https://` if missing).

**Verify:** send test event, wait ~5 seconds, run SKILL.md Step 6 query. **Expected:** row count +1.

## Lakeflow Jobs

Use a Job for batch/scheduled production or testing.

### Step 1: Store credentials
```bash
databricks secrets create-scope zerobus --profile <PROFILE>
databricks secrets put-secret zerobus client_secret --profile <PROFILE>   # prompts for the value, so it stays out of shell history
```

### Step 2: Install SDK and configure job
Add `databricks-zerobus-ingest-sdk` to job (cluster library on classic, environment dependency on serverless). Reference the secret with `{{secrets/<scope>/<key>}}`.

Excerpt (the `spark_env_vars` field of the job cluster spec):
```json
"spark_env_vars": {
  "ZEROBUS_SERVER_ENDPOINT": "https://<workspace-id>.zerobus.<region>.cloud.databricks.com",
  "DATABRICKS_WORKSPACE_URL": "https://<workspace>.cloud.databricks.com",
  "ZEROBUS_TABLE_NAME": "<catalog.schema.table>",
  "DATABRICKS_CLIENT_ID": "<service-principal-application-id>",
  "DATABRICKS_CLIENT_SECRET": "{{secrets/zerobus/client_secret}}"
}
```
Install the SDK through library configuration, not `pip install` at runtime. If your compute can't install the SDK, use the [REST API](rest.md) instead. To deploy the job as code, use the **databricks-dabs** skill.

### Step 3: Producer script
```python
import os
from datetime import datetime, timezone
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import TableProperties

sdk = ZerobusSdk(os.environ["ZEROBUS_SERVER_ENDPOINT"], os.environ["DATABRICKS_WORKSPACE_URL"])
stream = sdk.create_stream(
    os.environ["DATABRICKS_CLIENT_ID"],
    os.environ["DATABRICKS_CLIENT_SECRET"],
    TableProperties(os.environ["ZEROBUS_TABLE_NAME"]),
)
try:
    for i in range(1000):
        stream.ingest_record_offset({
            "device_id": f"device-{i % 10}",
            "temperature": 20 + (i % 20),
            # TIMESTAMP columns take epoch microseconds, not seconds
            "event_time": int(datetime.now(timezone.utc).timestamp() * 1_000_000),
        })
    stream.flush()
finally:
    stream.close()
```
**Verify:** `databricks jobs get-run-output <run-id> --profile <PROFILE>` shows no errors, then run the Step 6 query from SKILL.md. **Expected:** the row count rises by 1,000.

## Sources
- [DevHub: Databricks Apps configuration](https://developers.databricks.com/docs/apps/configuration) (injected variables, secrets, constraints)
- [Python SDK README](https://raw.githubusercontent.com/databricks/zerobus-sdk/main/python/README.md)
- [Use Zerobus Ingest](https://docs.databricks.com/ingestion/zerobus-ingest) (grants)
- [Databricks secrets](https://docs.databricks.com/security/secrets/) and [secrets in environment variables](https://docs.databricks.com/security/secrets/secrets-spark-conf-env-var)
