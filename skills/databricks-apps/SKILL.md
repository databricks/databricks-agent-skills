---
name: databricks-apps
description: "Build apps on Databricks Apps platform. Use when asked to create dashboards, data apps, analytics tools, or visualizations. Evaluates data access patterns (analytics vs Lakebase synced tables) before scaffolding. Invoke BEFORE starting implementation."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.1.2"
parent: databricks-core
---

# Databricks Apps Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Build apps that deploy to Databricks Apps platform.

## Pick your write path first

When the app must **persist or mutate data**, choose the backend before scaffolding or adding routes. Do not default every form to Lakebase or every save to Delta — match where the data must live.

| Need | Write path | Read next |
|------|------------|-----------|
| App-owned state (forms, CRUD, todos, sessions) — Postgres is the system of record | Custom route in `onPluginsReady` + `appkit.lakebase.query()` | [Lakebase Guide](references/appkit/lakebase.md) |
| User action must update an **existing Delta / UC table now** (small scoped DML) | Custom route + `appkit.analytics.query()` with fixed SQL + Zod | [Warehouse Mutations Guide](references/appkit/warehouse-mutations.md) |
| Large, multi-step, or async lakehouse write (batch ETL, heavy MERGE) | Custom route validates input → `jobs()` plugin runs a job | [Jobs Guide](references/appkit/jobs.md) |
| App writes Postgres; curated data should appear in Delta **later** (async OK) | Lakebase OLTP write + [Lakehouse Sync](../databricks-lakebase/references/lakehouse-sync.md) (UI-only) | **`databricks-lakebase`** skill |
| Read-only dashboard / KPI from warehouse | No write path — `config/queries/` + `useAnalyticsQuery` | [SQL Queries Guide](references/appkit/sql-queries.md) |

**If unclear**, ask: *Should this data live in Postgres (app state), in Delta/UC (lakehouse), or run as a background job?*

Route mechanics (Express + `onPluginsReady`) are the same for all mutation paths — see [Custom Endpoints Guide](references/appkit/custom-endpoints.md).

## Required Reading by Phase

| Phase | READ BEFORE proceeding |
|-------|------------------------|
| Scaffolding | **⚠️ STOP — complete *Pick your write path first* (if the app writes data), State Storage Guidance, and the Data Access Decision Gate below before scaffolding.** Parent `databricks-core` skill (auth, warehouse discovery); then run `databricks apps manifest` + `databricks apps init` with `--features` and `--set` (see AppKit section below) |
| Writing SQL queries | [SQL Queries Guide](references/appkit/sql-queries.md) |
| Writing UI components | [Frontend Guide](references/appkit/frontend.md) |
| Using `useAnalyticsQuery` | [AppKit SDK](references/appkit/appkit-sdk.md) |
| Adding API endpoints | [Custom Endpoints Guide](references/appkit/custom-endpoints.md) |
| Writing to Delta / UC tables (warehouse DML) | [Warehouse Mutations Guide](references/appkit/warehouse-mutations.md) |
| Using Lakebase (OLTP database) | [Lakebase Guide](references/appkit/lakebase.md) |
| Adding Genie chat / Genie-powered apps | [Genie Guide](references/appkit/genie.md) — follow the Genie agent workflow below |
| Using Model Serving (ML inference) | [Model Serving Guide](references/appkit/model-serving.md) |
| Typed data contracts (proto-first design) | [Proto-First Guide](references/appkit/proto-first.md) and [Plugin Contracts](references/appkit/proto-contracts.md) |
| Managing files in UC Volumes | [Files Guide](references/appkit/files.md) |
| Triggering / monitoring Lakeflow Jobs from the app | [Jobs Guide](references/appkit/jobs.md) |
| Platform rules (permissions, deployment, limits) | [Platform Guide](references/platform-guide.md) — READ for ALL apps including AppKit |
| Non-AppKit app (Streamlit, FastAPI, Flask, Gradio, Next.js, etc.) | [Other Frameworks](references/other-frameworks.md) |

## Generic Guidelines

