# Foundation Model API Endpoints

Pay-per-token Foundation Model API endpoints available in supported Model Serving regions; several endpoints (notably the Gemini family) require cross-geography routing — see the [supported models](https://docs.databricks.com/machine-learning/foundation-model-apis/supported-models) page for per-endpoint region and cross-geo notes. Use the **exact endpoint name** from the tables below as `served_entities[].entity_name` (or as the model identifier when calling `serving-endpoints query`); never abbreviate or guess.

For production-grade workloads, consider provisioned throughput mode.

## Chat / Instruct Models

| Endpoint Name | Provider | Notes |
|--------------|----------|-------|
| `databricks-gpt-5-5-pro` | OpenAI | Multimodal, 400K context, extended prompt caching |
| `databricks-gpt-5-5` | OpenAI | Multimodal, 400K context, extended prompt caching |
| `databricks-gpt-5-4` | OpenAI | Multimodal, 400K context, general-purpose reasoning |
| `databricks-gpt-5-4-mini` | OpenAI | Multimodal, 400K context, cost-optimized |
| `databricks-gpt-5-4-nano` | OpenAI | Multimodal, 400K context, high-throughput |
| `databricks-gpt-5-3-codex` | OpenAI | Multimodal, 400K context, agentic coding (not in AI Playground) |
| `databricks-gpt-5-2-codex` | OpenAI | Code-specialized; **retiring 2026-07-16** |
| `databricks-gpt-5-2` | OpenAI | Multimodal, 400K context, general-purpose reasoning |
| `databricks-gpt-5-1` | OpenAI | Instant + Thinking modes, 400K context |
| `databricks-gpt-5-1-codex-max` | OpenAI | Code-specialized (high perf); global endpoint, cross-geo required; **retiring 2026-07-16** |
| `databricks-gpt-5-1-codex-mini` | OpenAI | Code-specialized (cost-opt); global endpoint, cross-geo required; **retiring 2026-07-16** |
| `databricks-gpt-5` | OpenAI | 400K context, reasoning |
| `databricks-gpt-5-mini` | OpenAI | Cost-optimized reasoning |
| `databricks-gpt-5-nano` | OpenAI | High-throughput, lightweight |
| `databricks-gpt-oss-120b` | OpenAI | Open-weight reasoning, 128K context |
| `databricks-gpt-oss-20b` | OpenAI | Lightweight open-weight, 128K context |
| `databricks-claude-opus-4-7` | Anthropic | Most capable Claude; 1M context, improved vision |
| `databricks-claude-opus-4-6` | Anthropic | Adaptive thinking with max-effort mode, 1M context |
| `databricks-claude-opus-4-5` | Anthropic | Hybrid reasoning, 200K context |
| `databricks-claude-opus-4-1` | Anthropic | General-purpose hybrid reasoning, 200K/32K output |
| `databricks-claude-sonnet-4-6` | Anthropic | Hybrid reasoning with two modes |
| `databricks-claude-sonnet-4-5` | Anthropic | Hybrid reasoning with two modes |
| `databricks-claude-sonnet-4` | Anthropic | Hybrid reasoning with two modes |
| `databricks-claude-haiku-4-5` | Anthropic | Fastest, most cost-effective Claude |
| `databricks-meta-llama-3-3-70b-instruct` | Meta | 128K context, multilingual |
| `databricks-meta-llama-3-1-8b-instruct` | Meta | Lightweight, 128K context |
| `databricks-llama-4-maverick` | Meta | Multimodal, mixture-of-experts |
| `databricks-gemini-3-1-pro` | Google | 1M context; global endpoint, cross-geo required |
| `databricks-gemini-3-pro` | Google | **Retired 2026-03-26**; redirects to Gemini 3.1 Pro through 2026-06-07 |
| `databricks-gemini-3-1-flash-lite` | Google | Multimodal (text/image/video/audio); global endpoint, cross-geo required |
| `databricks-gemini-3-5-flash` | Google | Multimodal; cross-geo required outside US/EU |
| `databricks-gemini-3-flash` | Google | Multimodal; global endpoint, cross-geo required |
| `databricks-gemini-2-5-pro` | Google | 1M context, Deep Think mode, audio output |
| `databricks-gemini-2-5-flash` | Google | 1M context, fully hybrid reasoning |
| `databricks-gemma-3-12b` | Google | Multimodal, 128K context, 140+ languages |
| `databricks-qwen35-122b-a10b` | Alibaba | Reasoning-only (cannot disable), 256K context (Preview) |
| `databricks-qwen3-next-80b-a3b-instruct` | Alibaba | Ultra-long context, instruction-following (Preview) |

## Embedding Models

| Endpoint Name | Dimensions | Max Tokens | Notes |
|--------------|-----------|------------|-------|
| `databricks-gte-large-en` | 1024 | 8192 | English, not normalized |
| `databricks-bge-large-en` | 1024 | 512 | English, normalized |
| `databricks-qwen3-embedding-0-6b` | up to 1024 | ~32K | 100+ languages, instruction-aware |

## Common defaults

- **Agent LLM**: `databricks-meta-llama-3-3-70b-instruct` — good balance of quality/cost.
- **Embedding**: `databricks-gte-large-en`.
- **Code tasks**: `databricks-gpt-5-3-codex` (current agentic-coding endpoint; predecessor `databricks-gpt-5-2-codex` and the `databricks-gpt-5-1-codex-*` pair are retiring 2026-07-16).

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
