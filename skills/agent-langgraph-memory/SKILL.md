---
name: agent-langgraph-memory
description: "Add memory capabilities to your agent. Use when: (1) User asks about 'memory', 'state', 'remember', 'conversation history', (2) Want to persist conversations or user preferences, (3) Adding checkpointing or long-term storage."
metadata:
  version: "0.0.1"
---

# Adding Memory to Your Agent

> **Note:** This template does not include memory by default. Use this skill to **add memory capabilities**. For a pre-configured memory template, see:
> - [agent-langgraph-advanced](https://github.com/databricks/app-templates/tree/main/agent-langgraph-advanced) - Short-term and long-term memory with long-running background tasks

## Memory Types

| Type | Use Case | Storage | Identifier |
|------|----------|---------|------------|
| **Short-term** | Conversation history within a session | `AsyncCheckpointSaver` | `thread_id` |
| **Long-term** | User facts that persist across sessions | `AsyncDatabricksStore` | `user_id` |

## Prerequisites

1. **Add memory dependency** to `pyproject.toml`:
   ```toml
   dependencies = [
       "databricks-langchain[memory]",
   ]
   ```

   Then run `uv sync`

2. **Configure Lakebase** - See **lakebase-setup** skill for:
   - Creating/configuring Lakebase instance
   - Initializing tables (CRITICAL first-time step)

---

## Quick Setup Summary

Adding memory requires changes to **4 files**:

| File | What to Add |
|------|-------------|
| `pyproject.toml` | Memory dependency |
| `.env` | Lakebase env vars (for local dev) |
| `databricks.yml` | Lakebase database resource + env vars in config block |
| `agent_server/agent.py` | Memory tools and AsyncDatabricksStore |

---

## Key Principles

Before implementing memory, understand these patterns from the production implementation.

### 1. Factory Function Pattern

Memory tools should be returned from a factory function, not defined as standalone functions:

```python
def memory_tools():
    @tool
    async def get_user_memory(query: str, config: RunnableConfig) -> str:
        ...
    @tool
    async def save_user_memory(memory_key: str, memory_data_json: str, config: RunnableConfig) -> str:
        ...
    @tool
    async def delete_user_memory(memory_key: str, config: RunnableConfig) -> str:
        ...
    return [get_user_memory, save_user_memory, delete_user_memory]
```

### 2. User ID Extraction

Extract `user_id` from the request, checking `custom_inputs` first. Return `None` (not a default) to let the caller decide:

```python
def get_user_id(request: ResponsesAgentRequest) -> Optional[str]:
    custom_inputs = dict(request.custom_inputs or {})
    if "user_id" in custom_inputs:
        return custom_inputs["user_id"]
    if request.context and getattr(request.context, "user_id", None):
        return request.context.user_id
    return None
```

### 3. Separate Error Handling

Check `user_id` and `store` separately with distinct error messages:

```python
user_id = config.get("configurable", {}).get("user_id")
if not user_id:
    return "Memory not available - no user_id provided."

store: Optional[BaseStore] = config.get("configurable", {}).get("store")
if not store:
    return "Memory not available - store not configured."
```

### 4. JSON Validation for Save

Validate JSON input before storing - the LLM may pass invalid JSON:

```python
try:
    memory_data = json.loads(memory_data_json)
    if not isinstance(memory_data, dict):
        return f"Failed: memory_data must be a JSON object, not {type(memory_data).__name__}"
    await store.aput(namespace, memory_key, memory_data)
except json.JSONDecodeError as e:
    return f"Failed to save memory: Invalid JSON - {e}"
```

### 5. Pass Store via RunnableConfig

Pass the store through config, not as a function parameter:

```python
config = {"configurable": {"user_id": user_id, "store": store}}
# Tools access via: config.get("configurable", {}).get("store")
```

---

## Complete Example

A full implementation is available in this skill's examples folder:

```bash
# Copy to your project
cp .claude/skills/agent-memory/examples/memory_tools.py agent_server/
```

See `examples/memory_tools.py` for production-ready code including all helper functions.

## Production Reference

For implementations in the pre-built templates:

| File | Description |
|------|-------------|
| [`agent-langgraph-advanced/agent_server/utils_memory.py`](https://github.com/databricks/app-templates/tree/main/agent-langgraph-advanced/agent_server/utils_memory.py) | Memory tools factory, helpers, error handling |
| [`agent-langgraph-advanced/agent_server/agent.py`](https://github.com/databricks/app-templates/tree/main/agent-langgraph-advanced/agent_server/agent.py) | Integration with agent, store initialization |

Key functions:
- `memory_tools()` - Factory returning get/save/delete tools
- `get_user_id()` - Extract user_id from request
- `resolve_lakebase_instance_name()` - Handle hostname vs instance name
- `get_lakebase_access_error_message()` - Helpful error messages

---

## Configuration Files

### Step 1: databricks.yml (Lakebase Resource)

Add the Lakebase database resource to your app:

```yaml
resources:
  apps:
    agent_langgraph:
      name: "your-app-name"
      source_code_path: ./

      resources:
        # ... other resources (experiment, UC functions, etc.) ...

        # Lakebase instance for long-term memory
        - name: 'database'
          database:
            instance_name: '<your-lakebase-instance-name>'
            database_name: 'databricks_postgres'
            permission: 'CAN_CONNECT_AND_CREATE'
```

**Important:** The `name: 'database'` must match the `value_from` reference in the `databricks.yml` `config.env` block.

### Step 2: databricks.yml config block (Environment Variables)

Add the Lakebase environment variables to your app's `config.env` in `databricks.yml`:

```yaml
      config:
        command: ["uv", "run", "start-app"]
        env:
          # ... other env vars ...

          # Lakebase instance name (resolved from database resource)
          - name: LAKEBASE_INSTANCE_NAME
            value_from: "database"

          # Embedding configuration
          - name: EMBEDDING_ENDPOINT
            value: "databricks-gte-large-en"
          - name: EMBEDDING_DIMS
            value: "1024"
```

**Important:** `LAKEBASE_INSTANCE_NAME` uses `value_from: "database"` to resolve from the database resource at deploy time.

### Step 3: .env (Local Development)

```bash
# Lakebase configuration for long-term memory
LAKEBASE_INSTANCE_NAME=<your-instance-name>
EMBEDDING_ENDPOINT=databricks-gte-large-en
EMBEDDING_DIMS=1024
```

---

## Integration Example

Minimal example showing how to integrate memory into your streaming function:

```python
from agent_server.utils_memory import memory_tools, get_user_id

@stream()
async def streaming(request: ResponsesAgentRequest):
    user_id = get_user_id(request)

    async with AsyncDatabricksStore(
        instance_name=LAKEBASE_INSTANCE_NAME,
        embedding_endpoint=EMBEDDING_ENDPOINT,
        embedding_dims=EMBEDDING_DIMS,
    ) as store:
        await store.setup()  # Creates tables if needed

        tools = await mcp_client.get_tools() + memory_tools()
        config = {"configurable": {"user_id": user_id, "store": store}}

        agent = create_react_agent(model=model, tools=tools)
        async for event in agent.astream(messages, config):
            yield event
```

---

## Initialize Tables and Deploy

### Initialize Lakebase Tables (First Time Only)

Before deploying, initialize the tables locally:

```bash
uv run python -c "$(cat <<'EOF'
import asyncio
from databricks_langchain import AsyncDatabricksStore

async def setup():
    async with AsyncDatabricksStore(
        instance_name="<your-instance-name>",
        embedding_endpoint="databricks-gte-large-en",
        embedding_dims=1024,
    ) as store:
        await store.setup()
        print("Tables created!")

asyncio.run(setup())
EOF
)"
```

### Deploy

After initializing tables, deploy your agent. See **deploy** skill for full instructions.

---

## Short-Term Memory

For conversation history within a session, use `AsyncCheckpointSaver`:

```python
from databricks_langchain import AsyncCheckpointSaver

async with AsyncCheckpointSaver(instance_name=LAKEBASE_INSTANCE_NAME) as checkpointer:
    agent = create_react_agent(
        model=model,
        tools=tools,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": thread_id}}
    async for event in agent.astream(messages, config):
        yield event
```

See the [agent-langgraph-advanced](https://github.com/databricks/app-templates/tree/main/agent-langgraph-advanced) template for a complete implementation.

---

## Testing Memory

### Test Locally

```bash
# Start the server
uv run start-app

# Save a memory
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
      "input": [{"role": "user", "content": "Remember that I am on the shipping team"}],
      "custom_inputs": {"user_id": "alice@example.com"}
  }'

# Recall the memory
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
      "input": [{"role": "user", "content": "What team am I on?"}],
      "custom_inputs": {"user_id": "alice@example.com"}
  }'

# Delete a memory
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
      "input": [{"role": "user", "content": "Forget what team I am on"}],
      "custom_inputs": {"user_id": "alice@example.com"}
  }'
```

### Test Deployed App

```bash
# Get OAuth token (PATs don't work for apps)
TOKEN=$(databricks auth token --host <workspace-url> | jq -r '.access_token')

# Test memory save
curl -X POST https://<app-url>/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
      "input": [{"role": "user", "content": "Remember I prefer detailed explanations"}],
      "custom_inputs": {"user_id": "alice@example.com"}
  }'
```

---

## First-Time Setup Checklist

- [ ] Added `databricks-langchain[memory]` to `pyproject.toml`
- [ ] Run `uv sync` to install dependencies
- [ ] Created or identified Lakebase instance
- [ ] Added Lakebase env vars to `.env` (for local dev)
- [ ] Added `database` resource to `databricks.yml`
- [ ] Added `LAKEBASE_INSTANCE_NAME` to `databricks.yml` `config.env`
- [ ] **Initialized tables locally** by running `await store.setup()`
- [ ] Deployed with `databricks bundle deploy && databricks bundle run`

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| **"embedding_dims is required"** | Missing parameter | Add `embedding_dims=1024` to AsyncDatabricksStore |
| **"relation 'store' does not exist"** | Tables not created | Run `await store.setup()` locally first |
| **"Unable to resolve Lakebase instance 'None'"** | Missing env var | Check `LAKEBASE_INSTANCE_NAME` in databricks.yml `config.env` |
| **"permission denied for table store"** | Missing grants | Add `database` resource to databricks.yml |
| **"Memory not available - no user_id"** | Missing user_id | Pass `custom_inputs.user_id` in request |
| **Memory not persisting** | Different user_ids | Use consistent user_id across requests |
| **App not updated after deploy** | Forgot to run bundle | Run `databricks bundle run agent_langgraph` after deploy |

---

## Pre-Built Memory Templates

For fully configured implementations without manual setup:

| Template | Memory Type | Key Features |
|----------|-------------|--------------|
| [agent-langgraph-advanced](https://github.com/databricks/app-templates/tree/main/agent-langgraph-advanced) | Short-term + Long-term | AsyncCheckpointSaver, AsyncDatabricksStore, memory tools |

---

## Next Steps

- Configure Lakebase: see **lakebase-setup** skill
- Test locally: see **run-locally** skill
- Deploy: see **deploy** skill