- **App name**: ≤26 characters, lowercase letters/numbers/hyphens only (no underscores). dev- prefix adds 4 chars, max 30 total.
- **Validation**: `databricks apps validate --profile <PROFILE>` before deploying.
- **Smoke tests** (AppKit only): ALWAYS update `tests/smoke.spec.ts` selectors BEFORE running validation. Default template checks for "Minimal Databricks App" heading and "hello world" text — these WILL fail in your custom app. See [testing guide](references/testing.md).
- **Smoke test selectors**: use only Playwright locator APIs — `getByRole`, `getByText`, `getByPlaceholder`, `getByLabel`. `getByLabelText` does not exist in Playwright (it is a React Testing Library method) and throws `TypeError` at runtime. See [testing guide](references/testing.md) or `npx playwright codegen`.
- **Smoke test data**: keep result sets under the 1 MB analytics-event payload cap. Queries returning thousands of rows cause `INVALID_REQUEST: Event exceeds max size of 1048576 bytes` and `net::ERR_ABORTED`, leaving every asserted UI element absent. Use `LIMIT` or an aggregated query (e.g. `COUNT(*) GROUP BY status`) — never raw row dumps.
- **AppKit version**: never override the `@databricks/appkit` or `@databricks/appkit-ui` version in `package.json` — `databricks apps init` sets the correct version. Do not run `npm install @databricks/appkit@<version>` unless explicitly asked by the user. If you need a different version, re-scaffold with `databricks apps init --version <version>`.
- **Authentication**: covered by parent `databricks-core` skill.
- **AppKit API surface**: before writing code that calls AppKit APIs (`createApp`, plugin shapes, `useAnalyticsQuery`, etc.), run `npx @databricks/appkit docs <section>` and use the actual signature. Training data has stale shapes; a single invented signature fails `tsc --noEmit` during validate. The docs ship with the installed AppKit and are the authoritative source.
- **TypeScript casts**: never use `as unknown as <T>` double-assertions — `appkit lint` enforces `no-double-type-assertion` and one violation fails the entire validate step. Instead: narrow with Zod (`z.infer<typeof schema>`), use a runtime type guard, or write a typed mapper function. If a query result needs reshaping, type the row schema via queryKey types rather than casting.

## Project Structure (after `databricks apps init --features analytics`)
- `client/src/App.tsx` — main React component (start here)
- `config/queries/*.sql` — SQL query files (queryKey = filename without .sql)
- `server/server.ts` — backend entry (`onPluginsReady` + Express routes)
- `tests/smoke.spec.ts` — smoke test (⚠️ MUST UPDATE selectors for your app)
- `client/src/appKitTypes.d.ts` — auto-generated types (`npm run typegen`)

## Project Structure (after `databricks apps init --features lakebase`)
- `server/server.ts` — backend with Lakebase pool + Express routes
- `client/src/App.tsx` — React frontend
- `app.yaml` — manifest with `database` resource declaration
- `package.json` — includes `@databricks/lakebase` dependency
- Note: **No `config/queries/`** — Lakebase apps use `appkit.lakebase.query()` in Express routes, not SQL files

## Data Discovery

Before writing any SQL, use the parent `databricks-core` skill for data exploration — search `information_schema` by keyword, then batch `discover-schema` for the tables you need. Do NOT skip this step.

**State Storage Guidance (evaluate BEFORE the Decision Gate):**

If the user's app description involves storing or persisting data — forms, CRUD operations, user submissions, orders, todos, or other user-generated content — use *Pick your write path first* above. **Lakebase is the default for app-owned OLTP state**, but Delta DML or Jobs may be correct if the user needs writes to land in Unity Catalog or run asynchronously.

1. **Ask the user** where writes must land (Postgres app state vs Delta/UC table vs background job) before scaffolding. Do not silently add Lakebase or warehouse DML.
2. If Lakebase is chosen, use the **`databricks-lakebase`** skill to create a Lakebase project and obtain resource names.
3. Run `databricks apps manifest --profile <PROFILE>` and derive **all three** required Lakebase `--set` fields from the `lakebase` plugin's `postgres` resource (`project`, `branch`, `database` — do not guess keys or omit `project`):
   ```bash
   --set lakebase.postgres.project=<PROJECT_NAME> \
   --set lakebase.postgres.branch=<BRANCH_NAME> \
   --set lakebase.postgres.database=<DATABASE_NAME>
   ```
   Values are full resource paths (e.g. `projects/<id>`, `projects/<id>/branches/<id>`, `projects/<id>/branches/<id>/databases/<id>`). Discover them with `databricks postgres list-projects`, `list-branches`, and `list-databases` — field descriptions in the manifest match those commands.
4. If the app **also** reads from Unity Catalog tables, proceed to the Data Access Decision Gate below to determine whether to add `--features analytics` or use Lakebase synced tables.

Do NOT add Lakebase to analytics, dashboard, or visualization apps unless the user explicitly requests persistent write-back storage. Read-only data display, filters, and preferences do not require a database.

## Development Workflow (FOLLOW THIS ORDER)

**Data Access Decision Gate (REQUIRED before scaffolding):**

If the app reads from Unity Catalog / lakehouse tables, you MUST show the comparison below to the user and ask them to choose. Do not skip this. Do not choose for them.

