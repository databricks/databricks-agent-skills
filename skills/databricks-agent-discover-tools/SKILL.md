---
name: databricks-agent-discover-tools
description: "Discover available tools and resources in Databricks workspace. Use when: (1) User asks 'what tools are available', (2) Before writing agent code, (3) Looking for MCP servers, Genie spaces, UC functions, or vector search indexes, (4) User says 'discover', 'find resources', or 'what can I connect to'."
---

# Discover Available Tools

**Run tool discovery BEFORE writing agent code** to understand what resources are available in the workspace.

## Run Discovery

```bash
uv run discover-tools
```

**Options:**
```bash
# Limit to specific catalog/schema
uv run discover-tools --catalog my_catalog --schema my_schema

# Output as JSON
uv run discover-tools --format json --output tools.json

# Save markdown report
uv run discover-tools --output tools.md

# Use specific Databricks profile
uv run discover-tools --profile DEFAULT
```

## What Gets Discovered

| Resource Type | Description | MCP URL Pattern |
|--------------|-------------|-----------------|
| **UC Functions** | SQL UDFs as agent tools | `{host}/api/2.0/mcp/functions/{catalog}/{schema}` |
| **UC Tables** | Structured data for querying | (via UC functions) |
| **Vector Search Indexes** | RAG applications | `{host}/api/2.0/mcp/vector-search/{catalog}/{schema}` |
| **Genie Spaces** | Natural language data interface | `{host}/api/2.0/mcp/genie/{space_id}` |
| **Custom MCP Servers** | Apps starting with `mcp-*` | `{app_url}/mcp` |
| **External MCP Servers** | Via UC connections | `{host}/api/2.0/mcp/external/{connection_name}` |

## Next Steps

After discovering tools:
1. **Add MCP servers to your agent** - See **modify-agent** skill for SDK-specific code examples
2. **Grant permissions** in `databricks.yml` - See **add-tools** skill for YAML snippets
3. **Test locally** with `uv run start-app` - See **databricks-agent-run-locally** skill

Need a resource that doesn't exist yet? See the **databricks-agent-create-tools** skill.
