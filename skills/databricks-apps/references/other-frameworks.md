# Databricks Apps — Other Frameworks (Non-AppKit)

Setup guide for non-AppKit apps: Streamlit, FastAPI, Flask, Gradio, Dash, Django, Next.js, React, etc.

For universal platform rules (permissions, deployment, timeouts, resource injection), see [Platform Guide](platform-guide.md).

## 1. Port & Host Configuration

**The #1 cause of 502 Bad Gateway errors.**

| Setting | Required Value | Common Mistake |
|---------|---------------|----------------|
| Port | `DATABRICKS_APP_PORT` env var | Hardcoding 8080, 3000, or 3001 |
| Host | `0.0.0.0` | Binding to `localhost` or `127.0.0.1` |

The platform dynamically assigns a port via `DATABRICKS_APP_PORT`. Use `8000` as a local dev fallback only.

### Framework-Specific Port Configuration

#### Streamlit
```yaml
# app.yaml
command:
  - streamlit
  - run
  - app.py
  - --server.port
  - "${DATABRICKS_APP_PORT:-8000}"
  - --server.address
  - "0.0.0.0"
```

#### FastAPI / Uvicorn
```python
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

#### Flask
```python
port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
app.run(host="0.0.0.0", port=port)
```

#### Gradio
```python
demo.launch(server_name="0.0.0.0",
            server_port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))
```

#### Dash
```python
app.run(host="0.0.0.0",
        port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))
```

#### Next.js
```jsonc
// package.json
"scripts": {
  "start": "next start -p ${DATABRICKS_APP_PORT:-8000} -H 0.0.0.0"
}
```

⚠️ **Only ONE service can bind to `DATABRICKS_APP_PORT`.** If you need multiple services (e.g., frontend + backend), use a reverse proxy or serve everything from one process.

## 2. app.yaml vs databricks.yml

These two files serve different purposes. Getting them wrong causes silent deployment failures.

### app.yaml — Runtime Configuration
- Defines the **start command** and **environment variables** for the running app
- Used by the Databricks Apps runtime directly
- `valueFrom:` injects resource IDs from workspace configuration

```yaml
# app.yaml
command:
  - python
  - app.py
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: MY_CUSTOM_VAR
    value: "some-value"
```

### databricks.yml — Bundle/Deployment Configuration
- Defines the **app resource** for DABs (Declarative Automation Bundles)
- `config:` section only takes effect after `bundle run`, NOT just `bundle deploy`

```yaml
# databricks.yml
bundle:
  name: my-app-bundle

resources:
  apps:
    my-app:
      name: my-app
      source_code_path: .
      config:
        command: ['python', 'app.py']
        env:
          - name: DATABRICKS_WAREHOUSE_ID
            valueFrom: sql-warehouse
      permissions:
        - service_principal_name: ${bundle.target}.my-app
          level: CAN_MANAGE

targets:
  dev:
    default: true
```

### Critical Rules

| Rule | Why |
|------|-----|
| Always provide BOTH `app.yaml` AND `databricks.yml` config | UI deployments use app.yaml; DABs uses databricks.yml |
| Always run `bundle deploy` THEN `bundle run <app-name>` | `deploy` uploads code; `run` applies config and starts the app |
| Never use `${var.xxx}` in config env values | Variables are NOT resolved in config — values appear literally |

## 3. Using OBO in Non-AppKit Apps

```python
# FastAPI example
from fastapi import Request
from databricks.sdk import WorkspaceClient

@app.get("/user-data")
def get_user_data(request: Request):
    token = request.headers.get("x-forwarded-access-token")

    # create user-scoped client
    w = WorkspaceClient(token=token, host=os.environ["DATABRICKS_HOST"])
    # use w for user-scoped operations
