# Supervisor API Background Mode

**Prerequisites:**
1. Run **quickstart** first (`uv run quickstart`) — it creates the MLflow experiment and `.env` file needed by the server.
2. Follow the [`supervisor-api`](../supervisor-api/supervisor-api.md) reference to set up the Supervisor API with hosted tools and permissions. This skill extends that setup with background mode support.

Background mode submits the request asynchronously (`background=True`), polls for completion, and streams the result back to the frontend. Use this when agent tasks may exceed HTTP timeout limits (complex multi-tool workflows, large data analysis, etc.).

## Before Starting

Use the `AskUserQuestion` tool to ask: "How often should the agent poll for background task completion?" with options:
- **Every 2 seconds** — Fast response times, good for interactive use
- **Every 10 seconds** — Balanced between responsiveness and API load
- **Every 30 seconds** — Lower API load, suitable for very long-running tasks

Use their answer to set `POLL_INTERVAL` in `agent_server/utils.py`.

## Architecture

```
Chat UI ──POST /api/chat──> Express ──streamText()──> Python @stream()
                                                        |
                                                        +-- responses.create(background=True, stream=False)
                                                        |   (returns response_id immediately)
                                                        |
                                                        +-- poll every 2s: responses.retrieve(id)
                                                        |   skip items with status queued/incomplete/in_progress
                                                        |   yield completed items
                                                        |
                                                        +-- convert items to stream events
                                                        |   (chunk text into word-based deltas)
                                                        |
Chat UI <──SSE stream──── Express <──stream──------+
```

## What Changes from the Base Supervisor API

