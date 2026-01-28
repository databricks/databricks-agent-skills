---
name: databricks-apps
description: Build full-stack TypeScript apps on Databricks. Use when asked to create dashboards, data apps, analytics tools, or visualizations that query Databricks SQL. Provides project scaffolding, SQL data access patterns, and deployment commands. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= 0.250.0)
metadata:
  version: "0.1.0"
parent: databricks
---

# Databricks Apps Development

**FIRST**: Use the parent `databricks` skill for CLI basics, authentication, profile selection, and data exploration commands.

Build apps that deploy to Databricks Apps platform.

## Generic Guidelines (All Apps)

These apply regardless of framework:

- **Deployment**: `databricks apps deploy --profile <PROFILE>` (⚠️ USER CONSENT REQUIRED)
- **Validation**: `databricks apps validate` before deploying
- **App name**: Must be ≤26 characters (dev- prefix adds 4 chars, max 30 total)
- **References**:
  - [Testing](references/testing.md) - smoke tests, validation
  - Authentication: covered by parent `databricks` skill

## AppKit (Recommended)

AppKit is the recommended way to build Databricks Apps - provides type-safe SQL queries, React components, and seamless deployment.

### Workflow

1. **Scaffold**: `databricks apps init --description "<DESC>" --features analytics --warehouse-id <ID> --name <NAME> --run none --profile <PROFILE>`
2. **Develop**: `cd <NAME> && npm install && npm run dev`
3. **Validate**: `databricks apps validate`
4. **Deploy**: `databricks apps deploy --profile <PROFILE>`

### Project Structure (AppKit)

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

### Type Safety

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

### Adding Visualizations

**Step 1**: Create SQL file `config/queries/my_data.sql`
```sql
SELECT category, COUNT(*) as count FROM my_table GROUP BY category
```

**Step 2**: Use component (types auto-generated!)
```typescript
import { BarChart } from '@databricks/appkit-ui/react';
<BarChart queryKey="my_data" parameters={{}} />
```

### AppKit References

- [SQL Queries](references/appkit/sql-queries.md) - query files, parameterization, sql.* helpers
- [AppKit SDK](references/appkit/appkit-sdk.md) - imports, useAnalyticsQuery hook
- [Frontend](references/appkit/frontend.md) - visualization components, charts, DataTable
- [tRPC](references/appkit/trpc.md) - custom endpoints for mutations, Databricks APIs

### Critical Rules (AppKit)

1. **SQL for data retrieval**: Use `config/queries/` + visualization components. Never tRPC for SELECT.
2. **Numeric types**: SQL numbers may return as strings. Always convert: `Number(row.amount)`
3. **Type imports**: Use `import type { ... }` (verbatimModuleSyntax enabled).
4. **Charts are ECharts**: No Recharts children - use props (`xKey`, `yKey`, `colors`).
5. **No `enabled` option**: `useAnalyticsQuery` isn't React Query - use conditional rendering.

### Decision Tree (AppKit)

- **Display data from SQL?**
  - Chart/Table → `BarChart`, `LineChart`, `DataTable` components
  - Custom layout (KPIs, cards) → `useAnalyticsQuery` hook
- **Call Databricks API?** → tRPC (serving endpoints, MLflow, Jobs)
- **Modify data?** → tRPC mutations
