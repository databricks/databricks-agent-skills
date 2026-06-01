---
name: app-templates-lakebase-setup
description: "Configure Lakebase for agent memory storage. Use when: (1) Adding memory capabilities to the agent, (2) 'Failed to connect to Lakebase' errors, (3) Permission errors on checkpoint/store tables, (4) User says 'lakebase', 'memory setup', or 'add memory'."
---

# Lakebase Setup for Agent Persistence

> **Profile reminder:** All `databricks` CLI commands must include the profile from `.env`: `databricks <command> --profile <profile>` or `DATABRICKS_CONFIG_PROFILE=<profile> databricks <command>`

> **Two types of Lakebase:** Databricks supports **provisioned** instances (with instance name) and **autoscaling** instances (project/branch model). This skill covers both. Make sure you know which Lakebase instance the user is using, ask the user which type they are using if unclear.

## Use Cases

Lakebase is used for three distinct purposes across the agent templates:

| Use case | Templates | Description |
|----------|-----------|-------------|
| **Chat UI conversation history** | All templates | The built-in chat UI (`e2e-chatbot-app-next`) can persist conversations across page refreshes and browser sessions. This is purely UI-side persistence — the agent itself is stateless. |
| **Agent short-term memory** | `agent-langgraph-advanced`, `agent-openai-advanced` | Conversation threads within a session via `AsyncCheckpointSaver` (LangGraph) or `AsyncDatabricksSession` (OpenAI SDK). The agent remembers what was said earlier in the same conversation. |
| **Agent long-term memory** | `agent-langgraph-advanced` | User facts across sessions via `AsyncDatabricksStore`. The agent remembers things about a user from previous conversations. |

> **Note:** When the quickstart prompts for Lakebase on a non-memory template, it's for **chat UI history** only — not for the agent. Memory templates always require Lakebase.

## Overview

Lakebase provides persistent PostgreSQL storage for agents:
- **Short-term memory** (LangGraph): Conversation history within a thread (`AsyncCheckpointSaver`)
- **Long-term memory** (LangGraph): User facts across sessions (`AsyncDatabricksStore`)
- **Short-term memory** (OpenAI SDK): Conversation history via `AsyncDatabricksSession`
- **Long-running agent persistence** (OpenAI SDK): Background task state via custom SQLAlchemy tables (`agent_server` schema)

> **Note:** For pre-configured memory templates, see:
> - `agent-langgraph-advanced` - Short-term memory, long-term memory, and long-running background tasks (LangGraph)
> - `agent-openai-advanced` - Short-term memory and long-running background tasks (OpenAI SDK)

## Complete Setup Workflow

```
┌───────────────────────────────────────────────────────────────────────────┐
│  1. Add dependency  →  2. Get instance  →  3. Configure DAB              │
│  4. Configure .env  →  5. Deploy  →  6. Grant SP permissions  →  7. Run  │
└───────────────────────────────────────────────────────────────────────────┘
```

> **Shortcut:** If using a pre-configured memory template, `uv run quickstart` with Lakebase flags handles steps 2-4 automatically. You still need to do steps 5-7 manually.

---

## Step 1: Add Memory Dependency

Add the memory extra to your `pyproject.toml`:

```toml
dependencies = [
    "databricks-langchain[memory]",
    # ... other dependencies
]
```

Then sync dependencies:
```bash
uv sync
```

---

## Step 2: Create or Get Lakebase Instance

### Option A: Provisioned Instance

1. Go to your Databricks workspace
2. Navigate to **Compute** → **Lakebase**
3. Click **Create Instance** (or use an existing one)
4. Note the **instance name**

### Option B: Autoscaling Instance

Autoscaling uses a **project/branch** model. You need three values:
- **Project name** (e.g., `my-project`)
- **Branch name** (e.g., `my-branch`)
- **Database ID** (e.g., `db-xxxx-xxxxxxxxxx`)

Find these via the postgres API:

```bash
# List projects
databricks api get /api/2.0/postgres/projects --profile <profile>

# List branches for a project
databricks api get /api/2.0/postgres/projects/<project-name>/branches --profile <profile>

# List databases for a branch
databricks api get /api/2.0/postgres/projects/<project-name>/branches/<branch-name>/databases --profile <profile>
```

