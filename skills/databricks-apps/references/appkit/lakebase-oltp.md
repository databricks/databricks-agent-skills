# Lakebase OLTP (App-owned CRUD)

**Capability:** `writes_oltp` — Postgres as system of record for forms, CRUD, sessions, app state.

**Pattern selection:** [Data Patterns](data-patterns.md). **Synced lakehouse reads** (read-only Delta replicas) are a different pattern — [Lakebase Synced Reads](lakebase-synced-reads.md).

For warehouse dashboards, use `config/queries/` (`reads_warehouse`). Never use `useAnalyticsQuery` for Lakebase data.

> **Agentic mode:** the Lakebase project/branch/database already exist and `LAKEBASE_ENDPOINT` / `PG*` are injected. **Skip** the *Scaffolding*, *Adding Lakebase to an Existing App*, and `server/.env` sections, and the **deploy-first** rule — deploy and schema ownership are handled externally, and `npm run dev` hits the live database. Just write the schema init + CRUD routes in `onPluginsReady`. See [Environments](environments.md).

## Scaffolding

**Scaffolding is the fastest way to get started.** If you already have an app, see *Adding Lakebase to an Existing App* below.

**Always derive `--set` keys from the manifest** — do not guess field names:

```bash
databricks apps manifest --profile <PROFILE>
```

For the `lakebase` plugin, the required `postgres` resource has **three** user-supplied fields: `project`, `branch`, and `database`. All three must appear as `--set` flags — omitting `lakebase.postgres.project` causes init to fail.

Discover values (after creating a project via the `databricks-lakebase` skill):

```bash
databricks postgres list-projects --profile <PROFILE>                    # → lakebase.postgres.project
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>   # → lakebase.postgres.branch
databricks postgres list-databases projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>  # → lakebase.postgres.database
```

Use the `.name` field from each list command as the `--set` value.

**Lakebase only** (no analytics SQL warehouse):
```bash
databricks apps init --name <NAME> --features lakebase \
  --set "lakebase.postgres.project=<PROJECT_NAME>" \
  --set "lakebase.postgres.branch=<BRANCH_NAME>" \
  --set "lakebase.postgres.database=<DATABASE_NAME>" \
  --run none --profile <PROFILE>
```

**Both Lakebase and analytics**:
```bash
databricks apps init --name <NAME> --features analytics,lakebase \
  --set "analytics.sql-warehouse.id=<WAREHOUSE_ID>" \
  --set "lakebase.postgres.project=<PROJECT_NAME>" \
  --set "lakebase.postgres.branch=<BRANCH_NAME>" \
  --set "lakebase.postgres.database=<DATABASE_NAME>" \
  --run none --profile <PROFILE>
```

Where `<PROJECT_NAME>`, `<BRANCH_NAME>`, and `<DATABASE_NAME>` are full resource paths (e.g. `projects/<PROJECT_ID>`, `projects/<PROJECT_ID>/branches/<BRANCH_ID>`, `projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DB_ID>`).

> For multi-environment deployments (dev/prod), use `variables:` and `targets:` blocks in `databricks.yml` — see the **`databricks-dabs`** skill for patterns.

**Naming conventions:** Use domain names for user-facing code (`ItemsPage.tsx`, `/api/items`, `item-routes.ts`). Keep `lakebase` naming only for infrastructure config (`lakebase()` plugin, `LAKEBASE_ENDPOINT`, `postgres` app resource).

**Get resource names** (if you have an existing project):
```bash
# List projects → use the name field
databricks postgres list-projects --profile <PROFILE>
# List branches → use the name field of a READY branch
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>
# List databases → use the name field
databricks postgres list-databases projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

## Adding Lakebase to an Existing App

**`databricks.yml`** — add Lakebase variables and resource:

```yaml
variables:
  lakebase_branch:
    description: Lakebase branch resource name
  lakebase_database:
    description: Lakebase database resource name

resources:
  apps:
    app:
      resources:
        # ... existing resources ...
        - name: postgres
          postgres:
            branch: ${var.lakebase_branch}
            database: ${var.lakebase_database}

targets:
  default:
    variables:
      lakebase_branch: projects/<PROJECT_ID>/branches/<BRANCH_ID>
      lakebase_database: projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DB_ID>
