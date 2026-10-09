# Model Serving: Calling ML Endpoints from Apps

Use Model Serving when your app needs **AI features** — chat, inference, embeddings, or predictions from a Databricks Model Serving endpoint. For analytics dashboards, use `config/queries/` instead. For persistent storage, use Lakebase.

## When to Use

| Pattern | Use Case | Data Source |
|---------|----------|-------------|
| Analytics | Read-only dashboards, charts, KPIs | SQL Warehouse |
| Lakebase | CRUD operations, persistent state, forms | PostgreSQL (Lakebase) |
| Model Serving | Chat, AI features, model inference | Serving Endpoint |
| Multiple | Dashboard with AI features or persistent state | Combine as needed |

## Scaffolding

Check if the `serving` plugin is available in the AppKit template:

```bash
databricks apps manifest --profile <PROFILE>
```

**If the manifest includes a `serving` plugin:**

```bash
databricks apps init --name <APP_NAME> --features serving \
  --set "serving.serving-endpoint.name=<ENDPOINT_NAME>" \
  --run none --profile <PROFILE>
```

**If adding to an existing app**, see *Adding Model Serving to an Existing App* below.

Use the `databricks-model-serving` skill to create a serving endpoint first if one doesn't exist yet.

## Adding Model Serving to an Existing App

**`databricks.yml`** — add serving endpoint resource and user_api_scopes:

```yaml
resources:
  apps:
    app:
      user_api_scopes:
        # ... existing scopes ...
        - model-serving
      resources:
        # ... existing resources ...
        - name: serving-endpoint
          serving_endpoint:
            name: <ENDPOINT_NAME>
            permission: CAN_QUERY
```

**`app.yaml`** — add env injection:

```yaml
env:
  # ... existing env vars ...
  - name: DATABRICKS_SERVING_ENDPOINT_NAME
    valueFrom: serving-endpoint
```

The injected value is the endpoint **name** (not a URL). Use it in server-side code to call the endpoint.

**`server/server.ts`** — register the plugin:

```typescript
import { createApp, server, analytics, serving } from "@databricks/appkit";

createApp({
  plugins: [server(), analytics(), serving()],
}).catch(console.error);
```

Preserve existing plugins and add `serving()` to the array.

**`server/.env`** — for local development:

```dotenv
DATABRICKS_SERVING_ENDPOINT_NAME=<your-endpoint-name>
```

Update smoke tests if headings or routes changed, then `databricks apps validate`.

## Serving Plugin API

Access model serving through the plugin handle returned by `createApp()`:

```typescript
import { createApp, server, serving } from "@databricks/appkit";

const appkit = await createApp({
  plugins: [server(), serving()],
});

// Non-streaming invocation
const result = await appkit.serving().invoke({
  messages: [{ role: "user", content: "Hello" }],
});

// Streaming invocation
for await (const chunk of appkit.serving().stream({
  messages: [{ role: "user", content: "Hello" }],
})) {
  console.log(chunk);
}

// On-behalf-of user (OBO) — uses the requesting user's identity
const result = await appkit.serving().asUser(req).invoke({
  messages: [{ role: "user", content: prompt }],
});
```

All serving routes execute on behalf of the authenticated user (OBO) by default. For programmatic access via `exports()`, use `.asUser(req)` to run in user context.

## Named Endpoints

Use endpoint aliases to reference multiple serving endpoints by name:

```typescript
serving({
  endpoints: {
    llm: { env: "DATABRICKS_SERVING_ENDPOINT_NAME" },
    classifier: { env: "DATABRICKS_SERVING_ENDPOINT_CLASSIFIER" },
  },
  timeout: 120000, // optional, default 2 min
})
```

Each alias maps to an environment variable holding the actual endpoint name. Access by alias:

```typescript
const result = await appkit.serving("llm").invoke({ messages });
const classification = await appkit.serving("classifier").invoke({ inputs: ["text"] });
```

If an endpoint serves multiple models, use `servedModel` to target a specific model directly:

```typescript
serving({
  endpoints: {
    llm: { env: "DATABRICKS_SERVING_ENDPOINT_NAME", servedModel: "llama-v2" },
  },
})
```

## HTTP Endpoints

