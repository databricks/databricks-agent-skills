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

**If no `serving` plugin** (add manually to an existing app):

Use the `databricks-model-serving` skill to create a serving endpoint first, then follow the resource declaration and tRPC patterns below.

## Resource Declaration

Add the serving endpoint resource to `databricks.yml`:

```yaml
resources:
  apps:
    my_app:
      resources:
        - name: my-model-endpoint
          serving_endpoint:
            name: <ENDPOINT_NAME>
            permission: CAN_QUERY          # auto-granted to SP on deploy
```

Add environment variable injection in `app.yaml`:

```yaml
env:
  - name: SERVING_ENDPOINT
    valueFrom: serving-endpoint
```

The injected value is the endpoint **name** (not a URL). Use it in server-side code to call the endpoint.

## Non-Streaming Query Pattern (tRPC)

Always use tRPC for model serving calls — do NOT call endpoints directly from the client.

```typescript
// server/server.ts (or server/trpc.ts)
import { initTRPC } from "@trpc/server";
import { getExecutionContext } from "@databricks/appkit";
import { z } from "zod";
import superjson from "superjson";

const t = initTRPC.create({ transformer: superjson });
const publicProcedure = t.procedure;

export const appRouter = t.router({
  queryModel: publicProcedure
    .input(z.object({ prompt: z.string() }))
    .query(async ({ input: { prompt } }) => {
      const { serviceDatabricksClient: client } = getExecutionContext();
      const response = await client.servingEndpoints.query({
        name: process.env.SERVING_ENDPOINT,
        messages: [{ role: "user", content: prompt }],
      });
      return response;
    }),
});
```

## Client-side Pattern

```typescript
// client/src/components/ChatComponent.tsx
import { trpc } from "@/lib/trpc";

const result = await trpc.queryModel.query({ prompt: userInput });
const answer = result.choices?.[0]?.message?.content;
```

For AppKit's built-in serving plugin streaming (SSE via `stream()` and `useServingStream`), see `npx @databricks/appkit docs ./docs/plugins/model-serving.md`. The patterns below are for apps deployed **outside** Databricks Apps (e.g., Vercel, AWS, standalone Node.js servers) using direct AI SDK v6 integration with Databricks AI Gateway. For AppKit-based apps, use the built-in serving plugin above.

## AI SDK v6 Streaming Pattern

Use this pattern for streaming AI chat with Databricks AI Gateway and Vercel AI SDK v6 in off-platform apps.

**Dependencies:** `ai@6`, `@ai-sdk/react@3`, `@ai-sdk/openai`, `@databricks/sdk-experimental`

**Auth helper** — works for both local dev (CLI profile) and deployed apps (service principal token):

```typescript
import { Config } from "@databricks/sdk-experimental";

async function getDatabricksToken() {
  if (process.env.DATABRICKS_TOKEN) {
    return process.env.DATABRICKS_TOKEN;
  }
  const config = new Config({
    profile: process.env.DATABRICKS_CONFIG_PROFILE || "DEFAULT",
  });
  await config.ensureResolved();
  const headers = new Headers();
  await config.authenticate(headers);
  const authHeader = headers.get("Authorization");
  if (!authHeader) {
    throw new Error(
      "Failed to get Databricks token. Check your CLI profile or set DATABRICKS_TOKEN.",
    );
  }
  return authHeader.replace("Bearer ", "");
}
```

**Server route** (`POST /api/chat`):

