---
name: databricks-apps
description: "Build AppKit apps on Databricks: compose analytics, Lakebase OLTP/synced reads, Genie, serving, files, jobs, and custom endpoints. Capability-based scaffolding — invoke BEFORE implementation."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.1.2"
parent: databricks-core
---

# Databricks Apps Development

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Build TypeScript/React apps on the Databricks Apps platform (AppKit). Apps are **compositions of capabilities** — not single archetypes. See [Data Patterns Guide](references/appkit/data-patterns.md) for the full model.

## Agent workflow (follow in order)

### 0. Prerequisites

Profile + CLI via `databricks-core`. Never auto-select a profile.

### 1. Infer capabilities

From the user request, build a capability set (`reads_warehouse`, `writes_oltp`, `genie`, `files`, etc.). Include only what was asked for — do not add Lakebase or analytics by default.

→ [Data Patterns: Capability catalog](references/appkit/data-patterns.md#capability-catalog)

### 2. Run conditional gates

Run gates **only** for capabilities in the set (write path, read path, Genie space, Lakebase resources, data discovery).

→ [Data Patterns: Conditional gates](references/appkit/data-patterns.md#conditional-gates)

### 3. Scaffold

`databricks apps manifest` → derive `--features` (union of plugins) + all `--set` → `databricks apps init --run none`.

Apply manifest scaffolding rules silently; STOP only on `must` vs `never` conflict.

→ [Data Patterns: Scaffolding](references/appkit/data-patterns.md#scaffolding)

### 4. Execute checklist slices

Union the slice checklists for each capability. Follow [Lifecycle](references/appkit/lifecycle.md) for phase order (Genie space → Lakebase deploy → typegen → UI).

→ [Data Patterns: Checklist slices](references/appkit/data-patterns.md#checklist-slices)

**First action after init:** update `tests/smoke.spec.ts` before the first `databricks apps validate`.

### 5. Validate and deploy

Validate locally; deploy with user consent. First deploy: `bundle deploy` then `apps deploy`.

→ [Lifecycle](references/appkit/lifecycle.md)

## Generic guidelines

- **App name**: ≤26 chars, lowercase letters/numbers/hyphens only.
- **Validation**: `databricks apps validate --profile <PROFILE>` before deploying.
- **Smoke tests**: Update selectors before validate — default template expects "Minimal Databricks App". Use Playwright `getByRole`, `getByText`, `getByLabel` — not `getByLabelText`. See [testing guide](references/testing.md).
- **Smoke test data**: Keep analytics payloads under 1 MB — use `LIMIT` or aggregates.
- **AppKit version**: Do not override `@databricks/appkit` in `package.json`; re-scaffold with `--version` if needed.
- **AppKit API surface**: Before first use of an API shape, run `npx @databricks/appkit docs <section>` — do not guess signatures.
- **TypeScript**: No `as unknown as <T>` — use Zod or typed mappers (`appkit lint` enforces this).

## Deep-dive references

| Topic | Guide |
|-------|-------|
| Capabilities, gates, recipes, scaffolding | [Data Patterns](references/appkit/data-patterns.md) |
| Dev / validate / deploy order | [Lifecycle](references/appkit/lifecycle.md) |
| Project structure, visualizations | [Overview](references/appkit/overview.md) |
| Warehouse SELECT queries | [SQL Queries](references/appkit/sql-queries.md) |
| Custom routes | [Custom Endpoints](references/appkit/custom-endpoints.md) |
| Delta/UC DML | [Warehouse Mutations](references/appkit/warehouse-mutations.md) |
| Lakebase OLTP + synced reads | [Lakebase](references/appkit/lakebase.md) |
| Genie | [Genie](references/appkit/genie.md) |
| Model Serving | [Model Serving](references/appkit/model-serving.md) |
| Files | [Files](references/appkit/files.md) |
| Jobs from app | [Jobs](references/appkit/jobs.md) |
| UI components | [Frontend](references/appkit/frontend.md) |
| Platform permissions, resources | [Platform Guide](references/platform-guide.md) |
| Non-AppKit (Streamlit, FastAPI, …) | [Other Frameworks](references/other-frameworks.md) |
| Proto-first / multi-plugin contracts | [Proto-First](references/appkit/proto-first.md) (advanced, optional) |

## AppKit docs (source of truth)

```bash
npx @databricks/appkit docs              # index — start here
npx @databricks/appkit docs <query>      # section name or doc path
```

Skill files cover anti-patterns and Databricks-specific workflow; AppKit docs cover API signatures.

## Common scaffolding mistakes

```bash
# ❌ WRONG — name is not positional
databricks apps init --features analytics my-app-name

# ✅ CORRECT
databricks apps init --name my-app-name --features analytics \
  --set analytics.sql-warehouse.id=<ID> --run none --profile <PROFILE>
```

## Leave this skill when…

Creating Lakebase **projects** / synced tables → **`databricks-lakebase`**. Creating serving **endpoints** → **`databricks-model-serving`**. Authoring Lakeflow **jobs** → **`databricks-jobs`**. Wiring plugins into an app → stay here.