The plugin auto-registers routes under `/api/serving`:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/serving/invoke` | `POST` | Non-streaming (default mode) |
| `/api/serving/stream` | `POST` | Streaming SSE (default mode) |
| `/api/serving/:alias/invoke` | `POST` | Non-streaming (named mode) |
| `/api/serving/:alias/stream` | `POST` | Streaming SSE (named mode) |

## Frontend

Use the built-in React hooks from `@databricks/appkit-ui/react` — do NOT call serving endpoints directly from the client.

**Streaming** (chat, real-time inference):

```tsx
import { useServingStream } from "@databricks/appkit-ui/react";

function ChatStream() {
  const { stream, chunks, streaming, error, reset } = useServingStream(
    { messages: [{ role: "user", content: "Hello" }] },
    {
      alias: "llm",
      onComplete: (finalChunks) => console.log("Done:", finalChunks.length, "chunks"),
    },
  );

  return (
    <>
      <button onClick={stream} disabled={streaming}>Send</button>
      <button onClick={reset}>Reset</button>
      {chunks.map((chunk, i) => <pre key={i}>{JSON.stringify(chunk)}</pre>)}
      {error && <p>{error}</p>}
    </>
  );
}
```

**Non-streaming** (one-shot inference, classification):

```tsx
import { useServingInvoke } from "@databricks/appkit-ui/react";

function Classify() {
  const { invoke, data, loading, error } = useServingInvoke(
    { inputs: ["sample text"] },
    { alias: "classifier" },
  );

  return (
    <>
      <button onClick={() => invoke()} disabled={loading}>Classify</button>
      {data && <pre>{JSON.stringify(data)}</pre>}
      {error && <p>{error}</p>}
    </>
  );
}
```

Both hooks accept `autoStart: true` to invoke automatically on mount.

For the full hook API and type generation details, see `npx @databricks/appkit docs ./docs/plugins/model-serving.md`.

For off-platform streaming (AI SDK v6 with Databricks AI Gateway), see the **`databricks-model-serving`** skill.

AppKit integrates with **Model Serving endpoints**. AI Gateway (beta) endpoints are not directly supported — use the underlying Model Serving endpoint name instead. AI Gateway features (rate limits, usage tracking) can be configured on Model Serving endpoints via the `databricks-model-serving` skill.

## Unity Catalog model services

Built-in pay-per-token `databricks-*` foundation-model endpoints are being retired in favor of **Unity Catalog model services**, addressed by UC full name (`catalog.schema.name`; foundation models are `system.ai.<model>`). After the workspace enables **Enforce Unity Gateway**, an app that calls a retired endpoint on `/serving-endpoints/<name>/invocations` gets **HTTP 403 PERMISSION_DENIED** from the model-serving proxy: `"Querying pay-per-token foundation model endpoint '<name>' is disabled for this workspace. Please use Unity Gateway."` (the console UI phrases it as `"...is no longer available. Use Unity Catalog model services."`). Custom, external-model, and MPS-backed serving endpoints keep using `/serving-endpoints/<name>/invocations`.

Two related 403s look similar:

- **Provisioned-throughput (PT) foundation-model endpoints** also reject direct queries under enforcement: `"Querying provisioned throughput foundation model endpoint '<name>' directly is disabled for this workspace. Please use Unity Gateway."` Create a model service that references the PT endpoint and declare that model service as the `uc_securable` below.
- `"Endpoint '<name>' is no longer available. Please use Unity Gateway."` is returned for AI Gateway v2 endpoints of every type, custom and external included. On its own it doesn't mean a built-in endpoint was retired; check which endpoint the app is calling.

Declare the model service as a `uc_securable` app resource (`securable_type: MODEL_SERVICE`, `permission: EXECUTE`). On deploy, the app's service principal is granted `EXECUTE` on the model service, plus `USE CATALOG` and `USE SCHEMA` on its parents when account users don't already hold them — this replaces the `serving_endpoint` resource's `CAN_QUERY`. Inject it with `valueFrom: <resource-name>`; the env var resolves to the service's full name.

```yaml
# databricks.yml — declare the model service as an app resource (permissions granted on deploy)
resources:
  apps:
    my_app:
      resources:
        - name: model
          uc_securable:
            securable_type: MODEL_SERVICE
            permission: EXECUTE
            securable_full_name: system.ai.claude-sonnet-4-5
