---
name: app-templates-add-tools-langgraph
description: "Add tools to your agent and grant required permissions in databricks.yml. Use when: (1) Adding MCP servers, Genie spaces, vector search, or UC functions to agent, (2) Permission errors at runtime, (3) User says 'add tool', 'connect to', 'grant permission', (4) Configuring databricks.yml resources."
---

# Add Tools & Grant Permissions

> **Profile reminder:** All `databricks` CLI commands must include the profile from `.env`: `databricks <command> --profile <profile>`

> Don't have the resource yet? See **app-templates-create-tools** skill first.

**After adding any MCP server to your agent, you MUST grant the app access in `databricks.yml`.**

Without this, you'll get permission errors when the agent tries to use the resource.

## Workflow

**Step 1:** Add MCP server in `agent_server/agent.py`:
```python
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

genie_server = DatabricksMCPServer(
    url=f"{host}/api/2.0/mcp/genie/01234567-89ab-cdef",
    name="my genie space",
)

mcp_client = DatabricksMultiServerMCPClient([genie_server])
tools = await mcp_client.get_tools()
```

**Step 2:** Grant access in `databricks.yml`:
```yaml
resources:
  apps:
    agent_langgraph:
      resources:
        - name: 'my_genie_space'
          genie_space:
            name: 'My Genie Space'
            space_id: '01234567-89ab-cdef'
            permission: 'CAN_RUN'
```

**Step 3:** Deploy and run:
```bash
databricks bundle deploy
databricks bundle run agent_langgraph  # Required to start app with new code!
```

See **app-templates-deploy** skill for more details.

## Resource Type Examples

See the `examples/` directory for complete YAML snippets:

| File | Resource Type | When to Use |
|------|--------------|-------------|
| `uc-function.yaml` | Unity Catalog function | UC functions via MCP |
| `uc-connection.yaml` | UC connection | External MCP servers |
| `vector-search.yaml` | Vector search index | RAG applications |
| `sql-warehouse.yaml` | SQL warehouse | SQL execution |
| `serving-endpoint.yaml` | Model serving endpoint | Model inference |
| `genie-space.yaml` | Genie space | Natural language data |
| `lakebase.yaml` | Lakebase database | Agent memory storage (provisioned) |
| `lakebase-autoscaling.yaml` | Lakebase autoscaling postgres | Agent memory storage (autoscaling) |
| `experiment.yaml` | MLflow experiment | Tracing (already configured) |
| `app.yaml` | Databricks App (app-to-app) | Custom MCP servers hosted as Apps |
| `custom-mcp-server.md` | Custom MCP apps | Apps starting with `mcp-*` |

## Custom MCP Servers (Databricks Apps)

Declare the target app as an `app` resource in `databricks.yml` — the bundle grants `CAN_USE` on deploy. Requires Databricks CLI **v0.298.0+**.

```yaml
resources:
  apps:
    agent_langgraph:
      resources:
        - name: 'mcp_server'
          app:
            name: 'mcp-my-server'
            permission: CAN_USE
```

See `examples/custom-mcp-server.md` for the full flow (agent code + YAML + deploy).

## value_from Pattern

**IMPORTANT**: Make sure all `value_from` references in `databricks.yml` `config.env` reference an existing key in the `databricks.yml` `resources` list.
Some resources need environment variables in your app. Use `value_from` in `databricks.yml` `config.env` to reference resources defined in `databricks.yml`:

```yaml
# In databricks.yml, under apps.<app>.config.env:
env:
  - name: MLFLOW_EXPERIMENT_ID
    value_from: "experiment"        # References resources.apps.<app>.resources[name='experiment']
  - name: LAKEBASE_INSTANCE_NAME
    value_from: "database"   # References resources.apps.<app>.resources[name='database']
```

**Critical:** Every `value_from` value must match a `name` field in `databricks.yml` resources.

## MCP Error Handling

MCP tool calls can fail (network issues, permission errors, timeouts). Use `handle_tool_error` on MCP servers to catch errors and return them to the LLM instead of crashing the agent:

```python
DatabricksMCPServer(
    name="genie",
    url=f"{host}/api/2.0/mcp/genie/{space_id}",
    handle_tool_error=True,   # Return error messages to LLM instead of raising
    timeout=60.0,             # Increase timeout for slow tools like Genie
)
```

For local function tools defined with `@tool`, see `app-templates-create-tools` skill > `examples/local-python-tools.md` for the `ToolException` + `handle_tool_error` pattern.

## Important Notes

- **MLflow experiment**: Already configured in template, no action needed
- **Multiple resources**: Add multiple entries under `resources:` list
- **Permission types vary**: Each resource type has specific permission values
- **Deploy + Run after changes**: Run both `databricks bundle deploy` AND `databricks bundle run my_agent`
- **value_from matching**: Ensure `config.env` `value_from` values match `databricks.yml` resource `name` values
