# Modify the Agent

## Main File

**`agent_server/agent.py`** - Agent logic, model selection, instructions, MCP servers

## Key Files

| File                             | Purpose                                       |
| -------------------------------- | --------------------------------------------- |
| `agent_server/agent.py`          | Agent logic, model, instructions, MCP servers |
| `agent_server/start_server.py`   | FastAPI server + MLflow setup                 |
| `agent_server/evaluate_agent.py` | Agent evaluation with MLflow scorers          |
| `agent_server/utils.py`          | Databricks auth helpers, stream processing    |
| `databricks.yml`                 | Bundle config & resource permissions          |

## SDK Setup

```python
import mlflow
from databricks_openai import AsyncDatabricksOpenAI
from agents import set_default_openai_api, set_default_openai_client, Agent
from agents.tracing import set_trace_processors

# Set up async client (recommended for agent servers)
set_default_openai_client(AsyncDatabricksOpenAI())
set_default_openai_api("chat_completions")

# Use MLflow for tracing (disables SDK's built-in tracing)
set_trace_processors([])
mlflow.openai.autolog()
```

## Adding MCP Servers

```python
from databricks_openai.agents import McpServer

# UC Functions
uc_server = McpServer(
    url=f"{host}/api/2.0/mcp/functions/{catalog}/{schema}",
    name="uc functions",
)

# Genie Space
genie_server = McpServer(
    url=f"{host}/api/2.0/mcp/genie/{space_id}",
    name="genie space",
)

# Vector Search
vector_server = McpServer(
    url=f"{host}/api/2.0/mcp/vector-search/{catalog}/{schema}/{index}",
    name="vector search",
)

# Add to agent
agent = Agent(
    name="my agent",
    instructions="You are a helpful agent.",
    model="databricks-claude-3-7-sonnet",
    mcp_servers=[uc_server, genie_server, vector_server],
)
```

**After adding MCP servers:** Grant permissions in `databricks.yml` (see **add-tools** skill)

## Changing the Model

Available models (check workspace for current list):

- `databricks-claude-3-7-sonnet`
- `databricks-claude-3-5-sonnet`
- `databricks-meta-llama-3-3-70b-instruct`

```python
agent = Agent(
    name="my agent",
    model="databricks-claude-3-7-sonnet",  # Change here
    ...
)
```

**Note:** Some workspaces require granting the app access to the serving endpoint in `databricks.yml`. See the **add-tools** skill and `examples/serving-endpoint.yaml`.

## Changing Instructions

```python
agent = Agent(
    name="my agent",
    instructions="""You are a helpful data analyst assistant.

    You have access to:
    - Company sales data via Genie
    - Product documentation via vector search

    Always cite your sources when answering questions.""",
    ...
)
```

## Running the Agent

```python
from agents import Runner

# Non-streaming
messages = [{"role": "user", "content": "hi"}]
result = await Runner.run(agent, messages)

# Streaming
result = Runner.run_streamed(agent, input=messages)
async for event in result.stream_events():
    # Process stream events
    pass
```

**Converting to Responses API format:** Use `process_agent_stream_events()` from `agent_server/utils.py` to convert streaming output to Responses API compatible format:

```python
from agent_server.utils import process_agent_stream_events

result = Runner.run_streamed(agent, input=messages)
async for event in process_agent_stream_events(result.stream_events()):
    yield event  # Yields ResponsesAgentStreamEvent objects
```

## External Resources

1. [databricks-openai SDK](https://github.com/databricks/databricks-ai-bridge/tree/main/integrations/openai)
2. [Agent examples](https://github.com/databricks/app-templates)
3. [Agent Framework docs](https://docs.databricks.com/aws/en/generative-ai/agent-framework/)
4. [Adding tools](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool)
5. [OpenAI Agents SDK](https://platform.openai.com/docs/guides/agents-sdk)
6. [Responses API](https://mlflow.org/docs/latest/genai/serving/responses-agent/)

## Next Steps

- Discover available tools: see [`discover-tools`](../discover-tools/discover-tools.md) reference
- Grant resource permissions: see **add-tools** skill
- Test locally: see [`run-locally`](../run-locally/run-locally.md) reference
- Deploy: see [`deploy`](../deploy/deploy.md) reference
