# AppKit Development Lifecycle

Ordering for scaffold → develop → validate → deploy. Capability-specific steps — see [Data Patterns](data-patterns.md) for which apply.

> **Agentic mode:** scaffold and deploy are handled externally — skip both. No smoke tests. `npm run dev` runs against **live** injected resources, so the Lakebase deploy-first rule and "don't assert Lakebase rows locally" caveat below **do not apply**. You still run `databricks apps validate` (no `--profile`). See [Environments](environments.md).

## Phase order by capability

**All apps:** Prerequisites (profile + CLI via `databricks-core`) → Gates (conditional — [Data Patterns](data-patterns.md)) → Scaffold (`manifest` → `apps init --run none`) → First code (**update smoke tests first**) → Validate (`databricks apps validate`) → Deploy (user consent).

Capability-specific ordering layered on top:

- **`reads_warehouse`** — SQL files + `npm run typegen` before building UI; deploy is optional before `npm run dev`.
- **`writes_oltp`** — replace the scaffold and put schema init + routes in `onPluginsReady`; **deploy before local dev** (the SP must own the schema first); don't assert Lakebase rows in local validate.
- **`genie`** — create or reuse the space before/with init.

**Hybrid apps** (e.g. analytics + lakebase + genie): follow the **strictest** rule — e.g. deploy-before-dev, because OLTP requires it.

## Recommended slice order (multi-plugin)

After init, when several capabilities are active:

1. Genie space (if `genie`)
2. Lakebase schema/routes + first deploy (if `writes_oltp`)
3. Analytics SQL + typegen (if `reads_warehouse`)
4. Files / serving plugin config (if present)
5. Frontend — **separate UI surfaces** per capability
6. Smoke tests → validate

## First deploy

⚠️ **USER CONSENT REQUIRED** before any deploy. See [Platform Guide](../platform-guide.md).

A new scaffold has bundle config but **no workspace app** until bundle deploy. `databricks apps deploy` alone often fails with **app does not exist**.

1. `databricks bundle deploy -t <TARGET> --profile <PROFILE>`
2. `databricks apps deploy -t <TARGET> --profile <PROFILE>` (or `bundle run <APP_RESOURCE>`)

Check: `databricks apps get <APP_NAME> --profile <PROFILE>` — missing `active_deployment` means first-deploy path.

**Lakebase OLTP:** do not run `npm run dev` against Lakebase until step 2 succeeds — SP must own the schema first.

## Subsequent deploys

1. `databricks apps validate --profile <PROFILE>`
2. `databricks apps deploy -t <TARGET> --profile <PROFILE>`

`bundle deploy` alone does not restart the app — follow with `apps deploy` when config/code changed.

## Deploy before local dev?

| Mix | Deploy before `npm run dev`? |
|-----|------------------------------|
| Analytics only | No |
| Lakebase synced reads only | No (grant SP after deploy) |
| Lakebase OLTP CRUD | **Yes** |
| Hybrid with OLTP writes | **Yes** |
| Genie / serving / files only (no OLTP) | No |

## Post-deploy verification

```bash
databricks apps get <app-name> --profile <PROFILE> -o json   # app_status.state: RUNNING
databricks apps logs <app-name> --follow --profile <PROFILE>   # OAuth required; not PAT
```
