# Create Tool Resources

> This skill covers creating the Databricks resources your agent connects to.
> After creating a resource, use the **add-tools** skill to wire it into your agent and grant permissions.

## Which resource do you need?

| I want my agent to... | Resource to create | Guide |
|---|---|---|
| Answer questions about structured data | Genie space | `examples/genie-space.md` |
| Search documents / RAG | Vector Search index | `examples/vector-search-index.md` |
| Call custom SQL/Python logic | UC function | `examples/uc-function.md` |
| Connect to an external MCP server | UC connection | `examples/uc-connection.md` |
| Add inline Python tools | Local function tools | `examples/local-python-tools.md` |

## Workflow

1. **Discover** existing resources: `uv run discover-tools` (see [`discover-tools`](../discover-tools/discover-tools.md) reference)
2. **Create** the resource if it doesn't exist (this skill)
3. **Add** the MCP server to your agent code + grant permissions (see **add-tools** skill)
4. **Deploy** (see [`deploy`](../deploy/deploy.md) reference)
