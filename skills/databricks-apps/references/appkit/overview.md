# AppKit Overview

AppKit is the recommended way to build Databricks Apps - provides type-safe SQL queries, React components, and seamless deployment.

## Choose Your Data Pattern FIRST

Before scaffolding, decide which data pattern the app needs:

| Pattern | When to use | Init command |
|---------|-------------|-------------|
| **Analytics** (read-only) | Dashboards, charts, KPIs from warehouse | `--features analytics --set analytics.sql-warehouse.id=<ID>` |
| **Lakebase synced tables** (low-latency reads) | Point lookups, entity search, catalogs from lakehouse data | `--features lakebase` + all three `--set lakebase.postgres.{project,branch,database}=...` (derive from manifest) + sync Delta table via `databricks-lakebase` skill |
| **Lakebase (OLTP)** (read/write) | CRUD forms, persistent state, user data | `--features lakebase` + `--set lakebase.postgres.project=<PROJECT> --set lakebase.postgres.branch=<BRANCH> --set lakebase.postgres.database=<DB>` (derive from `databricks apps manifest`) |
| **Genie** (NL queries) | Chat interface over Unity Catalog tables | `--features genie --set genie.<resourceKey>.<field>=<value>` (check manifest) |
| **Model Serving** (ML inference) | Chat, AI features, model predictions | `--features serving --set serving.serving-endpoint.name=<NAME>` (check manifest) |
| **Jobs** (trigger Lakeflow Jobs) | Kick off and monitor pre-existing notebooks / Python / SQL / dbt jobs | `--features jobs --set jobs.<resourceKey>.<field>=<JOB_ID>` (check manifest) |
| **Multiple** | Combine plugins as needed (e.g. dashboard + CRUD, analytics + Genie) | `--features analytics,lakebase,genie,...` with all required `--set` flags per plugin |

See [Lakebase Guide](lakebase.md) for full Lakebase scaffolding and app-code patterns.
See [Genie Guide](genie.md) for space creation, plugin setup, and frontend components.

## Workflow

1. **Scaffold**: Run `databricks apps manifest`, then `databricks apps init` with `--features` and `--set` as in parent SKILL.md (App Manifest and Scaffolding)
2. **Develop**: `cd <NAME> && npm install`, implement SQL/routes/UI, update `tests/smoke.spec.ts` — use `npm run dev` to iterate (analytics, Genie, serving, etc.)
3. **Validate**: `databricks apps validate --profile <PROFILE>` — after smoke tests match your UI
4. **Deploy**: follow parent SKILL.md *Deployment Workflow* — first deploy: `bundle deploy` then `apps deploy`; updates: `apps deploy` (⚠️ USER CONSENT REQUIRED)

**Lakebase OLTP CRUD exception:** Write routes and UI in step 2, but do **not** run `npm run dev` against Lakebase until after the first successful deploy (step 4) — the Service Principal must own the schema first. See [Lakebase Guide](lakebase.md) *Local Development*.

## Data Discovery (Before Writing SQL)

**Use the parent `databricks-core` skill for data discovery** (table search, schema exploration, query execution).

## Pre-Implementation Checklist

Use the checklist that matches your scaffolded `--features`. See parent SKILL.md *Pick your write path first* if you have not chosen read vs write paths yet.

### Analytics apps (`--features analytics`)

Before writing `App.tsx`:

1. ✅ Create SQL files in `config/queries/` (SELECT only — not DML)
2. ✅ Run `npm run typegen` to generate query types
3. ✅ Read `client/src/appKitTypes.d.ts` to see available query result types
4. ✅ Verify component props via `npx @databricks/appkit docs` (check the relevant component page)
5. ✅ Plan smoke test updates (default expects "Minimal Databricks App")

**DO NOT** write UI code until types are generated and verified.

If the app also **writes to Delta/UC**, read [Warehouse Mutations](warehouse-mutations.md) before adding mutation routes.

### Lakebase apps (`--features lakebase`)

Before writing `App.tsx`:

1. ✅ Read [Lakebase Guide](lakebase.md) — *What the scaffold gives you* and *Lakebase route modules — typing*
2. ✅ Replace scaffold todo boilerplate with your domain routes and UI
3. ✅ Plan schema init and CRUD routes in `onPluginsReady` (no `config/queries/`, no typegen)
4. ✅ Plan smoke test updates — do not assert Lakebase-backed dynamic content during validate
5. ✅ **Lakebase OLTP CRUD**: deploy before local dev so the SP owns the schema (see parent SKILL.md *Deployment Workflow*)

### Hybrid apps (`analytics,lakebase` or similar)

Complete both checklists above: SQL files + typegen for warehouse **reads**; Lakebase routes for Postgres **writes**. Do not use `useAnalyticsQuery` for Lakebase data.

## Post-Implementation Checklist

Before running `databricks apps validate`:

