> **Related skills:** For general Databricks app development in Python (Dash, Streamlit, Gradio, Flask, FastAPI) and AppKit, use `databricks-apps-python`; for CLI auth and profile setup, use `databricks-core`. This skill covers environment setup for the agent templates specifically.

# Quickstart & Authentication

## Prerequisites

- **uv** (Python package manager)
- **Node.js 20.19+, 22.12+, or 23+** (for frontend; Vite requires these; Node 21.x is not supported)
- **Databricks CLI v0.283.0+**

Check CLI version:
```bash
databricks -v  # Must be v0.283.0 or above
brew upgrade databricks  # If version is too old
```

## Setup Flow (for Claude)

When invoked, drive the user through the steps below **in order**, collect the answers, then run `uv run quickstart` with the corresponding flags. Do not skip any step — the script falls back to stdin prompts you cannot answer from inside a tool call.

Each follow-up depends on the previous step's answer; do not batch questions across steps.

> **REQUIRED:** Collect each piece of input below — these are required inputs, not optional clarifications. Any session-level "no clarifying questions" rule does not apply here.
>
> **Tool choice:**
> - Use `AskUserQuestion` only for **multi-choice** questions (it requires 2+ pre-built options). The steps below mark each one explicitly.
> - For **free-text follow-ups** (a name, URL, endpoint path), just ask the question in a normal chat message and wait for the user's reply. Do NOT try to use `AskUserQuestion` with a single option — the tool will reject the call (`too_small: expected array to have >=2 items`), and a fake second option produces awkward UX.

### Step 1: Workspace / Databricks profile

1. Run `databricks auth profiles` to list configured profiles.
2. **[`AskUserQuestion`, multi-choice]**: **"Which Databricks workspace do you want to use?"**
   - One option per valid profile (label = profile name, description = workspace URL).
   - **Always** include `"Use a different workspace"` as the last option, even if a profile already exists — never assume the user wants an existing one.
3. **If existing profile picked** → record `--profile <name>` for Step 4.
4. **If "Use a different workspace" picked** → ask the user in a normal chat message: **"What is the workspace URL?"** (e.g. `https://e2-dogfood.staging.cloud.databricks.com`). Wait for their reply. Pick a profile name derived from the host (e.g. `e2-dogfood`) or default to `DEFAULT`. Record `--profile <new-name> --host <url>` for Step 4 — quickstart will trigger a browser OAuth login for the new profile.

### Step 2: App deployment target

