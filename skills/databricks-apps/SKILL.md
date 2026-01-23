---
name: databricks-apps
description: Build full-stack TypeScript apps on Databricks. Use when asked to create dashboards, data apps, analytics tools, or visualizations that query Databricks SQL. Provides project scaffolding, SQL data access patterns, and deployment commands. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= 0.250.0)
metadata:
  version: "0.1.0"
---

**CRITICAL**: Before proceeding with ANY databricks-apps task, you MUST first invoke the `databricks` skill using the Skill tool. The databricks skill provides essential context for:
- Authentication and profile selection (NEVER auto-select profiles)
- Data exploration commands (`discover-schema`, `query`)
- SQL warehouse identification
- CLI usage patterns specific to Claude Code

**Action Required**: If you haven't already invoked the `databricks` skill in this conversation, invoke it now with: `Skill(command: "databricks")`

# Databricks Apps Development

Build TypeScript apps that query Databricks SQL warehouses and deploy to Databricks Apps.

## Workflow

1. **Verify auth**: See `databricks` skill
2. **Find warehouse**: See `databricks` skill
3. **Explore data**: See `databricks` skill
4. **Scaffold project**: `apps init --description "<APP_DESCRIPTION>" --features analytics --warehouse-id <WAREHOUSE_ID> --name <APP_NAME>
 --run none --profile `
5. **Develop**: `cd <APP_NAME> && npm install && npm run dev`
6. **Validate**: `databricks apps validate`
7. **Deploy**: `databricks apps deploy --profile <PROFILE>` (⚠️ USER CONSENT REQUIRED: Only deploy with explicit user permission.)

## Data Exploration

See `databricks` skill

## Project Structure

After scaffolding:
- `server/` - Node.js backend with App Kit and tRPC
- `client/` - React frontend with App Kit hooks
- `config/queries/` - SQL query files
- `shared/` - Shared TypeScript types

## Adding Visualizations

**Step 1**: Create SQL file in `config/queries/my_data.sql`
```sql
SELECT category, COUNT(*) as count FROM my_table GROUP BY category
```

**Step 2**: Define schema in `config/queries/schema.ts`
```typescript
export const querySchemas = {
  my_data: z.array(z.object({ category: z.string(), count: z.number() })),
};
```

**Step 3**: Use visualization component
```typescript
import { BarChart } from '@databricks/appkit-ui/react';
<BarChart queryKey="my_data" parameters={{}} />
```

Run `npm run dev` to regenerate types after schema changes.

## Key References

Load these when implementing specific features:
- [SQL Queries](references/sql-queries.md) - query files, schemas, parameterization, sql.* helpers
- [AppKit SDK](references/appkit-sdk.md) - imports, server setup, useAnalyticsQuery hook
- [Frontend](references/frontend.md) - visualization components, styling, Radix constraints
- [tRPC](references/trpc.md) - custom endpoints for mutations, Databricks APIs
- [Testing](references/testing.md) - vitest unit tests, Playwright smoke tests
- [Authentication](references/authentication.md) - profiles, OAuth, troubleshooting

## Critical Rules

1. **SQL for data retrieval**: Always use `config/queries/` + visualization components. Never use tRPC for SELECT queries.
2. **Numeric types**: All SQL numbers return as strings in JSON. Always convert: `Number(row.amount).toFixed(2)`
3. **Type imports**: Use `import type { ... }` for type-only imports (verbatimModuleSyntax is enabled).
4. **App name**: Must be ≤26 characters (dev- prefix adds 4 chars, max 30 total).
5. **Validate before deploy**: Always run `databricks experimental aitools tools validate ./` first.

## Decision Tree

- **Display data from SQL?**
  - Chart/Table → Use `BarChart`, `LineChart`, `DataTable` components
  - Custom layout (KPIs, cards) → Use `useAnalyticsQuery` hook
- **Call Databricks API?** → Use tRPC (serving endpoints, MLflow, Jobs API)
- **Modify data?** → Use tRPC mutations
