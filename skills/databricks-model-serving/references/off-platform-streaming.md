# Off-Platform Streaming with AI SDK v6

These patterns are for apps deployed **outside** Databricks Apps (e.g., Vercel, AWS, standalone Node.js servers) using direct AI SDK v6 integration with Databricks AI Gateway. For AppKit-based apps, use the **`databricks-apps`** skill's built-in serving plugin instead.

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
- `DATABRICKS_WORKSPACE_ID` — for explicit setup: `databricks api get /api/2.1/unity-catalog/current-metastore-assignment --profile <PROFILE>` → `workspace_id` field
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
import { WorkspaceClient } from "@databricks/sdk-experimental";

const workspaceClient = new WorkspaceClient({
  host: process.env.DATABRICKS_HOST,
});

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

For vector similarity search with these embeddings, see the **`databricks-lakebase`** skill.

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| 502 from AI Gateway | Token expired or invalid endpoint | Refresh token via `getDatabricksToken()`; verify endpoint exists |
| `TextStreamChatTransport` not found | Wrong AI SDK version | Requires `ai@6` and `@ai-sdk/react@3` |
