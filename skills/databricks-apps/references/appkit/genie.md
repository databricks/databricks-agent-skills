# AppKit Genie Guide

Use this guide when building a Genie-powered app from scratch or when adding Databricks Genie to an existing AppKit app.

## When to Use This Guide

| Scenario | Start at |
|----------|----------|
| Build a NEW app powered by Genie | [Scaffolding a New Genie App](#scaffolding-a-new-genie-app) |
| Add Genie chat to an EXISTING AppKit app | [Adding Genie to an Existing App](#adding-genie-to-an-existing-app) |
| Create a Genie space from tables (no space ID yet) | [Create-or-Reuse Space Workflow](#create-or-reuse-space-workflow) |
| Wire a known space ID into an app | [Configuration Reference](#configuration-reference) |

## Space Setup UX Rule

When the user wants a Genie-powered app, do **not** start by asking for a `Genie Space ID`.

Instead, begin with a create-or-reuse workflow:

1. Ask whether the user wants to reuse an existing Genie space or create a new one.
2. If reusing, discover or confirm the existing space and only then ask for the ID if the agent cannot retrieve it directly.
3. If creating, ask which Unity Catalog tables or views the space should include before asking for any Genie-specific identifiers.

The goal is to keep the user in an app-building flow, not send them to the Databricks UI just to come back with a space ID.

## Architecture

```text
User (browser) -> AppKit genie plugin (/api/genie/...) -> Databricks Genie API -> SQL Warehouse
               <- SSE stream (status, message_result, query_result) <-
```

The built-in `genie()` plugin from `@databricks/appkit` proxies requests to the Databricks Genie API via SSE streaming. The browser talks only to the AppKit server. The server-side plugin holds the credentials and resolves the Genie space from the `DATABRICKS_GENIE_SPACE_ID` env var. Call `genie()` with no arguments — it picks up the space ID automatically.

## Scaffolding a New Genie App

Use this workflow when the user wants to build a new app from scratch that uses Genie as its primary interface (e.g. "I want a Genie app for my sales data").

### Prerequisites

1. Authenticated Databricks profile (use parent `databricks-core` skill).
2. Unity Catalog table names the user wants to query — fully qualified: `catalog.schema.table`.
3. A SQL warehouse ID. Discover with:
   ```bash
   databricks experimental aitools tools get-default-warehouse --profile <PROFILE>
   # or
   databricks warehouses list --profile <PROFILE>
   ```

### Step-by-Step Workflow

1. **Gather tables**: Ask the user which Unity Catalog tables or views the app should query. Accept fully qualified names like `catalog.schema.orders`.
2. **Discover the warehouse**: Run warehouse discovery (see Prerequisites above).
3. **Create the Genie space**: Use the Databricks CLI to create a space from the tables and warehouse. See [Genie Space Management](#genie-space-management) for details.
4. **Check the manifest**: Run `databricks apps manifest --profile <PROFILE>` to verify the `genie` plugin is available and to identify its resource keys and required `--set` fields.
5. **Scaffold the app**: Build the `databricks apps init` command from the manifest output. Example:
   ```bash
   databricks apps init --name <APP_NAME> \
     --features genie \
     --set "genie.<resourceKey>.<field>=<value>" \
     --run none --profile <PROFILE>
   ```
   Replace `<resourceKey>` and `<field>` with the actual keys from the manifest. **Do not guess** — always derive from `databricks apps manifest`.
6. **Verify wiring**: Confirm `server/server.ts` registers `genie()` and `app.yaml` maps `DATABRICKS_GENIE_SPACE_ID`.
7. **Set local env**: Add `DATABRICKS_GENIE_SPACE_ID=<space_id>` to `server/.env` for local development.
8. **Develop and validate**:
   ```bash
   cd <APP_NAME> && npm install && npm run dev
   # When ready:
   databricks apps validate --profile <PROFILE>
   ```

### Example: End-to-End New App

User says: *"I want a Genie app for my sales data in `main.sales.orders` and `main.sales.customers`."*

```bash
# 1. Discover warehouse
databricks experimental aitools tools get-default-warehouse --profile my-profile
# → returns warehouse ID, e.g. "abc123def456"

# 2. Create Genie space
databricks genie create-space \
  --title "Sales Assistant" \
  --description "Answers sales analytics questions" \
  --warehouse-id abc123def456 \
  --table main.sales.orders \
  --table main.sales.customers \
  --profile my-profile
# → returns space ID, e.g. "01ABCDEF12345678"

# 3. Check manifest for genie plugin keys
databricks apps manifest --profile my-profile

# 4. Scaffold (use keys from manifest output)
databricks apps init --name sales-genie \
  --features genie \
  --set "genie.genie-space.space_id=01ABCDEF12345678" \
  --set "genie.genie-space.name=Sales Assistant" \
  --set "genie.sql-warehouse.id=abc123def456" \
  --run none --profile my-profile

# 5. Local env + develop
cd sales-genie
echo "DATABRICKS_GENIE_SPACE_ID=01ABCDEF12345678" >> server/.env
npm install && npm run dev
```

**Do not hardcode** the `--set` flags from this example. Always derive them from `databricks apps manifest` output for the current template version.

## Adding Genie to an Existing App

For an existing AppKit app, use this order:

1. Confirm the app is AppKit-based and does not already register `genie()` or expose `/api/genie`.
2. Get the current plugin/resource shape from authoritative sources:
   - `databricks apps manifest --profile <PROFILE>`
   - `npx @databricks/appkit docs`
3. Add a Genie space resource in `databricks.yml` with `permission: CAN_VIEW`.
4. Inject `DATABRICKS_GENIE_SPACE_ID` through `app.yaml` and the local development env file.
5. Register `genie()` in `server/server.ts`, preserving existing plugins.
6. Add UI with `<GenieChat />` unless the user explicitly wants a custom chat experience.
7. Update smoke tests if headings or routes changed, then run the normal `databricks-apps` validation flow.

## Create-or-Reuse Space Workflow

Use this interaction pattern whenever the app needs Genie:

### Reuse Existing Space

Choose this path when the user already has a curated Genie space or wants to keep using an existing one.

1. List or discover existing Genie spaces.
2. Let the user choose one by title if there are multiple candidates.
3. Resolve the selected space ID and use it in the app wiring.

### Create New Space

Choose this path when the user does not already have a Genie space or does not want to manage one manually in the UI.

Ask for:

- a space title
- the SQL warehouse to associate with the space
- the Unity Catalog tables or views to include, using fully qualified names like `catalog.schema.table`
- optionally, a short description and a few sample questions

Start with a small table set. Genie can support larger spaces, but an initial scope of about five or fewer tables is usually easier to curate and debug.

After the space is created, wire the resulting space ID into the app resource configuration.

## Genie Space Management

### How Agents Should Help

Prefer helping the user create or discover the Genie space instead of requiring them to do it manually in the UI first.

- **Use the Databricks CLI** for space creation: `databricks genie create-space` is the simplest path.
- **Ask for tables first**: if the user wants a new space, gather the table list before asking for any Genie IDs.
- **Fall back to the Python SDK** only if the CLI does not support a required option (e.g. setting sample questions or instructions). The SDK exposes `create_space()`, `list_spaces()`, `get_space()`, and `update_space()`.

If the workspace blocks programmatic creation, explain the limitation clearly and fall back to a minimal UI creation flow.

### Discovery

Use these capabilities to avoid asking the user to manually hunt for IDs:

- `databricks genie get-space <SPACE_ID>` for validating a known space
- Genie management API `list spaces` or SDK `w.genie.list_spaces()` for enumerating available spaces

### Creating a Space

**Preferred: Databricks CLI**

```bash
databricks genie create-space \
  --title "Sales Assistant" \
  --description "Answers sales analytics questions" \
  --warehouse-id <WAREHOUSE_ID> \
  --table catalog.schema.orders \
  --table catalog.schema.customers \
  --profile <PROFILE>
```

Repeat `--table` for each Unity Catalog table or view. The command returns the space ID to use in the app configuration.

**Fallback: Python SDK**

Use the SDK when you need options the CLI does not expose (e.g. sample questions or custom instructions):

```python
import json
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
space = w.genie.create_space(
    warehouse_id="<WAREHOUSE_ID>",
    title="Sales Assistant",
    description="Answers sales analytics questions",
    serialized_space=json.dumps({
        "table_identifiers": [
            "catalog.schema.orders",
            "catalog.schema.customers"
        ],
        "instructions": "Help users explore order and customer data.",
        "sample_questions": [
            "What were total sales last quarter?",
            "Show top 10 customers by revenue"
        ]
    }),
)
print(f"Created space: {space.space_id}")
```

If the `serialized_space` format is unclear, export an existing space to see the current expected shape:

```python
existing = w.genie.get_space("<KNOWN_SPACE_ID>", include_serialized_space=True)
print(existing.serialized_space)  # Use this JSON as a template
```

### Warehouse Discovery

The agent needs a warehouse ID before creating a space. Use these commands:

```bash
# Preferred: get the workspace default
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>

# Alternative: list all warehouses and let the user pick
databricks warehouses list --profile <PROFILE>
```

## Key Files

| File | Purpose |
|------|---------|
| `databricks.yml` | Declare Genie variables and the `genie-space` app resource |
| `app.yaml` | Map `DATABRICKS_GENIE_SPACE_ID` from the `genie-space` resource |
| `server/server.ts` | Import and register the built-in `genie()` plugin |
| `server/.env` or equivalent local env file | Set `DATABRICKS_GENIE_SPACE_ID` for local development |
| `client/src/...` | Render `GenieChat` or use `useGenieChat` for custom UI |

## Configuration Reference

### Local Development Env

Set `DATABRICKS_GENIE_SPACE_ID` in the env file used by the app template for local server development. In the standard AppKit layout, that is commonly `server/.env`.

```dotenv
DATABRICKS_GENIE_SPACE_ID=<YOUR_SPACE_ID>
```

For deployment, use app resources and `valueFrom` in `app.yaml` instead of checking IDs into source control.

### `app.yaml`

Add Genie env injection next to the existing warehouse mapping:

```yaml
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: DATABRICKS_GENIE_SPACE_ID
    valueFrom: genie-space
```

The `valueFrom` name must match the resource name declared in `databricks.yml`.

### `databricks.yml`

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

Call `genie()` with no arguments. It reads `DATABRICKS_GENIE_SPACE_ID` from the environment and exposes it as the `default` space.

```typescript
import { createApp, server, genie } from "@databricks/appkit";

createApp({
  plugins: [server(), genie()],
}).catch(console.error);
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `timeout` | `number` | `120000` | Polling timeout in ms. Use `0` for no timeout |

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
      <GenieChat />
    </div>
  );
}
```

| Prop | Type | Default | Notes |
|------|------|---------|-------|
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
        <GenieChat className="flex-1" />
      </div>
    </div>
  );
}
```

### `useGenieChat` (Custom UI)

Use the hook only when the built-in component is not enough:

```tsx
import { useGenieChat } from "@databricks/appkit-ui/react";

const { messages, status, conversationId, error, sendMessage, reset } = useGenieChat();
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
  const { messages, status, sendMessage, reset } = useGenieChat();
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
- Start a new conversation when query accuracy matters. Long-lived threads can reduce answer quality.
- Prefer the built-in streaming UX. Do not bolt on custom polling unless there is a proven gap.
- Expect query result limits. If a large result looks truncated, explain that in the UI.
- Treat POST requests as rate-limited. Avoid designing retry loops that can spam the API.

## Common Mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Missing `DATABRICKS_GENIE_SPACE_ID` | Server reports Genie is not configured | Set env var in `server/.env` (local) or wire via `app.yaml` (deployed) |
| No explicit chat height | Chat collapses or renders poorly | Give the parent container a fixed height |
| Old local Genie proxy file | Duplicate routes or import confusion | Remove it and use `genie` from `@databricks/appkit` |
| Manual SSE reimplementation | Extra complexity and bugs | Use `GenieChat` or `useGenieChat` |
| Missing `whitespace-pre-wrap` in custom messages | Explanation text renders on one line | Add `whitespace-pre-wrap` to custom message content |
| Hardcoding scaffold command from memory | Wrong `--set` flags or missing resources | Always run `databricks apps manifest` first |
| Empty or malformed `serialized_space` | SDK `create_space()` fails or creates unusable space | Use the CLI instead, or use the SDK payload template above |
| Skipping warehouse discovery | No warehouse ID for space creation | Run `databricks warehouses list` or use the default warehouse command |
