---
name: databricks-apps
description: Build apps on Databricks Apps platform. Use when asked to create dashboards, data apps, analytics tools, or visualizations. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.1.1"
parent: databricks
---

# Databricks Apps Development

**FIRST**: Use the parent `databricks` skill for CLI basics, authentication, and profile selection.

Build apps that deploy to Databricks Apps platform.

## Required Reading by Phase

| Phase | READ BEFORE proceeding |
|-------|------------------------|
| Scaffolding | Parent `databricks` skill (auth, warehouse discovery); run `databricks apps manifest` and use its plugins/resources to build `databricks apps init` with `--features` and `--set` (see AppKit section below) |
| Writing SQL queries | [SQL Queries Guide](references/appkit/sql-queries.md) |
| Writing UI components | [Frontend Guide](references/appkit/frontend.md) |
| Using `useAnalyticsQuery` | [AppKit SDK](references/appkit/appkit-sdk.md) |
| Adding API endpoints | [tRPC Guide](references/appkit/trpc.md) |
| Using Lakebase (OLTP database) | [Lakebase Guide](references/appkit/lakebase.md) |
| Non-AppKit app (Streamlit, FastAPI, Flask, Gradio, Next.js,etc.) | [Platform Guide](references/platform-guide.md) |

## Generic Guidelines

- **App name**: ≤26 characters, lowercase letters/numbers/hyphens only (no underscores). dev- prefix adds 4 chars, max 30 total.
- **Validation**: `databricks apps validate --profile <PROFILE>` before deploying.
- **Smoke tests** (AppKit only): ALWAYS update `tests/smoke.spec.ts` selectors BEFORE running validation. Default template checks for "Minimal Databricks App" heading and "hello world" text — these WILL fail in your custom app. See [testing guide](references/testing.md).
- **Authentication**: covered by parent `databricks` skill.

## Platform Rules

These rules apply to ALL Databricks Apps regardless of framework (AppKit, Streamlit, FastAPI, etc.).

### Service Principal Permissions

**The #1 cause of runtime crashes after deployment.**

When your app uses a Databricks resource (SQL warehouse, model serving endpoint, vector search index, volume, secret scope), the app's **service principal** must have explicit permissions on that resource.

#### ⚠️ CRITICAL AGENT BEHAVIOR
After adding ANY resource to the app, IMMEDIATELY grant the SP access. Do NOT wait for a permission error — do it proactively every time.

#### How to Grant Permissions

```bash
# 1. find the app's service principal
databricks apps get <APP_NAME> --profile <PROFILE>
# look for service_principal_id in the output

# 2. grant permissions per resource type:

# SQL Warehouse
databricks warehouses set-permissions <WAREHOUSE_ID> \
  --json '{"access_control_list": [{"service_principal_name": "<SP_NAME>", "permission_level": "CAN_USE"}]}' \
  --profile <PROFILE>

# Model Serving Endpoint
databricks serving-endpoints set-permissions <ENDPOINT_NAME> \
  --json '{"access_control_list": [{"service_principal_name": "<SP_NAME>", "permission_level": "CAN_QUERY"}]}' \
  --profile <PROFILE>

# Secret Scope — deploying user needs MANAGE permission
databricks secrets put-acl <SCOPE> <SP_NAME> READ --profile <PROFILE>

# Unity Catalog resources (tables, volumes, vector search indexes)
# use SQL GRANT statements via a SQL warehouse:
# GRANT SELECT ON TABLE catalog.schema.table TO `<SP_NAME>`
# GRANT READ_VOLUME ON VOLUME catalog.schema.volume TO `<SP_NAME>`
```

#### Permission Matrix

| Resource Type | Permission Level | Notes |
|---------------|-----------------|-------|
| SQL Warehouse | CAN_USE | Minimum for query execution |
| Model Serving Endpoint | CAN_QUERY | For inference calls |
| Vector Search Index | SELECT on underlying table | VS index is a UC securable of type TABLE |
| Volume | READ_VOLUME or WRITE_VOLUME | Via UC GRANT |
| Secret Scope | READ | Deploying user needs MANAGE |
| Feature Table | SELECT | Via UC GRANT |

### Resource Types & Injection

**NEVER hardcode workspace-specific IDs in source code.** Always inject via environment variables with `valueFrom`.

| Resource Type | Default Key | Use Case |
|---------------|-------------|----------|
| SQL Warehouse | `sql-warehouse` | Query compute |
| Model Serving Endpoint | `serving-endpoint` | Model inference |
| Vector Search Index | `vector-search-index` | Semantic search |
| Lakebase Database | `database` | OLTP storage |
| Secret | `secret` | Sensitive values |
| UC Table | `table` | Structured data |
| UC Connection | `connection` | External data sources |
| Genie Space | `genie-space` | AI analytics |
| MLflow Experiment | `experiment` | ML tracking |
| Lakeflow Job | `job` | Data workflows |
| UDF | `function` | SQL/Python functions |
| Databricks App | `app` | App-to-app communication |

```python
# ✅ GOOD
warehouse_id = os.environ["DATABRICKS_WAREHOUSE_ID"]
```

```yaml
# app.yaml / databricks.yml env section
env:
  - name: DATABRICKS_WAREHOUSE_ID
    valueFrom: sql-warehouse
  - name: SERVING_ENDPOINT
    valueFrom: serving-endpoint
```

### Authentication: OBO vs Service Principal