```

Use the `databricks-lakebase` skill to create a Lakebase project and discover branch/database resource names.

For per-user connections (OBO/RLS), also add `postgres` to `user_api_scopes` — see `npx @databricks/appkit docs ./docs/plugins/lakebase.md` for OBO setup.

**`app.yaml`** — add env injection:

```yaml
env:
  # ... existing env vars ...
  - name: LAKEBASE_ENDPOINT
    valueFrom: postgres
```

Other Lakebase env vars (`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE`) are auto-injected by the platform when the `postgres` resource is configured. Only `LAKEBASE_ENDPOINT` must be set explicitly.

**`server/server.ts`** — register the plugin:

```typescript
import { createApp, server, analytics, lakebase } from "@databricks/appkit";

await createApp({
  plugins: [server(), analytics(), lakebase()],
});
```

Preserve existing plugins and add `lakebase()` to the array.

**`server/.env`** — for local development:

```dotenv
PGHOST=<host from endpoint>
PGPORT=5432
PGDATABASE=<your database name>
PGSSLMODE=require
LAKEBASE_ENDPOINT=projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID>
```

Get connection details from `databricks postgres get-endpoint`. See *Local Development* below for the full workflow.

Deploy the app before local development — see *Local Development > Prerequisites* below. Update smoke tests if headings or routes changed, then `databricks apps validate`.

## Project Structure (after `databricks apps init --features lakebase`)

```
my-app/
├── server/
│   ├── server.ts                          # Entry — calls setup from onPluginsReady
│   └── routes/lakebase/
│       └── todo-routes.ts                 # ⚠️ Starter CRUD — replace for your domain
├── client/src/
│   ├── App.tsx                            # Layout + nav (may include /lakebase route)
│   └── pages/lakebase/
│       └── LakebasePage.tsx               # ⚠️ Starter todo UI — replace for your domain
├── tests/smoke.spec.ts                    # ⚠️ Asserts "Todo List" — update for your UI
├── databricks.yml                         # Lakebase postgres resource wiring
├── app.yaml                               # Manifest with database resource declaration
└── package.json                           # Includes @databricks/lakebase dependency
```

Note: **No `config/queries/` directory** — Lakebase apps use server-side `appkit.lakebase.query()` calls, not SQL files.

## What the scaffold gives you (replace, don't keep)

`databricks apps init --features lakebase` generates a **working todo list demo**, not your final app. Treat every file below as **starter code to replace** once you know your domain (reading log, inventory, registrations, etc.).

| Scaffold artifact | What it is | What to do |
|-------------------|------------|------------|
| `server/routes/lakebase/todo-routes.ts` | Sample CRUD for `app.todos` + hand-written `AppKitWithLakebase` | Rename/replace (e.g. `book-routes.ts`), change table/schema/API paths to your domain |
| `client/src/pages/lakebase/LakebasePage.tsx` | Todo list UI wired to `/api/lakebase/todos` | Replace with your page (e.g. `ReadingLogPage.tsx`) and your API paths |
| `client/src/App.tsx` | Generic home page + nav link to `/lakebase` | Simplify or rewire — many CRUD apps use the domain page as `/` |
| `tests/smoke.spec.ts` | Expects headings like "Todo List" and todo-specific selectors | Update **every** assertion to match your UI before `databricks apps validate` |
| `AppKitWithLakebase` interface | Local typing workaround in `*-routes.ts` | **Not official AppKit API** — see *Lakebase route modules — typing* below |

**Agent checklist after init:**

1. **Decide your domain** (table name, API prefix, page title) — use domain names in routes and UI (`/api/books`, `BooksPage.tsx`), not "todo" or generic "lakebase" labels in user-facing code.
2. **Replace backend** — schema (`app.<your_table>`), Zod validators, Express routes under a domain path (e.g. `/api/books`, not `/api/lakebase/todos`).
3. **Replace frontend** — form, list, filters; point `fetch()` at your new API routes.
4. **Update smoke tests** — assert your headings, buttons, and stable empty-state copy. Avoid asserting dynamic Lakebase content (e.g. "Your shelf is empty") if validate runs without a live database.
5. **Remove dead scaffold files** — delete `todo-routes.ts` / `LakebasePage.tsx` after replacement so agents don't copy leftover patterns.

Do **not** ship a custom app that still exposes "Todo List" in the UI or `/api/lakebase/todos` unless the user explicitly asked for a todo app.

## Lakebase route modules — typing

Inside `server.ts`, `onPluginsReady(appkit)` is already fully typed via AppKit's internal `PluginMap<T>` — no manual interface needed:

```typescript
await createApp({
  plugins: [lakebase(), server()],
  async onPluginsReady(appkit) {
    // appkit.lakebase.query(...) and appkit.server.extend(...) are typed here
    await setupBookRoutes(appkit);
  },
});
```

The scaffold's `AppKitWithLakebase` in `todo-routes.ts` is **not** exported by `@databricks/appkit`. It exists because route setup was split into a separate file and `PluginMap` is not part of the public package exports. Agents often copy it and treat it as required AppKit surface area — **don't**.

### Recommended patterns

**Option A — Inline in `server.ts` (simplest)**

Register schema init and routes directly in `onPluginsReady`. No shared type, no duplicate interface.

**Option B — Extract routes with generic inference (recommended for larger apps)**

Pass `appkit` from `onPluginsReady` into a setup function. TypeScript infers `T` from the call site — no `appkit-types.ts`, no duplicated plugin tuple, no hand-trimmed interface:

```typescript
// server/routes/lakebase/book-routes.ts
import type { Application } from "express";

