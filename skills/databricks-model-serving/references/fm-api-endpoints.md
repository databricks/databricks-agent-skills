# Foundation Model API Endpoints

Pay-per-token Foundation Model API endpoints available in every workspace. Use the **exact endpoint name** from the tables below as `served_entities[].entity_name` (or as the model identifier when calling `serving-endpoints query`); never abbreviate or guess.

For production-grade workloads, consider provisioned throughput mode. See the docs page for [supported models](https://docs.databricks.com/machine-learning/foundation-model-apis/supported-models).

## Chat / Instruct Models

| Endpoint Name | Provider | Notes |
|--------------|----------|-------|
| `databricks-gpt-5-2` | OpenAI | Latest GPT, 400K context |
| `databricks-gpt-5-1` | OpenAI | Instant + Thinking modes |
| `databricks-gpt-5-1-codex-max` | OpenAI | Code-specialized (high perf) |
| `databricks-gpt-5-1-codex-mini` | OpenAI | Code-specialized (cost-opt) |
| `databricks-gpt-5` | OpenAI | 400K context, reasoning |
| `databricks-gpt-5-mini` | OpenAI | Cost-optimized reasoning |
| `databricks-gpt-5-nano` | OpenAI | High-throughput, lightweight |
| `databricks-gpt-oss-120b` | OpenAI | Open-weight, 128K context |
| `databricks-gpt-oss-20b` | OpenAI | Lightweight open-weight |
| `databricks-claude-opus-4-6` | Anthropic | Most capable, 1M context |
| `databricks-claude-sonnet-4-6` | Anthropic | Hybrid reasoning |
| `databricks-claude-sonnet-4-5` | Anthropic | Hybrid reasoning |
| `databricks-claude-opus-4-5` | Anthropic | Deep analysis, 200K context |
| `databricks-claude-sonnet-4` | Anthropic | Hybrid reasoning |
| `databricks-claude-opus-4-1` | Anthropic | 200K context, 32K output |
| `databricks-claude-haiku-4-5` | Anthropic | Fastest, cost-effective |
| `databricks-claude-3-7-sonnet` | Anthropic | Retiring April 2026 |
| `databricks-meta-llama-3-3-70b-instruct` | Meta | 128K context, multilingual |
| `databricks-meta-llama-3-1-405b-instruct` | Meta | Retiring May 2026 (PT) |
| `databricks-meta-llama-3-1-8b-instruct` | Meta | Lightweight, 128K context |
| `databricks-llama-4-maverick` | Meta | MoE architecture |
| `databricks-gemini-3-1-pro` | Google | 1M context, hybrid reasoning |
| `databricks-gemini-3-pro` | Google | 1M context, hybrid reasoning |
| `databricks-gemini-3-flash` | Google | Fast, cost-efficient |
| `databricks-gemini-2-5-pro` | Google | 1M context, Deep Think |
| `databricks-gemini-2-5-flash` | Google | 1M context, hybrid reasoning |
| `databricks-gemma-3-12b` | Google | 128K context, multilingual |
| `databricks-qwen3-next-80b-a3b-instruct` | Alibaba | Efficient MoE |

## Embedding Models

| Endpoint Name | Dimensions | Max Tokens | Notes |
|--------------|-----------|------------|-------|
| `databricks-gte-large-en` | 1024 | 8192 | English, not normalized |
| `databricks-bge-large-en` | 1024 | 512 | English, normalized |
| `databricks-qwen3-embedding-0-6b` | up to 1024 | ~32K | 100+ languages, instruction-aware |

## Common defaults

- **Agent LLM**: `databricks-meta-llama-3-3-70b-instruct` — good balance of quality/cost.
- **Embedding**: `databricks-gte-large-en`.
- **Code tasks**: `databricks-gpt-5-1-codex-mini` (cost-opt) or `databricks-gpt-5-1-codex-max` (high perf).

## Querying

Pay-per-token endpoints are pre-deployed; you don't need to create them. Query directly:

```bash
databricks serving-endpoints query databricks-meta-llama-3-3-70b-instruct \
  --json '{"messages":[{"role":"user","content":"hi"}]}'
```

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
response = w.serving_endpoints.query(
    name="databricks-meta-llama-3-3-70b-instruct",
    messages=[{"role": "user", "content": "hi"}],
)
```

For a full list of available models in the current workspace, browse the `system.ai` catalog in Unity Catalog. Endpoint names listed above match the model identifiers under `system.ai.*`.
