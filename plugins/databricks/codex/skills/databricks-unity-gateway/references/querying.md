# Query services

Read this reference when writing Python that invokes a Unity Gateway model service or model
provider service. Python is for inference; continue to use the Databricks CLI for service
lifecycle and permission management.

A model service is required to query a Unity Gateway model. Databricks-hosted models already exist as model services in `system.ai`. Reference [Model services](./model-services.md) if you need to create a new model service with its own governance.

## Access paths

Unity Gateway exposes three ways to call models. All three go through governed Unity Catalog services. They differ in API surface, feature coverage, and where the model runs:

| Path | Endpoint | Coverage and limits | Use when |
|---|---|---|---|
| 1. Unified APIs (provider-agnostic) | `/ai-gateway/mlflow/v1/responses`, `/ai-gateway/mlflow/v1/embeddings`, `/ai-gateway/mlflow/v1/chat/completions` | OpenAI-compatible request/response shape across any backing provider; one OpenAI SDK client calls GPT/Claude/Gemini/GLM/Kimi models. Common-denominator feature set; supports swapping the backing model and multi-provider model services. Full gateway governance. | Portability across providers matters more than provider-specific features. |
| 2. Native APIs (Databricks-hosted models) | `/ai-gateway/openai/v1/responses`, `/ai-gateway/anthropic`, `/ai-gateway/gemini` | Native provider APIs, with documented limitations on supported parameters and tools (see [OpenAI Responses limitations](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-openai-responses#limitations)). Full gateway governance. | A provider-specific application (e.g. OpenAI SDK) moving onto Databricks-hosted models with minimal refactoring. |
| 3. Provider passthrough (model provider service) | Managed chat / responses / embeddings paths, other provider paths (e.g. `/images/generations`) via unmanaged-path opt-in | Full native provider surface, including code interpreter and Files (these execute provider-side). Full governance on managed paths. Unmanaged paths (e.g. `/files`, `/images/generations`) get credential brokering with thinner governance. | Inference must stay with the provider (e.g. for provider-only features). |

## Resolve query inputs

Before writing or running a query, resolve:

- Workspace URL and authentication method
- Exact three-part service name: `<catalog>.<schema>.<service>`
- Find Databricks-hosted model names with `databricks ai-gateway list-model-services --parent schemas/system.ai`; do not guess version names.
- API format required by the request
- For a model provider service, an upstream model allowed by its target configuration
- Optional request tags

Use a Databricks credential to call Unity Gateway. Never expose or request the external
provider credential; Unity Gateway supplies it for provider-service calls. Read credentials
from the environment or the runtime's supported Databricks authentication mechanism, never
hardcode them.

The caller needs `USE CATALOG`, `USE SCHEMA`, and `EXECUTE` on the selected service. See
[permissions.md](permissions.md).

## Query a model service

The unified Responses API (`/ai-gateway/mlflow/v1/responses`) is the recommended way to run
LLM inference on Databricks. It implements the
[Open Responses](https://www.openresponses.org/reference) specification and works across
backing providers; Unity Gateway translates each request to the backing model's native
format. Set `model` to the model service's fully qualified three-part name:

```python
import os

from openai import OpenAI

workspace_url = os.environ["DATABRICKS_HOST"].rstrip("/")
client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url=f"{workspace_url}/ai-gateway/mlflow/v1",
)

response = client.responses.create(
    model="<catalog>.<schema>.<model-service>",
    input=[{"role": "user", "content": "What is Databricks?"}],
    max_output_tokens=256,
)

print(response.output_text)
```

Open Responses on Unity Gateway is stateless. `previous_response_id` and server-side
conversation storage are unsupported; send the full conversation in `input` on each turn.
For tool calls, return every model output item unchanged, including `encrypted_content`
on reasoning and Gemini `function_call` items, then add a `function_call_output` with the
same `call_id`. Only `function` tools are portable across providers. See
[Open Responses provider behavior](https://docs.databricks.com/aws/en/machine-learning/model-serving/query-open-responses-models)
and the [Open Responses API reference](https://www.openresponses.org/reference).

### Query open source models

When querying open source models hosted by Databricks (Kimi, Deepseek, GLM, etc), use the unified Responses API via the OpenAI SDK:

```python
import os

from openai import OpenAI

workspace_url = os.environ["DATABRICKS_HOST"].rstrip("/")
client = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url=f"{workspace_url}/ai-gateway/mlflow/v1",
)

response = client.responses.create(
    model="system.ai.glm-5-3-flash",
    input=[{"role": "user", "content": "What's the weather in San Francisco?"}],
    tools=[
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get the current temperature for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
                "additionalProperties": False,
            },
        }
    ],
    reasoning={"effort": "high"},
    max_output_tokens=4096,
)

for item in response.output:
    if item.type == "function_call":
        print(item.name, item.arguments)
```

Default to the unified Responses API for new code as it has greater tool calling and agentic support. The unified Chat Completions API on the
same base URL (`/ai-gateway/mlflow/v1/chat/completions`) remains supported for backward compatibility. Use it when existing code, an agent, or a framework does not support the
Responses API. 

```python
response = client.chat.completions.create(
    model="<catalog>.<schema>.<model-service>",
    messages=[{"role": "user", "content": "What is Databricks?"}],
)

print(response.choices[0].message.content)
```

### Native APIs

Use a native API only when the backing model supports that format:

| API | Python client base URL |
|---|---|
| OpenAI Responses | `<workspace-url>/ai-gateway/openai/v1` |
| Anthropic Messages | `<workspace-url>/ai-gateway/anthropic` |
| Gemini generate content | `<workspace-url>/ai-gateway/gemini` |

For OpenAI Responses, keep the fully qualified model-service name in `model`:

```python
response = OpenAI(
    api_key=os.environ["DATABRICKS_TOKEN"],
    base_url=f"{workspace_url}/ai-gateway/openai/v1",
).responses.create(
    model="<catalog>.<schema>.<model-service>",
    input="What is Databricks?",
    max_output_tokens=256,
)
```

Do not use `/serving-endpoints` or `databricks-<model>` endpoint names. Do not use a native API whose format does not match the backing model. Use the unified Responses path when the backing provider is unknown or portability is preferred.

> **Sovereign clouds:** On Azure Government, Azure China (Mooncake), and AWS GovCloud/DoD, the `system.ai.<model>` names are not available yet — use the legacy `databricks-<model>` endpoint names there instead.

### Anthropic SDK

The Anthropic SDK has no Responses API, and `databricks-ai-bridge` has no Anthropic client. For unified Responses, use the OpenAI client as in [Query a model service](#query-a-model-service). If the Anthropic SDK is required, use the native Messages API at `<workspace-url>/ai-gateway/anthropic` with a Databricks token.

## SQL `ai_query`

`ai_query` supports only Databricks-provided `system.ai` model services (for example, `system.ai.claude-sonnet-4-5`), not model services you create. Only usage tracking applies; rate limits, guardrails implemented with service policies, inference tables, and fallbacks do not. See [Limitations](https://docs.databricks.com/aws/en/ai-gateway/query-model-services).

## Query a model provider service

Provider-service requests differ in two fields:

- Set `Databricks-Model-Provider-Service` to the provider service's three-part name.
- Set `model` to the upstream provider model, not the provider-service name.

For an OpenAI-compatible target whose `native_api_types` include `openai/v1/responses`:

```python
# Uses the optional databricks-openai package to simplify authentication.
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI

client = DatabricksOpenAI(
    workspace_client=WorkspaceClient(),
    use_ai_gateway_native_api=True,
    default_headers={
        "Databricks-Model-Provider-Service":
            "<catalog>.<schema>.<model-provider-service>"
    },
)

response = client.responses.create(
    model="<allowed-provider-model>",
    input=[{"role": "user", "content": "What is Databricks?"}],
)

print(response.output_text)
```

Managed provider paths include:

| Provider API | Path |
|---|---|
| OpenAI chat completions | `/ai-gateway/openai/v1/chat/completions` |
| OpenAI responses | `/ai-gateway/openai/v1/responses` |
| OpenAI embeddings | `/ai-gateway/openai/v1/embeddings` |
| Anthropic messages | `/ai-gateway/anthropic/v1/messages` |
| Gemini generate content | `/ai-gateway/gemini/v1beta/models/<model>:generateContent` |

Prefer managed paths. Unmanaged passthrough must be explicitly enabled on the provider
service and bypasses usage token and cost tracking, token-based rate limits, model access
control, and service policies. Select a client and path matching the configured target's
`native_api_types`; do not assume every provider or target accepts the OpenAI format.
For OpenAI embeddings use the managed embeddings path; for an unmanaged path such as `openai/v1/images/generations`, enable passthrough via [Model provider services](model-provider-services.md).

## Request tags

Attach string-valued request tags for cost attribution and usage analysis:

```python
import json

request_tags = {"project": "chatbot", "team": "ml-platform"}

response = client.responses.create(
    model="<catalog>.<schema>.<model-service>",
    input=[{"role": "user", "content": "What is Databricks?"}],
    extra_headers={
        "Databricks-Ai-Gateway-Request-Tags": json.dumps(request_tags)
    },
)
```

For a model service that routes to a model provider service, the model service's rate
limits, guardrails, inference table, and fallback behavior apply. The referenced provider
service's corresponding features are skipped for that routed request.

## Troubleshooting

**A configured service fails at inference.** A model can be visible in Unity Catalog but unavailable from the workspace region. Confirm a matching service in the Unity Gateway UI and check the public model-serving availability matrix.