export async function setupBookRoutes<
  T extends {
    lakebase: {
      query(text: string, params?: unknown[]): Promise<{ rows: Record<string, unknown>[] }>;
    };
    server: { extend(fn: (app: Application) => void): void };
  },
>(appkit: T) {
  await appkit.lakebase.query("CREATE SCHEMA IF NOT EXISTS app");
  appkit.server.extend((app) => { /* ... */ });
}
```

```typescript
// server/server.ts — plugins inline; T inferred at the call site
await createApp({
  plugins: [lakebase(), server()],
  async onPluginsReady(appkit) {
    await setupBookRoutes(appkit); // appkit is fully typed here
  },
});
```

Keep `plugins: [lakebase(), server()]` inline in `server.ts` (same array as production). If AppKit later exports `PluginMap` / `AppKitHandle`, prefer that over widening the generic constraint.

**Option C — Minimal local interface (fallback only)**

If generics are not viable, a narrow app-local type is acceptable — rename it (e.g. `RouteSetupContext`) and comment that it is **not** AppKit API. Do **not** add a separate `appkit-types.ts` that re-declares the plugin list.

### Anti-patterns

```typescript
// ❌ Copy scaffold's AppKitWithLakebase — looks like official API
interface AppKitWithLakebase { /* ... */ }

// ❌ appkit-types.ts + exported appPlugins tuple — duplicates server.ts, drifts when plugins change
export const appPlugins = [lakebase(), server()] as const;

// ❌ Double-assert to satisfy a local interface — appkit lint forbids this
setupBookRoutes(appkit as unknown as AppKitWithLakebase);
```

Prefer Option A or B. When replacing scaffold routes, **rename** any local interface if you keep Option C — do not leave `AppKitWithLakebase` in a non-todo app.

## Lakebase Plugin API

Scaffolding with `--features lakebase` (see above) generates this pattern. Access Lakebase through the plugin handle returned by `createApp()`:

```typescript
import { createApp, lakebase } from "@databricks/appkit";

const appkit = await createApp({
  plugins: [lakebase()],
});

// Query via the plugin handle — handles pooling and token refresh automatically
const result = await appkit.lakebase.query("SELECT * FROM users WHERE id = $1", [userId]);
```

The `lakebase()` plugin auto-configures from platform-injected env vars at deploy time. No manual pool setup needed.

## Environment Variables (auto-set when deployed with database resource)

| Variable | Description |
|----------|-------------|
| `PGHOST` | Lakebase hostname |
| `PGPORT` | Port (default 5432) |
| `PGDATABASE` | Database name |
| `PGUSER` | Service principal client ID |
| `PGSSLMODE` | SSL mode (`require`) |
| `LAKEBASE_ENDPOINT` | Endpoint resource path |

## CRUD Routes Pattern

Always use server-side routes for Lakebase operations — do NOT call `appkit.lakebase.query()` from the client. Use `onPluginsReady` to initialize the schema and register Express routes:

```typescript
// server/server.ts
import { createApp, server, lakebase } from "@databricks/appkit";
import { z } from 'zod';