| Aspect | Base Supervisor API | Background Mode |
|--------|-------------------|-----------------|
| `responses.create()` | `stream=True` or `stream=False` | `background=True, stream=False` |
| Response | Immediate result or SSE stream | Returns `response_id` immediately |
| Result retrieval | Direct from response | Poll `responses.retrieve(id)` every 2s |
| Streaming to frontend | Native SSE from API | Simulated streaming (chunked text deltas) |
| Client pattern | Single `DatabricksOpenAI` | Single `AsyncDatabricksOpenAI` with `use_ai_gateway=True` |
| MCP tools | Executed in single request | Multi-turn approval flow (see gotcha #3) |
| Timeout | HTTP request timeout | No timeout — polls until terminal status |

## Step 1: Add `agent_server/utils.py`

This replaces the base Supervisor API's simple `responses.create()` call with a polling loop and streaming conversion.

Uses a single `AsyncDatabricksOpenAI` client with `use_ai_gateway=True` for both `responses.create()` and `responses.retrieve()`.

```python
import asyncio
import logging
from typing import AsyncGenerator
from uuid import uuid4

from databricks.sdk import WorkspaceClient
from databricks_openai import AsyncDatabricksOpenAI
from mlflow.types.responses import ResponsesAgentRequest, ResponsesAgentStreamEvent

POLL_INTERVAL = 2.0  # seconds between polls
INITIAL_POLL_DELAY = 1.0  # delay before first poll

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_session_id(request: ResponsesAgentRequest) -> str | None:
    if request.context and request.context.conversation_id:
        return request.context.conversation_id
    if request.custom_inputs and isinstance(request.custom_inputs, dict):
        return request.custom_inputs.get("session_id")
    return None


def create_supervisor_client(
    workspace_client: WorkspaceClient | None = None,
) -> AsyncDatabricksOpenAI:
    """
    Create an AsyncDatabricksOpenAI client routed through AI Gateway.
    use_ai_gateway=True automatically resolves the correct AI Gateway endpoint.
    """
    workspace_client = workspace_client or WorkspaceClient()
    client = AsyncDatabricksOpenAI(
        workspace_client=workspace_client,
        use_ai_gateway=True,
    )
    return client


def _count_history_items(request: ResponsesAgentRequest) -> int:
    """Count input items that will be echoed in the response output.

    Background mode returns ALL output items for the full conversation — including
    items echoed from the input history. We skip these so we only yield new items.
    """
    ECHOED_TYPES = {"function_call", "function_call_output"}
    count = 0
    for item in request.input:
        item_dict = item.model_dump() if hasattr(item, "model_dump") else item
        role = item_dict.get("role")
        item_type = item_dict.get("type")
        if role == "assistant" or item_type in ECHOED_TYPES:
            count += 1
    return count


async def poll_background_response(
    client: AsyncDatabricksOpenAI,
    response,
    request: ResponsesAgentRequest | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Poll a background response until terminal status (completed/failed/cancelled).
    Yields new output items as they appear, including mcp_approval_request items
    so the frontend can show them to the user for approval.

    When MCP tools are involved, the response will complete with mcp_approval_request
    items. These are yielded to the frontend. The user approves in the UI, and the
    frontend sends a new request with the approval in the input — that new request
    goes through background mode again naturally.

    Args:
        request: The original agent request. Used to calculate how many echoed
            history items to skip at the start of the output (background mode
            echoes back all previous assistant messages and tool calls).
    """
    skip_items = _count_history_items(request) if request else 0
    seen_item_count = skip_items
    if skip_items > 0:
        logger.info(f"[poll] Skipping first {skip_items} echoed history items")
    poll_count = 0
    response_id = response.id

    logger.info(
        f"[poll] Starting polling for response_id={response_id}, "
        f"interval={POLL_INTERVAL}s"
    )

    # Check if the initial response is already terminal (skip polling entirely)
    if response.status not in ("queued", "in_progress"):
        logger.info(
            f"[poll] Initial response already terminal: "
            f"status={response.status}"
        )
        for item in (response.output or [])[skip_items:]:
            item_dict = (
                item.model_dump() if hasattr(item, "model_dump") else item
            )
            item_status = item_dict.get("status", "")
            if item_status in ("queued", "incomplete", "in_progress"):
                continue
            yield item_dict
        return

    await asyncio.sleep(INITIAL_POLL_DELAY)

    while True:
        poll_count += 1
        logger.info(f"[poll] Poll #{poll_count} for response_id={response_id}")

        try:
            response = await client.responses.retrieve(response_id)
        except Exception as e:
            logger.warning(f"[poll] Retrieve failed (will retry): {e}")
            await asyncio.sleep(POLL_INTERVAL)
            continue

        status = response.status

        current_items = response.output or []
        new_items = len(current_items) - seen_item_count
        logger.info(
            f"[poll] status={status}, total_items={len(current_items)}, "
            f"new_items={new_items}"
        )

        if new_items > 0:
            for idx, item in enumerate(current_items[seen_item_count:]):
                item_dict = (
                    item.model_dump() if hasattr(item, "model_dump") else item
                )
                item_status = item_dict.get("status", "")
                item_id = item_dict.get("id")
                item_type = item_dict.get("type")
                # Stop at incomplete items to preserve ordering
                if item_status in ("queued", "incomplete", "in_progress"):
                    logger.info(
                        f"[poll] Stopping at incomplete item: "
                        f"type={item_type}, status={item_status}"
                    )
                    break
                if not item_id and item_type != "function_call_output":
                    logger.info(
                        f"[poll] Stopping at item with no id: "
                        f"type={item_type}, status={item_status}"
                    )
                    break
                logger.info(
                    f"[poll] Yielding item: type={item_type}, "
                    f"id={item_id}"
                )
                yield item_dict
                seen_item_count += 1
            else:
                # Loop completed without break — all items processed
                seen_item_count = len(current_items)

        if status == "completed":
            logger.info(
                f"[poll] Response completed after {poll_count} polls, "
                f"{seen_item_count} total items"
            )
            return
        elif status in ("failed", "cancelled"):
            error_msg = (
                getattr(response, "error", None)
                or f"Background response {status}"
            )
            logger.error(f"[poll] Response {status}: {error_msg}")
            raise RuntimeError(f"Background response {status}: {error_msg}")

        logger.info(f"[poll] Waiting {POLL_INTERVAL}s before next poll...")
        await asyncio.sleep(POLL_INTERVAL)


def _chunk_text(text: str, chunk_size: int = 1) -> list[str]:
    """Split text into word-based chunks for streaming."""
    words = text.split(" ")
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i : i + chunk_size])
        if i + chunk_size < len(words):
            chunk += " "
        chunks.append(chunk)
    return chunks


def output_item_to_stream_events(
    item: dict,
) -> list[ResponsesAgentStreamEvent]:
    """Convert a Responses API output item to stream events.

    For message items, text is chunked into small word-based deltas to simulate
    streaming on the frontend, since background mode returns the full text at once.
    """
    events = []
    item_type = item.get("type")
    item_id = item.get("id", str(uuid4()))

    if item_type == "message":
        seq = 0
        for content_part in item.get("content", []):
            if content_part.get("type") == "output_text":
                text = content_part.get("text", "")
                for chunk in _chunk_text(text):
                    events.append(
                        ResponsesAgentStreamEvent(
                            type="response.output_text.delta",
                            item_id=item_id,
                            content_index=seq,
                            delta=chunk,
                        )
                    )
                    seq += 1
        events.append(
            ResponsesAgentStreamEvent(
                type="response.output_item.done",
                item=item,
            )
        )
    else:
        # function_call, function_call_output, mcp_approval_request, or other types
        events.append(
            ResponsesAgentStreamEvent(
                type="response.output_item.done",
                item=item,
            )
        )

    return events
```

## Step 2: Update `agent_server/agent.py`

Replace the base Supervisor API handlers with async background mode handlers. The key differences from the base skill:
- Use `async` handlers (required for polling)
- Pass `background=True, stream=False` to `responses.create()`
- Poll with `poll_background_response()` instead of reading the response directly
- Convert output items to stream events with `output_item_to_stream_events()`
- Pass `request` to `poll_background_response()` so it can skip echoed history items in multi-turn conversations

Include your `TOOLS` list from the [`supervisor-api`](../supervisor-api/supervisor-api.md) reference's Step 2 if you have hosted tools.

```python
import asyncio
import logging
from typing import AsyncGenerator

import mlflow
from databricks.sdk import WorkspaceClient
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

from agent_server.utils import (
    create_supervisor_client,
    get_session_id,
    output_item_to_stream_events,
    poll_background_response,
)

mlflow.openai.autolog()
logging.getLogger("mlflow.utils.autologging_utils").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MODEL = "databricks-claude-sonnet-4"
SYSTEM_INSTRUCTIONS = "You are a helpful assistant."
TOOLS = [...]  # Your hosted tools from supervisor-api Step 2


def build_input(request: ResponsesAgentRequest) -> list[dict]:
    return [i.model_dump() for i in request.input]


@invoke()
async def invoke_handler(
    request: ResponsesAgentRequest,
) -> ResponsesAgentResponse:
    if session_id := get_session_id(request):
        mlflow.update_current_trace(
            metadata={"mlflow.trace.session": session_id}
        )

    workspace_client = WorkspaceClient()
    client = create_supervisor_client(workspace_client)

    logger.info(f"[invoke] Submitting background request with model={MODEL}")
    response = await client.responses.create(
        model=MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=build_input(request),
        tools=TOOLS,
        background=True,
        stream=False,
    )
    logger.info(
        f"[invoke] Background request submitted: "
        f"id={response.id}, status={response.status}"
    )

    # Poll until complete. If an MCP approval request is needed, the next
    # user message should contain the approval to continue the tool call.
    output_items = []
    async for item in poll_background_response(client, response, request):
        logger.info(
            f"[invoke] Received output item: "
            f"type={item.get('type')}, id={item.get('id')}"
        )
        output_items.append(item)

    logger.info(f"[invoke] Complete: {len(output_items)} output items")
    return ResponsesAgentResponse(output=output_items)


@stream()
async def stream_handler(
    request: ResponsesAgentRequest,
) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    if session_id := get_session_id(request):
        mlflow.update_current_trace(
            metadata={"mlflow.trace.session": session_id}
        )

    workspace_client = WorkspaceClient()
    client = create_supervisor_client(workspace_client)

    logger.info(f"[stream] Submitting background request with model={MODEL}")
    response = await client.responses.create(
        model=MODEL,
        instructions=SYSTEM_INSTRUCTIONS,
        input=build_input(request),
        tools=TOOLS,
        background=True,
        stream=False,
    )
    logger.info(
        f"[stream] Background request submitted: "
        f"id={response.id}, status={response.status}"
    )

    # Poll and yield stream events as new output items appear.
    # If an MCP approval request is needed, the next user message should
    # contain the approval to continue the tool call.
    async for item in poll_background_response(client, response, request):
        events = output_item_to_stream_events(item)
        logger.info(
            f"[stream] Received item type={item.get('type')}, "
            f"emitting {len(events)} stream events"
        )
        for event in events:
            yield event
            await asyncio.sleep(0.01)  # Small delay for visible streaming effect
    logger.info("[stream] Complete")
```

## Key Gotchas

### 1. Incomplete items during `in_progress`

While the response status is `in_progress`, the Supervisor API may return output items that are not yet complete (their `status` field will be `queued`, `incomplete`, or `in_progress`). These partial items may have `id: None` and will cause Pydantic validation errors in `ResponsesAgentStreamEvent` and `ResponsesAgentResponse`. **Always `break` at the first incomplete item** to preserve ordering — items after an incomplete one may also be incomplete or out of order. They'll appear as completed on a later poll.

### 2. Simulated streaming for the frontend

The chat frontend expects SSE streaming events. Since background mode returns the full text at once, `output_item_to_stream_events()` chunks text into 1-word deltas and the stream handler adds a 10ms delay between yields to simulate a realistic streaming experience.

### 3. MCP server tools require a multi-turn approval flow

MCP server tools (`uc_connection` or `app`) require a multi-turn approval flow — see the [`supervisor-api`](../supervisor-api/supervisor-api.md) reference for the full explanation and example input.

In background mode, when an MCP tool call requires approval, the response reaches `completed` status (not `in_progress`) with `mcp_approval_request` items in the output. This naturally ends the polling loop. The `mcp_approval_request` items are returned to the frontend for the user to approve.

The approval follow-up is itself a full background mode cycle: the frontend sends a new request (with the original input + `mcp_approval_request` + `mcp_approval_response` appended) using `background=True`, receives a new response ID, and polls again until the final `completed` response with the tool result and assistant message.

### 4. No timeout on polling

The polling loop runs indefinitely until a terminal status (`completed`, `failed`, `cancelled`). There is no max poll time — this is intentional for long-running background tasks. The frontend chat proxy also has no explicit timeout enforced in code.

## Testing

### Test background mode directly against the Supervisor API

```bash
# Get auth
export DATABRICKS_HOST=$(databricks auth env --profile <PROFILE> | grep DATABRICKS_HOST | cut -d= -f2)
export DATABRICKS_TOKEN=$(databricks auth env --profile <PROFILE> | grep DATABRICKS_TOKEN | cut -d= -f2)

# Submit background request with a Genie space tool
curl -s "${DATABRICKS_HOST}/ai-gateway/mlflow/v1/responses" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<MODEL>",
    "input": [{"role": "user", "content": "What were the top 5 products by revenue last quarter?"}],
    "tools": [
      {
        "type": "genie_space",
        "genie_space": {
          "description": "Query sales and revenue data",
          "id": "<genie-space-id>"
        }
      }
    ],
    "background": true,
    "stream": false
  }'

# Poll (use the id from above)
curl -s "${DATABRICKS_HOST}/ai-gateway/mlflow/v1/responses/<RESPONSE_ID>" \
  -H "Authorization: Bearer ${DATABRICKS_TOKEN}"
```

### Test locally via the agent server

```bash
uv run start-app --no-ui

# In another terminal:
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -H "x-forwarded-access-token: <YOUR_TOKEN>" \
  -d '{
    "input": [{"role": "user", "content": [{"type": "input_text", "text": "Hello"}]}]
  }'
```

### Example Expected log output

```
INFO:agent_server.agent:[stream] Submitting background request with model=databricks-claude-sonnet-4
INFO:agent_server.agent:[stream] Background request submitted: id=resp_xxx, status=queued
INFO:agent_server.utils:[poll] Starting polling for response_id=resp_xxx, interval=2.0s
INFO:agent_server.utils:[poll] Poll #1: status=in_progress, total_items=0, new_items=0
INFO:agent_server.utils:[poll] Waiting 2.0s before next poll...
INFO:agent_server.utils:[poll] Poll #2: status=completed, total_items=1, new_items=1
INFO:agent_server.utils:[poll] Yielding item: type=message, id=msg_xxx
INFO:agent_server.utils:[poll] Response completed after 2 polls, 1 total items
INFO:agent_server.agent:[stream] Received item type=message, emitting N stream events
INFO:agent_server.agent:[stream] Complete
```
