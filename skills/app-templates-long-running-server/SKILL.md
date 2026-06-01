---
name: app-templates-long-running-server
description: "Enable long-running background task support with LongRunningAgentServer. Use when: (1) Agent tasks may exceed HTTP timeout (~120s), (2) User wants background/async execution, (3) User says 'long running', 'background tasks', or 'async agent'."
---

# Enable Long-Running Agent Server

> **Prerequisite:** Lakebase must be configured. If not already set up, follow the **app-templates-lakebase-setup** skill first.

Upgrades from `AgentServer` to `LongRunningAgentServer`, enabling background task execution that survives HTTP timeouts. Long-running tasks are persisted to Lakebase PostgreSQL so clients can poll or stream results.

## What It Enables

| Request pattern | Description |
|---|---|
| **Standard** | `POST /responses` — blocks until complete (queries ≤ 120s) |
| **Background + Poll** | `POST /responses { background: true }` → `GET /responses/{id}` |
| **Background + Stream** | `POST /responses { background: true, stream: true }` with cursor-based resumption via `starting_after` |

---

## Step 1: Add Dependency

Add `databricks-ai-bridge[agent-server]` to `pyproject.toml`:

```toml
dependencies = [
    # ... existing dependencies ...
    "databricks-ai-bridge[agent-server]>=0.18.0",
]
```

Run `uv sync` to install.

---

## Step 2: Update `start_server.py`

Replace the basic `AgentServer` with `LongRunningAgentServer`. Key changes:

1. Import `LongRunningAgentServer` instead of `AgentServer`
2. Subclass it to override `transform_stream_event` (replaces placeholder IDs in streamed events)
3. Pass Lakebase connection config and timeout settings
4. Add a lifespan hook to initialize database tables at startup

### OpenAI SDK

```python
"""Agent server entry point. load_dotenv must run before agent imports (auth config)."""

# ruff: noqa: E402
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

import logging

from databricks_ai_bridge.long_running import LongRunningAgentServer
from mlflow.genai.agent_server import setup_mlflow_git_based_version_tracking

from agent_server.utils import lakebase_config, replace_fake_id

import agent_server.agent  # noqa: F401

logger = logging.getLogger(__name__)


class AgentServer(LongRunningAgentServer):
    def transform_stream_event(self, event, response_id):
        return replace_fake_id(event, response_id)


agent_server = AgentServer(
    "ResponsesAgent",
    enable_chat_proxy=True,
    db_instance_name=lakebase_config.instance_name,
    db_autoscaling_endpoint=lakebase_config.autoscaling_endpoint,
    db_project=lakebase_config.autoscaling_project,
    db_branch=lakebase_config.autoscaling_branch,
    task_timeout_seconds=float(os.getenv("TASK_TIMEOUT_SECONDS", "3600")),
    poll_interval_seconds=float(os.getenv("POLL_INTERVAL_SECONDS", "1.0")),
)

log_level = os.getenv("LOG_LEVEL", "INFO")
logging.getLogger("agent_server").setLevel(getattr(logging, log_level.upper(), logging.INFO))

_original_lifespan = agent_server.app.router.lifespan_context


@asynccontextmanager
async def _lifespan(app):
    # Initialize session/long-running tables at startup.
    # If using AsyncDatabricksSession, create a throwaway session and call _ensure_tables().
    async with _original_lifespan(app):
        yield


agent_server.app.router.lifespan_context = _lifespan

app = agent_server.app  # noqa: F841
setup_mlflow_git_based_version_tracking()


def main():
    agent_server.run(app_import_string="agent_server.start_server:app")
```

### LangGraph

```python
"""Agent server entry point. load_dotenv must run before agent imports (auth config)."""

# ruff: noqa: E402
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=True)

import logging

from databricks_ai_bridge.long_running import LongRunningAgentServer
from mlflow.genai.agent_server import setup_mlflow_git_based_version_tracking

from agent_server.utils import replace_fake_id, LAKEBASE_CONFIG

import agent_server.agent  # noqa: F401

logger = logging.getLogger(__name__)


class AgentServer(LongRunningAgentServer):
    def transform_stream_event(self, event, response_id):
        return replace_fake_id(event, response_id)


agent_server = AgentServer(
    "ResponsesAgent",
    enable_chat_proxy=True,
    db_instance_name=LAKEBASE_CONFIG.instance_name,
    db_autoscaling_endpoint=LAKEBASE_CONFIG.autoscaling_endpoint,
    db_project=LAKEBASE_CONFIG.autoscaling_project,
    db_branch=LAKEBASE_CONFIG.autoscaling_branch,
    task_timeout_seconds=float(os.getenv("TASK_TIMEOUT_SECONDS", "3600")),
    poll_interval_seconds=float(os.getenv("POLL_INTERVAL_SECONDS", "1.0")),
)

app = agent_server.app  # noqa: F841
setup_mlflow_git_based_version_tracking()

_original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _lifespan(app):
    # Initialize Lakebase tables at startup (e.g. run_lakebase_setup)
    try:
        async with _original_lifespan(app):
            yield
    except Exception as exc:
        logger.warning("Long-running DB init failed: %s. Background mode disabled.", exc)
        yield


app.router.lifespan_context = _lifespan


def main():
    agent_server.run(app_import_string="agent_server.start_server:app")
```

---

## Step 3: Add `replace_fake_id` Utility

Add to `utils.py` if not already present. The implementation differs by SDK:

### OpenAI SDK

