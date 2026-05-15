# AppKit Genie Guide

Use Genie when your app needs a **natural language query interface** over Unity Catalog tables. For analytics dashboards, use `config/queries/` instead. For persistent storage, use Lakebase.

## When to Use

| Pattern | Use Case | Data Source |
|---------|----------|-------------|
| Analytics | Read-only dashboards, charts, KPIs | SQL Warehouse |
| Lakebase | CRUD operations, persistent state, forms | PostgreSQL (Lakebase) |
| Model Serving | Chat, AI features, model inference | Serving Endpoint |
| Genie | Natural language queries over tables | Genie Space → SQL Warehouse |
| Multiple | Combine plugins as needed | Mix of the above |

## Architecture

```text
User (browser) -> AppKit genie plugin (/api/genie/...) -> Databricks Genie API -> SQL Warehouse
               <- SSE stream (status, message_result, query_result) <-
```

The built-in `genie()` plugin from `@databricks/appkit` proxies requests via SSE streaming. It reads the space ID from the `DATABRICKS_GENIE_SPACE_ID` env var. Call `genie()` with no arguments.

## Genie Space Creation

The `databricks genie create-space` command takes two positional arguments: `WAREHOUSE_ID` and `SERIALIZED_SPACE` (a JSON string).

```bash
databricks genie create-space <WAREHOUSE_ID> \
  '{"version":2,"data_sources":{"tables":[{"identifier":"catalog.schema.orders"},{"identifier":"catalog.schema.customers"}]}}' \
  --title "Sales Assistant" \
  --description "Answers sales analytics questions" \
  --profile <PROFILE>
```

The JSON must include `version` and `data_sources.tables` with each table as `{"identifier":"catalog.schema.table"}`. Optional flags: `--title`, `--description`, `--parent-path`.

To discover the full serialized space format (including optional fields), export an existing space:

```bash
databricks genie get-space <SPACE_ID> --include-serialized-space --profile <PROFILE>
```

Discover warehouse ID with:

```bash
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>
```

## Scaffolding a New Genie App

```bash
# 1. Discover warehouse
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>

# 2. Create Genie space (see syntax above)
databricks genie create-space <WAREHOUSE_ID> '<SERIALIZED_SPACE_JSON>' \
  --title "My Space" --profile <PROFILE>

# 3. Check manifest for genie plugin keys
databricks apps manifest --profile <PROFILE>

# 4. Scaffold (derive --set keys from manifest output)
databricks apps init --name <APP_NAME> --features genie \
  --set "genie.<resourceKey>.<field>=<SPACE_ID>" \
  --run none --profile <PROFILE>

# 5. Set local env + develop
cd <APP_NAME>
echo "DATABRICKS_GENIE_SPACE_ID=<SPACE_ID>" >> server/.env
npm install && npm run dev
```

**Do not guess** `--set` flags — always derive from `databricks apps manifest`.

## Adding Genie to an Existing App

**`databricks.yml`** — add Genie variables and resource:

```yaml
variables:
  genie_space_id:
    description: Genie Space ID
  genie_space_name:
    description: Genie Space name

resources:
  apps:
    app:
      resources:
        # ... existing resources ...
        - name: genie-space
          genie_space:
            name: ${var.genie_space_name}
            space_id: ${var.genie_space_id}
            permission: CAN_RUN

targets:
  default:
    variables:
      genie_space_id: <space_id>
      genie_space_name: <space_name>
```

**`app.yaml`** — add env injection:

```yaml
env:
  # ... existing env vars ...
  - name: DATABRICKS_GENIE_SPACE_ID
    valueFrom: genie-space
```

**`server/server.ts`** — register the plugin:

```typescript
import { createApp, server, analytics, genie } from "@databricks/appkit";

createApp({
  plugins: [server(), analytics(), genie()],
}).catch(console.error);
```

Preserve existing plugins and add `genie()` to the array.

**`server/.env`** — for local development:

```dotenv
DATABRICKS_GENIE_SPACE_ID=<YOUR_SPACE_ID>
```

**Frontend** — add the chat component:

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

Update smoke tests if headings or routes changed, then `databricks apps validate`.

For advanced Genie plugin usage, see `npx @databricks/appkit docs ./docs/plugins/genie.md`.

## Multi-Space Deployment

For the `spaces` map API, `GenieChat alias` prop, and `useGenieChat` hook, see `npx @databricks/appkit docs ./docs/plugins/genie.md`.

This section covers the **deployment-specific patterns** for multi-space Genie apps (databricks.yml, app.yaml, stale conversation cleanup).

**databricks.yml** — add one variable + resource per space, plus target-level values:

```yaml
variables:
  genie_space_id:
    description: Default Genie space ID (required by AppKit)
  genie_space_name:
    description: Default Genie space name
  genie_space_sales_id:
    description: Sales Genie space ID
  genie_space_support_id:
    description: Support Genie space ID

resources:
  apps:
    app:
      user_api_scopes:
        - dashboards.genie
      resources:
        - name: genie-space
          genie_space:
            name: ${var.genie_space_name}
            space_id: ${var.genie_space_id}
            permission: CAN_RUN
        - name: genie-space-sales
          genie_space:
            name: genie-space-sales
            space_id: ${var.genie_space_sales_id}
            permission: CAN_RUN
        - name: genie-space-support
          genie_space:
            name: genie-space-support
            space_id: ${var.genie_space_support_id}
            permission: CAN_RUN

targets:
  default:
    variables:
      genie_space_id: <any-space-id>
      genie_space_name: <space-name>
      genie_space_sales_id: <sales-space-id>
      genie_space_support_id: <support-space-id>
```

