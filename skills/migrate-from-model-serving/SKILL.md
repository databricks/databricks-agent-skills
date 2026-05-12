---
name: migrate-from-model-serving
description: "Migrate an MLflow ResponsesAgent from Databricks Model Serving to Databricks Apps. Use when: (1) User wants to migrate from Model Serving to Apps, (2) User has a ResponsesAgent with predict()/predict_stream() methods, (3) User wants to convert to @invoke/@stream decorators."
metadata:
  version: "0.0.1"
---

# Model Serving to Databricks Apps Migration Guide

This guide instructs LLM coding agents how to migrate an MLflow ResponsesAgent from Databricks Model Serving to Databricks Apps.

---

## Overview

**Goal:** Migrate an agent deployed on Databricks Model Serving (using `ResponsesAgent` with `predict()`/`predict_stream()`) to Databricks Apps (using MLflow GenAI Server with `@invoke`/`@stream` decorators).

**Key Transformation:**
- Model Serving: Synchronous `predict()` and `predict_stream()` methods on a class
- Apps: Functions with `@invoke` and `@stream` decorators (sync or async, based on user preference)

**Deliverables:** After migration is complete, you will have:

```
<working-directory>/
├── original_mlflow_model/    # Downloaded artifacts from Model Serving
│   ├── MLmodel
│   ├── code/
│   │   └── agent.py
│   ├── input_example.json
│   └── requirements.txt
│
└── <app-name>/               # New Databricks App (ready to deploy)
    ├── agent_server/
    │   ├── agent.py          # Migrated agent code
    │   └── ...
    ├── databricks.yml        # Bundle config with resources
    ├── pyproject.toml
    ├── requirements.txt
    └── ...
```

> **`<app-name>`** is the name the user provides at the start of the migration. It is used as both the directory name and the Databricks App name at deploy time.

---

## Before You Begin: Gather User Inputs

**Before doing anything else, ask the user three questions.** Use the `AskUserQuestion` tool to collect all answers at once so the user is only prompted once, then Claude can execute the rest of the migration autonomously.

**Questions to ask:**

1. **Databricks profile:** Which Databricks CLI profile should be used for the workspace where the Model Serving endpoint lives? (Run `databricks auth profiles` first to list available profiles and their workspaces, then present the options to the user.)
2. **App name:** What should the new Databricks App be named? (Must be lowercase, can contain letters, numbers, and hyphens, and must be unique within the workspace.)
3. **Async migration:** Would you like to migrate your agent code to be fully async?
   - **Yes (Recommended):** Converts all I/O operations to async (`await`/`async for`), enabling higher concurrency on smaller compute — no more threads sitting idle while waiting for LLM responses or long-running tool calls.
   - **No:** Keeps your existing synchronous code with minimal changes — just extracts the logic from the `ResponsesAgent` class and wraps it with `@invoke`/`@stream` decorators. Simpler migration, but each request blocks a thread while waiting for I/O.

Store the answers as:
- `<profile>` — used for ALL `databricks` CLI commands throughout the migration (via `--profile <profile>`)
- `<app-name>` — used as both the directory name for the migrated app AND the app name when deploying with `databricks bundle deploy`
- `<async>` — `yes` or `no`, determines whether to convert the agent code to async or keep it synchronous

### Validate Authentication

After receiving the user's answers, validate the selected profile:

```bash
databricks current-user me --profile <profile>
```

If this fails with an authentication error, prompt the user to re-authenticate:

```bash
databricks auth login --profile <profile>
```

> **Important:** Remember to include `--profile <profile>` on every `databricks` CLI command throughout the migration.

### Create the App Directory

Copy all scaffold files from the current working directory into a new directory named `<app-name>/`. Exclude instruction files (`AGENTS.md`, `CLAUDE.md`), hidden directories (`.claude/`, `.git/`), and any migration artifacts (e.g., `original_mlflow_model/`, `.migration-venv/`). Do NOT search for or copy scaffold files from other directories or templates — everything you need is right here.

All subsequent migration steps operate inside the `<app-name>/` directory.