```

```yaml
# app.yaml — inject the resource; the env var resolves to the service FQN
env:
  - name: MODEL_SERVICE
    valueFrom: model   # e.g. system.ai.claude-sonnet-4-5
```

`serving()` and its endpoint aliases take Model Serving endpoint names only — do not pass a model-service name to `serving()`. Call the model service from server code instead, passing the injected full name as `model` on the `/ai-gateway/mlflow/v1` path with the app service principal's credentials. From Python:

```python
import os

import requests
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # app service principal credentials injected by the Apps runtime

response = requests.post(
    f"{w.config.host.rstrip('/')}/ai-gateway/mlflow/v1/chat/completions",
    headers={**w.config.authenticate(), "Content-Type": "application/json"},
    json={
        "model": os.environ["MODEL_SERVICE"],
        "messages": [{"role": "user", "content": "Summarize this support case."}],
        "max_tokens": 256,
    },
    timeout=60,
)
response.raise_for_status()
print(response.json()["choices"][0]["message"]["content"])
```

From a Node.js server route (TypeScript), mint an OAuth token for the app service principal from the injected `DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`:

```typescript
const host = process.env.DATABRICKS_HOST!.replace(/^(?!https?:\/\/)/, 'https://').replace(/\/$/, '');

async function getAppToken(): Promise<string> {
  const res = await fetch(`${host}/oidc/v1/token`, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${Buffer.from(`${process.env.DATABRICKS_CLIENT_ID}:${process.env.DATABRICKS_CLIENT_SECRET}`).toString('base64')}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: 'grant_type=client_credentials&scope=all-apis',
  });
  if (!res.ok) throw new Error(`token request failed: ${res.status}`);
  return (await res.json()).access_token;
}

const res = await fetch(`${host}/ai-gateway/mlflow/v1/chat/completions`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${await getAppToken()}`, 'Content-Type': 'application/json' },
  body: JSON.stringify({
    model: process.env.MODEL_SERVICE,
    messages: [{ role: 'user', content: 'Summarize this support case.' }],
    max_tokens: 256,
  }),
});
if (!res.ok) throw new Error(`model service call failed: ${res.status}`);
const data = await res.json();
console.log(data.choices[0].message.content);
```

To migrate a retired built-in endpoint, look up the matching model service with `databricks ai-gateway list-model-services --parent schemas/system.ai` (don't guess the name from the endpoint), point `securable_full_name` at it, and call that full name in place of the endpoint name. For other query APIs (Responses, native provider APIs), permissions outside Apps, and migrating non-app clients, use the **`databricks-unity-gateway`** skill.

> **Sovereign clouds:** On Azure Government, Azure China (Mooncake), and AWS GovCloud/DoD, the `system.ai.<model>` names are not available yet — keep using the legacy `databricks-<model>` endpoint names there.

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| `PERMISSION_DENIED` on query | SP missing CAN_QUERY | Declare `serving_endpoint` resource in `databricks.yml` with `permission: CAN_QUERY` |
| `DATABRICKS_SERVING_ENDPOINT_NAME` env var empty | Missing env injection | Add `valueFrom: serving-endpoint` to `app.yaml` env section |
| 504 Gateway Timeout | Inference exceeds 120s proxy limit | Reduce `max_tokens` or use WebSockets — see [Platform Guide](../platform-guide.md) |
| Unknown serving endpoint alias | Alias not configured or env var not set | Check `serving()` config in `server.ts` and `DATABRICKS_SERVING_ENDPOINT_*` in `app.yaml` / `.env` |
| `403` / `PERMISSION_DENIED` on a foundation model: `"...is disabled for this workspace. Please use Unity Gateway."` (console UI: `"...is no longer available. Use Unity Catalog model services."`) | The workspace enabled Enforce Unity Gateway, so a built-in `databricks-*` pay-per-token endpoint is retired, or a provisioned-throughput foundation-model endpoint can no longer be queried directly (`"...provisioned throughput ... directly is disabled..."`); the UC model service needs `EXECUTE` (+ `USE CATALOG`/`USE SCHEMA`), not `CAN_QUERY` | For an app, declare a `uc_securable` (`MODEL_SERVICE`, `EXECUTE`) resource and call the model-service full name — see *Unity Catalog model services* above. For a PT endpoint, first create a model service that references it. For non-app callers, use the **`databricks-unity-gateway`** skill. |
