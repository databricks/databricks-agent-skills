# AppKit Data Patterns & Capabilities

**Canonical reference** for choosing plugins, running gates, and composing checklists. Plugin guides (`genie.md`, `files.md`, etc.) cover setup only — pattern selection lives here.

Apps are **compositions of capabilities**, not single archetypes. Derive `--features` as the **union** of capability flags below.

## Capability catalog

| Flag | Plugin | Owns | Deep guide |
|------|--------|------|------------|
| `reads_warehouse` | `analytics` | `config/queries/` (SELECT), charts, `useAnalyticsQuery` | [SQL Queries](sql-queries.md) |
| `reads_synced` | `lakebase` | Read-only queries on Lakebase synced tables | [Lakebase Synced Reads](lakebase-synced-reads.md) |
| `writes_oltp` | `lakebase` | Postgres CRUD, schema init, deploy-first | [Lakebase OLTP](lakebase-oltp.md) |
| `writes_delta` | `analytics` | Warehouse DML via custom routes | [Warehouse Mutations](warehouse-mutations.md) |
| `writes_via_job` | `jobs` | Trigger/monitor Lakeflow Jobs | [Jobs](jobs.md) |
| `genie` | `genie` | NL Q&A over UC tables (SSE) | [Genie](genie.md) |
| `files` | `files` | UC Volume upload/download/browse | [Files](files.md) |
| `serving` | `serving` | Model inference / chat endpoints | [Model Serving](model-serving.md) |

**Route mechanics** (all mutation paths): [Custom Endpoints](custom-endpoints.md) — `onPluginsReady` + `appkit.server.extend()`.

### Infer capabilities from the user request

Include a flag **only when the user asked for it** (or it is clearly required). Do not add Lakebase or analytics "just in case."

| User intent | Typical flags |
|-------------|---------------|
| Dashboard, KPIs, charts over UC tables | `reads_warehouse` |
| Form, todos, sessions, app-owned CRUD | `writes_oltp` |
| Save into existing Delta/UC table on submit | `writes_delta` |
| Large batch write, ETL from app action | `writes_via_job` |
| Sub-second lookup on synced lakehouse data | `reads_synced` |
| "Ask questions about my data" chat | `genie` |
| Upload/download files in volumes | `files` |
| LLM / model endpoint in app | `serving` |

Map flags → plugins → `--features` (comma-separated union). Derive every `--set` from `databricks apps manifest`.

## Conditional gates

Run **only** gates whose capability is in the set. Skip the rest.

