---
name: supervisor-api
description: "Replace the client-side agent loop with Databricks Supervisor API (hosted tools). Use when: (1) User asks about Supervisor API, (2) User wants Databricks to run the agent loop server-side, (3) Connecting Genie spaces, UC functions, agent endpoints, or MCP servers as hosted tools."
metadata:
  version: "0.0.1"
---

# Use the Databricks Supervisor API

The Supervisor API lets Databricks run the tool-selection and synthesis loop server-side. Instead of your agent managing tool calls and looping, you declare hosted tools and call `responses.create()` — Databricks handles the rest.

## When to Use

Use the Supervisor API when you want to:
- Connect Genie spaces, UC functions, Knowledge Assistants, or MCP servers without managing the agent loop yourself
- Choose models at runtime and control which tools are used per request
- Offload tool orchestration to Databricks while iterating on your agent

**Limitations:**
- Cannot mix hosted tools with client-side function tools in the same request
- Inference parameters (e.g., `temperature`, `top_p`) are not supported when tools are passed
- Scoped token access (OBO) is not supported — tools run as the app's service principal; grant tool permissions in `databricks.yml`
- `stream` and `background` cannot both be `true` in the same request
- Background mode requests have a maximum execution time of 30 minutes

## Step 1: Install `databricks-openai`

Add to `pyproject.toml` if not already present:

```toml
[project]
dependencies = [
    ...
    "databricks-openai>=0.14.0",
    "databricks-sdk>=0.55.0",
]
```

Then run `uv sync`.

## Step 2: Declare Hosted Tools

Define your tools as a list of dicts. Run `uv run discover-tools` to find available resources in your workspace.

```python
TOOLS = [
    # Genie space — natural language queries over structured data
    {
        "type": "genie_space",
        "genie_space": {
            "id": "<genie-space-id>",
            "description": "Query sales data using natural language",
        },
    },
    # UC function — SQL or Python UDF
    {
        "type": "uc_function",
        "uc_function": {
            "name": "<catalog>.<schema>.<function_name>",
            "description": "Executes a custom UC function",
        },
    },
    # Knowledge Assistant agent endpoint
    {
        "type": "knowledge_assistant",
        "knowledge_assistant": {
            "knowledge_assistant_id": "<ka-id>",
            "description": "Answers questions from internal documentation",
        },
    },
    # External MCP server via Unity Catalog connection
    {
        "type": "uc_connection",
        "uc_connection": {
            "name": "<uc-connection-name>",
            "description": "Searches the web for current information",
        },
    },
    # Databricks App endpoint or custom MCP server running as a Databricks App
    {
        "type": "app",
        "app": {
            "name": "<databricks-app-name>",
            "description": "Custom application or MCP server endpoint",
        },
    },
]
```

## Step 3: Update `agent_server/agent.py`

Replace your existing invoke/stream handlers with the Supervisor API pattern. Remove any MCP client setup, LangGraph agents, or OpenAI Agents SDK runner code — the Supervisor API replaces the client-side loop entirely.

`use_ai_gateway=True` automatically resolves the correct AI Gateway endpoint for the workspace.

Tools run as the app's service principal — grant each tool's resource permissions in `databricks.yml` (Step 4).

