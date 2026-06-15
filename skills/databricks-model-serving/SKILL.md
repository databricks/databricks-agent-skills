---
name: databricks-model-serving
description: "Databricks Model Serving (ops) plus MLflow model development (dev): manage serving endpoints, train and register models to Unity Catalog with @prod aliases, batch-score via spark_udf, build custom PyFunc / ResponsesAgent models, and discover Foundation Model API endpoints."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.3.0"
parent: databricks-core
---

# Model Serving Endpoints

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Model Serving provides managed endpoints for serving LLMs, custom ML models, and external models as scalable REST APIs. Endpoints are identified by **name** (unique per workspace).

## Endpoint Types

| Type | When to Use | Key Detail |
|------|-------------|------------|
| Pay-per-token | Foundation Model APIs (Llama, GPT-5, Claude, Gemini, etc.) | Uses `system.ai.*` catalog models, simplest setup. Discover endpoints at runtime — see [references/training-and-serving.md § Foundation Model API endpoints](references/training-and-serving.md#foundation-model-api-endpoints). |
| Provisioned throughput | Dedicated GPU capacity | Guaranteed throughput, higher cost |
| Custom model | Your own MLflow models or containers | Deploy any model with an MLflow signature |

## Endpoint Structure

```
Serving Endpoint (top-level, identified by NAME)
  ├── Config
  │     ├── Served Entities (model references + scaling config)
  │     └── Traffic Config (routing percentages across entities)
  ├── AI Gateway (rate limits, usage tracking)
  └── State (READY / NOT_READY, config_update status)
```

- **Served Entities**: Each entity references a model (from Unity Catalog or MLflow) with scaling parameters. Get the entity name from `served_entities[].name` in the `get` output — needed for `build-logs` and `logs` commands.
- **Traffic Config**: Routes requests across served entities by percentage (for A/B testing, canary deployments).
- **State**: Endpoints transition `NOT_READY` → `READY` after creation or config update. Poll via `get` to check `state.ready`.

## CLI Discovery — ALWAYS Do This First

**Do NOT guess command syntax.** Discover available commands and their usage dynamically:

```bash
# List all serving-endpoints subcommands
databricks serving-endpoints -h

# Get detailed usage for any subcommand (flags, args, JSON fields)
databricks serving-endpoints <subcommand> -h
```

Run `databricks serving-endpoints -h` before constructing any command. Run `databricks serving-endpoints <subcommand> -h` to discover exact flags, positional arguments, and JSON spec fields for that subcommand.

## Create an Endpoint

> **Do NOT list endpoints before creating.**

```bash
databricks serving-endpoints create <ENDPOINT_NAME> \
  --json '{
    "served_entities": [{
      "entity_name": "<MODEL_CATALOG_PATH>",
      "entity_version": "<VERSION>",
      "min_provisioned_throughput": 0,
      "max_provisioned_throughput": 0,
      "workload_size": "Small",
      "scale_to_zero_enabled": true
    }],
    "traffic_config": {
      "routes": [{
        "served_entity_name": "<ENTITY_NAME>",
        "traffic_percentage": 100
      }]
    }
  }' --profile <PROFILE>
```

- Discover available Foundation Models: see [references/training-and-serving.md § Foundation Model API endpoints](references/training-and-serving.md#foundation-model-api-endpoints) for the runtime-list snippet and default-picking rules. You can also check the `system.ai` catalog in Unity Catalog, or run `databricks serving-endpoints list --profile <PROFILE>` to see what's deployed in the workspace. Use `databricks serving-endpoints get-open-api <ENDPOINT_NAME> --profile <PROFILE>` to inspect a specific endpoint's API schema.
- Long-running operation; the CLI waits for completion by default. Use `--no-wait` to return immediately, then poll:
  ```bash
  databricks serving-endpoints get <ENDPOINT_NAME> --profile <PROFILE>
  # Check: state.ready == "READY"
  ```
- For provisioned throughput or custom model endpoints, run `databricks serving-endpoints create -h` to discover the required JSON fields for your endpoint type.

### Endpoint Readiness

After `create` or `update-config`, the endpoint provisions compute and loads the model. **Do not query the endpoint until it is ready.**

Poll for readiness:

```bash
databricks serving-endpoints get <ENDPOINT_NAME> --profile <PROFILE> -o json
# Ready when: state.ready == "READY" AND state.config_update == "NOT_UPDATING"
```

Provisioning may take several minutes. Provisioned throughput endpoints take the longest (GPU allocation). Queries to endpoints that are not yet `READY` return 404 or 503 errors.

## Query an Endpoint

```bash
databricks serving-endpoints query <ENDPOINT_NAME> \
  --json '{"messages": [{"role": "user", "content": "Hello, how are you?"}]}' \
  --profile <PROFILE>
```

- Use `--stream` for streaming responses.
- For non-chat endpoints (embeddings, custom models): use `get-open-api <ENDPOINT_NAME>` first to discover the request/response schema, then construct the appropriate JSON payload.

## Get Endpoint Schema (OpenAPI)

Returns the OpenAPI 3.1 JSON schema describing what each served model accepts and returns. Use this to understand an endpoint's input/output format before querying it.

```bash
databricks serving-endpoints get-open-api <ENDPOINT_NAME> --profile <PROFILE>
```

The schema shows paths per served model (e.g., `/served-models/<model-name>/invocations`) with full request/response definitions including parameter types, enums, and nullable fields.

## Other Commands

Run `databricks serving-endpoints <subcommand> -h` for usage details.

| Task | Command | Notes |
|------|---------|-------|
| List all endpoints | `list` | |
| Get endpoint details | `get <NAME>` | Shows state, config, served entities |
| Delete endpoint | `delete <NAME>` | |
| Update served entities or traffic | `update-config <NAME> --json '...'` | Zero-downtime: old config serves until new is ready |
| Rate limits & usage tracking | `put-ai-gateway <NAME> --json '...'` | |
| Update tags | `patch <NAME> --json '...'` | |
| Build logs | `build-logs <NAME> <SERVED_MODEL>` | Get `SERVED_MODEL` from `get` output: `served_entities[].name` |
| Runtime logs | `logs <NAME> <SERVED_MODEL>` | |
| Metrics (Prometheus format) | `export-metrics <NAME>` | |
| Permissions | `get-permissions <ENDPOINT_ID>` | ⚠️ Uses endpoint **ID** (hex string), not name. Find ID via `get`. |

## What's Next

### Integrate with a Databricks App

After creating a serving endpoint, wire it into a Databricks App.

**Step 1 — Check if the `serving` plugin is available** in the AppKit template:

```bash
databricks apps manifest --profile <PROFILE>
```

If the output includes a `serving` plugin, scaffold with:

```bash
databricks apps init --name <APP_NAME> \
  --features serving \
  --set "serving.serving-endpoint.name=<ENDPOINT_NAME>" \
  --run none --profile <PROFILE>
```

**Step 2 — If no `serving` plugin**, add the endpoint resource manually to an existing app's `databricks.yml`:

```yaml
resources:
  apps:
    my_app:
      resources:
        - name: my-model-endpoint
          serving_endpoint:
            name: <ENDPOINT_NAME>
            permission: CAN_QUERY
```

And inject the endpoint name as an environment variable in `app.yaml`:

```yaml
env:
  - name: SERVING_ENDPOINT
    valueFrom: serving-endpoint
```

Then wire the endpoint into your app via the `serving()` plugin or a custom route in `onPluginsReady`. For the full app integration pattern, use the **`databricks-apps`** skill and read the [Model Serving Guide](../databricks-apps/references/appkit/model-serving.md).

### Develop & deploy new models

This skill is ops-focused (manage existing endpoints). For the dev-side flow — train a model, register to Unity Catalog, log a PyFunc or `ResponsesAgent`, deploy — see the references below.

| Reference | When to read |
|---|---|
| [references/training-and-serving.md](references/training-and-serving.md) | Train + register classical ML with `mlflow.autolog`, alias-based promotion (`@prod`), batch scoring via `spark_udf`, real-time endpoint create + zero-downtime version swap, async deploy via `jobs submit --no-wait`. Includes the Foundation Model API endpoints runtime-list and the gotchas table. |
| [references/custom-pyfunc.md](references/custom-pyfunc.md) | When `autolog` isn't enough — file-based `PythonModel` ("Models from Code"), `infer_signature`, `code_paths`, pre-deploy validation with `mlflow.models.predict(env_manager="uv")`. |
| [references/genai-agents.md](references/genai-agents.md) | Hand-rolled `ResponsesAgent` with LangGraph + `UCFunctionToolkit` + `VectorSearchRetrieverTool`. Includes the `create_text_output_item` helper-method gotcha and the `resources=[...]` passthrough-auth list. |

## Troubleshooting

| Error | Solution |
|-------|----------|
| `cannot configure default credentials` | Use `--profile` flag or authenticate first |
| `PERMISSION_DENIED` | Check workspace permissions; for apps, ensure `serving_endpoint` resource declared with `CAN_QUERY` |
| Endpoint stuck in `NOT_READY` | Wait up to 30 min for provisioned throughput. Check build logs: `build-logs <NAME> <ENTITY_NAME>` (get entity name from `get` output → `served_entities[].name`) |
| `RESOURCE_DOES_NOT_EXIST` | Verify endpoint name with `list` |
| Query returns 404 | Endpoint may still be provisioning; check `state.ready` via `get` |
| `RATE_LIMIT_EXCEEDED` (429) | AI Gateway rate limit; check `put-ai-gateway` config or retry after backoff |