> **Note:** The `agent_server/agent.py` scaffold is intentionally framework-agnostic — it contains the `@invoke`/`@stream` decorator pattern with TODO placeholders. Step 3 (Migrate the Agent Code) will replace these placeholders with the actual agent logic from the original Model Serving endpoint.

### Create Task List

**Create a task list to track progress.** This helps the user follow along and see what's completed, in progress, and pending.

> **User tip:** Press `Ctrl+T` to toggle the task list view in your terminal. The display shows up to 10 tasks at a time with status indicators.

Create the following tasks using the `TaskCreate` tool:

| Task | Description |
|------|-------------|
| **Authenticate to Databricks** | Verify Databricks CLI authentication and validate the selected profile |
| **Download original agent artifacts** | Download the MLflow model artifacts from Model Serving endpoint |
| **Analyze and understand agent code** | Examine the original agent code, identify tools, resources, and dependencies |
| **Migrate agent code to Apps format** | Transform ResponsesAgent class to @invoke/@stream decorated functions |
| **Set up and configure the app** | Install dependencies, run quickstart, configure environment |
| **Test agent locally** | Start local server and verify the agent works correctly |
| **Deploy to Databricks Apps** | Configure databricks.yml resources and deploy with Databricks Asset Bundles |
| **Test deployed app** | Verify the deployed app responds correctly |

Update task status as you progress:
- Mark tasks as `in_progress` when starting each step
- Mark tasks as `completed` when finished
- This gives the user visibility into migration progress

---

## Step 1: Download the Original Agent Code

> **Task:** Mark "Authenticate to Databricks" as `completed`. Mark "Download original agent artifacts" as `in_progress`.
>
> **Note:** The `<profile>` and `<app-name>` values were collected from the user in the "Before You Begin" section. Use them throughout.

Download the original agent code from the Model Serving endpoint. This requires setting up a virtual environment with MLflow to access the model artifacts.

### 1.1 Get Model Info from Endpoint

If you have a serving endpoint name, extract the model details:

```bash
# Get endpoint info (remember to include --profile if using non-default)
databricks serving-endpoints get <endpoint-name> --profile <profile> --output json
```

Look for `served_entities[0].entity_name` (model name) and `entity_version` in the response. Find the entity with 100% traffic in `traffic_config.routes`.

### 1.2 Download Model Artifacts

Use `uv run --with` to download artifacts without creating a separate virtual environment. The `mlflow[databricks]` extra includes `boto3` for Unity Catalog artifact access:

```bash
DATABRICKS_CONFIG_PROFILE=<profile> uv run --no-project \
  --with "mlflow[databricks]>=2.15.0" \
  --with "databricks-sdk>=0.30.0" \
  python3 << 'EOF'
import mlflow

mlflow.set_tracking_uri("databricks")

# Replace with actual values from step 1.1
MODEL_NAME = "<model-name>"
VERSION = "<version>"

print(f"Downloading model: models:/{MODEL_NAME}/{VERSION}")
mlflow.artifacts.download_artifacts(
    artifact_uri=f"models:/{MODEL_NAME}/{VERSION}",
    dst_path="./original_mlflow_model"
)
print("Download complete! Artifacts saved to ./original_mlflow_model")
EOF
```

### 1.3 Verify Downloaded Artifacts

Check that the key files exist and understand the full structure:

```bash
# List all downloaded files recursively
find ./original_mlflow_model -type f | head -50

# Check for MLmodel file (contains resource requirements)
cat ./original_mlflow_model/MLmodel

# Check for input example (useful for testing)
cat ./original_mlflow_model/input_example.json 2>/dev/null
```

**Examine the `/code` folder** - contains all code dependencies logged via `code_paths=["..."]`:

```bash
# List all code files
ls -la ./original_mlflow_model/code/

# The main agent is typically agent.py, but there may be additional modules
find ./original_mlflow_model/code -name "*.py" -type f
```

**Examine the `/artifacts` folder** (if present) - contains artifacts logged via `artifacts={...}`:

```bash
# Check for artifacts folder
ls -la ./original_mlflow_model/artifacts/ 2>/dev/null

# List all artifacts
find ./original_mlflow_model/artifacts -type f 2>/dev/null
```

> **Important:** Take note of ALL files in `/code` and `/artifacts`. You will need to copy these to the migrated app and ensure imports still work correctly.

### Expected Output Structure

After successful download, you should have:

```
./original_mlflow_model/
├── MLmodel              # Model metadata and resource requirements
├── code/                # Code logged via code_paths=["..."]
│   ├── agent.py         # Main agent implementation
│   ├── utils.py         # (optional) Helper modules
│   ├── tools.py         # (optional) Custom tool definitions
│   └── ...              # Any other code dependencies
├── artifacts/           # (optional) Artifacts logged via artifacts={...}
│   ├── config.yaml      # (optional) Configuration files
│   ├── prompts/         # (optional) Prompt templates
│   └── ...              # Any other artifacts (data files, etc.)
├── input_example.json   # Sample request for testing
├── requirements.txt     # Original dependencies
└── ...
```

### Key Files to Examine

1. **`code/agent.py`** - Contains the `ResponsesAgent` class with `predict()` and `predict_stream()` methods
2. **`code/*.py`** - Any additional Python modules the agent imports
3. **`MLmodel`** - Contains the `resources` section listing required Databricks resources
4. **`artifacts/`** - Any configuration files, prompts, or data files the agent uses
5. **`input_example.json`** - Use this to test the migrated agent

### Troubleshooting Model Download

**"Unable to import necessary dependencies to access model version files in Unity Catalog"**
This means `boto3` is missing. Ensure you're using `mlflow[databricks]` (not just `mlflow`) in the `--with` flag — the `[databricks]` extra includes `boto3`.

**"INVALID_PARAMETER_VALUE" or authentication errors**
Re-authenticate with Databricks (include profile if non-default):
```bash
databricks auth login --profile <profile>
```

**Wrong workspace / Model not found**
Make sure you're using the correct profile that corresponds to the workspace where the model is deployed:
```bash
# List profiles to see which workspace each points to
databricks auth profiles

# Verify you can access the workspace
databricks current-user me --profile <profile>

# List models in that workspace
databricks registered-models list --profile <profile>
databricks model-versions list --name "<model-name>" --profile <profile>
```

---

## Step 2: Understand the Key Transformations

> **Task:** Mark "Download original agent artifacts" as `completed`. Mark "Analyze and understand agent code" as `in_progress`.

### Entry Point Transformation

In both cases, the `ResponsesAgent` class is replaced with decorated functions. The difference is whether those functions are async or sync.

**Model Serving (OLD):**
```python
from mlflow.pyfunc import ResponsesAgent, ResponsesAgentRequest, ResponsesAgentResponse

class MyAgent(ResponsesAgent):
    def predict(self, request: ResponsesAgentRequest, params=None) -> ResponsesAgentResponse:
        # Synchronous implementation
        ...
        return ResponsesAgentResponse(output=outputs)

    def predict_stream(self, request: ResponsesAgentRequest, params=None):
        # Synchronous generator
        for chunk in ...:
            yield ResponsesAgentStreamEvent(...)
```

**Apps — Async (if `<async>` = yes):**
```python
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

@invoke()
async def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    # Async implementation - typically calls streaming() and collects results
    outputs = [
        event.item
        async for event in streaming(request)
        if event.type == "response.output_item.done"
    ]
    return ResponsesAgentResponse(output=outputs)

@stream()
async def streaming(request: ResponsesAgentRequest) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    # Async generator
    async for event in ...:
        yield event
```

**Apps — Sync (if `<async>` = no):**
```python
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

@invoke()
def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    # Same sync logic from original predict(), extracted from the class
    ...
    return ResponsesAgentResponse(output=outputs)

@stream()
def streaming(request: ResponsesAgentRequest):
    # Same sync generator from original predict_stream(), extracted from the class
    for chunk in ...:
        yield ResponsesAgentStreamEvent(...)
```

### Key Differences

