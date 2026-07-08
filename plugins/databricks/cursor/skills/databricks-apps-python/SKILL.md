---
name: databricks-apps-python
description: "Python backend for Databricks Apps — FastAPI (default), Flask, Dash, Streamlit, Gradio, Reflex. **Default for a new Databricks App is `databricks-apps` (AppKit — Node/TypeScript/React) — reach for it first.** Use this skill only when the user asks for a Python backend, extends an existing Python app, or the team is Python-only. Covers OAuth auth, app resources, SQL warehouse and Lakebase connectivity, foundation-model / Vector Search / model-serving APIs (via `databricks-python-sdk`), and deployment via CLI or DABs."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Databricks Applications — Python backends

> **First, confirm this skill is the right one.** The default for new Databricks Apps is **[databricks-apps](../databricks-apps/SKILL.md)** (AppKit — Node.js + TypeScript + React SDK). Load that skill first unless the user explicitly asks for a Python backend, is extending an existing Python app, or the team is Python-only. Everything below is the Python-backend alternative.

## Critical Rules for Python apps (always follow)

- **MUST** confirm framework choice or use [Python Framework Selection](#python-framework-selection) below
- **MUST** use SDK `Config()` for authentication (never hardcode tokens)
- **MUST** use `app.yaml` `valueFrom` for resources (never hardcode resource IDs)
- **MUST** use `dash-bootstrap-components` for Dash app layout and styling
- **MUST** use `@st.cache_resource` for Streamlit database connections
- **MUST** deploy Flask with Gunicorn, FastAPI with uvicorn (not dev servers)

## Required Steps for Python apps

Copy this checklist and verify each item:
```
- [ ] Framework selected
- [ ] Auth strategy decided: app auth, user auth, or both
- [ ] App resources identified (SQL warehouse, Lakebase, serving endpoint, etc.)
- [ ] Backend data strategy decided (SQL warehouse, Lakebase, or SDK)
- [ ] Deployment method: CLI or DABs
```

---

## Python Framework Selection

| Framework | Best For | app.yaml Command |
|-----------|----------|------------------|
| **FastAPI** (default) | Any Python backend by default — async APIs, auto-generated OpenAPI docs, JSON-serving apps | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]` |
| **Flask** | Custom REST APIs, lightweight apps, webhooks | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8000"]` |
| **Dash** | Production dashboards, BI tools, complex interactivity | `["python", "app.py"]` |
| **Streamlit** | Rapid prototyping, data science apps, internal tools where the UI is a series of Python widgets | `["streamlit", "run", "app.py"]` |
| **Gradio** | ML demos, model interfaces, chat UIs | `["python", "app.py"]` |
| **Reflex** | Full-stack Python apps without JavaScript | `["reflex", "run", "--env", "prod"]` |

**Default: FastAPI.** Reach for FastAPI unless the user explicitly asks for Streamlit-style widget prototyping (Streamlit), a heavy dashboard grid (Dash), or a Gradio-style ML demo. FastAPI pairs naturally with a JS/HTML frontend or a JSON-consuming caller — the same posture `databricks-apps` uses on the Node side.

---

## Quick Reference

| Concept | Details |
|---------|---------|
| **Runtime** | Python 3.11, Ubuntu 22.04, 2 vCPU, 6 GB RAM |
| **Pre-installed** | Dash 2.18.1, Streamlit 1.38.0, Gradio 4.44.0, Flask 3.0.3, FastAPI 0.115.0 |
| **Auth (app)** | Service principal via `Config()` — auto-injected `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` |
| **Auth (user)** | `x-forwarded-access-token` header — see [references/1-authorization.md](references/1-authorization.md) |
| **Resources** | `valueFrom` in app.yaml — see [references/2-app-resources.md](references/2-app-resources.md) |
| **SDK / Foundation Models / Vector Search / Model Serving** | Use the `databricks-python-sdk` skill — same `WorkspaceClient` and OpenAI-compatible foundation-model patterns work inside a Databricks App |
| **Docs** | https://docs.databricks.com/dev-tools/databricks-apps/ |

---

## Detailed Guides

**Authorization**: Use [references/1-authorization.md](references/1-authorization.md) when configuring app or user authorization — covers service principal auth, on-behalf-of user tokens, OAuth scopes, and per-framework code examples. (Keywords: OAuth, service principal, user auth, on-behalf-of, access token, scopes)

**App resources**: Use [references/2-app-resources.md](references/2-app-resources.md) when connecting your app to Databricks resources — covers SQL warehouses, Lakebase, model serving, secrets, volumes, and the `valueFrom` pattern. (Keywords: resources, valueFrom, SQL warehouse, model serving, secrets, volumes, connections)

**Frameworks**: See [references/3-frameworks.md](references/3-frameworks.md) for Databricks-specific patterns per framework — FastAPI (default), Flask, Dash, Streamlit, Gradio, Reflex — with auth integration and deployment commands. (Keywords: FastAPI, Flask, Dash, Streamlit, Gradio, Reflex, framework selection)

**Deployment**: Use [references/4-deployment.md](references/4-deployment.md) when deploying your app — covers Databricks CLI, Asset Bundles (DABs), app.yaml configuration, and post-deployment verification. (Keywords: deploy, CLI, DABs, asset bundles, app.yaml, logs)

**Lakebase**: Use [references/5-lakebase.md](references/5-lakebase.md) when using Lakebase (PostgreSQL) as your app's data layer — covers auto-injected env vars, psycopg2/asyncpg patterns, and when to choose Lakebase vs SQL warehouse. (Keywords: Lakebase, PostgreSQL, psycopg2, asyncpg, transactional, PGHOST)