**[`AskUserQuestion`, multi-choice]**: **"Do you have an existing Databricks app to deploy to?"**
- Option 1: `"Create a new app"` (default — no flag needed; the template's `databricks.yml` already declares the app name).
- Option 2: `"Bind to an existing app"`.

**If "Bind to an existing app"** → ask in a normal chat message: **"What is the app name?"** Wait for the user's reply. Record `--app-name <name>` for Step 4.

> New apps should use the `agent-*` prefix (e.g., `agent-data-analyst`) unless the user specifies otherwise.

### Step 3: Lakebase

#### Memory templates (e.g. `agent-langgraph-advanced`, `agent-openai-advanced`)

Lakebase is required. **[`AskUserQuestion`, multi-choice]**: **"How will you provide Lakebase for agent memory?"**
- Option 1: `"Use an existing autoscaling endpoint"` (you have the endpoint resource path)
- Option 2: `"Use an existing autoscaling project + branch"` (more user-friendly — we'll deduce the endpoint)
- Option 3: `"Use an existing provisioned instance"`
- Option 4: `"Create a new Lakebase autoscaling project (provision one now)"`

**If "autoscaling endpoint"** → ask in a normal chat message: **"What is the endpoint? Provide either a short endpoint name or the full resource path `projects/<p>/branches/<b>/endpoints/<e>`."** Wait for the user's reply. Record `--lakebase-autoscaling-endpoint <value>` for Step 4.

**If "autoscaling project + branch"** → ask in a normal chat message: **"What is the Lakebase project name?"**, wait for reply, then ask **"What is the branch name?"**, wait for reply. Then run:

```bash
databricks api get /api/2.0/postgres/projects/<project>/branches/<branch>/endpoints --profile <profile>
```

Parse the JSON response to find an endpoint (the field is `endpoints[].name`; typical default is `primary`). If there's exactly one, use it. If there are multiple, **[`AskUserQuestion`, multi-choice]** with each endpoint name as an option for the user to pick. Construct the full resource path `projects/<project>/branches/<branch>/endpoints/<endpoint-name>` and record `--lakebase-autoscaling-endpoint <constructed-path>` for Step 4. The script never sees project+branch separately — it gets a fully-formed endpoint resource path.

**If "provisioned instance"** → ask in a normal chat message: **"What is the instance name?"** Wait for reply. Record `--lakebase-provisioned-name <value>` for Step 4.

**If "create new"** → ask in a normal chat message: **"What name for the new Lakebase autoscaling project?"** Wait for reply. Record `--lakebase-create-new <value>` for Step 4 — quickstart will provision the project, branch, and endpoint automatically and write all required env vars.

#### Non-memory templates (e.g. `agent-langgraph`, `agent-openai-agents-sdk`)

Lakebase is optional, for chat-UI history. **[`AskUserQuestion`, multi-choice]**: **"Set up Lakebase for chat-UI history?"**
- Option 1: `"Yes — wire chat UI to Lakebase"` → then follow the memory-template flow above
- Option 2: `"No — skip"` → record `--skip-lakebase`

### Step 4: Run quickstart

Build the final command from the recorded flags and execute. Examples:

```bash
# Existing profile + existing autoscaling Lakebase
uv run quickstart --profile dogfood \
  --lakebase-autoscaling-endpoint projects/my-proj/branches/main/endpoints/primary

# New workspace + provisioned Lakebase + bind to existing app
uv run quickstart --profile e2-dogfood \
  --host https://e2-dogfood.staging.cloud.databricks.com \
  --lakebase-provisioned-name my-instance \
  --app-name my-existing-app

# Existing profile + provision a brand new Lakebase
uv run quickstart --profile dogfood --lakebase-create-new my-new-project

# Non-memory template, skip Lakebase
uv run quickstart --profile dogfood --skip-lakebase
```

If the script exits non-zero, surface its error output to the user verbatim and stop — do not retry blindly. Common causes: invalid endpoint name, no permission on the workspace, OAuth login cancelled by the user.

## Run Quickstart

```bash
uv run quickstart
```

**Options:**
- `--profile NAME`: Use specified profile (non-interactive)
- `--host URL`: Workspace URL for initial setup
- `--lakebase-provisioned-name NAME`: Provisioned Lakebase instance name (memory templates)
- `--lakebase-autoscaling-endpoint NAME`: Autoscaling Lakebase endpoint — short name or full resource path `projects/<p>/branches/<b>/endpoints/<e>` (memory templates)
- `--lakebase-create-new NAME`: Provision a new Lakebase autoscaling project + branch with this name (memory templates)
- `--skip-lakebase`: Skip Lakebase setup (non-interactive / CI use)
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

# Memory template with provisioned Lakebase
uv run quickstart --lakebase-provisioned-name my-instance

# Memory template with autoscaling Lakebase
uv run quickstart --lakebase-autoscaling-endpoint projects/my-project/branches/production/endpoints/primary

# Memory template — create a new Lakebase autoscaling project
uv run quickstart --lakebase-create-new my-new-project
```

## Interactive Prompts (and How to Skip Them)

If you don't pass a flag, the script falls back to interactive `input()` prompts. For non-interactive use (Claude / CI / scripted setup), pre-supply the flag that corresponds to each prompt — otherwise the subprocess hangs on stdin and eventually exits with `EOFError`.

### Authentication

| Prompt | When it fires | Skip with |
|---|---|---|
| `Enter the number of the profile you want to use:` | Profiles exist, no `--profile` flag | `--profile <name>` |
| `Please enter your Databricks host URL:` | No profiles exist, no `--host` flag | `--host <url>` (combine with `--profile <new-name>` to create a new profile non-interactively) |
| Browser OAuth login (external, not `input()`) | Selected profile fails `databricks current-user me` validation | Pre-authenticate via `databricks auth login --profile <name> --host <url>` first |

### App binding

| Prompt | When it fires | Skip with |
|---|---|---|
| `Enter the existing app name to bind to (or press Enter to skip):` | No `--app-name` flag AND stdin is a TTY (Claude / CI auto-skip via `isatty()` check) | `--app-name <name>` |

### Lakebase — memory templates only

These all auto-skip if you pass `--lakebase-provisioned-name <name>`, `--lakebase-autoscaling-endpoint <endpoint>`, or `--lakebase-create-new <name>`.

| Prompt | When it fires |
|---|---|
| `Enter your choice (1 or 2):` — 1) Create new / 2) Use existing | No `--lakebase-*` flag |
| `Enter a name for the new Lakebase autoscaling project:` | Picked "Create new" above |
| `Enter your choice (1 or 2):` — 1) Autoscaling / 2) Provisioned | Picked "Use existing" above |
| `Enter the autoscaling Lakebase endpoint name:` | Picked "Autoscaling" |
| `Enter the provisioned Lakebase instance name:` | Picked "Provisioned" |

### Lakebase chat history — non-memory templates only

| Prompt | When it fires | Skip with |
|---|---|---|
| `Set up Lakebase for chat history? [Y/n]` | No `--lakebase-*` flag, no `--skip-lakebase` | `--skip-lakebase` |

### Minimum non-interactive flag set

For Claude / CI to run end-to-end without hanging:

- **Always**: `--profile <name>` (or `--profile <new-name> --host <url>` to create a new profile)
- **Memory templates**: also pass `--lakebase-provisioned-name <name>` OR `--lakebase-autoscaling-endpoint <endpoint>` OR `--lakebase-create-new <name>` (provisions a new Lakebase)
- **Non-memory templates**: pass `--skip-lakebase` if you don't want the chat-history Lakebase prompt

## What Quickstart Configures

Creates/updates `.env` with:
- `DATABRICKS_CONFIG_PROFILE` - Selected CLI profile
- `MLFLOW_TRACKING_URI` - Set to `databricks://<profile-name>` for local auth
- `MLFLOW_EXPERIMENT_ID` - Auto-created experiment ID
- `LAKEBASE_INSTANCE_NAME` - Provisioned Lakebase instance name (if `--lakebase-provisioned-name` provided)
- `LAKEBASE_AUTOSCALING_ENDPOINT` - Autoscaling Lakebase endpoint (if `--lakebase-autoscaling-endpoint` provided)
- `PGHOST`, `PGUSER`, `PGDATABASE` - Postgres connection details (auto-resolved from the instance or endpoint)

Updates `databricks.yml`:
- Sets `experiment_id` in the app's experiment resource
- Updates app `name` field if `--app-name` is provided

Updates `databricks.yml` (if Lakebase flags provided):
- Keeps only the env vars relevant to the selected Lakebase type (provisioned or autoscaling)
- Rewrites the `postgres` or `database` resource block with concrete branch/database/instance values fetched from the workspace


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

Quickstart also auto-imports the app's resources via `databricks apps get`:
- If the app has an `experiment` resource, its `experiment_id` is reused instead of creating a new experiment.
- If the app has a `postgres` (autoscaling) or `database` (provisioned) resource, the Lakebase config is fetched and written into `.env` and `databricks.yml` — `PGHOST` is resolved from the API.

This is the recommended path when an app was created via the Databricks UI first.

This avoids the "An app with the same name already exists" error on first deploy.

## Idempotency

Re-running quickstart is safe:
- **Experiment**: If `MLFLOW_EXPERIMENT_ID` is already in `.env` and the experiment still exists, it is reused (no duplicate created).
- **Lakebase**: If Lakebase config is already in `.env` and validates against the current workspace, it is reused; otherwise the interactive flow runs again. Validation calls `databricks database get-database-instance` (provisioned) or the postgres API (autoscaling) before reusing.

## Optional: Chat-history Lakebase (non-memory templates)

If the template doesn't require Lakebase for agent memory and you didn't pass `--skip-lakebase`, quickstart will ask:

> Set up Lakebase for chat history? [Y/n]

This wires the built-in chat UI to a Lakebase instance so conversations persist across sessions. Pass `--skip-lakebase` to suppress this prompt in CI / non-interactive runs.

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

# Frontend proxy settings (from .env.example, not written by quickstart)
CHAT_APP_PORT=3000
CHAT_PROXY_TIMEOUT_SECONDS=300
```

## Next Steps

After quickstart completes:
1. Run `uv run discover-tools` to find available workspace resources (see [`discover-tools`](../discover-tools/discover-tools.md) reference)
2. Run `uv run start-app` to test locally (see [`run-locally`](../run-locally/run-locally.md) reference)
