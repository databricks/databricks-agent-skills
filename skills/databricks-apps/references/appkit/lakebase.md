# Lakebase: OLTP Database for Apps

Use Lakebase when your app needs **persistent read/write storage** — forms, CRUD operations, user-generated data. For analytics dashboards reading from a SQL warehouse, use `config/queries/` instead.

## When to Use Lakebase vs Analytics

| Pattern | Use Case | Data Source |
|---------|----------|-------------|
| Analytics | Read-only dashboards, charts, KPIs | Databricks SQL Warehouse |
| Lakebase | CRUD operations, persistent state, forms, low-latency reads of synced lakehouse data | PostgreSQL (Lakebase Autoscaling) |
| Both | Dashboard with user preferences/saved state | Warehouse + Lakebase |

> **Serving lakehouse data to apps?** If your app needs low-latency reads of Delta/UC tables (entity lookups, product catalogs, feature serving), use **Lakebase synced tables** to materialize them into Lakebase instead of querying a SQL warehouse (which takes seconds to minutes). See *Reading from Synced Tables* below.

## Scaffolding

**ALWAYS scaffold with the correct feature flags** — do not add Lakebase manually to an analytics-only scaffold.

**Lakebase only** (no analytics SQL warehouse):
```bash
databricks apps init --name <NAME> --features lakebase \
  --set "lakebase.postgres.branch=<BRANCH_NAME>" \
  --set "lakebase.postgres.database=<DATABASE_NAME>" \
  --run none --profile <PROFILE>
```

**Both Lakebase and analytics**:
```bash
databricks apps init --name <NAME> --features analytics,lakebase \
  --set "analytics.sql-warehouse.id=<WAREHOUSE_ID>" \
  --set "lakebase.postgres.branch=<BRANCH_NAME>" \
  --set "lakebase.postgres.database=<DATABASE_NAME>" \
  --run none --profile <PROFILE>
```

Where `<BRANCH_NAME>` and `<DATABASE_NAME>` are full resource names (e.g. `projects/<PROJECT_ID>/branches/<BRANCH_ID>` and `projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DB_ID>`).

Use the `databricks-lakebase` skill to create a Lakebase project and discover branch/database resource names before running this command.

> For multi-environment deployments (dev/prod), use `variables:` and `targets:` blocks in `databricks.yml` — see the **`databricks-dabs`** skill for patterns.

**Get resource names** (if you have an existing project):
```bash
# List branches → use the name field of a READY branch
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>
# List databases → use the name field
databricks postgres list-databases projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

## Project Structure (after `databricks apps init --features lakebase`)

```
my-app/
├── server/
│   └── server.ts       # Backend with Lakebase pool + tRPC routes
├── client/
│   └── src/
│       └── App.tsx     # React frontend
├── app.yaml            # Manifest with database resource declaration
└── package.json        # Includes @databricks/lakebase dependency
```

Note: **No `config/queries/` directory** — Lakebase apps use server-side `pool.query()` calls, not SQL files.

## Lakebase Plugin API

Scaffolding with `--features lakebase` (see above) generates this pattern. Access Lakebase through the plugin handle returned by `createApp()`:

```typescript
import { createApp, server, lakebase } from "@databricks/appkit";

const AppKit = await createApp({
  plugins: [server(), lakebase()],
});

// Query via the plugin handle — handles pooling and token refresh automatically
const result = await AppKit.lakebase.query("SELECT * FROM users WHERE id = $1", [userId]);
```

The `lakebase()` plugin auto-configures from platform-injected env vars at deploy time. No manual pool setup needed.

## Environment Variables (auto-set when deployed with database resource)

| Variable | Description |
|----------|-------------|
| `PGHOST` | Lakebase hostname |
| `PGPORT` | Port (default 5432) |
| `PGDATABASE` | Database name |
| `PGUSER` | Service principal client ID |
| `PGSSLMODE` | SSL mode (`require`) |
| `LAKEBASE_ENDPOINT` | Endpoint resource path |

## tRPC CRUD Pattern

Always use tRPC for Lakebase operations — do NOT call `AppKit.lakebase.query()` from the client.

```typescript
// server/server.ts
import { createApp, server, lakebase } from "@databricks/appkit";