**Important:** The database ID is the internal ID (e.g., `db-xxxx-xxxxxxxxxx`), NOT `databricks_postgres`.

---

## Step 3: Configure databricks.yml (Lakebase Resource)

> **Note:** If you ran `uv run quickstart` with Lakebase flags (`--lakebase-provisioned-name` or `--lakebase-autoscaling-endpoint`), the quickstart already configured `databricks.yml` for you — including fetching the database ID for autoscaling. Manual configuration is only needed if you didn't use quickstart or need to change values.

### Option A: Provisioned

Add the `database` resource to your app in `databricks.yml`:

```yaml
resources:
  apps:
    your_app:
      name: "your-app-name"
      source_code_path: ./
      resources:
        # ... other resources (experiment, UC functions, etc.) ...

        # Lakebase instance for long-term memory
        - name: 'database'
          database:
            instance_name: '<your-lakebase-instance-name>'
            database_name: 'databricks_postgres'
            permission: 'CAN_CONNECT_AND_CREATE'
```

**Important:**
- The `instance_name: '<your-lakebase-instance-name>'` must match the actual Lakebase instance name
- Using the `database` resource type automatically grants the app's service principal access to Lakebase
See `.claude/skills/add-tools/examples/lakebase.yaml` for the YAML snippet.

### Option B: Autoscaling

Add the `postgres` resource to your app in `databricks.yml`:

```yaml
resources:
  apps:
    your_app:
      name: "your-app-name"
      source_code_path: ./
      resources:
        # ... other resources (experiment, UC functions, etc.) ...

        # Autoscaling Lakebase instance for long-term memory
        - name: 'postgres'
          postgres:
            branch: "projects/<project-name>/branches/<branch-name>"
            database: "projects/<project-name>/branches/<branch-name>/databases/<database-id>"
            permission: 'CAN_CONNECT_AND_CREATE'
```

**Important:** The `branch` and `database` fields use full resource path format.

See `.claude/skills/add-tools/examples/lakebase-autoscaling.yaml` for the YAML snippet.

### Add Environment Variables to databricks.yml config block

**Provisioned:**
```yaml
      config:
        env:
          # Lakebase instance name - resolved from database resource at deploy time
          - name: LAKEBASE_INSTANCE_NAME
            value_from: "database"
          # Static values for embedding configuration
          - name: EMBEDDING_ENDPOINT
            value: "databricks-gte-large-en"
          - name: EMBEDDING_DIMS
            value: "1024"
```

**Autoscaling:**
```yaml
      config:
        env:
          # Autoscaling Lakebase config
          - name: LAKEBASE_AUTOSCALING_PROJECT
            value: "<your-project-name>"
          - name: LAKEBASE_AUTOSCALING_BRANCH
            value: "<your-branch-name>"
          # Static values for embedding configuration
          - name: EMBEDDING_ENDPOINT
            value: "databricks-gte-large-en"
          - name: EMBEDDING_DIMS
            value: "1024"
```

---

## Step 4: Configure .env (Local Development)

For local development, add to `.env`:

**Provisioned:**
```bash
LAKEBASE_INSTANCE_NAME=<your-instance-name>
EMBEDDING_ENDPOINT=databricks-gte-large-en
EMBEDDING_DIMS=1024
```

**Autoscaling:**
```bash
LAKEBASE_AUTOSCALING_PROJECT=<your-project-name>
LAKEBASE_AUTOSCALING_BRANCH=<your-branch-name>
EMBEDDING_ENDPOINT=databricks-gte-large-en
EMBEDDING_DIMS=1024
```

**Important:** `embedding_dims` must match the embedding endpoint:

| Endpoint | Dimensions |
|----------|------------|
| `databricks-gte-large-en` | 1024 |
| `databricks-bge-large-en` | 1024 |

> **Note:** `.env` is only for local development. When deployed, the app gets values from `databricks.yml` config env.

---

## Step 5: Initialize Tables
## Step 5: Deploy

Deploy the app so the service principal and resources are created:

```bash
DATABRICKS_CONFIG_PROFILE=<profile> databricks bundle deploy
```

---

## Step 6: Grant SP Permissions (CRITICAL)

