# AppKit Genie Guide

Use this guide when adding Databricks Genie to an AppKit app, especially when retrofitting an existing app that does not already use the built-in `genie()` plugin.

## Architecture

```text
User (browser) -> AppKit genie plugin (/api/genie/:alias/...) -> Databricks Genie API -> SQL Warehouse
               <- SSE stream (status, message_result, query_result) <-
```

The built-in `genie()` plugin from `@databricks/appkit` proxies requests to the Databricks Genie API via SSE streaming. The browser talks only to the AppKit server. The server-side plugin holds the credentials and resolves a Genie space from either:

- the default `DATABRICKS_GENIE_SPACE_ID` env var
- a named alias in `genie({ spaces: { ... } })`

## Default Retrofit Workflow

For an existing AppKit app, use this order:

1. Confirm the app is AppKit-based and does not already register `genie()` or expose `/api/genie`.
2. Get the current plugin/resource shape from authoritative sources:
   - `databricks apps manifest --profile <PROFILE>`
   - `npx @databricks/appkit docs`
3. Add a Genie space resource in `databricks.yml` with `permission: CAN_VIEW`.
4. Inject `DATABRICKS_GENIE_SPACE_ID` through `app.yaml` and the local development env file.
5. Register `genie()` in `server/server.ts`, preserving existing plugins.
6. Add UI with `<GenieChat alias="default" />` unless the user explicitly wants a custom chat experience.
7. Update smoke tests if headings or routes changed, then run the normal `databricks-apps` validation flow.

## Key Files

| File | Purpose |
|------|---------|
| `databricks.yml` | Declare Genie variables and the `genie-space` app resource |
| `app.yaml` | Map `DATABRICKS_GENIE_SPACE_ID` from the `genie-space` resource |
| `server/server.ts` | Import and register the built-in `genie()` plugin |
| `server/.env` or equivalent local env file | Set `DATABRICKS_GENIE_SPACE_ID` for local development |
| `client/src/...` | Render `GenieChat` or use `useGenieChat` for custom UI |

## Local Development Env

Set `DATABRICKS_GENIE_SPACE_ID` in the env file used by the app template for local server development. In the standard AppKit layout, that is commonly `server/.env`.

```dotenv
DATABRICKS_GENIE_SPACE_ID=<YOUR_SPACE_ID>
```

For deployment, use app resources and `valueFrom` in `app.yaml` instead of checking IDs into source control.

## `app.yaml`

Add Genie env injection next to the existing warehouse mapping:

```yaml
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: DATABRICKS_GENIE_SPACE_ID
    valueFrom: genie-space
```

The `valueFrom` name must match the resource name declared in `databricks.yml`.

## `databricks.yml`

Add Genie variables and a Genie space resource. Keep names aligned with the rest of the repo: resource type `genie_space`, resource name `genie-space`, permission `CAN_VIEW`.

**Variables section**

```yaml
variables:
  sql_warehouse_id:
    description: SQL Warehouse ID
  genie_space_id:
    description: Genie Space ID
  genie_space_name:
    description: Genie Space name
```

**App resource**

```yaml
resources:
  apps:
    app:
      resources:
        - name: sql-warehouse
          sql_warehouse:
            id: ${var.sql_warehouse_id}
            permission: CAN_USE
        - name: genie-space
          genie_space:
            name: ${var.genie_space_name}
            space_id: ${var.genie_space_id}
            permission: CAN_VIEW
```

**Target variables**

```yaml
targets:
  default:
    variables:
      sql_warehouse_id: <warehouse_id>
      genie_space_id: <space_id>
      genie_space_name: <space_name>
```

If the app already has a `resources.apps.app.resources` list, append the Genie resource instead of rewriting the list.

## `server/server.ts`

Register the built-in plugin:

```typescript
import { createApp, server, analytics, genie } from "@databricks/appkit";

createApp({
  plugins: [server(), analytics(), genie()],
}).catch(console.error);
```

