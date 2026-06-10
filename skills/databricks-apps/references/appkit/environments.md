# Environments: Local vs Agentic Mode

AppKit apps are built in **two environments**. Detect which one you are in **before doing anything else** — the workflow differs.

## Detect first

```bash
echo "${DATABRICKS_APPS_AGENTIC_MODE:-}"
```

- `true` → **Agentic mode**. The app has already been initialized and every resource the wired plugins need is provisioned for you. Follow the **Agentic** column below.
- empty / anything else → **Local**. You are on a user machine and must discover, scaffold, and deploy yourself. Follow the **Local** column (the rest of this skill's default guidance).

## What changes

| Step | Local | Agentic mode (`DATABRICKS_APPS_AGENTIC_MODE=true`) |
|------|-------|----------------------------------------------------|
| **Auth / profile** | Select a profile via `databricks-core`; pass `--profile` on every CLI call. Never auto-select. | **Ambient — handled by the environment.** Never select a profile; **omit `--profile`** on every CLI call. |
| **Capabilities** | *Infer* from the request, then choose `--features`. | **Pre-wired. Do not infer or choose.** Read the enabled plugins from `appkit.plugins.json` / `app.yaml` (see below). |
| **Scaffold** | `databricks apps manifest` → `databricks apps init --features … --set …`. | **Already done.** Never run `manifest` or `init`. The project already exists on disk. |
| **Resources / `--set`** | Discover IDs (`list-projects`, warehouse id, …) and pass `--set` flags. | **Pre-provisioned.** Targets are injected as env vars (see below). Never create, select, or `--set` resources. |
| **Provisioning gates** | Run `lakebase_resources`, `genie_space` creation, etc. | **Skip.** Resources exist. |
| **Design + discovery gates** | Run `write_path`, `read_path`, `data_discovery`. | **Still run** — architecture and table selection are still your job. |
| **Resource-creation handoffs** | Use `databricks-lakebase` / `databricks-model-serving` / `databricks-jobs` and the Genie create/reuse-space flow to create infra. | **Skip all handoffs.** The space / endpoint / project / job already exist. |
| **Lakebase deploy-first** | OLTP requires deploy-before-dev (SP must own the schema). | **Suppressed** — deploy and schema ownership are handled externally. |
| **Dev / preview** | `npm run dev`. | `npm run dev` — connects to the **live** injected resources. |
| **Smoke tests** | Update `tests/smoke.spec.ts` before validate. | **Removed in agentic mode — do not write or update smoke tests.** |
| **Validate** | `databricks apps validate --profile <PROFILE>`. | `databricks apps validate` (no `--profile`; build/typecheck/lint only — no smoke). |
| **Deploy** | `bundle deploy` → `apps deploy` (user consent). | **None.** Deploy is handled externally. Never run deploy commands. |

## Reading what's wired (agentic mode)

The app is already scaffolded, so discover its shape from files instead of the CLI:

- **`appkit.plugins.json`** — which plugins are enabled (your capability set).
- **`app.yaml`** — the injected env vars (resource targets), e.g. `DATABRICKS_GENIE_SPACE_ID`, `DATABRICKS_JOB_*`, `DATABRICKS_SERVING_ENDPOINT_NAME`, `LAKEBASE_ENDPOINT` / `PG*`, `DATABRICKS_VOLUME_*`, and the warehouse id. These env var names align with what the plugins declare.
- `server/server.ts` — the `createApp({ plugins: [...] })` array confirms the same.

Read these env vars at runtime; **never** hardcode or re-provision the values behind them.

## If a needed capability is not wired

If the request requires a plugin that is **not** in `appkit.plugins.json`, **stop and tell the user** the app does not have that capability wired. **Do not** run `apps init`, provision resources, or otherwise try to add it yourself — provisioning is handled externally, not by the agent.

## Still your job in agentic mode

- **Data discovery** — which `catalog.schema.table` the analytics SQL should hit (resources existing ≠ knowing the tables). Use `databricks-core` (ambient auth, no `--profile`).
- **All application code** — `config/queries/*.sql`, custom routes, Lakebase schema init in `onPluginsReady`, React UI.
- **Design choices** — write path vs read path, route architecture, composition.
- **Run `npm run dev`** and **`databricks apps validate`** as your done-check.
