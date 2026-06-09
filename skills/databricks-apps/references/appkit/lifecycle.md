# AppKit Development Lifecycle

Ordering for scaffold → develop → validate → deploy. Capability-specific steps — see [Data Patterns](data-patterns.md) for which apply.

## Phase order by capability

| Phase | `reads_warehouse` | `writes_oltp` | `genie` | All apps |
|-------|-------------------|---------------|---------|----------|
| Prerequisites | | | | Profile + CLI (`databricks-core`) |
| Gates | data_discovery | write_path, deploy-first | genie_space | Conditional — [Data Patterns](data-patterns.md) |
| Scaffold | | | space before/with init | `manifest` → `apps init --run none` |
| First code | SQL files + typegen | replace scaffold, `onPluginsReady` | wire plugin | Update smoke tests **first** |
| First deploy | optional before dev | **required before local dev** | after init | See [First deploy](#first-deploy) |
| Local dev | `npm run dev` | after deploy | | |
| Validate | | don't assert Lakebase rows locally | | `databricks apps validate` |
| Deploy | user consent | | | See below |

**Hybrid apps** (e.g. analytics + lakebase + genie): follow the **strictest** row per phase (e.g. deploy-before-dev because of OLTP).

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