| | **(A) Lakebase synced tables** | **(B) Analytics** |
|--|---|---|
| Speed | Sub-second responses | Takes a few seconds |
| Best for | Full-text search, typeahead, autocomplete, real-time lookups, operational apps | Dashboards, charts, aggregations, KPIs, filtered queries, browsing |
| How it works | Data synced from Delta into Lakebase Postgres | Queries run on SQL warehouse at read time |

After showing the table, add a brief recommendation. Default to recommending Analytics (B) for most read-only apps — dashboards, charts, filtered queries, browsing, and aggregations. Recommend Lakebase synced tables (A) only when the app needs sub-second latency for full-text search, typeahead/autocomplete, real-time lookups by ID, or operational data serving. Note: "search" or "filter" in a prompt usually means SQL WHERE clauses (Analytics), not full-text search (Lakebase). Always let the user make the final call.

After the user chooses:
- (A) Lakebase synced tables → scaffold with `--features lakebase`. See [Lakebase Guide](references/appkit/lakebase.md) for full workflow.
- (B) Analytics → scaffold with `--features analytics`.
- Both → scaffold with `--features analytics,lakebase` if the app needs both patterns.
- If the app does NOT read Unity Catalog data (pure CRUD, Genie, Model Serving), skip this gate and scaffold with the appropriate `--features` flag.

**Analytics apps** (`--features analytics`):

1. Create SQL files in `config/queries/`
2. Run `npm run typegen` — verify all queries show ✓
3. Read `client/src/appKitTypes.d.ts` to see generated types
4. **THEN** write `App.tsx` using the generated types
5. Update `tests/smoke.spec.ts` selectors
6. Run `databricks apps validate --profile <PROFILE>`

**DO NOT** write UI code before running typegen — types won't exist and you'll waste time on compilation errors.

**Lakebase apps** (`--features lakebase`):

1. Read [Lakebase Guide](references/appkit/lakebase.md) sections **What the scaffold gives you** and **Lakebase route modules — typing** — the template ships todo CRUD boilerplate and a hand-written `AppKitWithLakebase` interface; replace both. For extracted route modules, use generic `setupXRoutes<T>(appkit: T)` called from `onPluginsReady` — do not add `appkit-types.ts`.
2. Initialize schema and register CRUD routes in `onPluginsReady` (see [Lakebase Guide](references/appkit/lakebase.md))
3. Replace scaffold UI (`LakebasePage.tsx`, routes, headings) with your domain — use domain names, not "todo" or "lakebase" in user-facing code
4. Build the React frontend (fetch `/api/...` routes — **not** `useAnalyticsQuery`)
5. Update `tests/smoke.spec.ts` selectors to match your UI (do not assert Lakebase-backed empty states during validate — Lakebase is unavailable locally)
6. Run `databricks apps validate --profile <PROFILE>`

No SQL files or typegen for pure Lakebase CRUD apps.

## When to Use What

After completing the decision gate above, use this routing table:

- **Read analytics data → display in chart/table**: Use visualization components with `queryKey` prop
- **Read analytics data → custom display (KPIs, cards)**: Use `useAnalyticsQuery` hook
- **Read analytics data → need computation before display**: Still use `useAnalyticsQuery`, transform client-side
- **Read lakehouse data at low latency (lookups, search, catalogs)**: Use Lakebase synced tables — see [Lakebase Guide](references/appkit/lakebase.md)
- **Read/write persistent data (users, orders, CRUD state)**: Use Lakebase via Express routes in `onPluginsReady` — see [Lakebase Guide](references/appkit/lakebase.md)
- **Write to Delta / Unity Catalog tables from the app**: Custom endpoint + `appkit.analytics.query()` — see [Warehouse Mutations Guide](references/appkit/warehouse-mutations.md). Prefer Lakebase or Jobs when those fit better.
- **Natural language query interface over tables (Genie)**: Use `genie()` plugin — see [Genie Guide](references/appkit/genie.md)
- **Call ML model endpoint**: Use `serving()` plugin — see [Model Serving Guide](references/appkit/model-serving.md)
- **Trigger or monitor a Lakeflow Job from the app**: Use the `jobs()` plugin — see [Jobs Guide](references/appkit/jobs.md)
- **⚠️ NEVER add custom endpoints to run SELECT queries against the warehouse** — always use SQL files in `config/queries/`
- **⚠️ NEVER use `useAnalyticsQuery` for Lakebase data** — it queries the SQL warehouse only

## Frameworks

### AppKit (Recommended)

TypeScript/React framework with type-safe SQL queries and built-in components.

**Official Documentation** — the source of truth for all API details:

```bash
npx @databricks/appkit docs                              # ← ALWAYS start here to see available pages
npx @databricks/appkit docs <query>                      # view a section by name or doc path
npx @databricks/appkit docs --full                       # full index with all API entries
npx @databricks/appkit docs "appkit-ui API reference"    # example: section by name
npx @databricks/appkit docs ./docs/plugins/analytics.md  # example: specific doc file
```

**DO NOT guess doc paths.** Run without args first, pick from the index. The `<query>` argument accepts both section names (from the index) and file paths. Docs are the authority on component props, hook signatures, and server APIs — skill files only cover anti-patterns and gotchas.

**App Manifest and Scaffolding**

**Agent workflow for scaffolding: get the manifest first, then build the init command.**

1. **Get the manifest** (JSON schema describing plugins and their resources):
   ```bash
   databricks apps manifest --profile <PROFILE>
   # See plugins available in a specific AppKit version:
   databricks apps manifest --version <VERSION> --profile <PROFILE>
   # Custom template:
   databricks apps manifest --template <GIT_URL> --profile <PROFILE>
   ```
   The output defines:
   - **Plugins**: each has a key (plugin ID for `--features`), plus `requiredByTemplate`, and `resources`.
   - **requiredByTemplate**: If **true**, that plugin is **mandatory** for this template — do **not** add it to `--features` (it is included automatically); you must still supply all of its required resources via `--set`. If **false** or absent, the plugin is **optional** — add it to `--features` only when the user's prompt indicates they want that capability (e.g. analytics/SQL), and then supply its required resources via `--set`.
   - **Resources**: Each plugin has `resources.required` and `resources.optional` (arrays). Each item has `resourceKey` and `fields` (object: field name → description/env). Use `--set <plugin>.<resourceKey>.<field>=<value>` for each required resource field of every plugin you include.

2. **Scaffold** (DO NOT use `npx`; use the CLI only):
   ```bash
   databricks apps init --name <NAME> --features <plugin1>,<plugin2> \
     --set <plugin1>.<resourceKey>.<field>=<value> \
     --set <plugin2>.<resourceKey>.<field>=<value> \
     --description "<DESC>" --run none --profile <PROFILE>
   # --run none: skip auto-run after scaffolding (review code first)
   # With custom template:
   databricks apps init --template <GIT_URL> --name <NAME> --features ... --set ... --profile <PROFILE>
   ```
   Optionally use `--version <VERSION>` to target a specific AppKit version.
   - **Required**: `--name`, `--profile`. Name: ≤26 chars, lowercase letters/numbers/hyphens only. Use `--features` only for **optional** plugins the user wants (plugins with `requiredByTemplate: false` or absent); mandatory plugins must not be listed in `--features`.
   - **Resources**: Pass `--set` for every required resource (each field in `resources.required`) for (1) all plugins with `requiredByTemplate: true`, and (2) any optional plugins you added to `--features`. Add `--set` for `resources.optional` only when the user requests them.
   - **Discovery**: Use the parent `databricks-core` skill to resolve IDs (e.g. warehouse: `databricks warehouses list --profile <PROFILE>` or `databricks experimental aitools tools get-default-warehouse --profile <PROFILE>`).

**DO NOT guess** plugin names, resource keys, or property names — always derive them from `databricks apps manifest` output. Example: if the manifest shows plugin `analytics` with a required resource `resourceKey: "sql-warehouse"` and `fields: { "id": ... }`, include `--set analytics.sql-warehouse.id=<ID>`.

**Scaffolding Rules Protocol** — `databricks apps manifest` may emit `scaffolding.rules` at the template level (top-level `scaffolding.rules`) and on individual plugins (`plugins[].scaffolding.rules`). Each block has `must` / `should` / `never` arrays of short directive strings. Consume them as follows:

1. **Gather** — for every plugin in your final `--features` list AND every plugin with `requiredByTemplate: true`, read `plugins[].scaffolding.rules`. Union those with the top-level template `scaffolding.rules` into one working set, tagged by source (template vs `<plugin>`).
2. **Precedence** — manifest rules override the directives baked into this skill. Where the manifest is silent on a topic, this skill's content is the floor.
3. **Phase ordering** — rules whose text begins with `Before init` MUST be executed before `databricks apps init`. Rules beginning with `After init` MUST be executed after init completes (e.g. migrations, typegen, connectivity checks). Rules without a phase prefix apply throughout the scaffold/develop loop.
4. **Conflict detection** — if a plugin `must` rule contradicts a template `never` rule on the same target (or vice versa), STOP and ask the user which to follow before proceeding. Do not silently pick one. Treat `must` vs `never` on the same action as a conflict; `should` is advisory and does not block.
5. **Reporting** — before running `databricks apps init`, surface the merged working set to the user grouped by phase (Before init / After init / Always) and by severity (must / should / never), so the active guardrails are explicit.

