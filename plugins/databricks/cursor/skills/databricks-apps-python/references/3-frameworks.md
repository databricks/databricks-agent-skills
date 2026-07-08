# Supported Frameworks

**Docs**: https://docs.databricks.com/dev-tools/databricks-apps/app-runtime (app.yaml, runtime, env config) · https://docs.databricks.com/dev-tools/databricks-apps/system-env (pre-installed package versions)

All frameworks below are **pre-installed** in the Databricks Apps runtime. This guide covers only **Databricks-specific** patterns — general framework usage is out of scope.

**Default: FastAPI** unless the user explicitly asks otherwise. Streamlit / Dash / Gradio are opt-in for UI-first prototypes; Flask and Reflex are edge cases.

---

## FastAPI (default)

**Best for**: Any Python backend by default — modern async APIs, auto-generated OpenAPI/Swagger docs, JSON-serving apps, high-performance backends. Pair naturally with a JS/HTML frontend or a JSON-consuming caller.

**Critical**: Deploy with uvicorn.

```python
import os
from fastapi import FastAPI, Request
from databricks.sdk.core import Config
from databricks import sql

app = FastAPI(title="My API")
cfg = Config()

@app.get("/api/data")
async def get_data(request: Request):
    user_token = request.headers.get("x-forwarded-access-token")
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
        access_token=user_token,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
        return cursor.fetchall()
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 0.115.0 |
| app.yaml command | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| Auth header | `request.headers.get('x-forwarded-access-token')` via `Request` |

**Databricks tips**:
- Auto-generates OpenAPI docs at `/docs` (Swagger) and `/redoc`
- Databricks SQL connector is synchronous — use `asyncio.to_thread()` for async endpoints
- Natural choice for API backends serving a separate JS/React frontend (mirrors `databricks-apps` on the Node side)

---

## Flask

**Best for**: Custom REST APIs, lightweight web apps, webhook receivers. Reach for FastAPI first; use Flask when the codebase is already Flask or when its synchronous-WSGI simplicity fits better.

**Critical**: Deploy with Gunicorn — never use Flask's dev server in production.

```python
import os
from flask import Flask, request, jsonify
from databricks.sdk.core import Config
from databricks import sql

app = Flask(__name__)
cfg = Config()

@app.route("/api/data")
def get_data():
    conn = sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
        credentials_provider=lambda: cfg.authenticate,
    )
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
        return jsonify(cursor.fetchall())
