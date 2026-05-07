---
name: databricks-model-serving
description: "Manage Databricks Model Serving endpoints via CLI. Use when asked to create, configure, query, or manage model serving endpoints for LLM inference, custom models, or external models."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Model Serving Endpoints

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Model Serving provides managed endpoints for serving LLMs, custom ML models, and external models as scalable REST APIs. Endpoints are identified by **name** (unique per workspace).

## Endpoint Types

| Type | When to Use | Key Detail |
|------|-------------|------------|
| Pay-per-token | Foundation Model APIs (Llama, DBRX, etc.) | Uses `system.ai.*` catalog models, simplest setup |
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
      "workload_size": "Small"
    }],
    "traffic_config": {
      "routes": [{
        "served_entity_name": "<ENTITY_NAME>",
        "traffic_percentage": 100
      }]
    }
  }' --profile <PROFILE>
```

- Discover available Foundation Models: check the `system.ai` catalog in Unity Catalog.
- Long-running operation; the CLI waits for completion by default. Use `--no-wait` to return immediately, then poll:
  ```bash
  databricks serving-endpoints get <ENDPOINT_NAME> --profile <PROFILE>
  # Check: state.ready == "READY"
  ```
- For provisioned throughput or custom model endpoints, run `databricks serving-endpoints create -h` to discover the required JSON fields for your endpoint type.

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

Then add a tRPC route to call it from your app. For the full app integration pattern, use the **`databricks-apps`** skill and read the [Model Serving Guide](../databricks-apps/references/appkit/model-serving.md).

## Troubleshooting

| Error | Solution |
|-------|----------|
| `cannot configure default credentials` | Use `--profile` flag or authenticate first |
| `PERMISSION_DENIED` | Check workspace permissions; for apps, ensure `serving_endpoint` resource declared with `CAN_QUERY` |
| Endpoint stuck in `NOT_READY` | Check `build-logs` for the served model (get entity name from `get` output) |
| `RESOURCE_DOES_NOT_EXIST` | Verify endpoint name with `list` |
| Query returns 404 | Endpoint may still be provisioning; check `state.ready` via `get` |
| `RATE_LIMIT_EXCEEDED` (429) | AI Gateway rate limit; check `put-ai-gateway` config or retry after backoff |
