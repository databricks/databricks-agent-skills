# Create a Genie Space

Genie spaces let agents query structured data in Unity Catalog tables using natural language. A Genie space can include up to 30 tables or views.

## Create via Databricks UI

1. In your workspace, go to **Genie** in the left sidebar.
2. Click **New** to create a new Genie space.
3. Add the Unity Catalog tables or views your agent needs to query.
4. Configure instructions to guide how Genie interprets queries (optional but recommended).
5. Configure a default SQL warehouse: go to **Configure** > **Settings** > **Default warehouse**.
6. Share the space with the app's service principal:
   - Click **Share** in the top right
   - Enter the service principal name, click **Add**, and set the permission level to **CAN RUN**
   - To find your app's service principal: `databricks apps get <app-name> --output json --profile <profile> | jq -r '.service_principal_name'`

## Find the space ID

The space ID is in the URL when viewing the Genie space:

```
https://<workspace>.databricks.com/genie/rooms/<space-id>?o=...
```

To list all Genie spaces via CLI:

```bash
databricks genie list-spaces --profile <profile>
```

## Next step

Wire the Genie space into your agent and grant permissions. See the **add-tools** skill and use `examples/genie-space.yaml` for the `databricks.yml` resource grant.

MCP URL: `{host}/api/2.0/mcp/genie/{space_id}` (OAuth scope for on-behalf-of-user auth: `genie`)