| Aspect | Model Serving | Apps (async) | Apps (sync) |
|--------|--------------|------|------|
| Structure | `class MyAgent(ResponsesAgent)` | Decorated functions | Decorated functions |
| Functions | `def predict()` / `def predict_stream()` | `async def` with `await` | `def` (same as original) |
| Streaming | Sync generator (`yield`) | Async generator (`async for` / `yield`) | Sync generator (`yield`) |
| Server | MLflow Model Server | MLflow GenAI Server (FastAPI) | MLflow GenAI Server (FastAPI) |
| Deployment | `databricks_agents.deploy()` | `databricks bundle deploy` + `bundle run` | `databricks bundle deploy` + `bundle run` |

### Async Patterns (only if `<async>` = yes)

> **Skip this section if the user chose synchronous migration.** The sync path keeps all original I/O calls as-is.

All I/O operations must be converted to async:

```python
# OLD (sync)
response = client.chat(messages)

# NEW (async)
response = await client.achat(messages)

# OLD (sync iteration)
for chunk in stream:
    yield chunk

# NEW (async iteration)
async for chunk in stream:
    yield chunk
```

---

## Step 3: Migrate the Agent Code

> **Task:** Mark "Analyze and understand agent code" as `completed`. Mark "Migrate agent code to Apps format" as `in_progress`.

### 3.1 Copy Code Dependencies and Artifacts

The original MLflow model may contain multiple code files and artifacts that need to be migrated.

**Copy all code files from `/code` to `agent_server/`:**

```bash
# Copy all Python files from original code folder
cp ./original_mlflow_model/code/*.py ./<app-name>/agent_server/

# If there are subdirectories with code, copy those too
# cp -r ./original_mlflow_model/code/submodule ./<app-name>/agent_server/
```

**Copy artifacts (if present):**

```bash
# Create an artifacts directory in the migrated app if needed
mkdir -p ./<app-name>/agent_server/artifacts

# Copy all artifacts
cp -r ./original_mlflow_model/artifacts/* ./<app-name>/agent_server/artifacts/ 2>/dev/null || true
```

**Fix import paths after copying:**

When code files are moved, imports may break. Check and update imports in all copied files:

```python
# BEFORE (if files were in different locations):
from code.utils import helper_function
from artifacts.prompts import SYSTEM_PROMPT

# AFTER (files are now in agent_server/):
from agent_server.utils import helper_function
# Or if in same directory:
from .utils import helper_function

# For artifacts, update file paths:
# BEFORE:
with open("artifacts/config.yaml") as f:
# AFTER:
import os
config_path = os.path.join(os.path.dirname(__file__), "artifacts", "config.yaml")
with open(config_path) as f:
```

> **Important:** Review each copied file and ensure all imports resolve correctly. The most common issues are:
> - Relative imports that assumed a different directory structure
> - Hardcoded file paths to artifacts
> - Missing `__init__.py` files for package imports

### 3.2 Extract Configuration

From the original agent code, identify and preserve:
- **LLM endpoint name** (e.g., `databricks-claude-sonnet-4-5`)
- **System prompt**
- **Tool definitions**
- **Any custom logic**

### 3.3 Update the Agent Entry Point

The approach depends on whether the user chose async or sync migration.

---

#### Path A: Synchronous Migration (`<async>` = no)

This is the minimal-changes path. Extract the logic from the `ResponsesAgent` class, wrap it with `@invoke`/`@stream` decorators, and keep all code synchronous.

Edit `<app-name>/agent_server/agent.py`:

1. **Replace the scaffold with the original agent logic.** The core transformation is extracting the class methods into decorated functions:

```python
from mlflow.genai.agent_server import invoke, stream
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

# Move any class __init__ or class-level setup to module level
# e.g., client initialization, tool setup, etc.

@invoke()
def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    # Paste the body of the original predict() method here
    # Remove 'self.' references — replace with module-level variables
    # Remove 'params' parameter (not used in Apps)
    ...
    return ResponsesAgentResponse(output=outputs)

@stream()
def streaming(request: ResponsesAgentRequest):
    # Paste the body of the original predict_stream() method here
    # Remove 'self.' references — replace with module-level variables
    # Remove 'params' parameter (not used in Apps)
    for chunk in ...:
        yield ResponsesAgentStreamEvent(...)
```

