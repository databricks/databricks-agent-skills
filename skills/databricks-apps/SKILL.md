---
name: databricks-apps
description: Build apps on Databricks Apps platform. Use when asked to create dashboards, data apps, analytics tools, or visualizations. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.1.1"
parent: databricks-core
---

# Databricks Apps Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Build apps that deploy to Databricks Apps platform.

## Required Reading by Phase

| Phase | READ BEFORE proceeding |
|-------|------------------------|
| Scaffolding | Parent `databricks-core` skill (auth, warehouse discovery); run `databricks apps manifest` and use its plugins/resources to build `databricks apps init` with `--features` and `--set` (see AppKit section below) |
| Writing SQL queries | [SQL Queries Guide](references/appkit/sql-queries.md) |
| Writing UI components | [Frontend Guide](references/appkit/frontend.md) |
| Using `useAnalyticsQuery` | [AppKit SDK](references/appkit/appkit-sdk.md) |
| Adding API endpoints | [tRPC Guide](references/appkit/trpc.md) |
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
- **Authentication**: covered by parent `databricks-core` skill.
- **AppKit API surface — consult `appkit docs` first, never write call sites from memory**: Before writing any non-trivial server-side code that calls AppKit APIs (`createApp`, plugin shapes, query primitives, `useAnalyticsQuery` config, `pool.query` types, etc.), run `npx @databricks/appkit docs <section>` and quote the actual API signature in your plan. The agent's training data has older AppKit shapes baked in, and `databricks apps validate` runs `tsc --noEmit` — a single invented signature (e.g. `createApp({setup: ...})` when the real config takes only `plugins / telemetry / cache / client`) fails the validate step even when build, types, and lint otherwise pass. The docs (also published to npm) are versioned with the installed AppKit and are the authoritative source.
- **Smoke test selectors — use only documented Playwright APIs**: `getByRole`, `getByText`, `getByPlaceholder`, `getByLabel` (NOT `getByLabelText` — that's a React Testing Library API, not Playwright). An invented selector throws `TypeError: page.getByX is not a function` at runtime and the smoke step fails before any UI assertion runs. When in doubt, see https://playwright.dev/docs/api/class-page or `npx playwright codegen`.
- **Smoke test data — keep query results under the 1 MB analytics event limit**: `useAnalyticsQuery` and the analytics plugin enforce a per-event payload cap; queries returning thousands of rows trip `INVALID_REQUEST: Event exceeds max size of 1048576 bytes` and the in-page request aborts with `net::ERR_ABORTED`, leaving every UI element your smoke spec asserts on absent. For smoke tests, either `LIMIT 500` the underlying SQL or use an aggregated/grouped query that returns one row per category — never raw row dumps.

## Project Structure (after `databricks apps init --features analytics`)
- `client/src/App.tsx` — main React component (start here)
- `config/queries/*.sql` — SQL query files (queryKey = filename without .sql)
- `server/server.ts` — backend entry (tRPC routers)
- `tests/smoke.spec.ts` — smoke test (⚠️ MUST UPDATE selectors for your app)
- `client/src/appKitTypes.d.ts` — auto-generated types (`npm run typegen`)

## Project Structure (after `databricks apps init --features lakebase`)
- `server/server.ts` — backend with Lakebase pool + tRPC routes
- `client/src/App.tsx` — React frontend
- `app.yaml` — manifest with `database` resource declaration
- `package.json` — includes `@databricks/lakebase` dependency
- Note: **No `config/queries/`** — Lakebase apps use `pool.query()` in tRPC, not SQL files

## Data Discovery

Before writing any SQL, use the parent `databricks-core` skill for data exploration — search `information_schema` by keyword, then batch `discover-schema` for the tables you need. Do NOT skip this step.

## Development Workflow (FOLLOW THIS ORDER)

**Analytics apps** (`--features analytics`):

1. Create SQL files in `config/queries/`
2. Run `npm run typegen` — verify all queries show ✓
3. Read `client/src/appKitTypes.d.ts` to see generated types
4. **THEN** write `App.tsx` using the generated types
5. Update `tests/smoke.spec.ts` selectors
6. Run `databricks apps validate --profile <PROFILE>`

**DO NOT** write UI code before running typegen — types won't exist and you'll waste time on compilation errors.

**Lakebase apps** (`--features lakebase`): No SQL files or typegen. See [Lakebase Guide](references/appkit/lakebase.md) for the tRPC pattern: initialize schema at startup, write procedures in `server/server.ts`, then build the React frontend.

## When to Use What
- **Read analytics data → display in chart/table**: Use visualization components with `queryKey` prop
- **Read analytics data → custom display (KPIs, cards)**: Use `useAnalyticsQuery` hook
- **Read analytics data → need computation before display**: Still use `useAnalyticsQuery`, transform client-side
- **Read/write persistent data (users, orders, CRUD state)**: Use Lakebase pool via tRPC — see [Lakebase Guide](references/appkit/lakebase.md)
- **Natural language query interface over tables (Genie)**: Use `genie()` plugin — see [Genie Guide](references/appkit/genie.md)
- **Call ML model endpoint**: Use tRPC — see [Model Serving Guide](references/appkit/model-serving.md)
- **Trigger or monitor a Lakeflow Job from the app**: Use the `jobs()` plugin — see [Jobs Guide](references/appkit/jobs.md)
- **⚠️ NEVER use tRPC to run SELECT queries against the warehouse** — always use SQL files in `config/queries/`
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
