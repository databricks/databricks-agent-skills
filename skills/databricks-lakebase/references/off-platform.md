# Off-Platform Lakebase: Connecting from External Apps

Connect to Lakebase from apps deployed outside Databricks App Platform (e.g. Vercel, AWS, Netlify, or any Node.js server).

## Recommended: `@databricks/lakebase` Package

The simplest way to connect — a drop-in `pg.Pool` replacement with automatic OAuth token refresh.

```bash
npm install @databricks/lakebase
```

**Zero-config usage** (reads from environment variables):

```typescript
import { createLakebasePool } from "@databricks/lakebase";

const pool = createLakebasePool();
const result = await pool.query("SELECT * FROM users");
```

**Explicit config:**

```typescript
const pool = createLakebasePool({
  host: "your-lakebase-host.databricks.com",
  database: "your_database_name",
  endpoint: "projects/<project-id>/branches/<branch-id>/endpoints/<endpoint-id>",
  user: "user_id",
  max: 10,
});
```

**Key features:**
- Automatic OAuth token refresh (1-hour lifetime, 2-minute buffer)
- Token caching to reduce API calls
- Username resolution: explicit config → `PGUSER` → `DATABRICKS_CLIENT_ID` → API lookup via `getUsernameWithApiLookup()`
- `getLakebaseOrmConfig()` for ORM-compatible connection config
- OpenTelemetry metrics: `lakebase.token.refresh.duration`, `lakebase.query.duration`, pool connection gauges
- Logging: `{ debug, info, warn, error }` boolean flags or custom logger instance

> **Lakebase Autoscaling only.** This package is not compatible with Lakebase Provisioned. For the full config reference, see the [`@databricks/lakebase` README](https://github.com/databricks/appkit/tree/main/packages/lakebase).

**ORM integration:**

```typescript
// Drizzle
import { drizzle } from "drizzle-orm/node-postgres";
const db = drizzle({ client: pool });

// Prisma
import { PrismaPg } from "@prisma/adapter-pg";
const adapter = new PrismaPg(pool);
const prisma = new PrismaClient({ adapter });

// TypeORM / Sequelize
import { getLakebaseOrmConfig } from "@databricks/lakebase";
// Pass getLakebaseOrmConfig() to your ORM's connection config
```

## Environment Management

### Required Environment Variables

| Variable | Description | How to find |
|----------|-------------|-------------|
| `PGHOST` | Lakebase endpoint host | `databricks postgres list-endpoints projects/<project>/branches/production --profile <PROFILE> -o json` → `status.hosts.host` |
| `PGDATABASE` | Postgres database name | Default is `databricks_postgres`. Verify via psql: `SELECT datname FROM pg_database WHERE datistemplate = false;` |
| `LAKEBASE_ENDPOINT` | Endpoint resource path | Same `list-endpoints` command → `name` field |
| `PGUSER` | Username | Your Databricks email (local dev) or service principal application ID (M2M) |
| `PGSSLMODE` | SSL mode | `require` (default) |
| `PGPORT` | Port | `5432` (default) |

### Authentication

**Local dev** — use a short-lived workspace token:
```bash
export DATABRICKS_TOKEN=$(databricks auth token --profile <PROFILE> -o json | jq -r '.access_token')
```

**Production** — use OAuth M2M credentials:
```bash
export DATABRICKS_CLIENT_ID=<service-principal-app-id>
export DATABRICKS_CLIENT_SECRET=<service-principal-secret>
export DATABRICKS_HOST=https://<workspace>.cloud.databricks.com
```

### `.env.example` Template

```bash
DATABRICKS_HOST=https://<workspace-host>
LAKEBASE_ENDPOINT=projects/<project>/branches/production/endpoints/primary
PGHOST=<status.hosts.host from list-endpoints>
PGPORT=5432
PGDATABASE=<status.postgres_database from list-databases>
PGUSER=<your Databricks email or service principal application ID>
PGSSLMODE=require

# Option A: local dev, token auth (expires ~1h)
DATABRICKS_TOKEN=

# Option B: production, M2M auth (service principal)
DATABRICKS_CLIENT_ID=
DATABRICKS_CLIENT_SECRET=
```

### Optional: Zod Validation

For strict fast-fail validation at startup:

```typescript
import { z } from "zod";

const baseSchema = z.object({
  DATABRICKS_HOST: z.string().min(1),
  LAKEBASE_ENDPOINT: z.string().min(1),
  PGHOST: z.string().min(1),
  PGPORT: z.coerce.number().default(5432),
  PGDATABASE: z.string().min(1),
  PGUSER: z.string().min(1),
  PGSSLMODE: z.enum(["require", "verify-full", "verify-ca", "prefer", "disable"]).default("require"),
  DATABRICKS_TOKEN: z.string().optional(),
  DATABRICKS_CLIENT_ID: z.string().optional(),
  DATABRICKS_CLIENT_SECRET: z.string().optional(),
});

function validateAuth(env: z.infer<typeof baseSchema>) {
  const hasToken = Boolean(env.DATABRICKS_TOKEN);
  const hasM2M = Boolean(env.DATABRICKS_CLIENT_ID) && Boolean(env.DATABRICKS_CLIENT_SECRET);
  if (!hasToken && !hasM2M) {
    throw new Error("Set DATABRICKS_TOKEN or both DATABRICKS_CLIENT_ID and DATABRICKS_CLIENT_SECRET");
  }
  return env;
}

export const env = validateAuth(baseSchema.parse(process.env));
```

Import `env` at the top of your server entry point for fast-fail on missing variables.

## Drizzle ORM Integration

**With `@databricks/lakebase`** (recommended):

```typescript
import { drizzle } from "drizzle-orm/node-postgres";
import { createLakebasePool } from "@databricks/lakebase";
import * as itemsSchema from "@/lib/items/schema";

const pool = createLakebasePool();
export const db = drizzle({ client: pool, schema: { ...itemsSchema } });
```

**Schema per domain** — organize schemas under `src/lib/<domain>/schema.ts`:

```typescript
import { pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";

export const items = pgTable("items", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
```

**Running migrations** — use Drizzle's programmatic migrator with the Lakebase pool:

```typescript
// scripts/db-migrate.ts
import { drizzle } from "drizzle-orm/node-postgres";
import { migrate } from "drizzle-orm/node-postgres/migrator";
import { createLakebasePool } from "@databricks/lakebase";

const pool = createLakebasePool();
const db = drizzle({ client: pool });
await migrate(db, { migrationsFolder: "./src/lib/db/migrations" });
await pool.end();
console.log("Migrations applied successfully");
```

**`drizzle.config.ts`** — used by `drizzle-kit generate` (no DB connection needed):

```typescript
import { defineConfig } from "drizzle-kit";

export default defineConfig({
  schema: "./src/lib/*/schema.ts",
  out: "./src/lib/db/migrations",
  dialect: "postgresql",
});
```

**Commands:**
- Generate: `npx drizzle-kit generate`
- Migrate: `npx dotenv -e .env.local -- npx tsx scripts/db-migrate.ts`

## Cross-references

- For on-platform connection patterns, see [connectivity.md](connectivity.md)
- For vector similarity search with pgvector, see [pgvector.md](pgvector.md)
- For AppKit-based Lakebase integration, see the `databricks-apps` skill's [lakebase.md](../../databricks-apps/references/appkit/lakebase.md)
