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
├── client/                    # React frontend
│   ├── src/
│   │   ├── App.tsx           # ← Main app component (start here)
│   │   ├── appKitTypes.d.ts  # AUTO-GENERATED query types
│   │   └── main.tsx          # Entry point
│   └── vite.config.ts
├── server/
│   └── server.ts             # AppKit server + tRPC routes
├── config/
│   └── queries/              # SQL files
│       └── my_query.sql      # → queryKey: "my_query"
├── shared/
│   └── types.ts              # Shared interfaces, helpers
├── tests/
│   └── smoke.spec.ts         # ⚠️ Update selectors after customizing!
└── databricks.yml            # Deployment config
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

**Types are AUTO-GENERATED** - no manual schema files needed!

1. Add/modify SQL in `config/queries/`
2. Run `npm run dev` (watches) or `npm run typegen`
3. Types appear in `client/src/appKitTypes.d.ts`

**Optional Zod validation** - create `config/queries/schema.ts`:
```typescript
import { z } from 'zod';
export const querySchemas = {
  my_query: z.array(z.object({
    amount: z.coerce.number(),  // z.coerce handles string/number from SQL
  })),
};
```

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
5. **No `enabled` option**: `useAnalyticsQuery` isn't React Query - use conditional rendering.

## Decision Tree

- **Display data from SQL?**
  - Chart/Table → `BarChart`, `LineChart`, `DataTable` components
  - Custom layout (KPIs, cards) → `useAnalyticsQuery` hook
- **Call Databricks API?** → tRPC (serving endpoints, MLflow, Jobs)
- **Modify data?** → tRPC mutations