```

```python
# SP auth is auto-configured — just use the SDK
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()  # picks up auto-injected env vars
```

## 4. Framework-Specific Timeout Gotchas

| Framework | Default Timeout | Fix |
|-----------|----------------|-----|
| Gradio | 30 seconds (internal) | Set `fn` timeout explicitly or use `gradio.queue()` |
| Gunicorn | 30 seconds (worker timeout) | Set `--timeout 120` in gunicorn command |
| Uvicorn | None (no default timeout) | Already fine |

## 5. Common Errors (Non-AppKit Specific)

| Error | Cause | Fix |
|-------|-------|-----|
| 502 Bad Gateway | Wrong port or host | Bind to `0.0.0.0:${DATABRICKS_APP_PORT:-8000}` |
| App works locally but 502 in prod | Binding to localhost | Change to `0.0.0.0` |
| `ModuleNotFoundError` at runtime | Dependency not in requirements.txt or version conflict | Pin exact versions; validate locally first |
| Wrong script runs on deploy | No `command` in app.yaml, platform picked wrong .py file | Always specify `command` explicitly in app.yaml |
| `apt-get: command not found` | No root access in container | Use pure-Python wheels from PyPI; no system packages |

## 6. Dependency Management

### Python

Only `requirements.txt` is natively supported. No native support for `pyproject.toml`, `uv.lock`, or Poetry.

**Workaround for `uv`:**
```
# requirements.txt
uv
```
```yaml
# app.yaml
command:
  - uv
  - run
  - app.py
```
Define actual dependencies in `pyproject.toml`. Note: This moves dependency installation from build to run step, slowing startup.

**Custom package repositories:**
- Set `PIP_INDEX_URL` as a secret in the app configuration
- Deploying user needs **MANAGE** permission on the secret scope (not just USE/READ)

### Node.js

- `package.json` is supported — `npm install` runs at startup
- Do NOT include `node_modules/` in source code (10 MB file limit)
- Large npm installs may exceed the 10-minute startup window
- In egress-restricted workspaces, add `registry.npmjs.org` to egress policy AND restart the app (egress changes require restart)

## 7. Networking & CORS

### CORS

- CORS headers are **not customizable** on the Databricks Apps reverse proxy
- Workspace origin (`*.databricks.com`) differs from app origin (`*.databricksapps.com`)
- Cross-app API calls return **302 redirect to login page** instead of the expected response

**Workaround:** Keep frontend and backend in a single app to avoid CORS entirely.

### Private Link / Hardened Environments

- Azure apps use `*.azure.databricksapps.com` — NOT `*.azuredatabricks.net`
- Existing Private Link DNS zones don't cover the apps domain
- Fix: Create a separate Private DNS Zone for `azure.databricksapps.com` with conditional DNS forwarding

### Egress Restrictions

- Egress policy changes require **app restart** to take effect
- For npm: allowlist `registry.npmjs.org`
- For pip: allowlist `pypi.org` and `files.pythonhosted.org`
- For custom registries: use `PIP_INDEX_URL` secret (see Dependency Management)

## 8. Streamlit-Specific Gotchas

### Required Environment Variables

```yaml
# app.yaml
command:
  - streamlit
  - run
  - app.py
  - --server.port
  - "${DATABRICKS_APP_PORT:-8000}"
  - --server.address
  - "0.0.0.0"
env:
  - name: STREAMLIT_SERVER_ENABLE_CORS
    value: "false"
  - name: STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION
    value: "false"
```

⚠️ **Both CORS and XSRF must be disabled** for Streamlit on Databricks Apps. The reverse proxy origin (`*.databricksapps.com`) differs from the workspace origin, triggering Streamlit's CORS/XSRF protection.

### OBO Token Staleness

Streamlit caches initial HTTP request headers, then switches to WebSocket. The OBO token from `x-forwarded-access-token` **never refreshes** — it goes stale.

**Workaround:** Periodically trigger a full page refresh. No clean in-Streamlit solution exists.

### Connection Exhaustion (Hangs After Initial Queries)

Streamlit re-runs the entire script on every user interaction. If `sql.connect()` is called during each render cycle, the rapid succession of TCP handshakes and OAuth negotiations exhausts the connection pool, causing 2-3 minute freezes.

**Fix:** Use `@st.cache_resource` to maintain persistent connections:
```python
@st.cache_resource
def get_connection():
    from databricks import sql
    from databricks.sdk.core import Config
    cfg = Config()
    return sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.environ['DATABRICKS_WAREHOUSE_ID']}",
        credentials_provider=lambda: cfg.authenticate,
    )
```

### Transient 502s During Startup

Streamlit apps commonly show brief 502 errors during startup. This is expected and does not indicate a problem.
