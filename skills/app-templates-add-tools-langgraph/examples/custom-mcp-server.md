# Custom MCP Server (Databricks App)

Custom MCP servers are Databricks Apps with names starting with `mcp-*`.

Declare the target app as an `app` resource in `databricks.yml` and the bundle will grant `CAN_USE` on deploy. Requires Databricks CLI **v0.298.0+**.

## Steps

### 1. Add MCP server in `agent_server/agent.py`

```python
from databricks_langchain import DatabricksMCPServer, DatabricksMultiServerMCPClient

custom_mcp = DatabricksMCPServer(
    url="https://mcp-my-server.cloud.databricks.com/mcp",
    name="my custom mcp server",
)

mcp_client = DatabricksMultiServerMCPClient([custom_mcp])
tools = await mcp_client.get_tools()
```

### 2. Grant access in `databricks.yml`

Add the target app as a resource:

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

### 3. Deploy

```bash
databricks bundle deploy
databricks bundle run agent_langgraph
```

The bundle grants `CAN_USE` on the target app automatically — no manual permission steps needed.

## Notes

- Requires CLI v0.298.0+ (earlier versions will warn `unknown field: name` on `app.name`)
- The only supported permission is `CAN_USE`
- Subsequent `databricks bundle deploy` commands preserve the `app` resource
