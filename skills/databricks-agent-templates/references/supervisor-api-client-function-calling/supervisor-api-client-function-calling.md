# Client-Side Function Tools with the Supervisor API

Client-side function tools (`type: "function"`) let you declare callables your application executes — business logic, calls to your own database, external APIs, etc. The Supervisor API returns the pending `function_call`, your app executes the function, and you resume the conversation by appending a `function_call_output` to the next request's input.

**Tool declaration constraints:**
- `name` must match `^[a-zA-Z0-9_-]{1,64}$` (no dots, spaces, or other characters).
- `parameters` must be a JSON Schema object, or omitted.

**Continuation pattern:** the Supervisor API uses full-history echo. On each subsequent request, append the prior `response.output` to your input list, then add `function_call_output` items for every client `function_call` you executed. (`previous_response_id` chaining is on the roadmap.)

## Function-Only Flow

The simplest case: a single client-side function tool, no hosted tools.

```python
import json
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI

client = DatabricksOpenAI(workspace_client=WorkspaceClient(), use_ai_gateway=True)
MODEL = "databricks-claude-sonnet-4-5"

GET_WEATHER = {
    "type": "function",
    "name": "get_weather",
    "description": "Get current weather for a location.",
    "parameters": {
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
        "additionalProperties": False,
    },
}

def run_get_weather(args):
    return json.dumps({
        "location": args["location"],
        "temp_c": 18,
        "condition": "sunny",
    })

CLIENT_TOOLS = {"get_weather": run_get_weather}
TOOLS = [GET_WEATHER]

input_list = [{"role": "user", "content": "What's the weather in Paris?"}]

# Turn 1 — model emits a function_call
resp = client.responses.create(model=MODEL, input=input_list, tools=TOOLS)

# Echo the model's turn into history, then execute pending client function_calls
input_list += [item.model_dump() for item in resp.output]
for item in resp.output:
    if item.type == "function_call" and item.name in CLIENT_TOOLS:
        args = json.loads(item.arguments)
        input_list.append({
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": CLIENT_TOOLS[item.name](args),
        })

# Turn 2 — model produces the final assistant message using the tool result
final = client.responses.create(model=MODEL, input=input_list, tools=TOOLS)
print(final.output_text)
```

## Streaming Function-Only Flow

The same pattern works with streaming. Collect the full response from the stream, execute pending function calls, then resume with a second streamed call.

```python
import json
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI

client = DatabricksOpenAI(workspace_client=WorkspaceClient(), use_ai_gateway=True)
MODEL = "databricks-claude-opus-4-6"

GET_WEATHER = {
    "type": "function",
    "name": "get_weather",
    "description": "Get the current weather for a location.",
    "parameters": {
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
        "additionalProperties": False,
    },
}

def run_get_weather(args):
    return json.dumps({
        "location": args["location"],
        "temp_c": 18,
        "condition": "sunny",
    })

CLIENT_TOOLS = {"get_weather": run_get_weather}
TOOLS = [GET_WEATHER]

input_list = [{"role": "user", "content": "What's the weather in Paris?"}]

# ── First streamed call: collect the response containing function_call(s) ──
stream = client.responses.create(
    model=MODEL,
    tools=TOOLS,
    input=input_list,
    stream=True,
)

first_response = None
for event in stream:
    if event.type == "response.completed":
        first_response = event.response

# ── Execute pending client function calls and echo into history ──
input_list += [item.model_dump() for item in first_response.output]
for item in first_response.output:
    if item.type == "function_call" and item.name in CLIENT_TOOLS:
        args = json.loads(item.arguments)
        input_list.append({
            "type": "function_call_output",
            "call_id": item.call_id,
            "output": CLIENT_TOOLS[item.name](args),
        })

# ── Second streamed call: model produces the final answer ──
followup = client.responses.create(
    model=MODEL,
    tools=TOOLS,
    input=input_list,
    stream=True,
)

for event in followup:
    if event.type == "response.completed":
        print(event.response.output_text)
```

## Mixed Flow: Hosted UC Function + Client-Side Function Tool

When you combine hosted tools (e.g. `uc_function`) with client-side function tools, the server executes hosted tool calls and returns their results in `response.output` alongside any pending client-side `function_call` items. Your code only needs to execute the client-side calls — skip hosted ones.

