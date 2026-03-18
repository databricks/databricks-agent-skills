# Databricks Apps Platform Guide

Universal platform rules that apply to ALL Databricks Apps regardless of framework (AppKit, Streamlit, FastAPI, etc.).

For non-AppKit framework-specific setup (port config, app.yaml, Streamlit gotchas), see [Other Frameworks](other-frameworks.md).

## Service Principal Permissions

**The #1 cause of runtime crashes after deployment.**

When your app uses a Databricks resource (SQL warehouse, model serving endpoint, vector search index, volume, secret scope), the app's **service principal** must have explicit permissions on that resource.

### How Permissions Work

When you declare a resource in `app.yaml` / `databricks.yml` with a `permission` field, the platform **automatically grants** that permission to the app's SP on deployment. You do NOT need to run manual `set-permissions` commands for declared resources.

```yaml
# databricks.yml — declaring resources with permissions
resources:
  apps:
    my_app:
      resources:
        - name: my-warehouse
          sql_warehouse:
            id: ${var.warehouse_id}
            permission: CAN_USE          # auto-granted to SP on deploy
        - name: my-endpoint
          serving_endpoint:
            name: ${var.endpoint_name}
            permission: CAN_QUERY        # auto-granted to SP on deploy
```

### Default Permissions by Resource Type

| Resource Type | Default Permission | Notes |
|---------------|-------------------|-------|
| SQL Warehouse | CAN_USE | Minimum for query execution |
| Model Serving Endpoint | CAN_QUERY | For inference calls |
| Vector Search Index (UC) | SELECT | UC securable of type TABLE |
| Volume (UC) | READ_VOLUME | Via UC securable |
| Secret Scope | READ | Deploying user needs MANAGE on the scope |
| Job | CAN_MANAGE_RUN | |
| Lakebase Database | CAN_CONNECT_AND_CREATE | |
| Genie Space | CAN_VIEW | |

### ⚠️ CRITICAL AGENT BEHAVIOR

Always declare resources in `databricks.yml` with the correct `permission` field — do NOT skip this. The platform handles granting automatically on deploy.

## Resource Types & Injection

**NEVER hardcode workspace-specific IDs in source code.** Always inject via environment variables with `valueFrom`.

| Resource Type | Default Key | Use Case |
|---------------|-------------|----------|
| SQL Warehouse | `sql-warehouse` | Query compute |
| Model Serving Endpoint | `serving-endpoint` | Model inference |
| Vector Search Index | `vector-search-index` | Semantic search |
| Lakebase Database | `database` | OLTP storage |
| Secret | `secret` | Sensitive values |
| UC Table | `table` | Structured data |
| UC Connection | `connection` | External data sources |
| Genie Space | `genie-space` | AI analytics |
| MLflow Experiment | `experiment` | ML tracking |
| Lakeflow Job | `job` | Data workflows |
| UDF | `function` | SQL/Python functions |
| Databricks App | `app` | App-to-app communication |

```python
# ✅ GOOD
warehouse_id = os.environ["DATABRICKS_WAREHOUSE_ID"]
```

```yaml
# app.yaml / databricks.yml env section
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: SERVING_ENDPOINT
    valueFrom: serving-endpoint
```

## Authentication: OBO vs Service Principal

| Context | When Used | Token Source | Cached Per |
|---------|-----------|--------------|------------|
| **Service Principal (SP)** | Default; background tasks, shared data | Auto-injected `DATABRICKS_CLIENT_ID` + `DATABRICKS_CLIENT_SECRET` | All users (shared) |
| **On-Behalf-Of (OBO)** | User-specific data, user-scoped access | `x-forwarded-access-token` header | Per user |

**SP auth** is auto-configured — `WorkspaceClient()` picks up injected env vars.

**OBO** requires extracting the token from request headers and declaring scopes:

| Scope | Purpose |
|-------|---------|
| `sql` | Query SQL warehouses |
| `dashboards.genie` | Manage Genie spaces |
| `files.files` | Manage files/directories |
| `iam.access-control:read` | Read permissions (default) |
| `iam.current-user:read` | Read current user info (default) |

⚠️ Databricks blocks access outside approved scopes even if the user has permission.

## Deployment Workflow

⚠️ **USER CONSENT REQUIRED** — always confirm with the user before deploying.

```bash
# Option A: single command (recommended) — validates, deploys, and runs
databricks apps deploy -t <TARGET> --profile <PROFILE>

# Option B: step by step
databricks apps validate --profile <PROFILE>
databricks bundle deploy -t <TARGET> --profile <PROFILE>
databricks bundle run <APP_RESOURCE_NAME> -t <TARGET> --profile <PROFILE>
```

❌ **Common mistake:** Running only `bundle deploy` and expecting the app to update. Deploy uploads code but does NOT apply config changes or restart the app. Use `databricks apps deploy` or add `bundle run` after `bundle deploy`.

### ⚠️ Destructive Updates Warning

`databricks apps update` (and `bundle run`) performs a **full replacement**, not a merge:
- Adding a new resource can silently **wipe** existing `user_api_scopes`
- OBO permissions may be stripped on every deployment

**Workaround:** After each deployment, verify OBO scopes are intact.

## Runtime Environment

| Constraint | Value |
|------------|-------|
| Max file size | 10 MB per file |
| Available port | Only `DATABRICKS_APP_PORT` |
| Auto-injected env vars | `DATABRICKS_HOST`, `DATABRICKS_APP_PORT`, `DATABRICKS_APP_NAME`, `DATABRICKS_WORKSPACE_ID`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` |
| No root access | Cannot use `apt-get`, `yum`, or `apk` — use PyPI/npm packages only |
| Graceful shutdown | SIGTERM → 15 seconds to shut down → SIGKILL |
| Logging | Only stdout/stderr are captured — file-based logs are lost on container recycle |
| Filesystem | Ephemeral — no persistent local storage; use UC Volumes/tables |

## Compute & Limits

| Size | RAM | vCPU | DBU/hour | Notes |
|------|-----|------|----------|-------|
| Medium | 6 GB | Up to 2 | 0.5 | Default |
| Large | 12 GB | Up to 4 | 1.0 | Select during app creation or edit |

- No GPU access. Use model serving endpoints for inference.
- Apps must start within **10 minutes** (including dependency installation).
- Max apps per workspace: **100**.

## HTTP Proxy & Streaming

The Databricks Apps reverse proxy enforces a **120-second per-request timeout** (NOT configurable).

| Behavior | Detail |
|----------|--------|
| 504 in app logs? | **No** — the error is generated at the proxy. App logs show nothing. |
| SSE streaming | Responses may be **buffered** and delivered in chunks, not token-by-token |
| WebSockets | Bypass the 120s limit — working but undocumented |

For long-running agent interactions, use **WebSockets** instead of SSE.

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `PERMISSION_DENIED` after deploy | SP missing permissions | Grant SP access to all declared resources |
| App deploys but config doesn't change | Only ran `bundle deploy` | Also run `bundle run <app-name>` |
| `File is larger than 10485760 bytes` | Bundled dependencies | Use requirements.txt / package.json |
| OBO scopes missing after deploy | Destructive update wiped them | Re-apply scopes after each deploy |
| `${var.xxx}` appears literally in env | Variables not resolved in config | Use literal values, not bundle variables |
| 504 Gateway Timeout | Request exceeded 120s | Use WebSockets for long operations |
