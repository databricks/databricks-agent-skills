---
name: app-templates-create-tools
description: "Create Databricks resources that agents connect to as tools. Use when: (1) User needs to create a Genie space, vector search index, UC function, or UC connection, (2) User says 'create tool', 'set up genie', 'create vector search', 'register MCP server', (3) Before add-tools when the resource doesn't exist yet, (4) User asks 'what do I need to create before adding this tool'."
---

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

1. **Discover** existing resources: `uv run discover-tools` (see **app-templates-discover-tools** skill)
2. **Create** the resource if it doesn't exist (this skill)
3. **Add** the MCP server to your agent code + grant permissions (see **add-tools** skill)
4. **Deploy** (see **app-templates-deploy** skill)