**READ [AppKit Overview](references/appkit/overview.md)** for project structure, workflow, and pre-implementation checklist.

**Genie Agent Workflow** — when the user wants a Genie-powered app, do **not** start by asking for a Genie Space ID. Instead:

1. Ask which Unity Catalog tables the app should query (fully qualified: `catalog.schema.table`).
2. Ask whether to reuse an existing Genie space or create a new one.
3. If creating: discover the warehouse, then create the space with `databricks genie create-space` (see [Genie Guide](references/appkit/genie.md) for syntax and serialized space format).
4. If reusing: discover existing spaces with `databricks genie list-spaces --profile <PROFILE>` and let the user pick.
5. Scaffold or wire the space ID into the app — derive `--set` keys from `databricks apps manifest`.

Read the [Genie Guide](references/appkit/genie.md) for configuration, SSE endpoints, and frontend integration.

### Common Scaffolding Mistakes

```bash
# ❌ WRONG: name is NOT a positional argument
databricks apps init --features analytics my-app-name
# → "unknown command" error

# ✅ CORRECT: use --name flag
databricks apps init --name my-app-name --features analytics --set "..." --profile <PROFILE>
```

### Directory Naming

`databricks apps init` creates directories in kebab-case matching the app name.
App names must be lowercase with hyphens only (≤26 chars).

### Other Frameworks (Streamlit, FastAPI, Flask, Gradio, Dash, Next.js, etc.)

Databricks Apps supports any framework that runs as an HTTP server. LLMs already know these frameworks — the challenge is Databricks platform integration.

**READ [Other Frameworks Guide](references/other-frameworks.md) BEFORE building any non-AppKit app.** It covers port/host configuration, `app.yaml` and `databricks.yml` setup, dependency management, networking, and framework-specific gotchas.

## Deployment Workflow (FOLLOW THIS ORDER)

⚠️ **USER CONSENT REQUIRED** — always confirm with the user before deploying. See [Platform Guide](references/platform-guide.md) for permissions, destructive updates, and runtime limits.

### First deploy (app does not exist in workspace yet)

A freshly scaffolded app has bundle config but **no workspace app resource** until you deploy the bundle. Running `databricks apps deploy` alone often fails with **app does not exist**.

1. **Register the app resource**: `databricks bundle deploy -t <TARGET> --profile <PROFILE>`
2. **Deploy code and start the app** (pick one):
   - **Recommended**: `databricks apps deploy -t <TARGET> --profile <PROFILE>` (validates, uploads, applies config, restarts)
   - **Alternative**: `databricks bundle run <APP_RESOURCE_NAME> -t <TARGET> --profile <PROFILE>` after `bundle deploy`
3. **Lakebase OLTP apps only**: after the first successful deploy, the Service Principal owns the schema. Do **not** run `npm run dev` against Lakebase until step 2 succeeds — see [Lakebase Guide](references/appkit/lakebase.md) *Local Development*.

Check whether the app exists: `databricks apps get <APP_NAME> --profile <PROFILE>` — if `active_deployment` is missing, you are still on the first-deploy path.

### Subsequent deploys (app already exists)

1. `databricks apps validate --profile <PROFILE>`
2. `databricks apps deploy -t <TARGET> --profile <PROFILE>`

`databricks bundle deploy` alone uploads bundle assets but **does not** restart the app or apply all config changes. After `bundle deploy`, also run `databricks apps deploy` or `databricks bundle run <APP_RESOURCE_NAME>`.

### When deploy-first is mandatory vs optional

| App type | Deploy before local dev? |
|----------|--------------------------|
| **Lakebase OLTP CRUD** (app creates schema/tables) | **Yes** — SP must create and own the schema |
| **Lakebase synced-table reads only** | No — synced tables already exist; grant SP `SELECT` after deploy |
| **Analytics-only** | No — warehouse queries work locally with profile auth |
| **Hybrid** (analytics + Lakebase CRUD) | **Yes** — because of the CRUD side |

### Post-Deploy Verification

After deploying, verify the app is running:

```bash
databricks apps get <app-name> --profile <PROFILE> -o json   # Check app_status.state: RUNNING
databricks apps logs <app-name> --follow --profile <PROFILE>  # Stream live logs (Ctrl+C to stop)
```

> **Note:** `databricks apps logs` requires OAuth authentication and does not work with PAT. Use `databricks apps get` for status checks if using PAT auth.