```python
import json
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI

client = DatabricksOpenAI(workspace_client=WorkspaceClient(), use_ai_gateway=True)
MODEL = "databricks-claude-sonnet-4-5"

GET_WEATHER = {
    "type": "function",
    "name": "get_weather",
    "description": "Get the current weather for a location.",
    "parameters": {
        "type": "object",
        "properties": {"location": {"type": "string"}},
        "required": ["location"],
        "additionalProperties": False,
    },
}

def run_get_weather(args):
    return json.dumps({
        "location": args["location"],
        "temp_c": 18,
        "condition": "sunny",
    })

CLIENT_TOOLS = {"get_weather": run_get_weather}

uc_function = {"type": "uc_function", "uc_function": {"name": "system.ai.python_exec"}}

TOOLS = [GET_WEATHER, uc_function]

input_list = [
    {
        "role": "user",
        "content": (
            "Run python_exec to get 15th fibonacci number "
            "AND call get_weather for Paris. Use both tools."
        ),
    }
]

# ── First call: server executes hosted UC function; client-side get_weather is pending ──
first = client.responses.create(
    model=MODEL,
    tools=TOOLS,
    input=input_list,
)

# Echo response.output back; only execute client-side function calls.
# Hosted calls (e.g. system__ai__python_exec) and their outputs are already
# in response.output — just echo them as conversation history.
input_list += [item.model_dump() for item in first.output]
for item in first.output:
    if item.type != "function_call":
        continue
    impl = CLIENT_TOOLS.get(item.name)
    if impl is None:        # hosted tool — server already ran it, skip
        continue
    args = json.loads(item.arguments)
    input_list.append({
        "type": "function_call_output",
        "call_id": item.call_id,
        "output": impl(args),
    })

# ── Second call: model sees both tool results and produces the final answer ──
final = client.responses.create(
    model=MODEL,
    tools=TOOLS,
    input=input_list,
)
print(final.output_text)
```

## Mixed Flow: MCP Approval + Client-Side Function Tools

When you mix MCP-approval-gated hosted tools with client-side function tools, both kinds need handling each turn. The supervisor serializes turns (one tool at a time per response), so a given response will have at most one kind pending — but the client loop has to cover both.

```python
import json
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI
from openai.types.responses.response_output_item import McpApprovalResponse

client = DatabricksOpenAI(workspace_client=WorkspaceClient(), use_ai_gateway=True)
MODEL = "databricks-claude-sonnet-4-5"

# Hosted MCP server (require_approval flow) + client-side function tool
TOOLS = [
    {
        "type": "uc_connection",
        "uc_connection": {
            "name": "<uc-connection-name>",
            "description": "Searches the web for current information",
        },
    },
    {
        "type": "function",
        "name": "get_weather",
        "description": "Get current weather for a location.",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
            "additionalProperties": False,
        },
    },
]

def run_get_weather(args):
    return json.dumps({
        "location": args["location"],
        "temp_c": 18,
        "condition": "sunny",
    })

CLIENT_TOOLS = {"get_weather": run_get_weather}


def has_pending(resp, client_tools):
    """Any pending client-side work in this response?"""
    return any(
        o.type == "mcp_approval_request"
        or (o.type == "function_call" and getattr(o, "name", None) in client_tools)
        for o in resp.output
    )


def execute_pending(prev_resp, input_list, client_tools):
    """Echo response.output + append the user-side responses for any pending items."""
    next_input = list(input_list) + [item.model_dump() for item in prev_resp.output]
    for item in prev_resp.output:
        if item.type == "mcp_approval_request":
            approval = McpApprovalResponse(
                id=item.id,
                approval_request_id=item.id,
                approve=True,
                type="mcp_approval_response",
            )
            next_input.append(approval.to_dict())
        elif item.type == "function_call":
            impl = client_tools.get(getattr(item, "name", None))
            if impl is None:
                # Hosted-tool function_call — server already executed it; do not run locally.
                continue
            args = json.loads(item.arguments)
            next_input.append({
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": impl(args),
            })
    return next_input


input_list = [
    {
        "type": "message",
        "role": "user",
        "content": (
            "Search the web for what Databricks is, "
            "then call get_weather for Paris and summarize both."
        ),
    }
]

resp = client.responses.create(model=MODEL, input=input_list, tools=TOOLS)
while has_pending(resp, CLIENT_TOOLS):
    input_list = execute_pending(resp, input_list, CLIENT_TOOLS)
    resp = client.responses.create(model=MODEL, input=input_list, tools=TOOLS)

print(resp.output_text)
```

**What's happening per turn (typical):**
- **Turn 1** — model picks the search tool first → output: `[..., mcp_approval_request]`
- **Turn 2** (after approval) — server executes MCP, returns its `function_call_output`, model decides to call `get_weather` → output: `[..., function_call_output, function_call]`
- **Turn 3** (after client executes `get_weather`) — model has both tool results and writes the final answer → output: `[message]`

The exact number of turns depends on the prompt and on retry behavior (e.g., the MCP server may reject the model's first-attempt arguments and the model self-corrects on the next turn). The drain loop handles all cases — it keeps iterating until `response.output` has no pending items.

**Why client tools must be filtered by name:** hosted tools (UC functions, executed MCP calls) also emit items with `type: "function_call"` in `response.output`. These represent work Databricks already executed; you must **NOT** execute them locally. Filter by `client_tools.get(item.name)` and skip when `None` — the hosted `function_call` is already paired with its `function_call_output` in the same response and just needs to be echoed back as conversation history.

## Troubleshooting

**"function tool 'name' must match ^[a-zA-Z0-9_-]{1,64}$"** — The `name` field on a `type: "function"` tool contains invalid characters (dots, spaces, etc.) or is longer than 64 chars. Rename the tool.

**"No tool output found for function call ."** — A prior client-side `function_call` in the input list has no matching `function_call_output`. Append the output before resuming.

**"No tool call found for function call output with call_id ."** — A `function_call_output` in input references a `call_id` no prior item introduced. Echo the originating `function_call` (or `mcp_approval_request`) in the input list.