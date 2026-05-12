---
name: modify-langgraph-agent
description: "Modify agent code, add tools, or change configuration. Use when: (1) User says 'modify agent', 'add tool', 'change model', or 'edit agent.py', (2) Adding MCP servers to agent, (3) Changing agent instructions, (4) Understanding SDK patterns."
metadata:
  version: "0.0.1"
---

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
from databricks.sdk import WorkspaceClient
from databricks_langchain import ChatDatabricks, DatabricksMCPServer, DatabricksMultiServerMCPClient
from langchain.agents import create_agent

# Enable autologging for tracing
mlflow.langchain.autolog()

# Initialize workspace client
workspace_client = WorkspaceClient()
```

---

## databricks-langchain SDK Overview

**SDK Location:** https://github.com/databricks/databricks-ai-bridge/tree/main/integrations/langchain

Before making any changes, ensure that the APIs actually exist in the SDK. If something is missing from the documentation here, look in the venv's `site-packages` directory for the `databricks_langchain` package. If it's not installed, run `uv sync` to create the .venv and install the package.

---

### ChatDatabricks - LLM Chat Interface

Connects to Databricks Model Serving endpoints for LLM inference.

```python
from databricks_langchain import ChatDatabricks

llm = ChatDatabricks(
    endpoint="databricks-claude-3-7-sonnet",  # or databricks-meta-llama-3-1-70b-instruct
    temperature=0,
    max_tokens=500,
)

# For Responses API agents:
llm = ChatDatabricks(endpoint="my-agent-endpoint", use_responses_api=True)
```

Available models (check workspace for current list):

- `databricks-claude-3-7-sonnet`
- `databricks-claude-3-5-sonnet`
- `databricks-meta-llama-3-3-70b-instruct`

**Note:** Some workspaces require granting the app access to the serving endpoint in `databricks.yml`. See the **add-tools** skill and `examples/serving-endpoint.yaml`.

---

### DatabricksEmbeddings - Generate Embeddings

Query Databricks embedding model endpoints.

```python
from databricks_langchain import DatabricksEmbeddings

embeddings = DatabricksEmbeddings(endpoint="databricks-bge-large-en")
vector = embeddings.embed_query("The meaning of life is 42")
vectors = embeddings.embed_documents(["doc1", "doc2"])
```

---

### DatabricksVectorSearch - Vector Store

Connect to Databricks Vector Search indexes for similarity search.

```python
from databricks_langchain import DatabricksVectorSearch

# Delta-sync index with Databricks-managed embeddings
vs = DatabricksVectorSearch(index_name="catalog.schema.index_name")

# Direct-access or self-managed embeddings
vs = DatabricksVectorSearch(
    index_name="catalog.schema.index_name",
    embedding=embeddings,
    text_column="content",
)

docs = vs.similarity_search("query", k=5)
```

---

### MCP Client - Tool Integration

Connect to MCP (Model Context Protocol) servers to get tools for your agent.

**Basic MCP Server (manual URL):**

```python
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

client = DatabricksMultiServerMCPClient([
    DatabricksMCPServer(
        name="system-ai",
        url=f"{host}/api/2.0/mcp/functions/system/ai",
    )
])
tools = await client.get_tools()
```

**From UC Function (convenience helper):**

Creates MCP server for Unity Catalog functions. If `function_name` is omitted, exposes all functions in the schema.

```python
server = DatabricksMCPServer.from_uc_function(
    catalog="main",
    schema="tools",
    function_name="send_email",  # Optional - omit for all functions in schema
    name="email-server",
    timeout=30.0,
    handle_tool_error=True,
)
```

**From Vector Search (convenience helper):**

Creates MCP server for Vector Search indexes. If `index_name` is omitted, exposes all indexes in the schema.

```python
server = DatabricksMCPServer.from_vector_search(
    catalog="main",
    schema="embeddings",
    index_name="product_docs",  # Optional - omit for all indexes in schema
    name="docs-search",
    timeout=30.0,
)
```

**From Genie Space:**

Create MCP server from Genie Space. Get the genie space ID from the URL.

Example: `https://workspace.cloud.databricks.com/genie/rooms/01f0515f6739169283ef2c39b7329700?o=123` means the genie space ID is `01f0515f6739169283ef2c39b7329700`

