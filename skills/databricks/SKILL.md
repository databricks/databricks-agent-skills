---
name: "databricks"
description: "MUST USE for anything related to Databricks!!!. Tool for working with Databricks services: Project Scaffolding (creating new apps/jobs/pipelines), Apps, Unity Catalog (UC), Data Exploration (schema discovery, SQL queries), DBSQL, LakeFlow, AI/BI Dashboards, Databricks Genie, Model Serving, and Asset Bundles (DABs). Use when user needs to create new projects, discover table schemas, execute SQL, or work with any Databricks resource."
---

# Databricks

This skill provides comprehensive guidance for working with Databricks across all services and use cases.

## Quick Navigation

- **[Project Scaffolding](projects.md)** - Create new Databricks projects with AI-friendly templates
- **[Databricks Apps](apps.md)** - Build and deploy data/AI applications
- **[Unity Catalog](unity-catalog.md)** - Catalogs, schemas, tables, volumes, and governance
- **[Data Exploration](data-exploration.md)** - Table schema discovery and SQL query execution
- **[Asset Bundles (DABs)](asset-bundles.md)** - Infrastructure-as-Code for Databricks projects
- **[Model Serving](model-serving.md)** - Real-time ML inference endpoints
- **[DBSQL](dbsql.md)** - SQL warehouses, queries, dashboards, and alerts
- **[LakeFlow](lakeflow.md)** - Delta Live Tables and ETL pipelines
- **[Jobs](jobs.md)** - Workflow orchestration
- **[Clusters](clusters.md)** - Compute resource management
- **[Workspace](workspace.md)** - Notebooks and file management
- **[DBFS](dbfs.md)** - Databricks File System operations
- **[Secrets](secrets.md)** - Secure credential storage
- **[AI/BI Dashboards](ai-bi-dashboards.md)** - Interactive analytics with AI
- **[Databricks Genie](genie.md)** - AI-powered data analysis
- **[Common Workflows](workflows.md)** - Best practices and complete workflows

## Task-Based Navigation

**IMPORTANT**: When the user asks about specific tasks, immediately read the relevant guide first before executing commands:

### Project Creation Tasks
- **"Create new project"** → Read [Project Scaffolding](projects.md)
- **"Initialize app/job/pipeline"** → Read [Project Scaffolding](projects.md)
- **"Start new Databricks project"** → Read [Project Scaffolding](projects.md)

### Data & Analysis Tasks
- **"Summarize dataset X"** → Read [Data Exploration](data-exploration.md) and use `discover-schema` command
- **"What's in table X?"** → Read [Data Exploration](data-exploration.md) and use `discover-schema` command
- **"Explore dataset X"** → Read [Data Exploration](data-exploration.md) and use `discover-schema` + `query` commands
- **"Run SQL query"** → Read [Data Exploration](data-exploration.md) and use `query` command
- **"Analyze with natural language"** → Read [Databricks Genie](genie.md) for AI-powered analysis

### Application Tasks
- **"Deploy app"** → Read [Databricks Apps](apps.md)
- **"Create/manage app"** → Read [Databricks Apps](apps.md)

### Data Management Tasks
- **"Create/manage tables"** → Read [Unity Catalog](unity-catalog.md)
- **"List catalogs/schemas"** → Read [Unity Catalog](unity-catalog.md)
- **"Set up governance"** → Read [Unity Catalog](unity-catalog.md)

### Pipeline & Workflow Tasks
- **"Create workflow"** → Read [Jobs](jobs.md)
- **"Build ETL pipeline"** → Read [LakeFlow](lakeflow.md)
- **"Deploy infrastructure"** → Read [Asset Bundles](asset-bundles.md)

### ML Tasks
- **"Deploy model"** → Read [Model Serving](model-serving.md)
- **"Query endpoint"** → Read [Model Serving](model-serving.md)

## Prerequisites

1. **Databricks CLI must be installed**
   - Verify: `databricks --version`
   - If not installed, see [CLI Installation Guide](databricks-cli-install.md) - Install or update the Databricks CLI on macOS, Windows, or Linux using Homebrew, WinGet, curl install script, or manual download

2. **Authentication must be configured**
   - Verify: `databricks auth profiles`
   - If not authenticated, see [CLI Authentication Guide](databricks-cli-auth.md) - Configure workspace/profile selection and authentication using OAuth2 (never PAT), with guidance for switching profiles and troubleshooting