```python
try:
    from agents.models.fake_id import FAKE_RESPONSES_ID
except ImportError:
    FAKE_RESPONSES_ID = "__fake_id__"


def replace_fake_id(obj, real_id: str):
    """Recursively replace FAKE_RESPONSES_ID with real_id."""
    if isinstance(obj, dict):
        return {k: replace_fake_id(v, real_id) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_fake_id(item, real_id) for item in obj]
    elif isinstance(obj, str) and obj == FAKE_RESPONSES_ID:
        return real_id
    return obj
```

### LangGraph

```python
_FAKE_ID_PREFIX = "resp_placeholder_"


def replace_fake_id(obj, real_id: str):
    """Recursively replace any resp_placeholder_* ID with real_id."""
    if isinstance(obj, dict):
        return {k: replace_fake_id(v, real_id) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_fake_id(item, real_id) for item in obj]
    elif isinstance(obj, str) and obj.startswith(_FAKE_ID_PREFIX):
        return real_id
    return obj
```

---

## Step 4: Add Lakebase Config

Add to `utils.py` if not already present. This reads Lakebase connection parameters from environment variables:

```python
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LakebaseConfig:
    instance_name: Optional[str]
    autoscaling_endpoint: Optional[str]
    autoscaling_project: Optional[str]
    autoscaling_branch: Optional[str]


def init_lakebase_config() -> LakebaseConfig:
    """Read lakebase env vars. Priority: endpoint > project+branch > instance_name."""
    endpoint = os.getenv("LAKEBASE_AUTOSCALING_ENDPOINT") or None
    raw_name = os.getenv("LAKEBASE_INSTANCE_NAME") or None
    project = os.getenv("LAKEBASE_AUTOSCALING_PROJECT") or None
    branch = os.getenv("LAKEBASE_AUTOSCALING_BRANCH") or None

    has_autoscaling = project and branch
    if not endpoint and not raw_name and not has_autoscaling:
        raise ValueError(
            "Lakebase configuration is required. Set one of:\n"
            "  LAKEBASE_AUTOSCALING_ENDPOINT=<endpoint>\n"
            "  LAKEBASE_AUTOSCALING_PROJECT + LAKEBASE_AUTOSCALING_BRANCH\n"
            "  LAKEBASE_INSTANCE_NAME=<instance-name>\n"
        )

    if endpoint:
        return LakebaseConfig(instance_name=None, autoscaling_endpoint=endpoint,
                              autoscaling_project=None, autoscaling_branch=None)
    elif has_autoscaling:
        return LakebaseConfig(instance_name=None, autoscaling_endpoint=None,
                              autoscaling_project=project, autoscaling_branch=branch)
    else:
        return LakebaseConfig(instance_name=raw_name, autoscaling_endpoint=None,
                              autoscaling_project=None, autoscaling_branch=None)


# Module-level singleton
lakebase_config = init_lakebase_config()
```

---

## Step 5: Configure `databricks.yml`

Add Lakebase resource and env vars per the **app-templates-lakebase-setup** skill. The long-running server additionally uses these optional env vars:

```yaml
config:
  env:
    # ... existing env vars ...
    - name: TASK_TIMEOUT_SECONDS
      value: "3600"
    - name: POLL_INTERVAL_SECONDS
      value: "1.0"
    - name: LOG_LEVEL
      value: "INFO"
```

---

## Step 6: Configure `.env` for Local Development

Add Lakebase connection vars (see **app-templates-lakebase-setup** skill for all options):

```bash
# Pick ONE mode:
# Option 1: Autoscaling endpoint
LAKEBASE_AUTOSCALING_ENDPOINT=<your-endpoint>
# Option 2: Autoscaling project/branch
LAKEBASE_AUTOSCALING_PROJECT=<project>
LAKEBASE_AUTOSCALING_BRANCH=<branch>
# Option 3: Provisioned instance
LAKEBASE_INSTANCE_NAME=<instance-name>

# Optional tuning
TASK_TIMEOUT_SECONDS=3600
POLL_INTERVAL_SECONDS=1.0
LOG_LEVEL=INFO
```

---

## Step 7: Deploy and Grant Permissions

Follow the **app-templates-lakebase-setup** skill Steps 5-7 to deploy, grant SP permissions, and run the app.

---

## Constructor Reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | `str` | required | Server name (e.g. `"ResponsesAgent"`) |
| `enable_chat_proxy` | `bool` | `False` | Enable chat UI proxy endpoint |
| `db_instance_name` | `str \| None` | `None` | Provisioned Lakebase instance name |
| `db_autoscaling_endpoint` | `str \| None` | `None` | Autoscaling endpoint hostname |
| `db_project` | `str \| None` | `None` | Autoscaling project name |
| `db_branch` | `str \| None` | `None` | Autoscaling branch name |
| `task_timeout_seconds` | `float` | `3600` | Max background task time before timeout |
| `poll_interval_seconds` | `float` | `1.0` | Stream event poll interval |

---

## Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| `ImportError: cannot import LongRunningAgentServer` | Missing dependency | Add `databricks-ai-bridge[agent-server]>=0.18.0` and `uv sync` |
| `background=true` returns but no result | Lakebase not configured | Set Lakebase env vars in `.env` / `databricks.yml` |
| Task times out | Long agent execution | Increase `TASK_TIMEOUT_SECONDS` |
| Stream events have placeholder IDs | Missing `transform_stream_event` | Ensure `AgentServer` subclass overrides it |
| DB initialization failed warning | Lakebase connection error | Check env vars and permissions (see **app-templates-lakebase-setup** skill) |
