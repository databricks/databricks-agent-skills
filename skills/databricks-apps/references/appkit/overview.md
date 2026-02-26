# AppKit Overview

AppKit is the recommended way to build Databricks Apps - provides type-safe SQL queries, React components, and seamless deployment.

## Workflow

1. **Scaffold**: Run `databricks apps manifest`, then `databricks apps init` with `--features` and `--set` as in parent SKILL.md (App Manifest and Scaffolding)
2. **Develop**: `cd <NAME> && npm install && npm run dev`
3. **Validate**: `databricks apps validate`
4. **Deploy**: `databricks apps deploy --profile <PROFILE>`

## Data Discovery (Before Writing SQL)

**Use the parent `databricks` skill for all data discovery.** See [Data Exploration](../../../databricks/data-exploration.md) for full details including keyword search, schema discovery, and query execution.

Do NOT manually iterate through `catalogs list` → `schemas list` → `tables list` — use `information_schema` keyword search instead (documented in the data exploration guide).

## Pre-Implementation Checklist

Before writing App.tsx, complete these steps:

1. ✅ Create SQL files in `config/queries/`
2. ✅ Run `npm run typegen` to generate query types
3. ✅ Read `client/src/appKitTypes.d.ts` to see available query result types
4. ✅ Verify component props via `npx @databricks/appkit docs` (check the relevant component page)
5. ✅ Plan smoke test updates (default expects "Minimal Databricks App")

**DO NOT** write UI code until types are generated and verified.

## Post-Implementation Checklist

Before running `databricks apps validate`, complete these steps:

1. ✅ Run `npx tsc --noEmit` to catch TypeScript errors early
2. ✅ Run `npm run lint` to catch unused imports/variables
3. ✅ Update `tests/smoke.spec.ts` heading selector to match your app title
4. ✅ Update or remove the 'hello world' text assertion
5. ✅ Verify `npm run typegen` has been run after all SQL files are finalized
6. ✅ Ensure all numeric SQL values use `Number()` conversion in display code

## Project Structure

```
my-app/
├── server/
│   ├── index.ts              # Backend entry point (AppKit)
│   └── .env                  # Optional local dev env vars (do not commit)
├── client/
│   ├── index.html
│   ├── vite.config.ts
│   └── src/
│       ├── main.tsx
│       └── App.tsx           # <- Main app component (start here)
├── config/
│   └── queries/
│       └── my_query.sql      # -> queryKey: "my_query"
├── app.yaml                  # Deployment config
├── package.json
└── tsconfig.json
```

**Key files to modify:**
| Task | File |
|------|------|
| Build UI | `client/src/App.tsx` |
| Add SQL query | `config/queries/<name>.sql` |
| Add API endpoint | `server/server.ts` (tRPC) |
| Add shared types | `shared/types.ts` |
| Fix smoke test | `tests/smoke.spec.ts` |

## Type Safety

For type generation details, see: `npx @databricks/appkit docs ./docs/docs/development/type-generation.md`

**Quick workflow:**
1. Add/modify SQL in `config/queries/`
2. Run `npm run typegen`
3. Types appear in `client/src/appKitTypes.d.ts`

## Adding Visualizations

**Step 1**: Create SQL file `config/queries/my_data.sql`
```sql
SELECT category, COUNT(*) as count FROM my_table GROUP BY category
```

**Step 2**: Use component (types auto-generated!)
```typescript
import { BarChart } from '@databricks/appkit-ui/react';
<BarChart queryKey="my_data" parameters={{}} />
```

## AppKit Official Documentation

**Always use AppKit docs as the source of truth for API details.** Run `npx @databricks/appkit docs` (no args) to see the full index, then navigate to specific pages. Do not guess paths.

## References — Read As Needed (NOT all upfront)

| When you're about to... | Read THIS |
|-------------------------|-----------|
| Write SQL files | [SQL Queries](sql-queries.md) — parameterization, dialect, sql.* helpers |
| Use `useAnalyticsQuery` | [AppKit SDK](appkit-sdk.md) — memoization, conditional queries |
| Add chart/table components | [Frontend](frontend.md) — component quick reference, anti-patterns |
| Add API mutation endpoints | [tRPC](trpc.md) — only if you need server-side logic |

**Do NOT read all docs upfront.** Read this overview first, then reference specific docs as you work.

## Critical Rules

1. **SQL for data retrieval**: Use `config/queries/` + visualization components. Never tRPC for SELECT.
2. **Numeric types**: SQL numbers may return as strings. Always convert: `Number(row.amount)`
3. **Type imports**: Use `import type { ... }` (verbatimModuleSyntax enabled).
4. **Charts are ECharts**: No Recharts children - use props (`xKey`, `yKey`, `colors`).
5. **Conditional queries**: Use `autoStart: false` option or conditional rendering to control query execution.

## Decision Tree

- **Display data from SQL?**
  - Chart/Table → `BarChart`, `LineChart`, `DataTable` components
  - Custom layout (KPIs, cards) → `useAnalyticsQuery` hook
- **Call Databricks API?** → tRPC (serving endpoints, MLflow, Jobs)
- **Modify data?** → tRPC mutations
