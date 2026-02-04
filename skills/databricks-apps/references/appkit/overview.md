# AppKit Overview

AppKit is the recommended way to build Databricks Apps - provides type-safe SQL queries, React components, and seamless deployment.

## Workflow

1. **Scaffold**: See parent SKILL.md for `databricks apps init` command
2. **Develop**: `cd <NAME> && npm install && npm run dev`
3. **Validate**: `databricks apps validate`
4. **Deploy**: `databricks apps deploy --profile <PROFILE>`

## Pre-Implementation Checklist

Before writing App.tsx, complete these steps:

1. ✅ Create SQL files in `config/queries/`
2. ✅ Run `npm run typegen` to generate query types
3. ✅ Read `client/src/appKitTypes.d.ts` to see available query result types
4. ✅ Verify component props in [Frontend Guide](frontend.md)
5. ✅ Plan smoke test updates (default expects "Minimal Databricks App")

**DO NOT** write UI code until types are generated and verified.

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

## References - READ BEFORE Writing Code

| Before doing... | READ |
|-----------------|------|
| Creating SQL files | [SQL Queries](sql-queries.md) - parameterization, sql.* helpers |
| Using `useAnalyticsQuery` | [AppKit SDK](appkit-sdk.md) - memoization, conditional queries |
| Adding charts/tables | [Frontend](frontend.md) - component props, invalid patterns |
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