```python
DatabricksMCPServer(
    name="genie",
    url=f"{host_name}/api/2.0/mcp/genie/01f0515f6739169283ef2c39b7329700",
)
```

**Non-Databricks MCP Server:**

```python
from databricks_langchain import MCPServer

server = MCPServer(
    name="external-server",
    url="https://other-server.com/mcp",
    headers={"X-API-Key": "secret"},
    timeout=15.0,
)
```

**After adding MCP servers:** Grant permissions in `databricks.yml` (see **add-tools** skill)

---

## Running the Agent

```python
from langchain.agents import create_agent

# Create agent - ONLY accepts tools and model, NO prompt/instructions parameter
agent = create_agent(tools=tools, model=llm)

# Non-streaming
messages = {"messages": [{"role": "user", "content": "hi"}]}
result = await agent.ainvoke(messages)

# Streaming
async for event in agent.astream(input=messages, stream_mode=["updates", "messages"]):
    # Process stream events
    pass
```

**Converting to Responses API format:** Use `process_agent_astream_events()` from `agent_server/utils.py`:

```python
from agent_server.utils import process_agent_astream_events

async for event in process_agent_astream_events(
    agent.astream(input=messages, stream_mode=["updates", "messages"])
):
    yield event  # Yields ResponsesAgentStreamEvent objects
```

---

## Customizing Agent Behavior (System Instructions)

> **IMPORTANT:** `create_agent()` does NOT accept `prompt`, `instructions`, or `system_message` parameters. Attempting to pass these will cause a runtime error.

In LangGraph, agent behavior is customized by prepending a system message to the conversation messages.

**Correct pattern in `agent.py`:**

1. Define instructions as a constant:

```python
AGENT_INSTRUCTIONS = """You are a helpful data analyst assistant.

You have access to:
- Company sales data via Genie
- Product documentation via vector search

Always cite your sources when answering questions."""
```

2. Prepend to messages in the `streaming()` function:

```python
@stream()
async def streaming(request: ResponsesAgentRequest) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    agent = await init_agent()
    # Prepend system instructions to user messages
    user_messages = to_chat_completions_input([i.model_dump() for i in request.input])
    messages = {"messages": [{"role": "system", "content": AGENT_INSTRUCTIONS}] + user_messages}

    async for event in process_agent_astream_events(
        agent.astream(input=messages, stream_mode=["updates", "messages"])
    ):
        yield event
```

**Common mistake to avoid:**

```python
# WRONG - will cause "unexpected keyword argument" error
agent = create_agent(tools=tools, model=llm, prompt=AGENT_INSTRUCTIONS)

# CORRECT - add instructions via messages
messages = {"messages": [{"role": "system", "content": AGENT_INSTRUCTIONS}] + user_messages}
```

For advanced customization (routing, state management, custom graphs), refer to the [LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/overview).

---

## External Connection Tools

Connect to external services via Unity Catalog HTTP connections:

- **Slack** - Post messages to channels
- **Google Calendar** - Calendar operations
- **Microsoft Graph API** - Office 365 services
- **Azure AI Search** - Search functionality
- **Any HTTP API** - Use `http_request` from databricks-sdk

Example: Create UC function wrapping HTTP request for Slack, then expose via MCP.

---

## External Resources

1. [databricks-langchain SDK](https://github.com/databricks/databricks-ai-bridge/tree/main/integrations/langchain)
2. [Agent examples](https://github.com/databricks/app-templates)
3. [Agent Framework docs](https://docs.databricks.com/aws/en/generative-ai/agent-framework/)
4. [Adding tools](https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool)
5. [LangGraph documentation](https://docs.langchain.com/oss/python/langgraph/overview)
6. [Responses API](https://mlflow.org/docs/latest/genai/serving/responses-agent/)

## Next Steps

- Discover available tools: see **discover-tools** skill
- Grant resource permissions: see **add-tools** skill
- Add memory capabilities: see **agent-memory** skill
- Test locally: see **run-locally** skill
- Deploy: see **deploy** skill
