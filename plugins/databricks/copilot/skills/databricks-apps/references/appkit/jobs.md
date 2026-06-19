# Jobs: Trigger Lakeflow Jobs from Apps

**For full Jobs plugin API (routes, types, config options)**: run `npx @databricks/appkit docs` → Jobs plugin.

Use the `jobs()` plugin when your app needs to **trigger or monitor pre-existing Databricks Lakeflow Jobs** (notebooks, Python scripts, SQL, dbt, JARs) and surface their status to users. The jobs themselves still live as regular Lakeflow Jobs in the workspace — the plugin is the typed, resource-scoped accessor that lets app code start runs, poll status, and stream completion events.

The plugin is **resource-scoped**: only jobs declared via config or discovered from `DATABRICKS_JOB_*` env vars are accessible. It is not a generic Jobs SDK wrapper — to author or schedule jobs, use the `databricks-jobs` (Lakeflow) skill instead. See [`overview.md`](./overview.md) for the cross-plugin data-pattern selector.

## Scaffolding

```bash
databricks apps init --name <NAME> --features jobs \
  --set "jobs.<resourceKey>.<field>=<JOB_ID>" \
  --run none --profile <PROFILE>
```

**Do not guess** `--set` keys — derive them from `databricks apps manifest --profile <PROFILE>` (look up the `jobs` plugin's `resources.required` entries).

Multi-job and analytics+jobs are common combinations:

```bash
databricks apps init --name <NAME> --features analytics,jobs \
  --set "analytics.sql-warehouse.id=<WAREHOUSE_ID>" \
  --set "jobs.<resourceKey>.<field>=<JOB_ID>" \
  --run none --profile <PROFILE>
```

Configure job IDs via environment variables in `app.yaml` (deployed) or `server/.env` (local dev):

```env
# Single-job mode → exposed under the "default" key
DATABRICKS_JOB_ID=123456789

# Multi-job mode → exposed under lowercased keys ("etl", "ml")
DATABRICKS_JOB_ETL=123456789
DATABRICKS_JOB_ML=987654321
```

The env var suffix (after `DATABRICKS_JOB_`) becomes the job key, lowercased. Explicit `jobs` config in `createApp()` is merged with env-discovered jobs; explicit config wins on key collisions.

## Plugin Setup

Minimal — discovers all jobs from the environment:

```typescript
import { createApp, server, jobs } from "@databricks/appkit";

await createApp({
  plugins: [server(), jobs()],
});
```

With per-job validation and task-type mapping:

```typescript
import { createApp, server, jobs } from "@databricks/appkit";
import { z } from "zod";

const appkit = await createApp({
  plugins: [
    server(),
    jobs({
      jobs: {
        etl: {
          taskType: "notebook",
          params: z.object({
            startDate: z.string(),
            endDate: z.string(),
            dryRun: z.boolean().optional(),
          }),
        },
      },
    }),
  ],
});
```

For the full `IJobsConfig`, `JobConfig`, and task-type → SDK parameter mapping, run `npx @databricks/appkit docs Jobs plugin`. Two non-obvious points: `dbt` accepts no parameters, and `notebook`/`python_wheel`/`sql` coerce all param values to strings before forwarding.

## Server-Side API (Programmatic)

`appkit.jobs(key)` returns a `JobHandle`. All methods return `ExecutionResult<T>` — **always check `.ok` before reading `.data`**. Full method list and types: `npx @databricks/appkit docs Jobs plugin`.

```typescript
const etl = appkit.jobs("etl");

// One-shot trigger
const result = await etl.runNow({ startDate: "2025-01-01" });
if (!result.ok) throw new Error(`Run failed: ${result.error}`);

// Trigger and stream status until completion (async iterable, SSE-backed)
for await (const status of etl.runAndWait({ startDate: "2025-01-01" })) {
  console.log(status.status); // "PENDING" | "RUNNING" | "TERMINATED" | ...
}
```

Read methods (`lastRun`, `listRuns`, `getRun`, `getRunOutput`, `getJob`) and `cancelRun` follow the same `ExecutionResult<T>` shape. Reads cache for 60s with 3 retries. `runAndWait` has a 600s server-side cap, but **client-facing requests are bounded by the Apps platform's 120s reverse-proxy timeout** (see [Platform Guide](../platform-guide.md), "HTTP Proxy & Streaming"). For runs longer than ~120s, use `runNow` and poll `getRun` (or `GET /api/jobs/:jobKey/status`) from separate short-lived requests instead of streaming.

### Execution context

All operations run as the **app's service principal**. The resource binding in `databricks.yml` grants the SP `CAN_MANAGE_RUN`, so users trigger runs without needing their own grant. Per-run attribution in the Jobs UI shows the SP, not the human user. The plugin does not support on-behalf-of (OBO) user execution.

## HTTP Endpoints

Routes mount at `/api/jobs/:jobKey/...` — full route list, request bodies, and SSE frame shape via `npx @databricks/appkit docs Jobs plugin`. The streaming endpoint (`POST /api/jobs/:jobKey/run?stream=true`) emits `data: <json>` events terminated by a blank line (`\n\n`), where the JSON is `{ status, timestamp, run }`; **clients must buffer until `\n\n` and reassemble across chunk boundaries** before parsing. `runAndWait` (server-side) honors `req.signal` and aborts cleanly on client disconnect — but the platform's 120s reverse-proxy cap applies regardless.

## Resource Requirements

Each job key requires a `job` resource with `CAN_MANAGE_RUN` in `databricks.yml`:

```yaml
resources:
  apps:
    my_app:
      resources:
        - name: etl-job
          job:
            id: ${var.etl_job_id}
            permission: CAN_MANAGE_RUN
```

Wire the env var in `app.yaml`:

```yaml
env:
  - name: DATABRICKS_JOB_ETL
    valueFrom: etl-job
```

Verify exact `--set` keys and resource shape via `databricks apps manifest --profile <PROFILE>`.

## Troubleshooting

| Error | Cause | Solution |
| --- | --- | --- |
| `Unknown job key "X"` | Job env var not set or misspelled | Check `DATABRICKS_JOB_X` is set in `app.yaml` or `server/.env` |
| 400 with Zod issues on `runNow` | Params don't match the per-job `params` schema | Fix the input or relax the schema |
| `dbt` job rejects params | `dbt` task type accepts no parameters | Trigger with no params, or remove `taskType: "dbt"` |
| 504 / timeout on `runAndWait` | Run exceeds the platform's 120s reverse-proxy timeout (server-side cap is 600s but the proxy cuts first) | Switch to `runNow` + poll `getRun` (or `GET /api/jobs/:jobKey/status`) from separate short-lived requests; raising `waitTimeout` does not help |
| SSE events arrive split / unparseable | Client not reassembling `data:` frames across chunks | Buffer until `\n\n`, then parse — see streaming pattern above |
| `result.data` is undefined | `result.ok` was false but the caller skipped the check | Always branch on `result.ok` before reading `result.data` |