> **WARNING:** You MUST complete this step before running the app. Without it, the app will fail with database migration errors like `CREATE TABLE IF NOT EXISTS "drizzle"."__drizzle_migrations"` — permission denied.

After deploying, the app's service principal needs Postgres roles to access Lakebase tables. The DAB resource grants basic connectivity, but you must also grant Postgres-level schema and table permissions.

**Step 1:** Get the app's service principal client ID:
```bash
DATABRICKS_CONFIG_PROFILE=<profile> databricks apps get <app-name> --output json | jq -r '.service_principal_client_id'
```

**Step 2:** Grant permissions using the grant script:

```bash
# Provisioned:
DATABRICKS_CONFIG_PROFILE=<profile> uv run python scripts/grant_lakebase_permissions.py <sp-client-id> \
  --memory-type <type> --instance-name <name>

# Autoscaling (endpoint — reads LAKEBASE_AUTOSCALING_ENDPOINT from .env by default):
DATABRICKS_CONFIG_PROFILE=<profile> uv run python scripts/grant_lakebase_permissions.py <sp-client-id> \
  --memory-type <type> --autoscaling-endpoint <endpoint>

# Autoscaling (project + branch):
DATABRICKS_CONFIG_PROFILE=<profile> uv run python scripts/grant_lakebase_permissions.py <sp-client-id> \
  --memory-type <type> --project <project> --branch <branch>
```

**Memory type by template:**

| Template | `--memory-type` value |
|----------|-----------------------|
| `agent-langgraph-advanced` | `langgraph` |
| `agent-openai-advanced` | `openai` |

