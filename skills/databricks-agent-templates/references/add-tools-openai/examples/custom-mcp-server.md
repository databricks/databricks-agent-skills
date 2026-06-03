# Custom MCP Server (Databricks App)

Custom MCP servers are Databricks Apps with names starting with `mcp-*`.

Declare the target app as an `app` resource in `databricks.yml` and the bundle will grant `CAN_USE` on deploy. Requires Databricks CLI **v0.298.0+**.

## Steps

### 1. Add MCP server in `agent_server/agent.py`

```python
from databricks_openai.agents import McpServer

custom_mcp = McpServer(
    url="https://mcp-my-server.cloud.databricks.com/mcp",
    name="my custom mcp server",
)

agent = Agent(
    name="my agent",
    model="databricks-claude-3-7-sonnet",
    mcp_servers=[custom_mcp],
)
```

### 2. Grant access in `databricks.yml`

Add the target app as a resource:

```yaml
resources:
  apps:
    agent_openai_agents_sdk:
      resources:
        - name: 'mcp_server'
          app:
            name: 'mcp-my-server'
            permission: CAN_USE
```

### 3. Deploy

```bash
databricks bundle deploy
databricks bundle run <your-app-resource-name>  # from databricks.yml resources.apps.*
```

The bundle grants `CAN_USE` on the target app automatically — no manual permission steps needed.

## Notes

- Requires CLI v0.298.0+ (earlier versions will warn `unknown field: name` on `app.name`)
- The only supported permission is `CAN_USE`
- Subsequent `databricks bundle deploy` commands preserve the `app` resource
