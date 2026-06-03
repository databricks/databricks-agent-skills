---
name: databricks-agent-memory-openai
description: "Add memory capabilities to your agent. Use when: (1) User asks about 'memory', 'state', 'remember', 'conversation history', (2) Want to persist conversations or user preferences, (3) Adding checkpointing or long-term storage."
---

# Stateful Memory with OpenAI Agents SDK Sessions

This template uses OpenAI Agents SDK [Sessions](https://openai.github.io/openai-agents-python/sessions/) with `AsyncDatabricksSession` to persist conversation history to a Databricks Lakebase instance.

## How Sessions Work

Sessions automatically manage conversation history for multi-turn interactions:

1. **Before each run**: The session retrieves prior conversation history and prepends it to input
2. **During the run**: New items (user messages, responses, tool calls) are generated
3. **After each run**: All new items are automatically stored in the session

This eliminates the need to manually manage conversation state between runs.

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Session** | Stores conversation history for a specific `session_id` |
| **`session_id`** | Unique identifier linking requests to the same conversation |
| **`AsyncDatabricksSession`** | Session implementation backed by Databricks Lakebase |
| **`LAKEBASE_INSTANCE_NAME`** | Environment variable specifying the Lakebase instance |

## How This Template Uses Sessions

### Session Creation (`agent_server/agent.py`)

```python
from databricks_openai.agents import AsyncDatabricksSession

session = AsyncDatabricksSession(
    session_id=get_session_id(request),
    instance_name=LAKEBASE_INSTANCE_NAME,
)

result = await Runner.run(agent, messages, session=session)
```

### Session ID Extraction (`agent_server/agent.py`)

The `session_id` is extracted from `custom_inputs` or auto-generated:

```python
def get_session_id(request: ResponsesAgentRequest) -> str:
    if hasattr(request, "custom_inputs") and request.custom_inputs:
        if "session_id" in request.custom_inputs:
            return request.custom_inputs["session_id"]
    return str(uuid7())
```

### Lakebase Instance Resolution (`agent_server/utils.py`)

The `LAKEBASE_INSTANCE_NAME` env var can be either an instance name or a hostname. The `resolve_lakebase_instance_name()` function handles both cases:

```python
_LAKEBASE_INSTANCE_NAME_RAW = os.environ.get("LAKEBASE_INSTANCE_NAME")
LAKEBASE_INSTANCE_NAME = resolve_lakebase_instance_name(_LAKEBASE_INSTANCE_NAME_RAW)
```

---

## Prerequisites

1. **Dependency**: `databricks-openai[memory]` must be in `pyproject.toml` (already included)

2. **Lakebase instance**: You need a Databricks Lakebase instance. See the **databricks-agent-lakebase-setup** skill for creating and configuring one.

3. **Environment variable**: Set `LAKEBASE_INSTANCE_NAME` in your `.env` file:
   ```bash
   LAKEBASE_INSTANCE_NAME=<your-lakebase-instance-name>
   ```

---

## Configuration Files

### databricks.yml (Lakebase Resource)

Add the Lakebase database resource to your app:

```yaml
resources:
  apps:
    agent_openai_advanced:
      name: "your-app-name"
      source_code_path: ./

      resources:
        # ... other resources (experiment, etc.) ...

        # Lakebase instance for session storage
        - name: 'database'
          database:
            instance_name: '<your-lakebase-instance-name>'
            database_name: 'databricks_postgres'
            permission: 'CAN_CONNECT_AND_CREATE'
```

### databricks.yml config block (Environment Variables)

The `LAKEBASE_INSTANCE_NAME` env var is resolved from the database resource at deploy time. Add to your app's `config.env` in `databricks.yml`:

```yaml
      config:
        env:
          - name: LAKEBASE_INSTANCE_NAME
            value_from: "database"
```

### .env (Local Development)

```bash
LAKEBASE_INSTANCE_NAME=<your-lakebase-instance-name>
```

---

## Testing Sessions

### Test Multi-Turn Conversation Locally

```bash
# Start the server
uv run start-app

# First message - starts a new session
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Hello, I live in SF!"}]}'

# Note the session_id from custom_outputs in the response

# Second message - continues the same session
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
      "input": [{"role": "user", "content": "What city did I say I live in?"}],
      "custom_inputs": {"session_id": "<session_id from previous response>"}
  }'
```

### Test Streaming

```bash
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
      "input": [{"role": "user", "content": "Hello!"}],
      "stream": true
  }'
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| **"LAKEBASE_INSTANCE_NAME environment variable is required"** | Missing env var | Set `LAKEBASE_INSTANCE_NAME` in `.env` |
| **SSL connection closed unexpectedly** | Network/instance issue | Verify Lakebase instance is running: `databricks lakebase instances get <name>` |
| **Agent doesn't remember previous messages** | Different session_id | Pass the same `session_id` via `custom_inputs` across requests |
| **"Unable to resolve hostname"** | Hostname doesn't match any instance | Verify the hostname or use the instance name directly |
| **Permission denied** | Missing Lakebase access | Add `database` resource to `databricks.yml` with `CAN_CONNECT_AND_CREATE` |

---

## Next Steps

- Configure Lakebase: see **databricks-agent-lakebase-setup** skill
- Test locally: see **databricks-agent-run-locally** skill
- Deploy: see **databricks-agent-deploy** skill