3. **Know your workspace URL and profile name**
   - Example workspace URLs:
     - AWS: `https://company-workspace.cloud.databricks.com`
     - Azure: `https://adb-1111111111111111.10.azuredatabricks.net`
     - GCP: `https://1111111111111111.2.gcp.databricks.com`

## Profile Selection - CRITICAL

**NEVER AUTOMATICALLY SELECT A PROFILE**

When a Databricks command is needed and a profile is not already configured, you MUST:

1. **First, list available profiles**:
   ```bash
   databricks auth profiles
   ```

2. **Present all profiles to the user** and let them choose:
   - Show each profile name and workspace URL
   - Include validity status
   - Let the user select which profile to use

3. **Always offer the option to create a new profile**:
   - "Would you like to create a new profile instead?"
   - If yes, see [CLI Authentication Guide](databricks-cli-auth.md) for OAuth2 setup instructions

4. **Never assume or automatically select a profile** - even if:
   - There's only one profile available
   - A profile seems like the obvious choice
   - You used a profile earlier in the conversation

**Example workflow**:
```
Assistant: Let me check for existing profiles.
[Runs: databricks auth profiles]

You have two configured profiles:
1. production - https://company-prod.cloud.databricks.com (Valid)
2. development - https://company-dev.cloud.databricks.com (Valid)

Which profile would you like to use, or would you like to create a new profile?

User: production

[Retries: databricks apps list --profile production]
[Success - apps listed]
```

## Claude Code-Specific Guidance

**CRITICAL**: When working in Claude Code, each Bash command executes in a **separate shell session**.

### Always Use --profile Flag (RECOMMENDED)

```bash
# ✅ RECOMMENDED: Specify profile with each command
databricks apps list --profile my-workspace
databricks jobs list --profile my-workspace
databricks clusters list --profile my-workspace

# ✅ ALTERNATIVE: Chain commands with &&
export DATABRICKS_CONFIG_PROFILE=my-workspace && databricks apps list

# ❌ DOES NOT WORK: Separate export command
export DATABRICKS_CONFIG_PROFILE=my-workspace
databricks apps list  # Will NOT use the profile!
```

## General CLI Usage

### Getting Help

```bash
# Show all available command groups
databricks --help

# Get help for a specific command group
databricks apps --help
databricks jobs --help
databricks bundle --help

# Get help for a specific command
databricks apps create --help
databricks jobs create --help
```

### Common Command Structure

Most Databricks CLI commands follow this pattern:
```bash
databricks <service> <action> [options] --profile <profile-name>
```

Examples:
```bash
databricks apps list --profile my-workspace
databricks jobs get --job-id 12345 --profile my-workspace
databricks workspace export /Users/user@example.com/notebook --format SOURCE --profile my-workspace
```

### Current User

Get information about the authenticated user:

```bash
# Get current user details
databricks current-user me --profile my-workspace
```

### Data Exploration

Explore tables, discover schemas, and run SQL queries:

```bash
# Discover table schema, columns, sample data, and statistics
databricks experimental aitools tools discover-schema samples.nyctaxi.trips --profile my-workspace

# Execute SQL queries
databricks experimental aitools tools query "SELECT * FROM samples.nyctaxi.trips LIMIT 10" --profile my-workspace

# Get the default SQL warehouse
databricks experimental aitools tools get-default-warehouse --profile my-workspace
```

See [Data Exploration](data-exploration.md) for complete documentation.

## Common Command Patterns

### Listing Resources

```bash
# List apps
databricks apps list --profile my-workspace

# List jobs
databricks jobs list --profile my-workspace

# List clusters
databricks clusters list --profile my-workspace

# List catalogs
databricks catalogs list --profile my-workspace

# List SQL warehouses
databricks sql-warehouses list --profile my-workspace

# List serving endpoints
databricks serving-endpoints list --profile my-workspace

# List pipelines
databricks pipelines list --profile my-workspace
```

### Getting Resource Details

```bash
# Get app details
databricks apps get <app-name> --profile my-workspace

# Get job details
databricks jobs get --job-id <job-id> --profile my-workspace

# Get cluster details
databricks clusters get --cluster-id <cluster-id> --profile my-workspace

# Get catalog details
databricks catalogs get <catalog-name> --profile my-workspace
```