| Context | When Used | Token Source | Cached Per |
|---------|-----------|--------------|------------|
| **Service Principal (SP)** | Default; background tasks, shared data | Auto-injected `DATABRICKS_CLIENT_ID` + `DATABRICKS_CLIENT_SECRET` | All users (shared) |
| **On-Behalf-Of (OBO)** | User-specific data, user-scoped access | `x-forwarded-access-token` header | Per user |

**SP auth** is auto-configured — `WorkspaceClient()` picks up injected env vars.

**OBO** requires extracting the token from request headers and declaring scopes:

| Scope | Purpose |
|-------|---------|
| `sql` | Query SQL warehouses |
| `dashboards.genie` | Manage Genie spaces |
| `files.files` | Manage files/directories |
| `iam.access-control:read` | Read permissions (default) |
| `iam.current-user:read` | Read current user info (default) |

⚠️ Databricks blocks access outside approved scopes even if the user has permission.

### Deployment Workflow

```bash
# 1. validate
databricks apps validate --profile <PROFILE>

# 2. deploy code
databricks bundle deploy -t <TARGET> --profile <PROFILE>

# 3. apply config and start/restart the app
databricks bundle run <APP_RESOURCE_NAME> -t <TARGET> --profile <PROFILE>
```

❌ **Common mistake:** Running only `bundle deploy` and expecting the app to update. Deploy uploads code but does NOT apply config changes or restart the app.

#### ⚠️ Destructive Updates Warning

`databricks apps update` (and `bundle run`) performs a **full replacement**, not a merge:
- Adding a new resource can silently **wipe** existing `user_api_scopes`
- OBO permissions may be stripped on every deployment

**Workaround:** After each deployment, verify OBO scopes are intact.

### Runtime Environment

| Constraint | Value |
|------------|-------|
| Max file size | 10 MB per file |
| Available port | Only `DATABRICKS_APP_PORT` |
| Auto-injected env vars | `DATABRICKS_HOST`, `DATABRICKS_APP_PORT`, `DATABRICKS_APP_NAME`, `DATABRICKS_WORKSPACE_ID`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` |
| No root access | Cannot use `apt-get`, `yum`, or `apk` — use PyPI/npm packages only |
| Graceful shutdown | SIGTERM → 15 seconds to shut down → SIGKILL |
| Logging | Only stdout/stderr are captured — file-based logs are lost on container recycle |
| Filesystem | Ephemeral — no persistent local storage; use UC Volumes/tables |

### Compute & Limits

| Size | RAM | vCPU | DBU/hour | Notes |
|------|-----|------|----------|-------|
| Medium | 6 GB | Up to 2 | 0.5 | Default |
| Large | 12 GB | Up to 4 | 1.0 | Select during app creation or edit |

- No GPU access. Use model serving endpoints for inference.
- Apps must start within **10 minutes** (including dependency installation).
- Max apps per workspace: **100**.

### HTTP Proxy & Streaming

The Databricks Apps reverse proxy enforces a **120-second per-request timeout** (NOT configurable).

| Behavior | Detail |
|----------|--------|
| 504 in app logs? | **No** — the error is generated at the proxy. App logs show nothing. |
| SSE streaming | Responses may be **buffered** and delivered in chunks, not token-by-token |
| WebSockets | Bypass the 120s limit — working but undocumented |

For long-running agent interactions, use **WebSockets** instead of SSE.

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `PERMISSION_DENIED` after deploy | SP missing permissions | Grant SP access to all declared resources |
| App deploys but config doesn't change | Only ran `bundle deploy` | Also run `bundle run <app-name>` |
| `File is larger than 10485760 bytes` | Bundled dependencies | Use requirements.txt / package.json |
| OBO scopes missing after deploy | Destructive update wiped them | Re-apply scopes after each deploy |
| `${var.xxx}` appears literally in env | Variables not resolved in config | Use literal values, not DABs variables |
| 504 Gateway Timeout | Request exceeded 120s | Use WebSockets for long operations |

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

Before writing any SQL, use the parent `databricks` skill for data exploration — search `information_schema` by keyword, then batch `discover-schema` for the tables you need. Do NOT skip this step.

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
- **Call ML model endpoint**: Use tRPC
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
   - **Required**: `--name`, `--profile`. Name: ≤26 chars, lowercase letters/numbers/hyphens only. Use `--features` only for **optional** plugins the user wants (plugins with `requiredByTemplate: false` or absent); mandatory plugins must not be listed in `--features`.
   - **Resources**: Pass `--set` for every required resource (each field in `resources.required`) for (1) all plugins with `requiredByTemplate: true`, and (2) any optional plugins you added to `--features`. Add `--set` for `resources.optional` only when the user requests them.
   - **Discovery**: Use the parent `databricks` skill to resolve IDs (e.g. warehouse: `databricks warehouses list --profile <PROFILE>` or `databricks experimental aitools tools get-default-warehouse --profile <PROFILE>`).

**DO NOT guess** plugin names, resource keys, or property names — always derive them from `databricks apps manifest` output. Example: if the manifest shows plugin `analytics` with a required resource `resourceKey: "sql-warehouse"` and `fields: { "id": ... }`, include `--set analytics.sql-warehouse.id=<ID>`.

**READ [AppKit Overview](references/appkit/overview.md)** for project structure, workflow, and pre-implementation checklist.

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

**READ [Platform Guide](references/platform-guide.md) BEFORE building any non-AppKit app.** It covers port/host configuration, `app.yaml` and `databricks.yml` setup, dependency management, networking, and framework-specific gotchas. For universal platform rules (permissions, deployment, timeouts), see the Platform Rules section above.