1. ✅ Update `tests/smoke.spec.ts` heading selector to match your app title
2. ✅ Update or remove the 'hello world' text assertion
3. ✅ **Analytics reads**: verify `npm run typegen` ran after all SQL files are finalized
4. ✅ Ensure all numeric SQL values use `Number()` conversion in display code

## Project Structure

```
my-app/
├── server/
│   ├── server.ts             # Backend entry point (AppKit)
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
| Add SQL query | `config/queries/<NAME>.sql` |
| Add API endpoint | `server/server.ts` (`onPluginsReady` + `server.extend`) |
| Add shared helpers (optional) | create `shared/types.ts` or `client/src/lib/formatters.ts` |
| Fix smoke test | `tests/smoke.spec.ts` |

## Type Safety

For type generation details, see: `npx @databricks/appkit docs ./docs/development/type-generation.md`

**Quick workflow:**
1. Add/modify SQL in `config/queries/`
2. Types auto-generate during dev via the Vite plugin (or run `npm run typegen` manually)
3. Types appear in `client/src/appKitTypes.d.ts`

## Adding Visualizations

**Step 1**: Create SQL file `config/queries/my_data.sql`
```sql
SELECT category, COUNT(*) as count FROM my_table GROUP BY category
```

**Step 2**: Use component (types auto-generated!)
```typescript
import { BarChart } from '@databricks/appkit-ui/react';
// Query mode: fetches data automatically
<BarChart queryKey="my_data" parameters={{}} />

// Data mode: pass static data directly (no queryKey/parameters needed)
<BarChart data={myData} xKey="category" yKey="count" />
```

## AppKit Official Documentation

**Always use AppKit docs as the source of truth for API details.**

```bash
npx @databricks/appkit docs                              # show the docs index (start here)
npx @databricks/appkit docs <query>                      # look up a section by name or doc path
```

Do not guess paths — run without args first, then pick from the index.

## References

| When you're about to... | Read |
|-------------------------|------|
| Write SQL files | [SQL Queries](sql-queries.md) — parameterization, dialect, sql.* helpers |
| Use `useAnalyticsQuery` | [AppKit SDK](appkit-sdk.md) — memoization, conditional queries |
| Add chart/table components | [Frontend](frontend.md) — component quick reference, anti-patterns |
| Add API mutation endpoints | [Custom Endpoints](custom-endpoints.md) + [Warehouse Mutations](warehouse-mutations.md) for Delta/UC DML |
| Use Lakebase for CRUD / persistent state | [Lakebase](lakebase.md) — replace scaffold todo boilerplate, route typing, `onPluginsReady` patterns, schema init |
| Add Genie chat | [Genie](genie.md) — space creation, plugin setup, frontend components |
| Call ML model serving endpoints | [Model Serving](model-serving.md) — serving plugin, frontend hooks |
| Trigger / monitor Lakeflow Jobs from the app | [Jobs](jobs.md) — env discovery, JobHandle API, SSE streaming |

## Critical Rules

1. **SQL for data retrieval**: Use `config/queries/` + visualization components. Never custom endpoints for warehouse SELECT.
2. **Numeric types**: SQL numbers may return as strings. Always convert: `Number(row.amount)`
3. **Type imports**: Use `import type { ... }` (verbatimModuleSyntax enabled).
4. **Charts are ECharts**: No Recharts children — use props (`xKey`, `yKey`, `colors`). `xKey`/`yKey` auto-detect from schema if omitted.
5. **Two data modes**: Charts/tables support query mode (`queryKey` + `parameters`) and data mode (static `data` prop).
6. **Conditional queries**: Use `autoStart: false` option or conditional rendering to control query execution.

## Decision Tree

- **Display data from SQL warehouse?**
  - Chart/Table → `BarChart`, `LineChart`, `DataTable` components
  - Custom layout (KPIs, cards) → `useAnalyticsQuery` hook
  - **Never** custom endpoints for warehouse SELECT — use [SQL Queries](sql-queries.md)
- **Call Databricks API?**
  - Model inference → `serving()` plugin — [Model Serving](model-serving.md)
  - Trigger/monitor jobs → `jobs()` plugin — [Jobs](jobs.md)
  - Files in UC Volumes → `files()` plugin — [Files](files.md)
  - MLflow, Workspace API, other APIs → custom endpoint via `onPluginsReady` — [Custom Endpoints](custom-endpoints.md)
- **Modify / persist data?** → Custom endpoint in `onPluginsReady` (see parent SKILL.md *Pick your write path first*)
  - Postgres app state (forms, CRUD) → `appkit.lakebase.query()` — [Lakebase](lakebase.md)
  - Small scoped Delta/UC DML now → `appkit.analytics.query()` — [Warehouse Mutations](warehouse-mutations.md)
  - Large / async lakehouse write → validate input, then `jobs()` — [Jobs](jobs.md)
- **Non-SQL server logic?** → Custom endpoint via `onPluginsReady` — [Custom Endpoints](custom-endpoints.md)
