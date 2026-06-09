# AppKit Overview

AppKit is the recommended way to build Databricks Apps — type-safe SQL queries, React components, and seamless deployment.

**Pattern selection, gates, and capability composition:** [Data Patterns](data-patterns.md) (canonical).

**Scaffold → dev → validate → deploy order:** [Lifecycle](lifecycle.md).

## Workflow (summary)

1. **Classify capabilities** → [Data Patterns](data-patterns.md)
2. **Scaffold**: `databricks apps manifest` → `databricks apps init --run none`
3. **Develop**: follow checklist slices + [Lifecycle](lifecycle.md)
4. **Validate**: `databricks apps validate` (after updating smoke tests)
5. **Deploy**: [Lifecycle: First deploy](lifecycle.md#first-deploy) (⚠️ user consent)

## Data discovery

When `reads_warehouse` or `writes_delta` is in the capability set, use the parent **`databricks-core`** skill before writing SQL.

## Pre-implementation checklists

Use the checklist slices for your capability set — [Data Patterns: Checklist slices](data-patterns.md#checklist-slices).

Quick reference:

| Capabilities | Before `App.tsx` |
|--------------|------------------|
| `reads_warehouse` | SQL files + typegen |
| `writes_oltp` | Replace scaffold; plan `onPluginsReady` routes; deploy before dev |
| Hybrid | Union both; warehouse reads ≠ Lakebase writes |

## Post-implementation

Before `databricks apps validate`:

1. Update `tests/smoke.spec.ts` selectors
2. Remove default "hello world" assertions
3. Run typegen if analytics reads changed
4. Convert numeric SQL display with `Number()`

## Project structure

**Analytics reads** (`reads_warehouse`):

```
my-app/
├── config/queries/*.sql     # SELECT only → queryKey
├── client/src/App.tsx
├── server/server.ts         # onPluginsReady + routes (if mutations/APIs)
└── tests/smoke.spec.ts
```

**Lakebase OLTP** (`writes_oltp`) — no `config/queries/`; CRUD via Express routes. See [Lakebase](lakebase.md).

**Key files:**

| Task | File |
|------|------|
| Build UI | `client/src/App.tsx` |
| Add warehouse read query | `config/queries/<NAME>.sql` |
| Add API / mutation route | `server/server.ts` (`onPluginsReady` + `server.extend`) |
| Fix smoke test | `tests/smoke.spec.ts` |

## Type safety (analytics reads)

1. Add/modify SQL in `config/queries/`
2. Run `npm run typegen` (or auto during dev)
3. Types in `client/src/appKitTypes.d.ts`

Details: `npx @databricks/appkit docs ./docs/development/type-generation.md`

## Adding visualizations

```sql
-- config/queries/my_data.sql
SELECT category, COUNT(*) as count FROM my_table GROUP BY category
```

```typescript
import { BarChart } from '@databricks/appkit-ui/react';
<BarChart queryKey="my_data" parameters={{}} />
```

## AppKit official documentation

```bash
npx @databricks/appkit docs
npx @databricks/appkit docs <query>
```

## Plugin setup guides

Pattern selection → [Data Patterns](data-patterns.md). These docs are **setup only**:

| Plugin | Guide |
|--------|-------|
| SQL reads | [SQL Queries](sql-queries.md) |
| Custom routes | [Custom Endpoints](custom-endpoints.md) |
| Delta DML | [Warehouse Mutations](warehouse-mutations.md) |
| Lakebase | [Lakebase](lakebase.md) |
| Genie | [Genie](genie.md) |
| Serving | [Model Serving](model-serving.md) |
| Files | [Files](files.md) |
| Jobs | [Jobs](jobs.md) |
| UI | [Frontend](frontend.md), [AppKit SDK](appkit-sdk.md) |

## Critical rules

1. Warehouse **reads** → `config/queries/` — never custom endpoints for SELECT.
2. **Writes** → pick path in [Data Patterns: Write path](data-patterns.md#write-path).
3. SQL numbers may be strings — use `Number(row.amount)`.
4. Charts are ECharts — use `xKey`/`yKey` props, not Recharts children.
5. Never `useAnalyticsQuery` for Lakebase data.

## Decision tree

→ [Data Patterns](data-patterns.md) — capability catalog, gates, write/read paths, recipes.