```typescript
import { createOpenAI } from "@ai-sdk/openai";
import { streamText, type UIMessage } from "ai";

app.post("/api/chat", async (req, res) => {
  const { messages } = req.body;

  // AI SDK v6 client sends UIMessage objects with a parts array.
  // Convert to CoreMessage format for streamText().
  const coreMessages = (messages as UIMessage[]).map((m) => ({
    role: m.role as "user" | "assistant" | "system",
    content:
      m.parts
        ?.filter((p) => p.type === "text" && p.text)
        .map((p) => p.text)
        .join("") ??
      m.content ??
      "",
  }));

  try {
    const token = await getDatabricksToken();
    const endpoint = process.env.DATABRICKS_ENDPOINT || "<ENDPOINT_NAME>";

    // AI Gateway URL uses /mlflow/v1 path, NOT /openai/v1
    // URL varies by cloud: .cloud.databricks.com (AWS), .azuredatabricks.net (Azure), .gcp.databricks.com (GCP)
    const databricks = createOpenAI({
      baseURL: `https://${process.env.DATABRICKS_WORKSPACE_ID}.ai-gateway.cloud.databricks.com/mlflow/v1`,
      apiKey: token,
    });

    const result = streamText({
      model: databricks.chat(endpoint),
      messages: coreMessages,
      maxOutputTokens: 1000,
    });

    result.pipeTextStreamToResponse(res);
  } catch (err) {
    const message = (err as Error).message;
    console.error(`[chat] Streaming request failed:`, message);
    res.status(502).json({ error: "Chat request failed", detail: message });
  }
});
```

**Environment variables:**
- `DATABRICKS_WORKSPACE_ID` — auto-discovered by AppKit at runtime; for explicit setup: `databricks api get /api/2.1/unity-catalog/current-metastore-assignment --profile <PROFILE>` → `workspace_id` field
- `DATABRICKS_ENDPOINT` — model endpoint name (e.g. `databricks-meta-llama-3-3-70b-instruct`). Run `databricks serving-endpoints list --profile <PROFILE>` to see available models.

## Streaming Client Pattern (AI SDK v6)

```tsx
import { useChat } from "@ai-sdk/react";
import { TextStreamChatTransport } from "ai";
import { useState } from "react";

export function ChatPage() {
  const [input, setInput] = useState("");

  const { messages, sendMessage, status } = useChat({
    transport: new TextStreamChatTransport({ api: "/api/chat" }),
  });

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-4 p-4">
        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "text-right" : ""}>
            <span className="text-sm font-medium">
              {m.role === "user" ? "You" : "Assistant"}
            </span>
            {m.parts.map((part, i) =>
              part.type === "text" ? (
                <p key={`${m.id}-${i}`} className="whitespace-pre-wrap">
                  {part.text}
                </p>
              ) : null,
            )}
          </div>
        ))}
        {status === "submitted" && <div className="p-4">Loading...</div>}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (input.trim()) {
            void sendMessage({ text: input });
            setInput("");
          }
        }}
        className="border-t p-4 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          className="flex-1 border rounded px-3 py-2"
          disabled={status !== "ready"}
        />
        <button type="submit" disabled={status !== "ready"}>
          {status === "submitted" || status === "streaming"
            ? "Sending..."
            : "Send"}
        </button>
      </form>
    </div>
  );
}
```

Key differences from AI SDK v5: use `sendMessage({ text })` (NOT `append`), render `m.parts` array (NOT `m.content`), and `status` states are `ready`, `submitted`, `streaming`.

## Embeddings Pattern

Generate text embeddings using a Databricks AI Gateway endpoint.

```typescript
import { getWorkspaceClient } from "@databricks/appkit";

const workspaceClient = getWorkspaceClient({});

export async function generateEmbedding(text: string): Promise<number[]> {
  const endpoint =
    process.env.DATABRICKS_EMBEDDING_ENDPOINT || "databricks-gte-large-en";
  const result = await workspaceClient.servingEndpoints.query({
    name: endpoint,
    input: text,
  });
  return result.data![0].embedding!;
}
```

Common embedding endpoints: `databricks-gte-large-en` (1024d), `databricks-bge-large-en` (1024d). Set `DATABRICKS_EMBEDDING_ENDPOINT` in `.env` and `app.yaml`.

For vector similarity search with these embeddings, see the `databricks-lakebase` skill's [pgvector.md](../../../databricks-lakebase/references/pgvector.md).

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| `PERMISSION_DENIED` on query | SP missing CAN_QUERY | Declare `serving_endpoint` resource in `databricks.yml` with `permission: CAN_QUERY` |
| `SERVING_ENDPOINT` env var empty | Missing env injection | Add `valueFrom: serving-endpoint` to `app.yaml` env section |
| 504 Gateway Timeout | Inference exceeds 120s proxy limit | Reduce `max_tokens` or use WebSockets — see [Platform Guide](../platform-guide.md) |
| `getExecutionContext` undefined | Called outside AppKit server context | Ensure call is inside a tRPC procedure on the server side |
| 502 from AI Gateway | Token expired or invalid endpoint | Refresh token via `getDatabricksToken()`; verify endpoint exists |
| `TextStreamChatTransport` not found | Wrong AI SDK version | Requires `ai@6` and `@ai-sdk/react@3` |