const AppKit = await createApp({
  plugins: [server(), lakebase()],
});

// Define routes using AppKit.lakebase.query()
AppKit.server.router({
  listItems: AppKit.server.procedure.query(async () => {
    const { rows } = await AppKit.lakebase.query(
      "SELECT * FROM app_data.items ORDER BY created_at DESC LIMIT 100"
    );
    return rows;
  }),

  createItem: AppKit.server.procedure
    .input(z.object({ name: z.string().min(1) }))
    .mutation(async ({ input }) => {
      const { rows } = await AppKit.lakebase.query(
        "INSERT INTO app_data.items (name) VALUES ($1) RETURNING *",
        [input.name]
      );
      return rows[0];
    }),

  deleteItem: AppKit.server.procedure
    .input(z.object({ id: z.number() }))
    .mutation(async ({ input }) => {
      await AppKit.lakebase.query("DELETE FROM app_data.items WHERE id = $1", [input.id]);
      return { success: true };
    }),
});
```

> **Deploy first (App + Lakebase only)!** When your Databricks App uses Lakebase, the Service Principal must create and own the schema. Run `databricks apps deploy` before any local development. See **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps** for details.

## Schema Initialization

**Always create a custom schema** — the Service Principal cannot access any existing schemas (including `public`). It must create the schema itself to become its owner. See **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps** for the full permission model and deploy-first workflow. Initialize tables on server startup:

```typescript
// server/server.ts — run once at startup before handling requests
await AppKit.lakebase.query(`
  CREATE SCHEMA IF NOT EXISTS app_data;
  CREATE TABLE IF NOT EXISTS app_data.items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );
`);
```

## ORM Integration (Optional)

The plugin exposes the raw `pg.Pool` via `AppKit.lakebase.pool` — works with any PostgreSQL library:

```typescript
// Drizzle ORM
import { drizzle } from "drizzle-orm/node-postgres";
const db = drizzle(AppKit.lakebase.pool);