await createApp({
  plugins: [server(), lakebase()],
  async onPluginsReady(appkit) {
    // Schema init (runs once before server accepts requests)
    await appkit.lakebase.query(`
      CREATE SCHEMA IF NOT EXISTS app_data;
      CREATE TABLE IF NOT EXISTS app_data.items (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
      );
    `);

    // CRUD routes via Express
    appkit.server.extend((app) => {
      app.get('/api/items', async (_req, res) => {
        const { rows } = await appkit.lakebase.query(
          "SELECT * FROM app_data.items ORDER BY created_at DESC LIMIT 100"
        );
        res.json(rows);
      });

      app.post('/api/items', async (req, res) => {
        const parsed = z.object({ name: z.string().min(1) }).safeParse(req.body);
        if (!parsed.success) { res.status(400).json({ error: 'Invalid input' }); return; }
        const { rows } = await appkit.lakebase.query(
          "INSERT INTO app_data.items (name) VALUES ($1) RETURNING *",
          [parsed.data.name]
        );
        res.status(201).json(rows[0]);
      });

      app.delete('/api/items/:id', async (req, res) => {
        const id = parseInt(req.params.id, 10);
        if (isNaN(id)) { res.status(400).json({ error: 'Invalid id' }); return; }
        await appkit.lakebase.query("DELETE FROM app_data.items WHERE id = $1", [id]);
        res.status(204).send();
      });
    });
  },
});
```

> **Deploy first!** The Service Principal must create and own the schema before local development. See [Lifecycle: First deploy](lifecycle.md#first-deploy) and **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps**.

## Schema Initialization

**Always create a custom schema** — the Service Principal cannot access any existing schemas (including `public`). It must create the schema itself to become its owner. See **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps** for the full permission model and deploy-first workflow. Initialize tables inside the `onPluginsReady` callback before registering routes (see CRUD pattern above):

```typescript
// Inside onPluginsReady — runs once at startup before handling requests
await appkit.lakebase.query(`
  CREATE SCHEMA IF NOT EXISTS app_data;
  CREATE TABLE IF NOT EXISTS app_data.items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
`);
```

## ORM Integration (Optional)

The plugin exposes the raw `pg.Pool` via `appkit.lakebase.pool` — works with any PostgreSQL library:

```typescript
// Drizzle ORM
import { drizzle } from "drizzle-orm/node-postgres";
const db = drizzle(appkit.lakebase.pool);

// Prisma (with @prisma/adapter-pg)
import { PrismaPg } from "@prisma/adapter-pg";
const adapter = new PrismaPg(appkit.lakebase.pool);
const prisma = new PrismaClient({ adapter });
```

For ORM-compatible config: `appkit.lakebase.getOrmConfig()`.

## Chat Persistence Pattern

Save AI chat conversations to Lakebase so users can resume sessions and scroll full message history.

**Schema** — create in a separate `chat` schema (not `app`) so the deploy-first ownership model stays clean:

```sql
CREATE SCHEMA IF NOT EXISTS chat;