## Troubleshooting

### Authentication Errors

**Symptom**: `Error: default auth: cannot configure default credentials`

**Solution**:
1. Check for existing profiles: `databricks auth profiles`
2. If profiles exist, use `--profile` flag
3. If no profiles exist, authenticate: `databricks auth login --host <workspace-url> --profile <profile-name>`

See the [CLI Authentication Guide](databricks-cli-auth.md) for detailed authentication troubleshooting including OAuth2 setup, profile switching, and Claude Code-specific guidance.

### Permission Errors

**Symptom**: `Error: PERMISSION_DENIED` or `Error: FORBIDDEN`

**Solution**:
1. Verify you have the correct permissions in the workspace
2. For Unity Catalog resources, check catalog/schema/table grants
3. For workspace resources, check workspace permissions
4. Contact your workspace administrator if you need additional permissions

### Resource Not Found

**Symptom**: `Error: RESOURCE_DOES_NOT_EXIST`

**Solution**:
1. Verify the resource ID, name, or path is correct
2. Ensure you're using the correct profile/workspace
3. Check if the resource was deleted or moved
4. Use list commands to find the correct resource identifier

### Profile Not Found in Claude Code

**Symptom**: Command fails with profile error even after setting `DATABRICKS_CONFIG_PROFILE`

**Solution**: Remember that Claude Code runs each command in a separate shell session.

```bash
# ❌ DOES NOT WORK
export DATABRICKS_CONFIG_PROFILE=my-workspace
databricks apps list

# ✅ WORKS: Use --profile flag
databricks apps list --profile my-workspace

# ✅ WORKS: Chain with &&
export DATABRICKS_CONFIG_PROFILE=my-workspace && databricks apps list
```

### JSON Configuration File Errors

**Symptom**: `Error: invalid JSON` or `Error parsing JSON file`

**Solution**:
1. Validate JSON syntax using a JSON validator
2. Check for trailing commas (not allowed in JSON)
3. Ensure file path is correct
4. Use proper quotes around string values

## Quick Command Reference

```bash
# Apps
databricks apps list --profile <profile>
databricks apps deploy <app-name> --profile <profile>

# Unity Catalog
databricks catalogs list --profile <profile>
databricks schemas list --catalog-name <catalog> --profile <profile>
databricks tables list --catalog-name <catalog> --schema-name <schema> --profile <profile>
databricks volumes list --catalog-name <catalog> --schema-name <schema> --profile <profile>

# Data Exploration
databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <profile>
databricks experimental aitools tools query "SQL" --profile <profile>

# DBSQL
databricks sql-warehouses list --profile <profile>
databricks queries list --profile <profile>
databricks dashboards list --profile <profile>

# Pipelines (LakeFlow)
databricks pipelines list --profile <profile>
databricks pipelines start-update --pipeline-id <id> --profile <profile>

# Model Serving
databricks serving-endpoints list --profile <profile>
databricks serving-endpoints query --name <name> --json @input.json --profile <profile>

# Asset Bundles
databricks bundle init --profile <profile>
databricks bundle validate --profile <profile>
databricks bundle deploy -t <env> --profile <profile>
databricks bundle run <resource> -t <env> --profile <profile>

# Jobs
databricks jobs list --profile <profile>
databricks jobs run-now --job-id <id> --profile <profile>

# Clusters
databricks clusters list --profile <profile>
databricks clusters start --cluster-id <id> --profile <profile>

# Workspace
databricks workspace list <path> --profile <profile>
databricks workspace export <path> --format SOURCE --profile <profile>

# Secrets
databricks secrets list-scopes --profile <profile>
databricks secrets put --scope <scope> --key <key> --string-value <value> --profile <profile>
```

## Additional Resources

- [Databricks CLI Documentation](https://docs.databricks.com/dev-tools/cli/)
- [Databricks Asset Bundles Documentation](https://docs.databricks.com/dev-tools/bundles/)
- [Unity Catalog Documentation](https://docs.databricks.com/data-governance/unity-catalog/)
- [Model Serving Documentation](https://docs.databricks.com/machine-learning/model-serving/)
- [Delta Live Tables Documentation](https://docs.databricks.com/delta-live-tables/)
- [Databricks Apps Documentation](https://docs.databricks.com/apps/)
- [Databricks SQL Documentation](https://docs.databricks.com/sql/)