2. **Key changes from class to functions:**
   - Remove the `class MyAgent(ResponsesAgent):` wrapper
   - Remove `self` parameter from all methods
   - Move `__init__` logic (client creation, tool setup) to module-level code
   - Replace `self.some_attribute` with module-level variables
   - Add `@invoke()` decorator to the non-streaming function
   - Add `@stream()` decorator to the streaming function

3. **Keep all other code as-is** — no need to convert sync calls to async, no need to change `for` to `async for`, no need to add `await`.

---

#### Path B: Async Migration (`<async>` = yes)

This path converts all I/O operations to async for higher concurrency. More changes are required, but the result is a more efficient server.

Edit `<app-name>/agent_server/agent.py`:

1. **Update the LLM endpoint:**
   ```python
   LLM_ENDPOINT_NAME = "<your-endpoint-from-original>"
   ```

2. **Update the system prompt:**
   ```python
   SYSTEM_PROMPT = """<your-system-prompt-from-original>"""
   ```

3. **Add your custom tools:**
   If your original agent had custom tools, add them:
   ```python
   from langchain_core.tools import tool

   @tool
   async def my_custom_tool(arg: str) -> str:
       """Tool description."""
       # Your tool logic (make async if needed)
       return result
   ```

4. **Convert all I/O to async:**
   - `def predict()` → `async def non_streaming()`
   - `def predict_stream()` → `async def streaming()`
   - `client.chat()` → `await client.achat()`
   - `for chunk in stream:` → `async for chunk in stream:`
   - Sync HTTP calls → `await` async equivalents

5. **Preserve any special logic:**
   Migrate any custom preprocessing, postprocessing, or business logic from the original agent.

---

### 3.4 Handle Stateful Agents

**If original uses checkpointer (short-term memory):**
- Add checkpointer with Lakebase integration (use `AsyncCheckpointSaver` if async, or sync equivalent if sync)
- Configure `LAKEBASE_INSTANCE_NAME` in `.env`
- Extract thread_id from `request.custom_inputs` or `request.context.conversation_id`

**If original uses store (long-term memory):**
- Add store with Lakebase integration (use `AsyncDatabricksStore` if async, or sync equivalent if sync)
- Configure `LAKEBASE_INSTANCE_NAME` in `.env`
- Extract user_id from `request.custom_inputs` or `request.context.user_id`

---

## Step 4: Set Up the App

> **Task:** Mark "Migrate agent code to Apps format" as `completed`. Mark "Set up and configure the app" as `in_progress`.

### 4.1 Verify Build Configuration

Before installing dependencies, ensure a README file exists (hatchling requires this):

**Ensure a README file exists:**

```bash
# Create a minimal README if one doesn't exist
if [ ! -f "README.md" ]; then
  echo "# Migrated Agent App" > README.md
fi
```

### 4.2 Install Dependencies

```bash
cd <app-name>
uv sync
```

### 4.3 Create requirements.txt for Databricks Apps

Databricks Apps requires a `requirements.txt` file with `uv` to install dependencies from `pyproject.toml`:

```bash
echo "uv" > requirements.txt
```

### 4.4 Run Quickstart

Run the `uv run quickstart` script to quickly set up your local environment. This is the **recommended** way to configure the app as it handles all necessary setup automatically.

```bash
uv run quickstart
```

This script will:

1. Verify uv, nvm, and Databricks CLI installations
2. Configure Databricks authentication
3. Configure agent tracing, by creating and linking an MLflow experiment to your app
4. Configure `.env` with the necessary environment variables

> **Important:** The quickstart script creates the MLflow experiment that the app needs for logging traces and models. This experiment will be added as a resource when deploying the app.

If there are issues with the quickstart script, refer to the manual setup in section 4.5.

### 4.5 Manual Environment Configuration (Optional)

If you need to manually configure the environment or add additional variables, edit `.env`:

```bash
# Databricks authentication
DATABRICKS_CONFIG_PROFILE=<your-profile>

# MLflow experiment (created by quickstart, or create manually)
MLFLOW_EXPERIMENT_ID=<experiment-id>

# Example: Lakebase for stateful agents
LAKEBASE_INSTANCE_NAME=<your-lakebase-instance>

# Example: Custom API keys
MY_API_KEY=<value>
```

To manually create an MLflow experiment:

```bash
databricks experiments create-experiment "/Users/<your-username>/<app-name>" --profile <profile>
```

---

## Step 5: Test Locally

> **Task:** Mark "Set up and configure the app" as `completed`. Mark "Test agent locally" as `in_progress`.

> Test your migrated agent locally before deploying to Databricks Apps. This helps catch configuration issues early and ensures the agent works correctly.

### 5.1 Start the Server

After the quickstart setup is complete, start the agent server and chat app locally:

```bash
cd <app-name>
uv run start-app
```

Wait for the server to start. You should see output indicating the server is running on `http://localhost:8000`.

> **Note:** If you only need the API endpoint (without the chat UI), you can run `uv run start-server` instead.

### 5.2 Test with Original Input Example

The original model artifacts include an `input_example.json` file that contains a sample request. Use this to verify your migrated agent produces the same behavior. If there's no valid sample request then figure out a valid sample request to query agent based on its code.

```bash
# Check the original input example (from the <app-name> directory)
cat ../original_mlflow_model/input_example.json
```

Example content:
```json
{"input": [{"role": "user", "content": "What is an LLM agent?"}], "custom_inputs": {"thread_id": "example-thread-123"}}
```

Test your local server with this input:

```bash
# Test with the original input example
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d "$(cat ../original_mlflow_model/input_example.json)"
```

### 5.3 Test Basic Requests

```bash
# Non-streaming
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Hello!"}]}'

# Streaming
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Hello!"}], "stream": true}'
```

### 5.4 Test with Custom Inputs (for stateful agents)

```bash
# With thread_id for short-term memory
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Hi"}], "custom_inputs": {"thread_id": "test-123"}}'

# With user_id for long-term memory
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Hi"}], "custom_inputs": {"user_id": "user@example.com"}}'
```

### 5.5 Verify Before Proceeding

Before proceeding to deployment, ensure:
- [ ] The server starts without errors
- [ ] The original input example returns a valid response
- [ ] Streaming responses work correctly
- [ ] Custom inputs (thread_id, user_id) are handled properly (if applicable)

> **Note:** Only proceed to Step 6 (Deploy) after confirming the agent works correctly locally.

---

## Step 6: Deploy to Databricks Apps

> **Task:** Mark "Test agent locally" as `completed`. Mark "Deploy to Databricks Apps" as `in_progress`.

This step uses Databricks Asset Bundles (DAB) to deploy. The scaffold includes a `databricks.yml` that you need to update with the app name and resources from the original model.

### 6.1 Extract Resources from Original Model

The original model's `MLmodel` file contains a `resources` section that lists all Databricks resources the agent needs access to. Check `../original_mlflow_model/MLmodel` (or `./original_mlflow_model/MLmodel` if you're in the parent directory) for content like:

```yaml
resources:
  api_version: '1'
  databricks:
    lakebase:
    - name: lakebase
    serving_endpoint:
    - name: databricks-claude-sonnet-4-5
```

### 6.2 Update `databricks.yml` with Resources

The scaffold includes a `databricks.yml` with the experiment resource pre-configured. You need to:

1. **Update the app name** to `<app-name>` (the name provided by the user) in both the `resources.apps.agent_migration.name` field and the `targets.prod.resources.apps.agent_migration.name` field.
2. **Add resources** extracted from the original MLmodel file to the `resources.apps.agent_migration.resources` list.

**Resource Type Mapping (MLmodel → `databricks.yml`):**

