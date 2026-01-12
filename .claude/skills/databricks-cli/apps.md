# Databricks Apps Development

## Validation

⚠️ **Always validate before deploying:**

```bash
databricks experimental aitools tools validate ./ --profile my-workspace
```

This is battle-tested to catch common issues before deployment. Prefer using this over manual checks (e.g. `npm run lint`), as it covers more ground specific to Databricks Apps.

## Deployment

⚠️ **USER CONSENT REQUIRED: Only deploy with explicit user permission.**

```bash
databricks experimental aitools tools deploy --profile my-workspace
```

**If deployment requires manual steps** (see Deployment Debugging section below)

## View and Manage

```bash
databricks bundle summary --profile my-workspace
```

## View App Logs

To troubleshoot deployed apps, view their logs:

```bash
databricks apps logs <app-name> --tail-lines 100 --profile my-workspace
```

## Working with SQL Warehouses

Many apps need to query data from SQL warehouses. To get the default warehouse:

```bash
# Get the default SQL warehouse that the workspace uses
databricks experimental aitools tools get-default-warehouse --profile my-workspace
```

This is useful when configuring apps that need to connect to a warehouse for data access.

## Local Development vs Deployed Apps

### During Development

- Start template-specific dev server (see project's CLAUDE.md for command and port)
- Use localhost URL shown when dev server starts

### After Deployment

- Get URL from: `databricks bundle summary --profile my-workspace`

### Decision Tree

- **"open the app"** + not deployed → localhost
- **"open the app"** + deployed → ask which environment
- **"localhost"/"local"** → always localhost

## Common Workflows

### Creating a New App

See [Project Scaffolding](projects.md) for creating new apps using templates.

### Updating an Existing App

1. Make changes to your code
2. Validate: `databricks experimental aitools tools validate ./ --profile my-workspace`
3. Get user consent to deploy
4. Deploy: `databricks experimental aitools tools deploy --profile my-workspace`
5. Check logs if issues occur: `databricks apps logs <app-name> --tail-lines 100 --profile my-workspace`

### Troubleshooting

1. Check validation output first
2. View app logs: `databricks apps logs <app-name> --tail-lines 100 --profile my-workspace`
3. Check bundle summary: `databricks bundle summary --profile my-workspace`
4. Verify app status: `databricks apps get <app-name> --profile my-workspace`

## Deployment Debugging

### Common Deployment Errors

#### 1. Validation npm Install Conflicts

**Symptom**: `databricks experimental aitools tools validate` fails with npm ENOTEMPTY errors

**Cause**: Validation tries to run `npm install` while dev server or previous install has files locked

**Solution**:
```bash
# Stop all dev servers first
# Kill any running npm processes

# Clean and reinstall
npm run clean && npm install

# Try manual build to verify app is valid
npm run build

# If manual build succeeds, validation failure is due to npm conflicts
# You can proceed to deploy without validation
```

#### 2. Warehouse Lookup Errors

**Symptom**: `Error: failed to resolve warehouse: Serverless Starter Warehouse`

**Cause**: `databricks.yml` has a warehouse lookup that doesn't match an actual warehouse name

**Solution**:
```yaml
# Edit databricks.yml
# Remove the lookup section and rely on explicit warehouse_id
variables:
  warehouse_id:
    description: The ID of the warehouse to use
    # REMOVE THIS:
    # lookup:
    #   warehouse: Serverless Starter Warehouse

# Make sure target has explicit warehouse_id
targets:
  dev:
    variables:
      warehouse_id: <your-warehouse-id>
```

Get warehouse ID:
```bash
databricks experimental aitools tools get-default-warehouse --profile my-workspace
```

#### 3. Source Code Path Errors

**Symptom**:
- `Error: Source code path must be a valid workspace path`
- `Error: Source code path is required for an app with no previous active deployment`

**Cause**: App was created but source code not deployed yet, or using local path instead of workspace path

**Solution**:
```bash
# Get the workspace path from bundle summary
databricks bundle summary --profile my-workspace

# Use the "Path" value from output
# Format: /Workspace/Users/<your-email>/.bundle/<bundle-name>/<target>/files
databricks apps deploy <app-name> --source-code-path /Workspace/Users/<email>/.bundle/<bundle-name>/dev/files --profile my-workspace
```

#### 4. App Status UNAVAILABLE After Deployment

**Symptom**: `bundle deploy` succeeds but app shows "UNAVAILABLE" or "App has not been deployed yet"

**Cause**: Bundle created the app resource but didn't deploy source code, or compute is stopped

**Solution**:
```bash
# Step 1: Verify app exists
databricks apps get <app-name> --profile my-workspace

# Step 2: Start compute if stopped
databricks apps start <app-name> --profile my-workspace

# Step 3: Deploy source code manually
databricks apps deploy <app-name> --source-code-path /Workspace/Users/<email>/.bundle/<bundle-name>/dev/files --profile my-workspace

# Step 4: Check app status
databricks apps get <app-name> --profile my-workspace
# Look for: "app_status": { "state": "RUNNING" }
```

### Manual Deployment Workflow

If `databricks experimental aitools tools deploy` fails, follow this complete workflow:

```bash
# Step 1: Deploy bundle (creates/updates app infrastructure)
databricks bundle deploy --profile my-workspace
# Note the workspace path from output: "Uploading bundle files to /Workspace/Users/..."

# Step 2: Get app name from bundle summary
databricks bundle summary --profile my-workspace
# Note the app name (e.g., "dev-myapp")

# Step 3: Start app compute
databricks apps start <app-name> --profile my-workspace

# Step 4: Deploy source code using workspace path from Step 1
databricks apps deploy <app-name> --source-code-path /Workspace/Users/<your-email>/.bundle/<bundle-name>/dev/files --profile my-workspace

# Step 5: Verify deployment
databricks apps get <app-name> --profile my-workspace
# Check: app_status.state = "RUNNING" and active_deployment.status.state = "SUCCEEDED"
```

### Checking App Status

Get complete app information including status, URLs, and configuration:

```bash
databricks apps get <app-name> --profile my-workspace
```

**Key fields to check:**
- `app_status.state`: Should be "RUNNING" when healthy
- `compute_status.state`: Should be "ACTIVE" when running
- `url`: The public URL to access your app
- `active_deployment.status.state`: Should be "SUCCEEDED" after deployment
- `active_deployment.status.message`: Deployment status message

### Redeploying After Changes

```bash
# Using bundle (automatically redeploys source code if changed)
databricks bundle deploy --profile my-workspace

# Always check logs after redeployment
databricks apps logs <app-name> --tail-lines 50 --profile my-workspace
```

### App Lifecycle Commands

```bash
# Start stopped app
databricks apps start <app-name> --profile my-workspace

# Stop running app (stops compute to save costs)
databricks apps stop <app-name> --profile my-workspace

# Delete app entirely
databricks apps delete <app-name> --profile my-workspace

# List all apps
databricks apps list --profile my-workspace
```

## Related Topics

- [Project Scaffolding](projects.md) - Create new apps with templates
- [Asset Bundles](asset-bundles.md) - Manage apps with Infrastructure-as-Code
- [Secrets](secrets.md) - Store credentials securely
