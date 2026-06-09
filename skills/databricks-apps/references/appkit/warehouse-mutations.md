# Warehouse Mutations (Delta / Unity Catalog)

Use this guide when an AppKit app must **write to Unity Catalog Delta tables** via the SQL warehouse — `INSERT`, `UPDATE`, `DELETE`, or `MERGE` — in response to a user action.

For **reads** from the warehouse, use [SQL Queries](sql-queries.md) (`config/queries/` + `useAnalyticsQuery`). **Never** add custom endpoints for SELECT.

For **app-owned operational state** (forms, CRUD, session data), prefer [Lakebase](lakebase.md) instead of writing Delta directly from the app.

**Pattern selection and gates:** [Data Patterns](data-patterns.md).

## Decision gate

Before implementing warehouse DML, confirm this is the right layer:

| Need | Use |
|------|-----|
| User form / CRUD / low-latency app state | [Lakebase](lakebase.md) — `appkit.lakebase.query()` |
| App data must appear in Delta later (async OK) | Lakebase write + [Lakehouse Sync](../../../databricks-lakebase/references/lakehouse-sync.md) (UI-only) |
| Large / batch / multi-step lakehouse write | [Jobs](jobs.md) — `jobs()` plugin triggers a Lakeflow Job |
| User action must land in Delta **now**, small scoped DML | **This guide** — custom endpoint + `appkit.analytics.query()` |
| Read lakehouse data in the UI | [SQL Queries](sql-queries.md) or Lakebase synced tables (read-only) |

**Never write to Lakebase synced tables** — they are read-only replicas of Delta; app writes corrupt sync. See [Lakebase Guide](lakebase.md) *Reading from Synced Tables*.

## How it works

The analytics plugin exposes **server-side** SQL execution via `appkit.analytics.query()` (and `appkit.analytics.asUser(req).query(...)` for on-behalf-of-user). This is separate from the client hook `useAnalyticsQuery`, which is for **read-only** display.

```
Browser  →  POST /api/your-mutation  →  Express route (Zod validate)
                                      →  appkit.analytics.query(fixed SQL, params)
                                      →  SQL warehouse  →  Delta table
```

**Scaffold with analytics** so the warehouse resource is wired:

```bash
databricks apps init --name <NAME> --features analytics \
  --set "analytics.sql-warehouse.id=<WAREHOUSE_ID>" \
  --run none --profile <PROFILE>
```

Hybrid apps (read warehouse + write Lakebase, or read SQL files + write Delta) use `--features analytics,lakebase` with all required `--set` flags from `databricks apps manifest`.

## Canonical pattern

Register **one named route per mutation**. Use **fixed SQL** with `:param` placeholders and `sql.*` helpers. Validate input with Zod. **Never** accept arbitrary SQL from the client.

Before writing code, run `npx @databricks/appkit docs ./docs/plugins/analytics.md` on the installed AppKit version and verify `query()` signature and parameter types.

```typescript
// server/routes/warehouse/feedback-routes.ts
import { sql } from "@databricks/appkit";
import { z } from "zod";
import type { Application, Request } from "express";

const FeedbackBody = z.object({
  userId: z.string().min(1),
  rating: z.number().int().min(1).max(5),
  comment: z.string().max(2000).optional(),
});

export function setupFeedbackRoutes<
  T extends {
    analytics: {
      query(
        statement: string,
        parameters?: Record<string, ReturnType<typeof sql.string>>,
      ): Promise<unknown>;
      asUser: (req: Request) => { query: T["analytics"]["query"] };
    };
    server: { extend(fn: (app: Application) => void): void };
  },
>(appkit: T) {
  appkit.server.extend((app) => {
    app.post("/api/feedback", async (req, res) => {
      const parsed = FeedbackBody.safeParse(req.body);
      if (!parsed.success) {
        res.status(400).json({ error: "Invalid input" });
        return;
      }

      try {
        await appkit.analytics.query(
          `INSERT INTO catalog.schema.feedback (user_id, rating, comment, created_at)
           VALUES (:user_id, :rating, :comment, current_timestamp())`,
          {
            user_id: sql.string(parsed.data.userId),
            rating: sql.int(parsed.data.rating),
            comment: sql.string(parsed.data.comment ?? ""),
          },
        );
        res.status(201).json({ ok: true });
      } catch (err) {
        console.error("Failed to insert feedback:", err);
        res.status(500).json({ error: "Failed to save feedback" });
      }
    });
  });
}
```