```

```yaml
# app.yaml — deploy with Gunicorn (never the Flask dev server); bind to 0.0.0.0:8000.
# Pass the warehouse ID via valueFrom so it is never hardcoded in source.
command: ["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 3.0.3 |
| app.yaml command | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| Auth header | `request.headers.get('x-forwarded-access-token')` |

**Databricks tips**:
- Use connection pooling (Flask doesn't cache connections like Streamlit)
- Gunicorn workers (`-w 4`) handle concurrent requests
- Use `request.headers` for user authorization tokens

---

## Dash

**Best for**: Production dashboards, BI tools, complex interactive visualizations built with a grid of Python components. For a plain read-only dashboard consider **`databricks-aibi-dashboards`** first.

**Critical**: Always use `dash-bootstrap-components` for layout and styling.

```python
import dash
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    title="My Dashboard",
)
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 2.18.1 |
| app.yaml command | `["python", "app.py"]` |
| Default port | 8050 — override in code: `app.run(port=int(os.environ.get("DATABRICKS_APP_PORT", 8000)))` |
| Auth header | `request.headers.get('x-forwarded-access-token')` (Flask under the hood) |

**Databricks tips**:
- Use `dbc.themes.BOOTSTRAP` and `dbc.icons.FONT_AWESOME` for consistent styling
- Use Bootstrap badge color names (`"success"`, `"danger"`), not hex colors, for `dbc.Badge`
- Use `prevent_initial_call=True` on expensive callbacks
- Use `dcc.Store` for client-side caching

---

## Streamlit

**Best for**: Rapid prototyping, data-science-style apps, internal tools where the UI is a series of Python widgets and the developer wants zero frontend code. Reach for this only when the user explicitly asks for a Streamlit-style flow.

**Critical**: Always use `@st.cache_resource` for database connections.

```python
import os
import streamlit as st
from databricks.sdk.core import Config
from databricks import sql

st.set_page_config(page_title="My App", layout="wide")  # Must be first!

@st.cache_resource(ttl=300)
def get_connection():
    cfg = Config()
    return sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
        credentials_provider=lambda: cfg.authenticate,
    )
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 1.38.0 |
| app.yaml command | `["streamlit", "run", "app.py"]` |
| Auth header | `st.context.headers.get('x-forwarded-access-token')` |

**Databricks tips**:
- `st.set_page_config()` must be the **first** Streamlit command
- `@st.cache_resource` for connections/models; `@st.cache_data(ttl=...)` for query results
- Use `st.form()` to batch inputs and prevent reruns on every keystroke
- Use `st.column_config` for formatted DataFrames (currency, dates)

---

## Gradio

**Best for**: ML model demos, chat interfaces, image/audio/video processing UIs.

**Critical**: Use `gr.Request` parameter to access auth headers.

```python
import os
import gradio as gr
import requests
from databricks.sdk.core import Config

cfg = Config()

def predict(message, request: gr.Request):
    user_token = request.headers.get("x-forwarded-access-token")
    # Call the serving endpoint with the USER's token (on-behalf-of) so Unity Catalog
    # row/column filters are enforced — NOT cfg.authenticate() (the app service-principal token).
    headers = {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}
    resp = requests.post(
        f"https://{cfg.host}/serving-endpoints/my-model/invocations",
        headers=headers,
        json={"inputs": [{"prompt": message}]},
    )
    return resp.json()["predictions"][0]

demo = gr.Interface(fn=predict, inputs="text", outputs="text")
port = int(os.environ.get("DATABRICKS_APP_PORT", 8000))
demo.launch(server_name="0.0.0.0", server_port=port)
```

| Detail | Value |
|--------|-------|
| Pre-installed version | 4.44.0 |
| app.yaml command | `["python", "app.py"]` |
| Default port | 7860 — override in code: `server_port=int(os.environ.get("DATABRICKS_APP_PORT", 8000))` |
| Auth header | `request.headers.get('x-forwarded-access-token')` via `gr.Request` |

**Databricks tips**:
- Natural fit for model serving endpoint integration — pairs with the `databricks-python-sdk` skill
- Use `gr.ChatInterface` for conversational AI demos
- Use `gr.Blocks` for complex multi-component layouts

**Docs**: [gradio.app/docs](https://www.gradio.app/docs)

---

## Reflex

**Best for**: Full-stack Python apps with reactive UIs, no JavaScript required. Edge case — for a JS/React frontend prefer `databricks-apps` (AppKit); for a JSON API prefer FastAPI.

```python
import os
import reflex as rx
from databricks.sdk.core import Config

cfg = Config()

class State(rx.State):
    data: list[dict] = []

    def load_data(self):
        from databricks import sql
        conn = sql.connect(
            server_hostname=cfg.host,
            http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
            credentials_provider=lambda: cfg.authenticate,
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM catalog.schema.table LIMIT 10")
            self.data = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
```

| Detail | Value |
|--------|-------|
| app.yaml command | `["reflex", "run", "--env", "prod"]` |
| Auth header | `session.http_conn.headers.get('x-forwarded-access-token')` |

---

## Common: All Frameworks

- All frameworks are **pre-installed** — no need to add them to `requirements.txt`
- Add only additional packages your app needs to `requirements.txt`
- SDK `Config()` auto-detects credentials from injected environment variables
- Apps must bind to `DATABRICKS_APP_PORT` env var (defaults to 8000). Streamlit is auto-configured by the runtime; for other frameworks, read the env var in code or hardcode 8000 in `app.yaml` command. **Never use 8080**
- For framework-specific deployment commands, see [4-deployment.md](4-deployment.md)
- For authorization integration, see [1-authorization.md](1-authorization.md)