The script handles fresh branches gracefully (warns but doesn't fail if tables don't exist yet — they'll be created on first app startup).

---

## Step 7: Run Your App

```bash
DATABRICKS_CONFIG_PROFILE=<profile> databricks bundle run my_agent
```

> **Note:** `bundle deploy` only uploads files and configures resources. `bundle run` is required to actually start the app with the new code.

---

## Complete Examples: databricks.yml with Lakebase

### Provisioned Lakebase

```yaml
bundle:
  name: agent_langgraph

resources:
  apps:
    agent_langgraph:
      name: "my-agent-app"
      description: "Agent with long-term memory"
      source_code_path: ./
      config:
        command: ["uv", "run", "start-app"]
        env:
          - name: MLFLOW_TRACKING_URI
            value: "databricks"
          - name: MLFLOW_REGISTRY_URI
            value: "databricks-uc"
          - name: API_PROXY
            value: "http://localhost:8000/invocations"
          - name: CHAT_APP_PORT
            value: "3000"
          - name: CHAT_PROXY_TIMEOUT_SECONDS
            value: "300"
          - name: MLFLOW_EXPERIMENT_ID
            value_from: "experiment"
          # Lakebase instance name (resolved from database resource)
          - name: LAKEBASE_INSTANCE_NAME
            value_from: "database"
          # Static values for embedding configuration
          - name: EMBEDDING_ENDPOINT
            value: "databricks-gte-large-en"
          - name: EMBEDDING_DIMS
            value: "1024"

      resources:
        - name: 'experiment'
          experiment:
            experiment_id: ""
            permission: 'CAN_MANAGE'
        - name: 'database'
          database:
            instance_name: '<your-lakebase-instance-name>'
            database_name: 'databricks_postgres'
            permission: 'CAN_CONNECT_AND_CREATE'

targets:
  dev:
    mode: development
    default: true
```

### Autoscaling Lakebase

```yaml
bundle:
  name: agent_langgraph

resources:
  apps:
    agent_langgraph:
      name: "my-agent-app"
      description: "Agent with long-term memory"
      source_code_path: ./
      config:
        command: ["uv", "run", "start-app"]
        env:
          - name: MLFLOW_TRACKING_URI
            value: "databricks"
          - name: MLFLOW_REGISTRY_URI
            value: "databricks-uc"
          - name: API_PROXY
            value: "http://localhost:8000/invocations"
          - name: CHAT_APP_PORT
            value: "3000"
          - name: CHAT_PROXY_TIMEOUT_SECONDS
            value: "300"
          - name: MLFLOW_EXPERIMENT_ID
            value_from: "experiment"
          # Autoscaling Lakebase config
          - name: LAKEBASE_AUTOSCALING_PROJECT
            value: "<your-project-name>"
          - name: LAKEBASE_AUTOSCALING_BRANCH
            value: "<your-branch-name>"
          # Static values for embedding configuration
          - name: EMBEDDING_ENDPOINT
            value: "databricks-gte-large-en"
          - name: EMBEDDING_DIMS
            value: "1024"

      resources:
        - name: 'experiment'
          experiment:
            experiment_id: ""
            permission: 'CAN_MANAGE'
        - name: 'postgres'
          postgres:
            branch: "projects/<your-project-name>/branches/<your-branch-name>"
            database: "projects/<your-project-name>/branches/<your-branch-name>/databases/<your-database-id>"
            permission: 'CAN_CONNECT_AND_CREATE'

targets:
  dev:
    mode: development
    default: true
```

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| **"embedding_dims is required when embedding_endpoint is specified"** | Missing `embedding_dims` parameter | Add `embedding_dims=1024` to AsyncDatabricksStore |
| **"relation 'store' does not exist"** | Tables not initialized | The app creates tables on first use; ensure SP has CREATE permission |
| **"Unable to resolve Lakebase instance 'None'"** | Missing env var in deployed app | Add `LAKEBASE_INSTANCE_NAME` to databricks.yml `config.env` |
| **"permission denied for table store"** | Missing grants | Run `uv run python scripts/grant_lakebase_permissions.py <sp-client-id>` to grant permissions |
| **"Failed to connect to Lakebase"** | Wrong instance name or project/branch | Verify values in databricks.yml and .env |
| **Connection pool errors on exit** | Python cleanup race | Ignore `PythonFinalizationError` - it's harmless |
| **App not updated after deploy** | Forgot to run bundle | Run `databricks bundle run <app>` after deploy |
| **value_from not resolving** | Resource name mismatch | Ensure `value_from` value matches `name` in databricks.yml resources |
| **"Invalid postgres resource parameters"** | Missing `database` field in postgres resource | Add full `database` path: `projects/<project>/branches/<branch>/databases/<db-id>` |
| **`CREATE TABLE IF NOT EXISTS "drizzle"."__drizzle_migrations"` fails** | Grant step was skipped — SP lacks Postgres permissions | Run `grant_lakebase_permissions.py` with `--memory-type`, then restart the app |

---

## LakebaseClient API (for reference)

```python
from databricks_ai_bridge.lakebase import LakebaseClient, SchemaPrivilege, TablePrivilege

# Provisioned:
client = LakebaseClient(instance_name="...")
# Autoscaling:
client = LakebaseClient(project="...", branch="...")

# Create role (must do first)
client.create_role(identity_name, "SERVICE_PRINCIPAL")

# Grant schema (note: schemas is a list, grantee not role)
client.grant_schema(
    grantee="...",
    schemas=["public"],
    privileges=[SchemaPrivilege.USAGE, SchemaPrivilege.CREATE],
)

# Grant tables (note: tables includes schema prefix)
client.grant_table(
    grantee="...",
    tables=["public.store"],
    privileges=[TablePrivilege.SELECT, TablePrivilege.INSERT, ...],
)

# Execute raw SQL
client.execute("SELECT * FROM pg_tables WHERE schemaname = 'public'")
```

### Service Principal Identifiers

When granting permissions manually, note that Databricks apps have multiple identifiers:

| Field | Format | Example |
|-------|--------|---------|
| `service_principal_id` | Numeric ID | `1234567890123456` |
| `service_principal_client_id` | UUID | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `service_principal_name` | String name | `my-app-service-principal` |

**Get all identifiers:**
```bash
DATABRICKS_CONFIG_PROFILE=<profile> databricks apps get <app-name> --output json | jq '{
  id: .service_principal_id,
  client_id: .service_principal_client_id,
  name: .service_principal_name
}'
```

**Which to use:**
- `LakebaseClient.create_role()` - Use `service_principal_client_id` (UUID) or `service_principal_name`
- Raw SQL grants - Use `service_principal_client_id` (UUID)

---

## Next Steps

- Add memory to agent code: see **agent-memory** skill
- Test locally: see **app-templates-run-locally** skill
- Deploy: see **app-templates-deploy** skill
