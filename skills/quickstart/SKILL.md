---
name: quickstart
description: "Set up Databricks agent development environment. Use when: (1) First time setup, (2) Configuring Databricks authentication, (3) User says 'quickstart', 'set up', 'authenticate', or 'configure databricks', (4) No .env file exists."
metadata:
  version: "0.0.1"
---

# Quickstart & Authentication

## Prerequisites

- **uv** (Python package manager)
- **nvm** with Node 20 (for frontend)
- **Databricks CLI v0.283.0+**

Check CLI version:
```bash
databricks -v  # Must be v0.283.0 or above
brew upgrade databricks  # If version is too old
```

## Run Quickstart

```bash
uv run quickstart
```

**Options:**
- `--profile NAME`: Use specified profile (non-interactive)
- `--host URL`: Workspace URL for initial setup
{{LAKEBASE_OPTIONS}}- `--skip-lakebase`: Skip Lakebase setup (non-interactive / CI use)
- `--app-name NAME`: Existing Databricks app name to bind this bundle to
- `-h, --help`: Show help

**Examples:**
```bash
# Interactive (prompts for profile selection)
uv run quickstart

# Non-interactive with existing profile
uv run quickstart --profile DEFAULT

# New workspace setup
uv run quickstart --host https://your-workspace.cloud.databricks.com

# Bind to an existing app created via the Databricks UI
uv run quickstart --app-name my-existing-app

# Skip Lakebase setup (CI / non-interactive)
uv run quickstart --profile DEFAULT --skip-lakebase
{{LAKEBASE_EXAMPLES}}```

## What Quickstart Configures

Creates/updates `.env` with:
- `DATABRICKS_CONFIG_PROFILE` - Selected CLI profile
- `MLFLOW_TRACKING_URI` - Set to `databricks://<profile-name>` for local auth
- `MLFLOW_EXPERIMENT_ID` - Auto-created experiment ID
{{LAKEBASE_CONFIGURES_ENV}}
Updates `databricks.yml`:
- Sets `experiment_id` in the app's experiment resource
- Updates app `name` field if `--app-name` is provided
{{LAKEBASE_CONFIGURES_YML}}

## Existing App

If you created an app via the Databricks UI before cloning a template, use `--app-name` to bind the bundle to it:

```bash
uv run quickstart --app-name my-existing-app
```

Quickstart will update `databricks.yml` with the app name and print the binding command:
```bash
databricks bundle deployment bind <KEY> my-existing-app --auto-approve
databricks bundle deploy
```

This avoids the "An app with the same name already exists" error on first deploy.

## Idempotency

Re-running quickstart is safe:
- **Experiment**: If `MLFLOW_EXPERIMENT_ID` is already in `.env` and the experiment still exists, it is reused (no duplicate created).
- **Lakebase**: If Lakebase config is already in `.env`, the interactive prompt is skipped and the existing config is reused.

## Manual Authentication (Fallback)

If quickstart fails:

```bash
# Create new profile
databricks auth login --host https://your-workspace.cloud.databricks.com

# Verify
databricks auth profiles
```

Then manually create `.env` (copy from `.env.example`):
```bash
# Authentication (choose one method)
DATABRICKS_CONFIG_PROFILE=DEFAULT
# DATABRICKS_HOST=https://<your-workspace-here>.databricks.com
# DATABRICKS_TOKEN=dapi....

# MLflow configuration
MLFLOW_EXPERIMENT_ID=<your-experiment-id>
MLFLOW_TRACKING_URI="databricks://DEFAULT"
MLFLOW_REGISTRY_URI="databricks-uc"

# Frontend proxy settings
CHAT_APP_PORT=3000
CHAT_PROXY_TIMEOUT_SECONDS=300
```

## Next Steps

After quickstart completes:
1. Run `uv run discover-tools` to find available workspace resources (see **discover-tools** skill)
2. Run `uv run start-app` to test locally (see **run-locally** skill)
