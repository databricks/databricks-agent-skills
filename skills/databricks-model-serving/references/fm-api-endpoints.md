# Foundation Model API endpoints

Pay-per-token Foundation Model API endpoints are pre-provisioned in every supported workspace. New models land regularly and a static skill list goes stale fast — **always list at runtime instead of hard-coding names**.

Filter by the `databricks-` name prefix AND by the served entity living under `system.ai.*` — other endpoints (e.g. `databricks-app-template-serving`) share the prefix but aren't FM API endpoints.

```bash
# Foundation Model API endpoints in this workspace, grouped by task (chat / embeddings / etc.)
databricks serving-endpoints list --profile <PROFILE> \
  | jq -r '.[]
      | select(.name | startswith("databricks-"))
      | select((.config.served_entities[0].entity_name // "") | startswith("system.ai."))
      | "\(.task)\t\(.name)"' \
  | sort
```

For per-endpoint region, cross-geo, and retirement notes, see the [supported models](https://docs.databricks.com/machine-learning/foundation-model-apis/supported-models) docs page. For production-grade workloads, consider provisioned throughput mode.

## Defaults when the user doesn't specify

Resolve actual names from the live list above; pick by family rather than memorising a version:

- **Agent / chat LLM**: highest-numbered `databricks-claude-sonnet-*` (good quality / latency / cost balance).
- **Code tasks**: highest-numbered `databricks-gpt-*-codex` available (older `databricks-gpt-5-1-codex-*` and `databricks-gpt-5-2-codex` are scheduled to retire 2026-07-16).
- **Embeddings**: `databricks-gte-large-en` (1024 dims, 8192 max tokens).

The `system.ai` catalog in Unity Catalog is a second source of truth — endpoint names match the model identifiers under `system.ai.*`.

## Querying

Pay-per-token endpoints are pre-deployed; you don't need to create them. Use the endpoint name resolved from the runtime list:

```bash
databricks serving-endpoints query <ENDPOINT_NAME> \
  --json '{"messages":[{"role":"user","content":"hi"}]}' \
  --profile <PROFILE>
```

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
response = w.serving_endpoints.query(
    name="<ENDPOINT_NAME>",
    messages=[{"role": "user", "content": "hi"}],
)
```

Use `databricks serving-endpoints get-open-api <ENDPOINT_NAME> --profile <PROFILE>` to inspect a specific endpoint's request/response schema before constructing non-chat payloads (e.g. embeddings).
