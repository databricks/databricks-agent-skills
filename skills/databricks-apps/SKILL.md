---
name: databricks-apps
description: Build apps on Databricks Apps platform. Use when asked to create dashboards, data apps, analytics tools, or visualizations. Invoke BEFORE starting implementation.
compatibility: Requires databricks CLI (>= 0.250.0)
metadata:
  version: "0.1.0"
parent: databricks
---

# Databricks Apps Development

**FIRST**: Use the parent `databricks` skill for CLI basics, authentication, profile selection, and data exploration commands.

Build apps that deploy to Databricks Apps platform.

## Required Reading by Phase

| Phase | READ BEFORE proceeding |
|-------|------------------------|
| Scaffolding | Parent `databricks` skill (auth, warehouse discovery) |
| Writing SQL queries | [SQL Queries Guide](references/appkit/sql-queries.md) |
| Writing UI components | [Frontend Guide](references/appkit/frontend.md) |
| Using `useAnalyticsQuery` | [AppKit SDK](references/appkit/appkit-sdk.md) |
| Adding API endpoints | [tRPC Guide](references/appkit/trpc.md) |

## Generic Guidelines

These apply regardless of framework:

- **Deployment**: `databricks apps deploy --profile <PROFILE>` (⚠️ USER CONSENT REQUIRED)
- **Validation**: `databricks apps validate` before deploying
- **App name**: Must be ≤26 characters, lowercase letters/numbers/hyphens only (no underscores). dev- prefix adds 4 chars, max 30 total.
- **Smoke tests**: ALWAYS update `tests/smoke.spec.ts` selectors BEFORE running validation. Default template checks for "Minimal Databricks App" heading and "hello world" text — these WILL fail in your custom app. See [testing guide](references/testing.md).
- **Authentication**: covered by parent `databricks` skill

## Project Structure (after `databricks apps init --features analytics`)
- `client/src/App.tsx` — main React component (start here)
- `config/queries/*.sql` — SQL query files (queryKey = filename without .sql)
- `server/server.ts` — backend entry (tRPC routers)
- `tests/smoke.spec.ts` — smoke test (⚠️ MUST UPDATE selectors for your app)
- `client/src/appKitTypes.d.ts` — auto-generated types (`npm run typegen`)

## Development Workflow (FOLLOW THIS ORDER)

1. Create SQL files in `config/queries/`
2. Run `npm run typegen` — verify all queries show ✓
3. Read `client/src/appKitTypes.d.ts` to see generated types
4. **THEN** write `App.tsx` using the generated types
5. Update `tests/smoke.spec.ts` selectors
6. Run `databricks apps validate`

**DO NOT** write UI code before running typegen — types won't exist and you'll waste time on compilation errors.

## When to Use What
- **Read data → display in chart/table**: Use visualization components with `queryKey` prop
- **Read data → custom display (KPIs, cards)**: Use `useAnalyticsQuery` hook
- **Read data → need computation before display**: Still use `useAnalyticsQuery`, transform client-side
- **Call ML model endpoint**: Use tRPC
- **Write/update data (INSERT/UPDATE/DELETE)**: Use tRPC
- **⚠️ NEVER use tRPC to run SELECT queries** — always use SQL files in `config/queries/`

## Frameworks

### AppKit (Recommended)

TypeScript/React framework with type-safe SQL queries and built-in components.

**Official Documentation** — the source of truth for all API details:

```bash
npx @databricks/appkit docs              # ← ALWAYS start here to see available pages
npx @databricks/appkit docs <path>       # then use paths from the index
```

**DO NOT guess doc paths.** Run without args first, pick from the index. Docs are the authority on component props, hook signatures, and server APIs — skill files only cover anti-patterns and gotchas.

**Scaffold** (requires `--warehouse-id`, see parent skill; DO NOT use `npx`):
```bash
databricks apps init --description "<DESC>" --features analytics --warehouse-id <ID> --name <NAME> --run none --profile <PROFILE>
```

**READ [AppKit Overview](references/appkit/overview.md)** for project structure, workflow, and pre-implementation checklist.

### Other Frameworks

Databricks Apps supports any framework that can run as a web server (Flask, FastAPI, Streamlit, Gradio, etc.). Use standard framework documentation - this skill focuses on AppKit.