If the app does not use analytics, keep the existing plugins and add `genie()` to the array. If the app already uses other plugins, preserve them and add `genie()`. Do not create a local Genie proxy plugin file unless the user explicitly needs behavior that the built-in plugin cannot provide.

## Server Config Patterns

### Default Single Space

```typescript
import { createApp, server, genie } from "@databricks/appkit";

createApp({
  plugins: [server(), genie()],
}).catch(console.error);
```

This reads `DATABRICKS_GENIE_SPACE_ID` and exposes it as the `default` alias.

### Multiple Spaces

```typescript
genie({
  spaces: {
    sales: "01ABCDEF12345678",
    support: "01GHIJKL87654321",
  },
  timeout: 60000,
})
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `spaces` | `Record<string, string>` | `{ default: DATABRICKS_GENIE_SPACE_ID }` | Alias-to-space map |
| `timeout` | `number` | `120000` | Polling timeout in ms. Use `0` for no timeout |

Use named aliases only when the UI truly needs multiple Genie spaces. Otherwise keep the default single-space flow.

### Programmatic Server Access

```typescript
const app = await createApp({
  plugins: [server(), genie({ spaces: { demo: "space-id" } })],
});

for await (const event of app.genie.sendMessage("demo", "Show revenue by region")) {
  console.log(event.type, event);
}
```

## HTTP Endpoints

The plugin mounts SSE endpoints under `/api/genie`:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/genie/:alias/messages` | `POST` | Send a message and stream progress/results |
| `/api/genie/:alias/conversations/:conversationId` | `GET` | Replay an existing conversation |

### Send Message Request

```http
POST /api/genie/:alias/messages
Content-Type: application/json

{ "content": "What were total sales last quarter?", "conversationId": "optional-existing-id" }
```

### SSE Event Types

| Event | Payload | Description |
|-------|---------|-------------|
| `message_start` | `{ conversationId, messageId, spaceId }` | Message and conversation IDs assigned |
| `status` | `{ status: "ASKING_AI" \| "EXECUTING_QUERY" \| ... }` | Progress updates |
| `message_result` | `{ content, attachments }` | Final assistant message |
| `query_result` | `{ attachmentId, statementId, data }` | Tabular results for a query attachment |
| `error` | `{ error }` | Error details |

Message statuses commonly progress through:

`SUBMITTED -> FILTERING_CONTEXT -> ASKING_AI -> EXECUTING_QUERY -> COMPLETED`

Failure states also include `FAILED` and `CANCELLED`.

### Attachment Types

Completed responses can contain attachments. Identify them by key:

| Key | Meaning |
|-----|---------|
| `query` | Generated SQL plus metadata |
| `text` | Natural-language explanation |
| `suggestedQuestions` | Follow-up prompts |

## Frontend Patterns

Import UI pieces from `@databricks/appkit-ui/react`.

### `GenieChat` (Default)

Use this unless the user asks for a custom layout or specialized rendering:

```tsx
import { GenieChat } from "@databricks/appkit-ui/react";

function GeniePage() {
  return (
    <div style={{ height: 600 }}>
      <GenieChat alias="default" />
    </div>
  );
}
```

| Prop | Type | Default | Notes |
|------|------|---------|-------|
| `alias` | `string` | none | Must match the server alias |
| `basePath` | `string` | `"/api/genie"` | Override only if routes are customized |
| `placeholder` | `string` | `"Ask a question..."` | Input placeholder |
| `className` | `string` | none | Root container styling |

Full-page example:

```tsx
import { GenieChat } from "@databricks/appkit-ui/react";

function GeniePage() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center p-4 w-full">
      <div className="w-full max-w-4xl flex flex-col h-[calc(100vh-2rem)]">
        <h1 className="text-2xl font-bold mb-4">Genie Chat</h1>
        <GenieChat alias="default" className="flex-1" />
      </div>
    </div>
  );
}
```

