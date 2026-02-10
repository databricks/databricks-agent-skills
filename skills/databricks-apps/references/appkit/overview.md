# AppKit Overview

AppKit is the recommended way to build Databricks Apps - provides type-safe SQL queries, React components, and seamless deployment.

## Workflow

1. **Scaffold**: See parent SKILL.md for `databricks apps init` command
2. **Develop**: `cd <NAME> && npm install && npm run dev`
3. **Validate**: `databricks apps validate`
4. **Deploy**: `databricks apps deploy --profile <PROFILE>`

## Data Discovery (Before Writing SQL)

```bash
# 1. get warehouse id
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>

# 2. explore table structure
databricks experimental aitools tools discover-schema catalog.schema.table --profile <PROFILE>

# 3. test query
databricks experimental aitools tools query "SELECT * FROM catalog.schema.table LIMIT 5" --profile <PROFILE>
```

Do NOT manually iterate through `catalogs list` → `schemas list` → `tables list`.

## Pre-Implementation Checklist

Before writing App.tsx, complete these steps:

1. ✅ Create SQL files in `config/queries/`
2. ✅ Run `npm run typegen` to generate query types
3. ✅ Read `client/src/appKitTypes.d.ts` to see available query result types
4. ✅ Verify component props: `npx @databricks/appkit docs ./docs/docs/api/appkit-ui.md`
5. ✅ Plan smoke test updates (default expects "Minimal Databricks App")

**DO NOT** write UI code until types are generated and verified.

## Post-Implementation Checklist

Before running `databricks apps validate`, complete these steps:

1. ✅ Update `tests/smoke.spec.ts` heading selector to match your app title
2. ✅ Update or remove the 'hello world' text assertion
3. ✅ Verify `npm run typegen` has been run after all SQL files are finalized
4. ✅ Ensure all numeric SQL values use `Number()` conversion in display code

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

**Always use AppKit docs as the source of truth for API details:**

```bash
npx @databricks/appkit docs                                    # full index
npx @databricks/appkit docs ./docs/docs/development/llm-guide.md  # LLM-specific guardrails
npx @databricks/appkit docs ./docs/docs/api/appkit-ui.md       # UI components
npx @databricks/appkit docs ./docs/docs/api/appkit-ui/data/BarChart.md  # specific component
```

## References - READ BEFORE Writing Code

| Before doing... | READ |
|-----------------|------|
| Creating SQL files | [SQL Queries](sql-queries.md) - parameterization, sql.* helpers |
| Using `useAnalyticsQuery` | [AppKit SDK](appkit-sdk.md) - memoization, conditional queries |
| Adding charts/tables | [Frontend](frontend.md) - anti-patterns and gotchas |
| Adding API endpoints | [tRPC](trpc.md) - mutations, Databricks API calls |

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
