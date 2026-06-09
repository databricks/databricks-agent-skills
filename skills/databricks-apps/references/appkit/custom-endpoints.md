# Custom API Endpoints

**CRITICAL**: Do NOT add custom endpoints for warehouse **SELECT** queries or read-only data retrieval. Use `config/queries/` + `useAnalyticsQuery` instead.

**CRITICAL**: Do NOT add custom endpoints for Unity Catalog file operations. Use the Files plugin instead.

When you need server-side logic that no plugin covers, extend the AppKit server in `onPluginsReady` and register Express routes with `appkit.server.extend()`.

**Writes are allowed via custom endpoints** — but pick the right backend first (see parent SKILL.md *Pick your write path first*):

- **Postgres app state** (forms, CRUD, session data) → `appkit.lakebase.query()` — [Lakebase Guide](lakebase.md)
- **Delta / Unity Catalog DML** (small scoped `INSERT`/`UPDATE`/`DELETE`/`MERGE`) → `appkit.analytics.query()` — [Warehouse Mutations](warehouse-mutations.md)
- **Large or async lakehouse writes** → [Jobs](jobs.md) plugin

Use custom endpoints ONLY for:

- **Data mutations** — Express routes in `onPluginsReady` using Lakebase or warehouse DML as above (not `useAnalyticsQuery`)
- **External APIs**: Calling Databricks APIs not covered by a dedicated plugin (MLflow, Workspace API, etc.)
- **Complex business logic**: Multi-step operations that cannot be expressed in SQL
- **File processing**: Uploads, processing, transformations (when not covered by the Files plugin)
- **Custom computations**: Operations requiring TypeScript/Node.js logic

## Before Adding Endpoints

**ALWAYS complete these checks before registering routes:**

### 1. Check AppKit Version

Read `package.json` to identify the installed `@databricks/appkit` version. Available server APIs and plugins differ across versions.

```bash
# From the project root
cat package.json | grep @databricks/appkit
```

### 2. Review Available Plugins

Check what plugins are already enabled and what server-side functionality they provide — avoid reimplementing what a plugin already handles.

```bash
# See plugin docs for the installed version
npx @databricks/appkit docs ./docs/plugins.md

# See all plugins available for a specific version
databricks apps manifest --version <VERSION> --profile <PROFILE>

# See plugins available for the default template
databricks apps manifest --profile <PROFILE>
```

**Key plugins to check for:**