```typescript
// server/server.ts
import { createApp, analytics, server } from "@databricks/appkit";
import { setupFeedbackRoutes } from "./routes/warehouse/feedback-routes";

createApp({
  plugins: [server(), analytics({})],
  async onPluginsReady(appkit) {
    setupFeedbackRoutes(appkit);
  },
}).catch(console.error);
```

For typing extracted route modules, see [Lakebase Guide](lakebase.md) *Lakebase route modules — typing* — use the same generic `setupXRoutes<T>(appkit: T)` pattern when `analytics()` is in the plugin list. Do not add `appkit-types.ts` or hand-written `AppKitWith*` interfaces.

## Service principal vs on-behalf-of-user

| Call | Credentials | When to use |
|------|-------------|-------------|
| `appkit.analytics.query(...)` | App service principal | System writes, batch ops, trusted server-side validation |
| `appkit.analytics.asUser(req).query(...)` | End user's Databricks identity | UC row/column policies must apply; user-scoped audit |

OBO requires the deployed app proxy headers (`x-forwarded-user`, `x-forwarded-access-token`). In local dev without those headers, OBO may fall back to SP — verify behavior with `npx @databricks/appkit docs` for your AppKit version.

Grant UC privileges to whichever identity executes the statement (SP client ID from `databricks apps get <APP_NAME>` or the signed-in user).

## Unity Catalog permissions

The app SP (or user, for OBO) needs at minimum:

- `USE CATALOG` on the target catalog
- `USE SCHEMA` on the target schema
- `MODIFY` (or table-appropriate write privilege) on the target table

`CAN_USE` on the SQL warehouse is wired via the analytics plugin resource in `databricks.yml`. **Warehouse access does not imply table write access** — verify UC grants separately.

Test with a one-off statement (as the app SP or your user) before wiring the route:

```bash
databricks experimental aitools tools query \
  "INSERT INTO catalog.schema.feedback (user_id, rating, comment) VALUES ('test', 5, 'smoke')" \
  --profile <PROFILE>
```

## Client-side pattern

Mutations use `fetch` to your custom route — **not** `useAnalyticsQuery`:

```typescript
await fetch("/api/feedback", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ userId, rating, comment }),
});
```

Keep reads on `useAnalyticsQuery` / visualization components; keep writes on POST/PUT/PATCH/DELETE to your mutation routes.

## Anti-patterns

```typescript
// ❌ NEVER — arbitrary SQL from the client (injection, privilege escalation)
app.post("/api/sql", async (req, res) => {
  await appkit.analytics.query(req.body.sql);
});

// ❌ NEVER — SELECT in a custom endpoint (use config/queries/)
app.get("/api/items", async (_req, res) => {
  const rows = await appkit.analytics.query("SELECT * FROM catalog.schema.items");
  res.json(rows);
});

// ❌ NEVER — string concatenation with user input
await appkit.analytics.query(
  `INSERT INTO t VALUES ('${req.body.name}')`,
);

// ❌ NEVER — heavy MERGE / large batch in a synchronous request handler
// Use jobs() plugin instead
```

## When to use Jobs instead

Prefer the [Jobs](jobs.md) plugin when the write:

- Touches many rows or large partitions
- Runs multi-statement ETL
- Should be retried/monitored asynchronously
- Must not block the HTTP response

Pattern: custom endpoint validates input → `appkit.jobs.run(...)` with parameters → job notebook/SQL task writes Delta.

## Agents plugin note

If you enable the **agents** plugin, built-in `analytics.query` **agent tools** are **read-only** (SELECT-only classifier). That restriction applies to LLM-invoked tools, **not** to your own server routes calling `appkit.analytics.query()` directly. Do not confuse agent tool safety with app mutation routes.

## Validation and testing

- Update `tests/smoke.spec.ts` to assert mutation **UI** (buttons, forms) — not that a Delta row landed (validate runs without live warehouse writes in many setups).
- `databricks apps validate` checks build/typecheck/lint/smoke — it does **not** prove UC write permissions. Verify grants after deploy.
- After deploy, confirm with `databricks apps logs <APP_NAME> --follow` if mutations fail at runtime.

## Related guides

- [Custom Endpoints](custom-endpoints.md) — when to add routes vs use plugins
- [SQL Queries](sql-queries.md) — read path only (`config/queries/`)
- [Lakebase](lakebase.md) — Postgres CRUD and hybrid read/write patterns
- [Jobs](jobs.md) — async lakehouse writes
