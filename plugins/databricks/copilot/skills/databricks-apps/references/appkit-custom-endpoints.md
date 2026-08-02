# Custom API Endpoints

**CRITICAL**: Do NOT add custom endpoints for SQL queries or warehouse data retrieval. Use `config/queries/` + `useAnalyticsQuery` instead.

**CRITICAL**: Do NOT add custom endpoints for Unity Catalog file operations. Use the Files plugin instead.

When you need server-side logic that no plugin covers, extend the AppKit server in `onPluginsReady` and register Express routes with `appkit.server.extend()`.

Use custom endpoints ONLY for:

- **Mutations**: Creating, updating, or deleting data (INSERT, UPDATE, DELETE)
- **External APIs**: Calling Databricks APIs not covered by a dedicated plugin (MLflow, Workspace API, etc.)
- **Complex business logic**: Multi-step operations that cannot be expressed in SQL
- **File processing**: Uploads, processing, transformations (when not covered by the Files plugin)
- **Custom computations**: Operations requiring TypeScript/Node.js logic

## Contents

- [Before Adding Endpoints](#before-adding-endpoints)
  - [1. Check AppKit Version](#1-check-appkit-version)
  - [2. Review Available Plugins](#2-review-available-plugins)
  - [3. Check Existing Routes](#3-check-existing-routes)
- [Server-side Pattern](#server-side-pattern)
- [Client-side Pattern](#client-side-pattern)
- [Decision Tree for Data Operations](#decision-tree-for-data-operations)

---

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

- **analytics** — provides SQL warehouse query execution (do NOT reimplement with custom endpoints)
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

Register routes inside `onPluginsReady` so plugins are initialized before the server accepts requests:

```typescript
// server/server.ts
import { createApp, server } from "@databricks/appkit";
import { getExecutionContext } from "@databricks/appkit";
import { z } from "zod";

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

      // Example: Mutation
      app.post("/api/records", async (req, res) => {
        const parsed = z.object({ name: z.string() }).safeParse(req.body);
        if (!parsed.success) {
          res.status(400).json({ error: "Invalid input" });
          return;
        }
        // Custom logic here
        res.status(201).json({ success: true, id: 123 });
      });
    });
  },
});
```

For Lakebase CRUD routes, schema initialization, and chat persistence, see appkit-lakebase.

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
    await fetch("/api/records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "test" }),
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
   - Serving endpoints → use `serving()` plugin (see appkit-model-serving)
   - Jobs → use `jobs()` plugin (see appkit-jobs)
   - MLflow, Workspace API, other APIs → custom endpoint via `onPluginsReady`

3. **Need to modify data?** → Custom endpoint in `onPluginsReady`
   - INSERT, UPDATE, DELETE operations
   - Multi-step transactions
   - Business logic with side effects

4. **Need non-SQL custom logic?** → Custom endpoint in `onPluginsReady`
   - File processing
   - External API calls
   - Complex computations in TypeScript

**Summary:**

- ✅ SQL queries → Visualization components or `useAnalyticsQuery`
- ✅ Databricks APIs without a plugin → custom endpoint via `onPluginsReady`
- ✅ Data mutations → custom endpoint via `onPluginsReady`
- ❌ SQL warehouse queries → custom endpoints (NEVER do this)
- ❌ Files operations → custom endpoints (NEVER do this — use Files plugin)