### `useGenieChat` (Custom UI)

Use the hook only when the built-in component is not enough:

```tsx
import { useGenieChat } from "@databricks/appkit-ui/react";

const { messages, status, conversationId, error, sendMessage, reset } = useGenieChat({
  alias: "default",
});
```

| Field | Type | Description |
|-------|------|-------------|
| `messages` | `GenieMessageItem[]` | Conversation messages |
| `status` | `"idle" \| "loading-history" \| "streaming" \| "error"` | Current chat state |
| `conversationId` | `string \| null` | Active conversation ID |
| `error` | `string \| null` | Current error, if any |
| `sendMessage` | `(content: string) => void` | Sends a prompt |
| `reset` | `() => void` | Starts a new conversation |

Example custom chat:

```tsx
import { useGenieChat } from "@databricks/appkit-ui/react";
import { useState } from "react";

function CustomChat() {
  const { messages, status, sendMessage, reset } = useGenieChat({ alias: "default" });
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;
    sendMessage(input.trim());
    setInput("");
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-bold">Chat</h2>
        <Button variant="outline" size="sm" onClick={reset}>New Chat</Button>
      </div>
      <ScrollArea className="flex-1 min-h-0">
        {messages.map((message) => (
          <div key={message.id} className={message.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={`max-w-[85%] rounded-lg px-4 py-3 ${
                message.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
              }`}
            >
              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
            </div>
          </div>
        ))}
      </ScrollArea>
      <div className="flex gap-2 mt-4 pt-4 border-t">
        <Input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask a question..."
          disabled={status === "streaming"}
        />
        <Button onClick={handleSend} disabled={status === "streaming"}>Send</Button>
      </div>
    </div>
  );
}
```

### Lower-Level Components

These are also available from `@databricks/appkit-ui/react`:

| Component | Purpose |
|-----------|---------|
| `GenieChatInput` | Auto-expanding input with Enter-to-send |
| `GenieChatMessage` | Single chat bubble with attachment rendering |
| `GenieChatMessageList` | Scrollable list with auto-scroll and streaming state |

## Behavioral Defaults

- Prefer `GenieChat` for most apps. It already handles SSE streaming, conversation state, history replay, and query result rendering.
- Give the parent container an explicit height. Without one, the chat UI may collapse.
- Keep the alias as `"default"` unless the server config defines named spaces.
- Start a new conversation when query accuracy matters. Long-lived threads can reduce answer quality.
- Prefer the built-in streaming UX. Do not bolt on custom polling unless there is a proven gap.
- Expect query result limits. If a large result looks truncated, explain that in the UI.
- Treat POST requests as rate-limited. Avoid designing retry loops that can spam the API.

## Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Alias mismatch | `404` under `/api/genie/...` | Make the frontend alias match the server alias |
| Missing `DATABRICKS_GENIE_SPACE_ID` | Server reports Genie is not configured | Set env var or pass `spaces` explicitly |
| No explicit chat height | Chat collapses or renders poorly | Give the parent container a fixed height |
| Old local Genie proxy file | Duplicate routes or import confusion | Remove it and use `genie` from `@databricks/appkit` |
| Manual SSE reimplementation | Extra complexity and bugs | Use `GenieChat` or `useGenieChat` |
| Missing `whitespace-pre-wrap` in custom messages | Explanation text renders on one line | Add `whitespace-pre-wrap` to custom message content |

## Scaffolding New Apps

When starting a new app, follow the normal `databricks-apps` scaffolding workflow:

1. Run `databricks apps manifest --profile <PROFILE>`
2. Confirm the current template exposes a Genie feature and what resource fields it requires
3. Build the `databricks apps init` command from the manifest output

Do not hardcode a scaffold command from a different template. The manifest is the source of truth for plugin IDs, resource keys, and required `--set` fields.