// Prisma (with @prisma/adapter-pg)
import { PrismaPg } from "@prisma/adapter-pg";
const adapter = new PrismaPg(AppKit.lakebase.pool);
const prisma = new PrismaClient({ adapter });
```

For ORM-compatible config: `AppKit.lakebase.getOrmConfig()`.

## Reading from Lakebase synced tables

Lakebase synced tables materialize Delta/UC tables into Lakebase Postgres for low-latency app reads. The lakehouse remains the source of truth; Lakebase serves as a read-optimized index.

**Architecture:**
```
Delta gold tables  →  Synced tables (read-only)  →  App reads via AppKit.lakebase.query()
App writes         →  Lakebase OLTP tables        →  optional Lakehouse Sync → Delta
```

**Use synced tables when** data is curated in Delta, changes relatively slowly, and must be served at OLTP latency — operational consoles, user-facing apps on gold tables, feature serving, or hybrid read/write patterns. See the **`databricks-lakebase`** skill's [synced-tables.md](../../../databricks-lakebase/references/synced-tables.md) for the full decision checklist.

> **Security note:** Synced tables do not propagate Unity Catalog fine-grained access control (row filters, column masks). If UC FGAC is critical, use DBSQL with user authorization instead.

### How It Works

Synced tables (created via `databricks postgres create-synced-table`) appear as regular Postgres tables. From the app's perspective, use the same `AppKit.lakebase.query()` pattern but **read-only**.

**Key differences from CRUD tables:**

| | CRUD tables | Lakebase synced tables |
|--|-------------|---------------|
| Created by | App SP (via `CREATE TABLE`) | Sync pipeline (DLT) |
| Owned by | SP role | System role (`databricks_writer_*`) |
| Operations | Read + Write | **Read-only** (writes corrupt sync) |
| Schema init | App must `CREATE SCHEMA/TABLE` | Already exists after sync |
| Deploy-first | Required (SP must own schema) | Not required |

**Permission grant required:** The app's SP has `CAN_CONNECT_AND_CREATE` but does **not** have `pg_read_all_data`. To read synced tables, the project owner must grant access — see the **`databricks-lakebase`** skill's SKILL.md "Grant app SP access to synced tables" section for the SQL commands and psql connection steps.

**Example tRPC route reading synced taxi data:**

```typescript
topPickups: publicProcedure.query(async () => {
  const { rows } = await AppKit.lakebase.query(`
    SELECT pickup_zip, COUNT(*) AS trip_count, AVG(fare_amount) AS avg_fare
    FROM public.nyc_trips
    GROUP BY pickup_zip
    ORDER BY trip_count DESC
    LIMIT 10
  `);
  return rows;
}),
```

> **Do not write to synced tables.** The sync pipeline manages the data — direct writes corrupt the sync state. For mixed read/write patterns, read from synced tables and write to separate app-owned tables. To create synced tables and grant the app's SP read access, see the **`databricks-lakebase`** skill's [synced-tables.md](../../../databricks-lakebase/references/synced-tables.md) and the "Grant app SP access to synced tables" section in its SKILL.md.

## Key Differences from Analytics Pattern

| | Analytics | Lakebase |
|--|-----------|---------|
| SQL dialect | Databricks SQL (Spark SQL) | Standard PostgreSQL |
| Query location | `config/queries/*.sql` files | `pool.query()` in tRPC routes |
| Data retrieval | `useAnalyticsQuery` hook | tRPC query procedure |
| Date functions | `CURRENT_TIMESTAMP()`, `DATEDIFF(DAY, ...)` | `NOW()`, `AGE(...)` |
| Auto-increment | N/A | `SERIAL` or `GENERATED ALWAYS AS IDENTITY` |
| Insert pattern | N/A | `INSERT ... VALUES ($1) RETURNING *` |
| Params | Named (`:param`) | Positional (`$1, $2, ...`) |

**NEVER use `useAnalyticsQuery` for Lakebase data** — it queries the SQL warehouse, not Lakebase.
**NEVER put Lakebase SQL in `config/queries/`** — those files are only for warehouse queries.

## Local Development

### Prerequisites (MUST verify before local development)

**This applies when your Databricks App uses Lakebase.** Run this check before any local development:

```bash
databricks apps get <APP_NAME> --profile <PROFILE>
```

Check the response for the `active_deployment` field. If it exists with `status.state` of `SUCCEEDED`, the app has been deployed. If `active_deployment` is missing, the app has never been deployed:
1. **STOP** — do not proceed with local development
2. Deploy first: `databricks apps deploy <APP_NAME> --profile <PROFILE>`
3. Wait for deployment to complete, then continue

If you skip this step, the Service Principal won't own the database schema. You'll create schemas under your credentials that the SP **cannot access** after deployment. See **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps** for the full workflow and recovery steps.

The Lakebase env vars (`PGHOST`, `PGDATABASE`, etc.) are auto-set only when deployed. For local development, get the connection details from your endpoint and set them manually:

```bash
# Get endpoint connection details
databricks postgres get-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  --profile <PROFILE>
```

Then create `server/.env` with the values from the endpoint response:

```
PGHOST=<host from endpoint>
PGPORT=5432
PGDATABASE=<your database name>
PGUSER=<your service principal client ID>
PGSSLMODE=require
LAKEBASE_ENDPOINT=projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID>
```

Load `server/.env` in your dev server (e.g. via `dotenv` or `node --env-file=server/.env`). Never commit `.env` files — add `server/.env` to `.gitignore`.

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|---------|
| `permission denied for schema public` | SP cannot access `public` schema | Create custom schema: `CREATE SCHEMA IF NOT EXISTS app_data` and qualify all table names with `app_data.` |
| `permission denied for schema <name>` | Schema was created by another role (e.g. you ran locally before deploying) | **Ask the user before dropping** — `DROP SCHEMA` deletes all data. See **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps** for options |
| Works locally but `permission denied` after deploy | Local credentials created the schema; the SP can't access schemas it doesn't own | **Ask the user before dropping** — warn about data loss, then deploy first. See **`databricks-lakebase`** skill's **Schema Permissions for Deployed Apps** for options |
| `connection refused` | Pool not connected or wrong env vars | Check `PGHOST`, `PGPORT`, `LAKEBASE_ENDPOINT` are set |
| `relation "X" does not exist` | Tables not initialized | Run `CREATE TABLE IF NOT EXISTS` at startup |
| App builds but pool fails at runtime | Env vars not set locally | Set vars in `server/.env` — see Local Development above |