```python
import os
import logging
import mlflow
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI
from mlflow import MlflowClient
from mlflow.genai.agent_server import invoke, stream
from mlflow.tracing import get_tracing_context_headers_for_http_request
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
)

mlflow.openai.autolog()

logger = logging.getLogger(__name__)

MODEL = "databricks-claude-sonnet-4-5"
TOOLS = [...]  # From Step 2

# Resolve and cache the AI Gateway client once at module load
_wc = WorkspaceClient()
_client = DatabricksOpenAI(workspace_client=_wc, use_ai_gateway=True)


def _get_trace_destination() -> dict:
    experiment_id = os.environ.get("MLFLOW_EXPERIMENT_ID")
    if not experiment_id:
        raise RuntimeError(
            "MLFLOW_EXPERIMENT_ID is not set. Cannot configure distributed tracing."
        )
    trace_location = MlflowClient().get_experiment(experiment_id).trace_location
    if trace_location is None or not hasattr(trace_location, "catalog_name"):
        msg = (
            f"Experiment {experiment_id} trace_location is not a Unity Catalog location "
            f"(got: {type(trace_location).__name__ if trace_location else None}). "
            "Distributed tracing requires UC-backed traces. "
            "Ensure 'MLflow traces in Unity Catalog' is enabled for your workspace and that "
            "the target UC tables use customer-managed storage (Arclight default storage is not supported)."
        )
        logger.error(msg)
        raise RuntimeError(msg)
    dest = {
        "catalog_name": trace_location.catalog_name,
        "schema_name": trace_location.schema_name,
    }
    if trace_location.table_prefix is not None:
        dest["table_prefix"] = trace_location.table_prefix
    return dest


_TRACE_DESTINATION = _get_trace_destination()


@invoke()
def invoke_handler(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    mlflow.update_current_trace(
        metadata={"mlflow.trace.session": request.context.conversation_id}
    )
    response = _client.responses.create(
        model=MODEL,
        input=[i.model_dump() for i in request.input],
        tools=TOOLS,
        stream=False,
        extra_headers=get_tracing_context_headers_for_http_request(),
        extra_body={
            "trace_destination": _TRACE_DESTINATION,
        },
    )
    return ResponsesAgentResponse(output=[item.model_dump() for item in response.output])


@stream()
def stream_handler(request: ResponsesAgentRequest):
    mlflow.update_current_trace(
        metadata={"mlflow.trace.session": request.context.conversation_id}
    )
    return _client.responses.create(
        model=MODEL,
        input=[i.model_dump() for i in request.input],
        tools=TOOLS,
        stream=True,
        extra_headers=get_tracing_context_headers_for_http_request(),
        extra_body={
            "trace_destination": _TRACE_DESTINATION,
        },
    )
```

## Step 4: Grant Permissions in `databricks.yml`

Grant the service principal access to each hosted tool. See the **add-tools** skill for YAML examples — the resource types are the same. The model serving endpoint is always required.

| Tool type | `resources` entry | Permission |
|-----------|-------------------|------------|
| *(all)* | `serving_endpoint` (model) | `CAN_QUERY` |
| `genie_space` | `genie_space` | `CAN_RUN` |
| `uc_function` | `uc_securable` (`FUNCTION`) | `EXECUTE` |
| `knowledge_assistant` | `serving_endpoint` | `CAN_QUERY` |
| `uc_connection` | `uc_securable` (`CONNECTION`) | `USE_CONNECTION` |
| `app` | `app` *(CLI support coming soon)* | `CAN_USE` |

## Step 5: Test and Deploy

```bash
uv run start-app       # Test locally
databricks bundle deploy && databricks bundle run {{BUNDLE_NAME}}  # Deploy
```

## Supported Models

Pass any of these as the `model` parameter:

| Model | ID |
|-------|----|
| Claude Sonnet 4 | `databricks-claude-sonnet-4` |
| Claude Sonnet 4.5 | `databricks-claude-sonnet-4-5` |
| Claude Sonnet 4.6 | `databricks-claude-sonnet-4-6` |
| Claude Haiku 4.5 | `databricks-claude-haiku-4-5` |
| Claude Opus 4.1 | `databricks-claude-opus-4-1` |
| Claude Opus 4.5 | `databricks-claude-opus-4-5` |
| Claude Opus 4.6 | `databricks-claude-opus-4-6` |
| GPT-5 | `databricks-gpt-5` |

## Enabling Tracing

The Supervisor API supports **distributed tracing** — spans from the server-side agent loop are linked into the same trace as your agent's client-side spans, giving end-to-end visibility in MLflow. See the [MLflow distributed tracing docs](https://mlflow.org/docs/latest/genai/tracing/app-instrumentation/distributed-tracing/) for more details.

### How It Works

1. The trace destination (UC catalog/schema/table) is resolved from your MLflow experiment at startup
2. `get_tracing_context_headers_for_http_request()` propagates the active span context to the Supervisor API via HTTP headers
3. `trace_destination` tells the Supervisor API where to write its server-side spans
4. Both sets of spans appear as a single connected trace in MLflow

### Setup

Add to `agent_server/agent.py`:

```python
import os
import logging
import mlflow
from mlflow import MlflowClient
from mlflow.tracing import get_tracing_context_headers_for_http_request

logger = logging.getLogger(__name__)


def _get_trace_destination() -> dict:
    """Resolve trace destination from the experiment's Unity Catalog trace location."""
    experiment_id = os.environ.get("MLFLOW_EXPERIMENT_ID")
    if not experiment_id:
        raise RuntimeError(
            "MLFLOW_EXPERIMENT_ID is not set. Cannot configure distributed tracing. "
            "Ensure the app is configured with a valid MLflow experiment."
        )

    client = MlflowClient()
    experiment = client.get_experiment(experiment_id)
    trace_location = experiment.trace_location

    if trace_location is None or not hasattr(trace_location, "catalog_name"):
        msg = (
            f"Experiment {experiment_id} trace_location is not a Unity Catalog location "
            f"(got: {type(trace_location).__name__ if trace_location else None}). "
            "Distributed tracing requires UC-backed traces. "
            "Ensure 'MLflow traces in Unity Catalog' is enabled for your workspace and that "
            "the target UC tables use customer-managed storage (Arclight default storage is not supported)."
        )
        logger.error(msg)
        raise RuntimeError(msg)

    dest = {
        "catalog_name": trace_location.catalog_name,
        "schema_name": trace_location.schema_name,
    }
    if trace_location.table_prefix is not None:
        dest["table_prefix"] = trace_location.table_prefix
    return dest


# Resolve once at module load — fail fast if the experiment is misconfigured
_TRACE_DESTINATION = _get_trace_destination()
```

Then pass `extra_headers` and `extra_body` in every `responses.create()` call:

```python
response = _client.responses.create(
    model=MODEL,
    input=[i.model_dump() for i in request.input],
    tools=TOOLS,
    stream=False,
    extra_headers=get_tracing_context_headers_for_http_request(),
    extra_body={
        "trace_destination": _TRACE_DESTINATION,
    },
)
```

- `extra_headers` — propagates the active MLflow span context so client and server spans are linked into one trace
- `trace_destination` — tells the Supervisor API where to write server-side spans in Unity Catalog

### Environment Variable

`MLFLOW_EXPERIMENT_ID` must be set in your app environment. The quickstart script sets this automatically. To verify:

```bash
grep MLFLOW_EXPERIMENT_ID .env
```

> **Claude:** Before writing any tracing code, check `.env` for `MLFLOW_EXPERIMENT_ID`. If it is missing or empty, ask the user:
> *"Distributed tracing requires `MLFLOW_EXPERIMENT_ID` to be set in `.env`. Do you have an MLflow experiment ID? If not, run `uv run quickstart` to create one, or provide the experiment ID and I'll add it to `.env`."*
>
> If the value is present but looks wrong (e.g. not a numeric string), warn the user before proceeding.

## MCP Server Tools: Multi-Turn Approval Flow

When using MCP server tools (`uc_connection` or `app`), the Supervisor API does **not** execute the MCP tool call in a single request. Instead, it returns a `completed` response containing `mcp_approval_request` output items. To complete the tool call, your agent must handle a multi-turn flow:

1. **First request** — `responses.create()` → response completes with `mcp_approval_request` items in the output
2. **Return to frontend** — the `mcp_approval_request` item is returned to the chat UI so the user can approve the tool call
3. **Second request** — user approves → frontend sends a new request with the original input + `mcp_approval_request` + `mcp_approval_response` (with `approve: true`) appended to the input
4. **Result** — the second response completes with the actual `function_call_output` (tool result) and the final assistant `message`

No special backend handling is needed — the agent server simply returns all output items (including `mcp_approval_request`) to the frontend. The multi-turn flow is handled naturally through the conversation: each request/response is a separate `responses.create()` call.

**Example input for the follow-up request (step 3):**
```python
input = [
    # Original user message
    {"type": "message", "role": "user", "content": "Search for Databricks"},
    # The mcp_approval_request from the first response's output
    {"type": "mcp_approval_request", "id": "call_xxx", "name": "web-search",
     "server_label": "you_dot_com", "arguments": '{"query": "Databricks"}'},
    # The approval
    {"type": "mcp_approval_response", "id": "call_xxx",
     "approval_request_id": "call_xxx", "approve": True},
]
```

## Troubleshooting

**"Please ensure AI Gateway V2 is enabled"** — AI Gateway must be enabled for the workspace. Contact your Databricks account team.

**"Cannot mix hosted and client-side tools"** — Remove any `function`-type tools (Python callables) from `TOOLS`. All tools must be hosted types (`genie_space`, `uc_function`, `knowledge_assistant`, `uc_connection`, `app`).

**"Parameter not supported when tools are provided"** — Remove `temperature`, `top_p`, or other inference parameters from the `responses.create()` call.

## Background Mode (Long-Running Tasks)

If your agent needs to run long-running tasks that may exceed HTTP timeout limits (e.g., complex multi-tool workflows, large data analysis), you can enable **background mode**. This submits the request asynchronously, polls for completion, and streams the result back to the frontend.

See the **supervisor-api-background-mode** skill for full implementation details.
