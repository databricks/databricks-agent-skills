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
        - serving.serving-endpoints
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

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| `PERMISSION_DENIED` on query | SP missing CAN_QUERY | Declare `serving_endpoint` resource in `databricks.yml` with `permission: CAN_QUERY` |
| `DATABRICKS_SERVING_ENDPOINT_NAME` env var empty | Missing env injection | Add `valueFrom: serving-endpoint` to `app.yaml` env section |
| 504 Gateway Timeout | Inference exceeds 120s proxy limit | Reduce `max_tokens` or use WebSockets — see [Platform Guide](../platform-guide.md) |
| Unknown serving endpoint alias | Alias not configured or env var not set | Check `serving()` config in `server.ts` and `DATABRICKS_SERVING_ENDPOINT_*` in `app.yaml` / `.env` |
