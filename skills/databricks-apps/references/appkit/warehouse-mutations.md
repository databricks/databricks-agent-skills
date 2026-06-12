# Warehouse Mutations (Delta / Unity Catalog)

Use this guide when an AppKit app must **write to Unity Catalog Delta tables** via the SQL warehouse — `INSERT`, `UPDATE`, `DELETE`, or `MERGE` — in response to a user action.

For **reads** from the warehouse, use [SQL Queries](sql-queries.md) (`config/queries/` + `useAnalyticsQuery`). **Never** add custom endpoints for SELECT.

For **app-owned operational state** (forms, CRUD, session data), prefer [Lakebase OLTP](lakebase-oltp.md) instead of writing Delta directly from the app.

**Pattern selection and gates:** [Data Patterns](data-patterns.md).

> **Agentic mode:** the warehouse is already wired (id injected). **Skip** the `databricks apps init … --set` scaffold block below; just write the mutation route. You still confirm the target `catalog.schema.table` via data discovery. See [Environments](environments.md).

## When this guide applies

You're in the right place **only if** a user action must land in an existing Delta / Unity Catalog table **now**, as small scoped DML (`INSERT` / `UPDATE` / `DELETE` / `MERGE`).

Anything else — app-owned CRUD, async/batch writes, or reads — is a different path. Choose it in **[Data Patterns: Write path](data-patterns.md#write-path)** (the canonical decision table); don't re-decide it here.

**Never write to Lakebase synced tables** — they are read-only replicas of Delta; app writes corrupt sync. See [Lakebase Synced Reads](lakebase-synced-reads.md).

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

Hybrids need only the plugins actually involved: read warehouse + write Delta is `--features analytics` alone; read warehouse + write Lakebase is `--features analytics,lakebase` — in all cases with the required `--set` flags from `databricks apps manifest`.

## Canonical pattern

Register **one named route per mutation**. Use **fixed SQL** with `:param` placeholders and `sql.*` helpers. Validate input with Zod. **Never** accept arbitrary SQL from the client.

Before writing code, run `npx @databricks/appkit docs ./docs/plugins/analytics.md` on the installed AppKit version and verify `query()` signature and parameter types.

**Start inline in `onPluginsReady`** — `appkit` is already fully typed there, so no extra interfaces or generics are needed:

```typescript
// server/server.ts
import { createApp, analytics, server, sql } from "@databricks/appkit";
import { z } from "zod";

const FeedbackBody = z.object({
  userId: z.string().min(1),
  rating: z.number().int().min(1).max(5),
  comment: z.string().max(2000).optional(),
});

await createApp({
  plugins: [server(), analytics({})],
  async onPluginsReady(appkit) {
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
              rating: sql.number(parsed.data.rating),
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
  },
});
```

### Extracting routes (larger apps, optional)

For bigger apps, move the handler into a `setupFeedbackRoutes(appkit)` function and call it from `onPluginsReady`. Let TypeScript **infer** the type from the call site — do **not** hand-write an `AppKitWith*` interface or add `appkit-types.ts`:

```typescript
// server/routes/warehouse/feedback-routes.ts
import { sql } from "@databricks/appkit";
import type { Application } from "express";

export function setupFeedbackRoutes<
  T extends {
    analytics: {
      query(
        statement: string,
        parameters?: Record<string, ReturnType<typeof sql.string> | ReturnType<typeof sql.number>>,
      ): Promise<unknown>;
    };
    server: { extend(fn: (app: Application) => void): void };
  },
>(appkit: T) {
  appkit.server.extend((app) => {
    // same /api/feedback handler as above
  });
}
```

```typescript
// server/server.ts
await createApp({
  plugins: [server(), analytics({})],
  async onPluginsReady(appkit) {
    setupFeedbackRoutes(appkit); // T inferred here — fully typed, no casts
  },
});
```

For on-behalf-of-user calls (`appkit.analytics.asUser(req).query(...)`), see *Service principal vs on-behalf-of-user* below. Same generic-inference pattern as [Lakebase OLTP](lakebase-oltp.md) *Lakebase route modules — typing*.

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

Confirm access **without mutating real data** before wiring the route:

```bash
# Preferred: verify the identity can read the target (no write side effect)
databricks experimental aitools tools query \
  "SELECT 1 FROM catalog.schema.feedback LIMIT 1" --profile <PROFILE>
```

If you must exercise the write path itself, insert into a disposable table (e.g. `catalog.schema._appkit_smoke`) and drop it afterward — **do not** write throwaway rows into the real target table.

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

Pattern: custom endpoint validates input → `appkit.jobs("<key>").runNow(...)` with parameters → job notebook/SQL task writes Delta. See [Jobs](jobs.md) for the `JobHandle` API.

## Agents plugin note

If you enable the **agents** plugin, built-in `analytics.query` **agent tools** are **read-only** (SELECT-only classifier). That restriction applies to LLM-invoked tools, **not** to your own server routes calling `appkit.analytics.query()` directly. Do not confuse agent tool safety with app mutation routes.

## Validation and testing

- Update `tests/smoke.spec.ts` to assert mutation **UI** (buttons, forms) — not that a Delta row landed (validate runs without live warehouse writes in many setups).
- `databricks apps validate` checks build/typecheck/lint/smoke — it does **not** prove UC write permissions. Verify grants after deploy.
- After deploy, confirm with `databricks apps logs <APP_NAME> --follow` if mutations fail at runtime.

## Related guides

- [Custom Endpoints](custom-endpoints.md) — when to add routes vs use plugins
- [SQL Queries](sql-queries.md) — read path only (`config/queries/`)
- [Lakebase OLTP](lakebase-oltp.md) — Postgres CRUD; [Lakebase Synced Reads](lakebase-synced-reads.md) — read-only Delta replicas
- [Jobs](jobs.md) — async lakehouse writes