| Gate | Run when | Action |
|------|----------|--------|
| **write_path** | `writes_oltp`, `writes_delta`, or `writes_via_job` | Use [Write path](#write-path) table; ask if unclear |
| **read_path** | App reads UC/lakehouse data **and** you must choose synced vs warehouse SQL | Use [Read path](#read-path); see skip rules below |
| **genie_space** | `genie` | Tables + create/reuse space — [Genie workflow](#genie-workflow) |
| **lakebase_resources** | `writes_oltp` or `reads_synced` | Three `--set lakebase.postgres.{project,branch,database}` from manifest |
| **data_discovery** | `reads_warehouse` or `writes_delta` | Parent `databricks-core` skill — schema search before SQL |

**Skip read_path when:**
- App has no UC/lakehouse reads (pure CRUD, serving-only, files-only).
- User already chose warehouse SQL (`reads_warehouse`) **and** does not need synced-table latency.
- App uses `genie` + fixed dashboards — Genie complements analytics; both use the warehouse (different UX).

**write_path question (if unclear):** *Should this data live in Postgres (app state), in Delta/UC (lakehouse), or run as a background job?*

## Write path

When the app **persists or mutates** data:

| Need | Write path | Read next |
|------|------------|-----------|
| App-owned state (forms, CRUD, sessions) — Postgres is system of record | Custom route + `appkit.lakebase.query()` | [Lakebase OLTP](lakebase-oltp.md) |
| User action updates **existing Delta/UC table now** (small scoped DML) | Custom route + `appkit.analytics.query()` + Zod | [Warehouse Mutations](warehouse-mutations.md) |
| Large / async lakehouse write | Custom route → `jobs()` plugin | [Jobs](jobs.md) |
| Postgres now; curated data in Delta **later** (async OK) | Lakebase OLTP + [Lakehouse Sync](../../../databricks-lakebase/references/lakehouse-sync.md) (UI-only) | **`databricks-lakebase`** skill |
| Read-only dashboard / KPI | No write path | [SQL Queries](sql-queries.md) |

**Defaults:** App-owned CRUD → `writes_oltp`. Curated lakehouse table the user explicitly named → consider `writes_delta` or `writes_via_job`.

## Read path

When the app **reads** Unity Catalog / lakehouse data and synced vs warehouse SQL is not already decided:

| | **(A) Lakebase synced reads** | **(B) Analytics (warehouse SQL)** |
|--|---|---|
| Speed | Sub-second | Few seconds |
| Best for | Typeahead, ID lookups, operational serving from synced gold | Dashboards, charts, KPIs, SQL filters |
| How | Delta synced into Lakebase Postgres (read-only) | `config/queries/` + warehouse at read time |

Recommend **(B)** for most dashboards. Recommend **(A)** only for sub-second lookup/typeahead on synced tables.

**Do not** use synced reads **and** warehouse SQL for the **same dataset** without a explicit reason.

After choice: (A) → `--features lakebase` (+ analytics if also dashboarding different data). (B) → `--features analytics`.

## Composition rules

- **Genie + analytics:** OK — SQL files for fixed KPIs; Genie for NL. Flags: `reads_warehouse`, `genie`.
- **Lakebase OLTP + analytics:** Common hybrid — reads via SQL files; writes via Postgres routes. Flags: `writes_oltp`, `reads_warehouse`.
- **Files / serving / jobs:** Stack freely with any read/write combo.
- **Never write to synced tables** — read-only replicas; see [Lakebase Synced Reads](lakebase-synced-reads.md).
- **Never** warehouse SELECT in custom endpoints — use `config/queries/`.
- **Never** `useAnalyticsQuery` for Lakebase data.

## Named recipes (examples)

Recipes illustrate common **capability unions** — not exclusive app types.

### Analytics dashboard

`{ reads_warehouse }` → `--features analytics`

Gates: data_discovery. Slices: analytics only.

### Lakebase CRUD

`{ writes_oltp }` → `--features lakebase`

Gates: write_path, lakebase_resources. Slices: lakebase_oltp. Deploy before local dev.

### AI analyst

`{ reads_warehouse, genie }` → `--features analytics,genie`

Gates: genie_space; skip read_path. Slices: genie → analytics.

### Ops console (multi-plugin)

`{ reads_warehouse, writes_oltp, files, genie }` → `--features analytics,lakebase,files,genie`

Gates: write_path, genie_space, lakebase_resources; skip read_path if user wants warehouse dashboards.

Slice order: genie space → lakebase scaffold replace → SQL/typegen → files volumes → UI.

**UI:** Separate surfaces — dashboard | chat | files | CRUD (do not merge into one data hook).

### Serving chatbot

`{ serving }` (+ optional `writes_oltp` for chat history) → `--features serving` or `serving,lakebase`

Use **`databricks-model-serving`** skill to create the endpoint first.

## Checklist slices

Union slices for every flag in the capability set. See [Lifecycle](lifecycle.md) for ordering.

### Slice: `reads_warehouse`

- [ ] `config/queries/*.sql` (SELECT only — not DML)
- [ ] `npm run typegen` — verify types in `appKitTypes.d.ts`
- [ ] UI with `queryKey` / `useAnalyticsQuery`
- [ ] → [SQL Queries](sql-queries.md), [Frontend](frontend.md)

### Slice: `reads_synced`

- [ ] Synced table exists; SP granted SELECT — **`databricks-lakebase`** skill
- [ ] Read-only Express routes — never write to synced tables
- [ ] → [Lakebase Synced Reads](lakebase-synced-reads.md)

### Slice: `writes_oltp`

- [ ] Replace scaffold todo boilerplate; use `setupXRoutes<T>(appkit)` — no `AppKitWithLakebase`
- [ ] Schema + CRUD in `onPluginsReady`
- [ ] Frontend uses `fetch('/api/...')` — not `useAnalyticsQuery`
- [ ] Deploy before local dev
- [ ] → [Lakebase OLTP](lakebase-oltp.md)

### Slice: `writes_delta`

- [ ] `[server(), analytics({})]` plugins
- [ ] One route per mutation; fixed SQL + Zod — never client SQL
- [ ] → [Warehouse Mutations](warehouse-mutations.md)

### Slice: `writes_via_job`

- [ ] Job exists — **`databricks-jobs`** skill to author; app only triggers
- [ ] → [Jobs](jobs.md)

### Slice: `genie`

- [ ] Space + tables wired before or during init
- [ ] → [Genie workflow](#genie-workflow), [Genie](genie.md)

### Slice: `files` / `serving`

- [ ] Manifest `--set` + volume or endpoint env vars
- [ ] → [Files](files.md) or [Model Serving](model-serving.md)

### All AppKit apps

- [ ] Update `tests/smoke.spec.ts` **before first** `databricks apps validate`
- [ ] → [Testing](../testing.md)

## Genie workflow

Do **not** start by asking for a Space ID.

1. Ask which UC tables (`catalog.schema.table`).
2. Ask: reuse existing space or create new?
3. If creating: warehouse + `databricks genie create-space` — see [Genie](genie.md).
4. If reusing: `databricks genie list-spaces`.
5. Scaffold with `--features genie` (+ others) — derive `--set` from manifest.

## Scaffolding

1. `databricks apps manifest --profile <PROFILE>` (or `--version`, `--template`).
2. Build `--features` from capability union; add `--set` for every required resource field.
3. **Manifest rules:** Gather rules for selected plugins only. Apply automatically. **STOP and ask user only** if a plugin `must` contradicts a template `never`. Do not dump the full rule list unless there is a conflict.
4. Init:

```bash
databricks apps init --name <NAME> --features <plugin1>,<plugin2> \
  --set <plugin>.<resourceKey>.<field>=<value> \
  --description "<DESC>" --run none --profile <PROFILE>
```

**DO NOT guess** plugin keys or `--set` paths — derive from manifest.

**Common mistake:** `databricks apps init --features analytics my-app` — name must be `--name my-app`.

## Leave this skill when…

| Task | Skill |
|------|-------|
| Create Lakebase **project**, synced table pipeline, SP grants | **`databricks-lakebase`** |
| Create model serving **endpoint** | **`databricks-model-serving`** |
| Author Lakeflow **job** definition | **`databricks-jobs`** |
| Wire endpoints/routes into AppKit app | Stay here |

## State storage (Lakebase OLTP)

When `writes_oltp` is in the set:

1. Use **`databricks-lakebase`** skill to create/obtain project, branch, database.
2. All three `--set lakebase.postgres.{project,branch,database}` from manifest.
3. If also `reads_warehouse` or `reads_synced`, complete [Read path](#read-path) for the lakehouse read side.

Do **not** add Lakebase to read-only dashboards unless the user requests persistent storage.
