# Local Python Function Tools

For operations that don't need external data sources or MCP servers, define tools directly in your agent code. These run in the same process as your agent — no resource creation or `databricks.yml` permissions needed.

## When to use local tools vs. MCP

- **Local tools**: Simple logic, API calls with custom auth, data transformations, utility functions
- **MCP tools**: When you need Databricks-managed auth, UC governance, or access to Databricks resources (tables, indexes, Genie)

## OpenAI Agents SDK

```python
from agents import Agent, function_tool

@function_tool
def get_current_time() -> str:
    """Get the current date and time in ISO format."""
    from datetime import datetime
    return datetime.now().isoformat()

@function_tool
def calculate_discount(price: float, percent: float) -> str:
    """Calculate a discounted price. Returns the new price after applying the discount."""
    discounted = price * (1 - percent / 100)
    return f"${discounted:.2f}"

agent = Agent(
    name="My agent",
    instructions="You are a helpful assistant.",
    model="databricks-claude-sonnet-4-5",
    tools=[get_current_time, calculate_discount],
)
```

## LangGraph

```python
from langchain_core.tools import tool

@tool
def get_current_time() -> str:
    """Get the current date and time in ISO format."""
    from datetime import datetime
    return datetime.now().isoformat()

@tool
def calculate_discount(price: float, percent: float) -> str:
    """Calculate a discounted price. Returns the new price after applying the discount."""
    discounted = price * (1 - percent / 100)
    return f"${discounted:.2f}"

# Pass to create_react_agent or add to your tools list
tools = [get_current_time, calculate_discount]
```

## Error handling

Both SDKs handle tool errors gracefully by default — the error message is returned to the LLM so it can retry or respond to the user. For custom error messages, use the patterns below.

### OpenAI Agents SDK

`@function_tool` includes a built-in `default_tool_error_function` that catches exceptions and returns `"An error occurred while running the tool. Error: {error}"` to the LLM. To customize:

```python
from agents import RunContextWrapper, function_tool

def handle_api_error(ctx: RunContextWrapper, error: Exception) -> str:
    """Return a helpful error message the LLM can act on."""
    return f"Tool failed: {error}. Try a different query or ask the user for clarification."

@function_tool(failure_error_function=handle_api_error)
def call_external_api(query: str) -> str:
    """Call an external API."""
    # If this raises, handle_api_error returns a message to the LLM
    ...
```

### LangGraph

LangGraph tools raise by default. To return errors to the LLM instead of crashing, raise `ToolException` and set `handle_tool_error`:

```python
from langchain_core.tools import tool, ToolException

@tool
def call_external_api(query: str) -> str:
    """Call an external API."""
    try:
        ...
    except Exception as e:
        raise ToolException(f"API call failed: {e}. Try a different query.")

# Enable error handling on the tool
call_external_api.handle_tool_error = True
```

Set `handle_tool_error=True` for a generic message, or assign a string/callable for custom messages. Only `ToolException` is caught — other exceptions still raise.

## Tips

- The docstring becomes the tool description the LLM sees — make it clear and specific
- Type annotations on parameters help the LLM provide correct arguments
- Local tools can call the Databricks SDK, external APIs, or any Python library
