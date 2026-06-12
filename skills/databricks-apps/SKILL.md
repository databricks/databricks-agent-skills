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

**For data UI design (required for any data-displaying app)**: if the app shows ANY data — a dashboard, KPI/overview page, report, chart, table, query results, OR a **conversational / chat / Genie natural-language assistant** — you MUST use the `databricks-app-design` skill (alongside this one) to decide layout, charts, KPIs, semantic color, required states, and AI-result trust, and map them to AppKit components. This includes chat/Genie apps, not just dashboards — if in doubt, use it.

Build apps that deploy to Databricks Apps platform.

## Required Reading by Phase

| Phase | READ BEFORE proceeding |
|-------|------------------------|
| Scaffolding | **⚠️ STOP — review the State Storage Guidance and complete the Data Access Decision Gate below before scaffolding.** Parent `databricks-core` skill (auth, warehouse discovery); then run `databricks apps manifest` + `databricks apps init` with `--features` and `--set` (see AppKit section below) |
| Writing SQL queries | [SQL Queries Guide](references/appkit/sql-queries.md) |
| Writing UI components | [Frontend Guide](references/appkit/frontend.md) |
| Using `useAnalyticsQuery` | [AppKit SDK](references/appkit/appkit-sdk.md) |
| Adding API endpoints | [Custom Endpoints Guide](references/appkit/custom-endpoints.md) |
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

If the user's app description involves storing or persisting data — forms, CRUD operations, user submissions, orders, todos, or other user-generated content — the app likely needs a Lakebase database.

1. **Ask the user** whether the app needs persistent storage (Lakebase) before scaffolding. Do not silently add Lakebase.
2. If confirmed, use the **`databricks-lakebase`** skill to create a Lakebase project and obtain the branch and database resource names.
3. Scaffold with `--features lakebase` and pass `--set lakebase.postgres.branch=<BRANCH_NAME> --set lakebase.postgres.database=<DATABASE_NAME>`.
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

**Lakebase apps** (`--features lakebase`): No SQL files or typegen. See [Lakebase Guide](references/appkit/lakebase.md) for the `onPluginsReady` pattern: initialize schema at startup, register Express routes in `server/server.ts`, then build the React frontend.

## When to Use What

After completing the decision gate above, use this routing table:

- **Read analytics data → display in chart/table**: Use visualization components with `queryKey` prop
- **Read analytics data → custom display (KPIs, cards)**: Use `useAnalyticsQuery` hook
- **Read analytics data → need computation before display**: Still use `useAnalyticsQuery`, transform client-side
- **Read lakehouse data at low latency (lookups, search, catalogs)**: Use Lakebase synced tables — see [Lakebase Guide](references/appkit/lakebase.md)
- **Read/write persistent data (users, orders, CRUD state)**: Use Lakebase via Express routes in `onPluginsReady` — see [Lakebase Guide](references/appkit/lakebase.md)
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

### Post-Deploy Verification

After deploying, verify the app is running:

```bash
databricks apps get <app-name> --profile <PROFILE> -o json   # Check app_status.state: RUNNING
databricks apps logs <app-name> --follow --profile <PROFILE>  # Stream live logs (Ctrl+C to stop)
```

> **Note:** `databricks apps logs` requires OAuth authentication and does not work with PAT. Use `databricks apps get` for status checks if using PAT auth.
