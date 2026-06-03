# Create a UC Connection for External MCP Servers

Unity Catalog HTTP connections let you register external MCP servers so Databricks can securely proxy requests and manage credentials. After creating the connection, your agent accesses the external MCP server through a managed Databricks endpoint.

## Create the connection

### Option 1: Managed OAuth (Glean, GitHub, Atlassian, Google Drive, SharePoint)

For supported providers, Databricks manages the OAuth credentials. Create the connection in the Databricks UI:

1. Go to **Catalog** > **External Data** > **Connections**
2. Click **Create connection**
3. Select **HTTP** connection type
4. Choose **OAuth User to Machine Per User** auth type
5. Select the provider from the **OAuth Provider** drop-down
6. Configure scopes as needed

You can also install pre-built integrations from the **Databricks Marketplace**.

See [external MCP docs](https://docs.databricks.com/aws/en/generative-ai/mcp/external-mcp) for the full list of supported providers, scopes, and setup methods.

### Option 2: CLI with bearer token

```bash
databricks connections create --json '{
  "name": "my-external-mcp",
  "connection_type": "HTTP",
  "options": {
    "host": "https://mcp.example.com",
    "base_path": "/api",
    "bearer_token": "<your-token>"
  }
}' --profile <profile>
```

### Option 3: CLI with OAuth M2M

```bash
databricks connections create --json '{
  "name": "my-external-mcp",
  "connection_type": "HTTP",
  "options": {
    "host": "https://mcp.example.com",
    "base_path": "/mcp",
    "client_id": "<client-id>",
    "client_secret": "<client-secret>",
    "token_endpoint": "https://auth.example.com/oauth/token",
    "oauth_scope": "read write"
  }
}' --profile <profile>
```

## Verify

```bash
databricks connections get my-external-mcp --profile <profile>
```

## Next step

Wire the external MCP server into your agent. See the **add-tools** skill and use `examples/uc-connection.yaml` for the `databricks.yml` resource grant.

MCP URL: `{host}/api/2.0/mcp/external/{connection_name}`

> You can also access the external server through the [UC connections proxy](https://docs.databricks.com/aws/en/query-federation/http#proxy), which works with any HTTP or MCP client and supports arbitrary sub-paths and all HTTP methods: `{host}/api/2.0/unity-catalog/connections/{connection_name}/proxy[/<sub-path>]`
