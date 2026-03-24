# tRPC for Custom Endpoints

**CRITICAL**: Do NOT use tRPC for SQL queries or data retrieval. Use `config/queries/` + `useAnalyticsQuery` instead.

**CRITICAL**: Do NOT use tRPC for accessing Unity Catalog and File operations. Use the Files plugin instead.

Use tRPC ONLY for:

- **Mutations**: Creating, updating, or deleting data (INSERT, UPDATE, DELETE)
- **External APIs**: Calling Databricks APIs (serving endpoints, jobs, MLflow, etc.)
- **Complex business logic**: Multi-step operations that cannot be expressed in SQL
- **File operations**: File uploads, processing, transformations
- **Custom computations**: Operations requiring TypeScript/Node.js logic

## Before Writing New Routes

**ALWAYS complete these checks before adding tRPC routes:**

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

- **analytics** — provides SQL warehouse query execution (do NOT reimplement with tRPC)
- **lakebase** — provides `createLakebasePool` for PostgreSQL CRUD (use pool in tRPC routes, don't create raw connections)
- **genie** — provides Genie AI-powered data exploration (check before building custom natural-language-to-SQL routes)
- **files** — provides file storage and retrieval helpers (check before writing custom file upload/download routes)

If a plugin already covers your use case, use the plugin's API instead of writing a custom tRPC route.

If there's a newer version of `@databricks/appkit` has a plugin that fits the use-case.
Prompt the user for updating.

### 3. Check Existing Routes

Read `server/server.ts` (or `server/trpc.ts`) to see what routes already exist. Extend the existing router rather than creating a parallel one.

## Server-side Pattern

```tsx
// server/trpc.ts
import { initTRPC } from "@trpc/server";
import { getExecutionContext } from "@databricks/appkit";
import { z } from "zod";
import superjson from "superjson";

const t = initTRPC.create({ transformer: superjson });
const publicProcedure = t.procedure;

export const appRouter = t.router({
  // Example: Query a serving endpoint
  queryModel: publicProcedure
    .input(z.object({ prompt: z.string() }))
    .query(async ({ input: { prompt } }) => {
      const { serviceDatabricksClient: client } = getExecutionContext();
      const response = await client.servingEndpoints.query({
        name: "your-endpoint-name",
        messages: [{ role: "user", content: prompt }],
      });
      return response;
    }),

  // Example: Mutation
  createRecord: publicProcedure
    .input(z.object({ name: z.string() }))
    .mutation(async ({ input }) => {
      // Custom logic here
      return { success: true, id: 123 };
    }),
});
```

## Client-side Pattern

```typescript
// client/src/components/MyComponent.tsx
import { trpc } from '@/lib/trpc';
import { useState, useEffect } from 'react';

function MyComponent() {
  const [result, setResult] = useState(null);

  useEffect(() => {
    trpc.queryModel
      .query({ prompt: "Hello" })
      .then(setResult)
      .catch(console.error);
  }, []);

  const handleCreate = async () => {
    await trpc.createRecord.mutate({ name: "test" });
  };

  return <div>{/* component JSX */}</div>;
}
```

## Decision Tree for Data Operations

1. **Need to display data from SQL?**
   - **Chart or Table?** → Use visualization components (`BarChart`, `LineChart`, `DataTable`, etc.)
   - **Custom display (KPIs, cards, lists)?** → Use `useAnalyticsQuery` hook
   - **Never** use tRPC for SQL SELECT statements

2. **Need to call a Databricks API?** → Use tRPC
   - Serving endpoints (model inference)
   - MLflow operations
   - Jobs API
   - Workspace API

3. **Need to modify data?** → Use tRPC mutations
   - INSERT, UPDATE, DELETE operations
   - Multi-step transactions
   - Business logic with side effects

4. **Need non-SQL custom logic?** → Use tRPC
   - File processing
   - External API calls
   - Complex computations in TypeScript

**Summary:**

- ✅ SQL queries → Visualization components or `useAnalyticsQuery`
- ✅ Databricks APIs → tRPC
- ✅ Data mutations → tRPC
- ❌ SQL queries → tRPC (NEVER do this)
- ❌ Files operations → tRPC (NEVER do this)