- **analytics** — provides SQL warehouse execution: **reads** via `config/queries/` + `useAnalyticsQuery`; **writes** via `appkit.analytics.query()` inside custom mutation routes (see [Warehouse Mutations](warehouse-mutations.md)). Do NOT reimplement SELECT retrieval with custom endpoints.
- **lakebase** — provides Lakebase plugin for PostgreSQL CRUD (use plugin in routes, don't create raw connections)
- **genie** — provides Genie AI-powered data exploration (check before building custom natural-language-to-SQL routes)
- **files** — provides file storage and retrieval helpers (check before writing custom file upload/download routes)
- **serving** — provides model serving endpoint proxy with invoke/stream (do NOT reimplement with custom endpoints)
- **jobs** — provides Lakeflow Job triggering and monitoring (do NOT reimplement with custom endpoints)

If a plugin already covers your use case, use the plugin's API instead of writing a custom route.

If a newer version of `@databricks/appkit` has a plugin that fits the use case, prompt the user for updating.

### 3. Check Existing Routes

Read `server/server.ts` to see what routes already exist. Add new handlers inside the existing `onPluginsReady` callback rather than creating a parallel server setup.

## Server-side Pattern

Register routes inside `onPluginsReady` so plugins are initialized before the server accepts requests.

**Include the plugins your routes need** — `server()` alone is not enough for warehouse or Lakebase mutations:

| Route purpose | Plugins (minimum) |
|---------------|-------------------|
| External Databricks APIs (MLflow, Workspace) | `[server()]` |
| Delta / UC DML | `[server(), analytics({})]` — see [Warehouse Mutations](warehouse-mutations.md) |
| Postgres CRUD | `[server(), lakebase()]` — see [Lakebase](lakebase.md) |
| Trigger Lakeflow Jobs | `[server(), jobs()]` — see [Jobs](jobs.md) |

### Example: external API (no warehouse or Lakebase)

```typescript
// server/server.ts
import { createApp, server } from "@databricks/appkit";
import { getExecutionContext } from "@databricks/appkit";

await createApp({
  plugins: [server()],
  async onPluginsReady(appkit) {
    appkit.server.extend((app) => {
      // Example: Call a Databricks API (e.g. MLflow)
      app.get("/api/experiments/:experimentId", async (req, res) => {
        const { experimentId } = req.params;
        const { serviceDatabricksClient: client } = getExecutionContext();
        const response = await client.experiments.getExperiment({
          experiment_id: experimentId,
        });
        res.json(response);
      });
    });
  },
});
```

Do **not** copy a placeholder mutation that returns fake IDs — real writes must use `appkit.lakebase.query()` or `appkit.analytics.query()` as in [Lakebase Guide](lakebase.md) and [Warehouse Mutations Guide](warehouse-mutations.md).

For Lakebase CRUD routes, schema initialization, and chat persistence, see [Lakebase Guide](lakebase.md).

For Delta / Unity Catalog writes (`INSERT`, `UPDATE`, `DELETE`, `MERGE`), see [Warehouse Mutations Guide](warehouse-mutations.md).

## Client-side Pattern

Call your endpoints with `fetch` from React components:

```typescript
// client/src/components/MyComponent.tsx
import { useState, useEffect } from "react";

function MyComponent() {
  const [result, setResult] = useState(null);

  useEffect(() => {
    fetch("/api/experiments/123")
      .then((r) => r.json())
      .then(setResult)
      .catch(console.error);
  }, []);

  const handleCreate = async () => {
    // POST to your mutation route — see Lakebase or Warehouse Mutations guides for server handlers
    await fetch("/api/books", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Example" }),
    });
  };

  return <div>{/* component JSX */}</div>;
}
```

## Decision Tree for Data Operations

1. **Need to display data from SQL?**
   - **Chart or Table?** → Use visualization components (`BarChart`, `LineChart`, `DataTable`, etc.)
   - **Custom display (KPIs, cards, lists)?** → Use `useAnalyticsQuery` hook
   - **Never** add custom endpoints for SQL SELECT statements against the warehouse

2. **Need to call a Databricks API?**
   - Serving endpoints → use `serving()` plugin (see [Model Serving Guide](model-serving.md))
   - Jobs → use `jobs()` plugin (see [Jobs Guide](jobs.md))
   - MLflow, Workspace API, other APIs → custom endpoint via `onPluginsReady`

3. **Need to modify data?** → Custom endpoint in `onPluginsReady`
   - **Delta / UC table (SQL warehouse)** → `appkit.analytics.query()` with fixed SQL + Zod validation — see [Warehouse Mutations](warehouse-mutations.md)
   - **Postgres app state** → `appkit.lakebase.query()` — see [Lakebase](lakebase.md)
   - **Large / async lakehouse writes** → `jobs()` plugin — see [Jobs](jobs.md)
   - Multi-step transactions or business logic with side effects

4. **Need non-SQL custom logic?** → Custom endpoint in `onPluginsReady`
   - File processing
   - External API calls
   - Complex computations in TypeScript

**Summary:**

- ✅ SQL **reads** → Visualization components or `useAnalyticsQuery`
- ✅ Delta / UC **writes** → custom endpoint + `appkit.analytics.query()` — see [Warehouse Mutations](warehouse-mutations.md)
- ✅ Databricks APIs without a plugin → custom endpoint via `onPluginsReady`
- ✅ Postgres app mutations → Lakebase routes — see [Lakebase](lakebase.md)
- ❌ SQL warehouse **SELECT** in custom endpoints (NEVER — use `config/queries/`)
- ❌ Files operations → custom endpoints (NEVER do this — use Files plugin)