**CLI commands**: Use [references/6-cli-approach.md](references/6-cli-approach.md) for managing app lifecycle via CLI — covers creating, deploying, monitoring, and deleting apps. (Keywords: CLI, create app, deploy app, app logs)

**Foundation Models / SDK / Vector Search / Model Serving**: Use the **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** skill for the OpenAI-compatible foundation-model client, `WorkspaceClient` calls, Vector Search, and model-serving invocation — the same patterns apply inside a Databricks App. The examples in this skill's `examples/` folder (`fm-minimal-chat.py`, `fm-parallel-calls.py`, `fm-structured-outputs.py`, `llm_config.py`) show the App-side wiring only.

---

## Workflow

1. Determine the task type:

   **New app from scratch?** → Load **[databricks-apps](../databricks-apps/SKILL.md)** first (AppKit / Node). Only stay in this skill if the user explicitly asks for a Python backend.
   **Python-backend confirmed?** → [Python Framework Selection](#python-framework-selection) — default to FastAPI.
   **Setting up authorization?** → Read [references/1-authorization.md](references/1-authorization.md)
   **Connecting to data/resources?** → Read [references/2-app-resources.md](references/2-app-resources.md)
   **Using Lakebase (PostgreSQL)?** → Read [references/5-lakebase.md](references/5-lakebase.md)
   **Deploying to Databricks?** → Read [references/4-deployment.md](references/4-deployment.md)
   **Using CLI for app lifecycle?** → Read [references/6-cli-approach.md](references/6-cli-approach.md)
   **Calling foundation model / LLM APIs, Vector Search, or model-serving endpoints?** → Load the **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** skill. This skill's `examples/` folder shows only the App-side wiring on top of those SDK patterns.

2. Follow the instructions in the relevant guide.

---

## Core Architecture

All Python Databricks apps follow this pattern:

```
app-directory/
├── app.py                 # Main application (or framework-specific name)
├── models.py              # Pydantic data models
├── backend.py             # Data access layer
├── requirements.txt       # Additional Python dependencies
├── app.yaml               # Databricks Apps configuration
└── README.md
```

### Backend Toggle Pattern

```python
import os
from databricks.sdk.core import Config

USE_MOCK = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"

if USE_MOCK:
    from backend_mock import MockBackend as Backend
else:
    from backend_real import RealBackend as Backend

backend = Backend()
```

### SQL Warehouse Connection (shared across all frameworks)

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()  # Auto-detects credentials from environment
conn = sql.connect(
    server_hostname=cfg.host,
    http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
    credentials_provider=lambda: cfg.authenticate,
)
```

### Pydantic Models

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class Status(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"

class EntityOut(BaseModel):
    id: str
    name: str
    status: Status
    created_at: datetime

class EntityIn(BaseModel):
    name: str = Field(..., min_length=1)
    status: Status = Status.PENDING
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Connection exhausted** | Use `@st.cache_resource` (Streamlit) or connection pooling |
| **Auth token not found** | Check `x-forwarded-access-token` header — only available when deployed, not locally |
| **App won't start** | Check `app.yaml` command matches framework; check `databricks apps logs <name>` |
| **Resource not accessible** | Add resource via UI, verify SP has permissions, use `valueFrom` in app.yaml |
| **Import error on deploy** | Add missing packages to `requirements.txt` (pre-installed packages don't need listing) |
| **Lakebase app crashes on start** | `psycopg2`/`asyncpg` are NOT pre-installed — MUST add to `requirements.txt` |
| **Port conflict** | Apps must bind to `DATABRICKS_APP_PORT` env var (defaults to 8000). Never use 8080. Streamlit is auto-configured; for others, read the env var in code or use 8000 in app.yaml command |
| **Streamlit: set_page_config error** | `st.set_page_config()` must be the first Streamlit command |
| **Dash: unstyled layout** | Add `dash-bootstrap-components`; use `dbc.themes.BOOTSTRAP` |
| **Slow queries** | Use Lakebase for transactional/low-latency; SQL warehouse for analytical queries |

---

## Platform Constraints

| Constraint | Details |
|------------|---------|
| **Runtime** | Python 3.11, Ubuntu 22.04 LTS |
| **Compute** | 2 vCPUs, 6 GB memory (default) |
| **Pre-installed frameworks** | Dash, Streamlit, Gradio, Flask, FastAPI, Shiny |
| **Custom packages** | Add to `requirements.txt` in app root |
| **Network** | Apps can reach Databricks APIs; external access depends on workspace config |
| **User auth** | Public Preview — workspace admin must enable before adding scopes |

---

## Official Documentation

- **[Databricks Apps Overview](https://docs.databricks.com/dev-tools/databricks-apps/)** — main docs hub
- **[Authorization](https://docs.databricks.com/dev-tools/databricks-apps/auth)** — app auth and user auth
- **[Resources](https://docs.databricks.com/dev-tools/databricks-apps/resources)** — SQL warehouse, Lakebase, serving, secrets
- **[app.yaml Reference](https://docs.databricks.com/dev-tools/databricks-apps/app-runtime)** — command and env config
- **[System Environment](https://docs.databricks.com/dev-tools/databricks-apps/system-env)** — pre-installed packages, runtime details

## Related Skills

- **[databricks-apps](../databricks-apps/SKILL.md)** — the default for new Databricks Apps (AppKit / Node / TypeScript + React); load it first unless a Python backend is explicitly required
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — `WorkspaceClient`, OpenAI-compatible foundation-model client, Vector Search, model-serving invocation; the same patterns work inside a Databricks App
- **[databricks-lakebase](../databricks-lakebase/SKILL.md)** — persistent PostgreSQL state (autoscaling managed PG with branching)
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** — endpoint lifecycle for ML models an App calls
- **databricks-dabs** — deploying apps via DABs