| MLmodel Resource | `databricks.yml` Resource | Key Fields |
|------------------|--------------------------|------------|
| `serving_endpoint` | `serving_endpoint` | `name`, `permission` (CAN_QUERY) |
| `lakebase` | `database` | `database_name: databricks_postgres`, `instance_name`, `permission` (CAN_CONNECT_AND_CREATE) |
| `vector_search_index` | `uc_securable` | `securable_full_name`, `securable_type: TABLE`, `permission: SELECT` |
| `function` | `uc_securable` | `securable_full_name`, `securable_type: FUNCTION`, `permission: EXECUTE` |
| `table` | `uc_securable` | `securable_full_name`, `securable_type: TABLE`, `permission: SELECT` |
| `uc_connection` | `uc_securable` | `securable_full_name`, `securable_type: CONNECTION`, `permission: USE_CONNECTION` |
| `sql_warehouse` | `sql_warehouse` | `id`, `permission` (CAN_USE) |
| `genie_space` | `genie_space` | `space_id`, `permission` (CAN_RUN) |

> **Note:** The `experiment` resource is already configured in the scaffold `databricks.yml` and is automatically created by the bundle. You do not need to add it manually.

**Example: `databricks.yml` for an agent with a serving endpoint and UC function:**

```yaml
resources:
  experiments:
    agent_migration_experiment:
      name: /Users/${workspace.current_user.userName}/${bundle.name}-${bundle.target}

  apps:
    agent_migration:
      name: "<app-name>"  # Update to user's app name
      description: "Migrated agent from Model Serving to Databricks Apps"
      source_code_path: ./
      resources:
        - name: 'experiment'
          experiment:
            experiment_id: "${resources.experiments.agent_migration_experiment.id}"
            permission: 'CAN_MANAGE'
        - name: 'serving-endpoint'
          serving_endpoint:
            name: 'databricks-claude-sonnet-4-5'
            permission: 'CAN_QUERY'
        - name: 'python-exec'
          uc_securable:
            securable_full_name: 'system.ai.python_exec'
            securable_type: 'FUNCTION'
            permission: 'EXECUTE'

targets:
  prod:
    resources:
      apps:
        agent_migration:
          name: "<app-name>"  # Same name for production
```

**Example: Adding Lakebase resources (for stateful agents):**

```yaml
        - name: 'database'
          database:
            database_name: 'databricks_postgres'
            instance_name: 'lakebase'
            permission: 'CAN_CONNECT_AND_CREATE'
```

### 6.3 Deploy with Databricks Asset Bundles

From inside the `<app-name>` directory, validate, deploy, and run:

```bash
# 1. Validate bundle configuration (catches errors before deploy)
databricks bundle validate --profile <profile>

# 2. Deploy the bundle (creates/updates resources, uploads files)
databricks bundle deploy --profile <profile>

# 3. Run the app (starts/restarts with uploaded source code) - REQUIRED!
databricks bundle run agent_migration --profile <profile>
```

> **Important:** `bundle deploy` only uploads files and configures resources. `bundle run` is **required** to actually start/restart the app with the new code. If you only run `deploy`, the app will continue running old code!

### 6.4 Test Deployed App

> **Task:** Mark "Deploy to Databricks Apps" as `completed`. Mark "Test deployed app" as `in_progress`.

```bash
# Get the app URL
APP_URL=$(databricks apps get <app-name> --profile <profile> --output json | jq -r '.url')

# Get OAuth token
TOKEN=$(databricks auth token --profile <profile> | jq -r .access_token)

# Query the app
curl -X POST ${APP_URL}/invocations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "Hello!"}]}'
```

Once the deployed app responds successfully:

> **Task:** Mark "Test deployed app" as `completed`. Migration complete!

### 6.5 Deployment Troubleshooting

If you encounter issues during deployment, refer to the **deploy** skill for detailed guidance.

**Debug commands:**
```bash
# Validate bundle configuration
databricks bundle validate --profile <profile>

# View app logs
databricks apps logs <app-name> --profile <profile> --follow

# Check app status
databricks apps get <app-name> --profile <profile> --output json | jq '{app_status, compute_status}'

# Get app URL
databricks apps get <app-name> --profile <profile> --output json | jq -r '.url'
```

**"App already exists" error:**
If `databricks bundle deploy` fails because the app already exists, refer to the **deploy** skill for instructions on binding an existing app to the bundle.