**app.yaml** — keep `DATABRICKS_GENIE_SPACE_ID` (AppKit validates it on startup). Add one `valueFrom` per UI space:

```yaml
env:
  - name: DATABRICKS_GENIE_SPACE_ID
    valueFrom: genie-space
  - name: DATABRICKS_GENIE_SPACE_SALES
    valueFrom: genie-space-sales
  - name: DATABRICKS_GENIE_SPACE_SUPPORT
    valueFrom: genie-space-support
```

**Critical gotcha**: `DATABRICKS_GENIE_SPACE_ID` must always be set — AppKit validates it on startup even when using a custom `spaces` map.

**Build version stamp** — stamp every build so the page can detect a new deployment and clear stale conversation state:

```typescript
// client/vite.config.ts
export default defineConfig({
  // ... existing config ...
  define: {
    "import.meta.env.VITE_APP_VERSION": JSON.stringify(Date.now().toString()),
  },
});
```

**Stale conversation cleanup** — `GenieChat` stores conversation IDs in URLs and localStorage that become stale across space switches or redeployments:

```typescript
function clearConversationUrl() {
  const url = new URL(window.location.href);
  url.searchParams.delete("conversationId");
  window.history.replaceState({}, "", url.toString());
}

function initAlias(): string {
  const buildVersion = import.meta.env.VITE_APP_VERSION ?? "dev";
  if (localStorage.getItem("appkit:genie:version") !== buildVersion) {
    const savedAlias = localStorage.getItem("appkit:genie:alias");
    Object.keys(localStorage)
      .filter((k) => k.startsWith("appkit:genie:"))
      .forEach((k) => localStorage.removeItem(k));
    localStorage.setItem("appkit:genie:version", buildVersion);
    if (savedAlias) localStorage.setItem("appkit:genie:alias", savedAlias);
    clearConversationUrl();
  }
  // SPACES: array of {alias, spaceId} defined in your component
  return localStorage.getItem("appkit:genie:alias") ?? SPACES[0]?.alias ?? "";
}
```

## Frontend

**For full component API**: run `npx @databricks/appkit docs "GenieChat"`.

The `GenieChat` component handles SSE streaming, conversation state, history replay, and query result rendering. For custom UI, use the `useGenieChat` hook — see `npx @databricks/appkit docs "useGenieChat"`.

Common anti-patterns:

| Mistake | Why it's wrong | What to do |
|---------|---------------|------------|
| No explicit height on parent container | Chat collapses to zero height | Give the parent a fixed height (`style={{ height: 600 }}` or CSS class) |
| Old local Genie proxy file | Duplicate routes, import confusion | Remove it — use `genie` from `@databricks/appkit` |
| Manual SSE reimplementation | Extra complexity, bugs | Use `GenieChat` or `useGenieChat` |
| Missing `whitespace-pre-wrap` in custom UI | Explanation text renders on one line | Add `whitespace-pre-wrap` to message content |

## HTTP Endpoints

The plugin mounts SSE endpoints under `/api/genie`:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/genie/:alias/messages` | `POST` | Send a message and stream results |
| `/api/genie/:alias/conversations/:conversationId` | `GET` | Replay an existing conversation |

### SSE Event Types

| Event | Payload | Description |
|-------|---------|-------------|
| `message_start` | `{ conversationId, messageId, spaceId }` | IDs assigned |
| `status` | `{ status: "ASKING_AI" \| "EXECUTING_QUERY" \| ... }` | Progress |
| `message_result` | `{ content, attachments }` | Final message |
| `query_result` | `{ attachmentId, statementId, data }` | Tabular results |
| `error` | `{ error }` | Error details |

### Attachment Types

| Key | Meaning |
|-----|---------|
| `query` | Generated SQL plus metadata |
| `text` | Natural-language explanation |
| `suggestedQuestions` | Follow-up prompts |

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| `create-space` fails with "Cannot find field" | Wrong `serialized_space` JSON format | Use `{"version":2,"data_sources":{"tables":[{"identifier":"..."}]}}` — export an existing space to verify |
| `plugin "genie" has no resource with key "..."` | Wrong `--set` flags during scaffold | Always derive resource keys from `databricks apps manifest` |
| Chat collapses or renders poorly | No explicit height on container | Give the parent a fixed height |
| Duplicate routes or import confusion | Old local Genie proxy file | Remove it — use `genie` from `@databricks/appkit` |
| `does not have required scopes: genie` | Missing API scope | Confirm `user_api_scopes` includes `dashboards.genie` in `databricks.yml` and redeploy |
| Genie space not found | Wrong space ID | Verify space ID matches the value on the Genie space **About** tab |
| `valueFrom` mismatch | `app.yaml` value doesn't match `databricks.yml` | `valueFrom` in `app.yaml` must exactly match the resource `name` in `databricks.yml` |