CREATE TABLE IF NOT EXISTS chat.chats (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  title TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat.messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id UUID NOT NULL REFERENCES chat.chats(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_id_created_at
  ON chat.messages(chat_id, created_at);
```

**Bootstrap** — run setup in `onPluginsReady` so tables exist before the server accepts requests:

```typescript
await createApp({
  plugins: [server(), lakebase()],
  async onPluginsReady(appkit) {
    await setupChatTables(appkit);
    // then register routes via appkit.server.extend(...)
  },
});
```

**Persistence helpers** — use parameterized queries:

```typescript
export async function createChat(appkit, input: { userId: string; title: string }) {
  const result = await appkit.lakebase.query(
    `INSERT INTO chat.chats (user_id, title) VALUES ($1, $2)
     RETURNING id, user_id, title, created_at, updated_at`,
    [input.userId, input.title],
  );
  return result.rows[0];
}

export async function appendMessage(appkit, input: { chatId: string; role: string; content: string }) {
  const result = await appkit.lakebase.query(
    `INSERT INTO chat.messages (chat_id, role, content) VALUES ($1, $2, $3)
     RETURNING id, chat_id, role, content, created_at`,
    [input.chatId, input.role, input.content],
  );
  return result.rows[0];
}
```

**User identity**: In deployed apps, use `req.header("x-forwarded-email")` (injected by the Databricks Apps platform proxy; for off-platform deployments, use your own auth middleware). For local dev, hardcode a test user ID.

**History endpoints**:
- `GET /api/chats` — list chats for current user
- `GET /api/chats/:chatId/messages` — load ordered history
- `DELETE /api/chats/:chatId` — delete chat (messages cascade)

**AI SDK v6 integration**: Use `setMessages()` from `useChat` return value for history loading (NOT `initialMessages`). To read response headers like `X-Chat-Id`, pass a custom `fetch` wrapper on the `TextStreamChatTransport` constructor.

## Key Differences from Analytics Pattern

| | Analytics | Lakebase |
|--|-----------|---------|
| SQL dialect | Databricks SQL (Spark SQL) | Standard PostgreSQL |
| Query location | `config/queries/*.sql` files | `appkit.lakebase.query()` in Express routes |
| Data retrieval | `useAnalyticsQuery` hook | Express route via `server.extend()` |
| Date functions | `CURRENT_TIMESTAMP()`, `DATEDIFF(DAY, ...)` | `NOW()`, `AGE(...)` |
| Auto-increment | N/A | `SERIAL` or `GENERATED ALWAYS AS IDENTITY` |
| Insert pattern | N/A | `INSERT ... VALUES ($1) RETURNING *` |
| Params | Named (`:param`) | Positional (`$1, $2, ...`) |

**NEVER use `useAnalyticsQuery` for Lakebase data** — it queries the SQL warehouse, not Lakebase.
**NEVER put Lakebase SQL in `config/queries/`** — those files are only for warehouse queries.

## Local Development

### Prerequisites (MUST verify before local development)

**This applies when your Databricks App uses Lakebase.** Run this check before any local development:

```bash
databricks apps get <APP_NAME> --profile <PROFILE>
```

Check the response for the `active_deployment` field. If it exists with `status.state` of `SUCCEEDED`, the app has been deployed. If `active_deployment` is missing, the app has never been deployed:
1. **STOP** — do not proceed with local development
2. **First deploy** (app not in workspace): `databricks bundle deploy -t <TARGET> --profile <PROFILE>`, then `databricks apps deploy -t <TARGET> --profile <PROFILE>`
3. Wait for deployment to complete, then continue

For apps that already have `active_deployment`, use `databricks apps deploy` only. See [Lifecycle](lifecycle.md).

If you skip this step, the Service Principal won't own the database schema. You'll create schemas under your credentials that the SP **cannot access** after deployment. See **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps** for the full workflow and recovery steps.

Lakebase project creators already have database access after the first deploy. Collaborators need `databricks_superuser` granted by the project creator via Branch Overview.

> **Project-owner note:** If you are the Lakebase project owner, `databricks_create_role` may fail with "role already exists" and `GRANT databricks_superuser` may fail with "permission denied to grant role" — both errors are safe to ignore; the project owner already has the necessary access.

The Lakebase env vars (`PGHOST`, `PGDATABASE`, etc.) are auto-set only when deployed. For local development, get the connection details from your endpoint and set them manually:

```bash
# Get endpoint connection details
databricks postgres get-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  --profile <PROFILE>
```

Then create `server/.env` with the values from the endpoint response:

```
PGHOST=<host from endpoint>
PGPORT=5432
PGDATABASE=<your database name>
PGUSER=<your service principal client ID>
PGSSLMODE=require
LAKEBASE_ENDPOINT=projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID>
```

Load `server/.env` in your dev server (e.g. via `dotenv` or `node --env-file=server/.env`). Never commit `.env` files — add `server/.env` to `.gitignore`.

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| `permission denied for schema public` | SP cannot access `public` schema | Create custom schema: `CREATE SCHEMA IF NOT EXISTS app_data` and qualify all table names with `app_data.` |
| `permission denied for schema <name>` | Schema was created by another role (e.g. you ran locally before deploying) | Schema owned by wrong role. To preserve data: export first (`pg_dump` or temp schema copy). **Ask the user before dropping.** Then drop + redeploy. See **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps** for full steps. |
| Works locally but `permission denied` after deploy | Local credentials created the schema; the SP cannot access schemas it does not own | Schema owned by wrong role — see row above for export + drop + redeploy steps |
| `connection refused` | Pool not connected or wrong env vars | Check `PGHOST`, `PGPORT`, `LAKEBASE_ENDPOINT` are set |
| `relation "X" does not exist` | Tables not initialized | Run `CREATE TABLE IF NOT EXISTS` at startup |
| App builds but pool fails at runtime | Env vars not set locally | Set vars in `server/.env` — see Local Development above |