---

## Reference: App File Structure

```
<app-name>/
├── agent_server/
│   ├── __init__.py
│   ├── agent.py          # Main agent logic - THIS IS WHERE YOU MIGRATE TO
│   ├── start_server.py   # FastAPI server setup
│   ├── utils.py          # Helper utilities
│   └── evaluate_agent.py # Agent evaluation
├── scripts/
│   ├── __init__.py
│   ├── quickstart.py     # Setup script
│   └── start_app.py      # App startup
├── databricks.yml        # Databricks Asset Bundle configuration (resources, config, targets)
├── pyproject.toml        # Dependencies (for local dev with uv)
├── requirements.txt      # REQUIRED: Must contain "uv" for Databricks Apps
├── .env.example          # Environment template
└── README.md
```

> **IMPORTANT:** The `requirements.txt` file must exist and contain `uv` so that Databricks Apps can install dependencies using the `pyproject.toml`. Without this file, the app will fail to start.

---

## Reference: Common Migration Patterns

### Pattern 1: Simple Chat Agent

**Original:**
```python
class ChatAgent(ResponsesAgent):
    def predict(self, request, params=None):
        messages = to_chat_completions_input(request.input)
        response = self.llm.invoke(messages)
        return ResponsesAgentResponse(output=[...])
```

**Migrated (sync):**
```python
llm = ...  # Move class-level init to module level

@invoke()
def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    messages = to_chat_completions_input(request.input)
    response = llm.invoke(messages)
    return ResponsesAgentResponse(output=[...])

@stream()
def streaming(request: ResponsesAgentRequest):
    # Original predict_stream() body, with self. removed
    ...
```

**Migrated (async):**
```python
@invoke()
async def non_streaming(request: ResponsesAgentRequest) -> ResponsesAgentResponse:
    outputs = [e.item async for e in streaming(request) if e.type == "response.output_item.done"]
    return ResponsesAgentResponse(output=outputs)

@stream()
async def streaming(request: ResponsesAgentRequest) -> AsyncGenerator[ResponsesAgentStreamEvent, None]:
    messages = {"messages": to_chat_completions_input([i.model_dump() for i in request.input])}
    agent = await init_agent()
    async for event in process_agent_astream_events(agent.astream(messages, stream_mode=["updates", "messages"])):
        yield event
```

### Pattern 2: Agent with Custom Tools

**Sync:** Keep tools as-is from the original code.

**Async:** Migrate tools to async LangChain tools:

```python
from langchain_core.tools import tool

@tool
async def search_docs(query: str) -> str:
    """Search the documentation."""
    results = await vector_store.asimilarity_search(query)
    return format_results(results)
```

### Pattern 3: Using LangGraph with create_agent (async only)

```python
from langchain.agents import create_agent
from databricks_langchain import ChatDatabricks

async def init_agent():
    tools = await mcp_client.get_tools()  # MCP tools are async
    model = ChatDatabricks(endpoint=LLM_ENDPOINT_NAME)
    return create_agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT)
```

---

## Reference: Useful Resources

- **Responses API Docs:** https://mlflow.org/docs/latest/genai/serving/responses-agent/
- **Agent Framework:** https://docs.databricks.com/aws/en/generative-ai/agent-framework/
- **Agent Tools:** https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool
- **databricks-langchain SDK:** https://github.com/databricks/databricks-ai-bridge/tree/main/integrations/langchain

---

## Troubleshooting

### "Module not found" errors
```bash
uv sync  # Reinstall dependencies
```

### Authentication errors
```bash
databricks auth login  # Re-authenticate
```

### Lakebase permission errors
- Ensure the Lakebase instance is added as an app resource in Databricks UI
- Grant appropriate permissions on the Lakebase instance

### Async errors (async migration only)
- Ensure all I/O calls use async versions (e.g., `await client.achat()` not `client.chat()`)
- Use `async for` instead of `for` when iterating async generators
- If you chose sync migration, these errors should not occur — double-check that you're not mixing sync and async patterns
