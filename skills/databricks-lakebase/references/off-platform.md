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

**ORM integration:**

```typescript
// Drizzle
import { drizzle } from "drizzle-orm/node-postgres";
const db = drizzle(pool);

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
| `PGDATABASE` | Postgres database name | `databricks postgres list-databases projects/<project>/branches/production --profile <PROFILE> -o json` → `status.postgres_database` |
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
  PGSSLMODE: z.enum(["require", "prefer", "disable"]).default("require"),
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

## Manual Token Management

> **Prefer `@databricks/lakebase`** for Node.js apps — it handles everything below automatically. Use this section only for non-Node.js apps or custom token flows.

Lakebase requires a **two-token system**: a workspace token + a short-lived Lakebase Postgres credential.

```typescript
const REFRESH_BUFFER_MS = 2 * 60 * 1000; // Refresh 2 minutes before expiry

type CachedToken = { value: string; expiresAt: number };

let cachedWorkspaceToken: CachedToken | null = null;
let workspaceRefreshPromise: Promise<CachedToken> | null = null;
let cachedLakebaseToken: CachedToken | null = null;
let lakebaseRefreshPromise: Promise<CachedToken> | null = null;

function isFresh(token: CachedToken | null): token is CachedToken {
  return token !== null && Date.now() < token.expiresAt - REFRESH_BUFFER_MS;
}
```

**M2M OIDC flow** (production):

```typescript
async function fetchWorkspaceTokenM2M(host: string, clientId: string, clientSecret: string): Promise<CachedToken> {
  const response = await fetch(`${host}/oidc/v1/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "client_credentials",
      client_id: clientId,
      client_secret: clientSecret,
      scope: "all-apis",
    }),
  });
  if (!response.ok) throw new Error(`M2M token request failed: ${response.status}`);
  const data = await response.json() as { access_token: string; expires_in: number };
  return { value: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
}
```

**Lakebase credential** (exchange workspace token for Postgres password):

```typescript
async function fetchLakebaseCredential(host: string, workspaceToken: string): Promise<CachedToken> {
  const response = await fetch(`${host}/api/2.0/postgres/credentials`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${workspaceToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ endpoint: env.LAKEBASE_ENDPOINT }),
  });
  if (!response.ok) throw new Error(`Lakebase credential request failed: ${response.status}`);
  const data = await response.json() as { token: string; expire_time: string };
  return { value: data.token, expiresAt: new Date(data.expire_time).getTime() };
}
```

**Concurrent deduplication** — use a singleton promise pattern to avoid duplicate refresh calls:

```typescript
export async function getLakebasePostgresToken(): Promise<string> {
  if (isFresh(cachedLakebaseToken)) return cachedLakebaseToken.value;
  if (!lakebaseRefreshPromise) {
    lakebaseRefreshPromise = (async () => {
      const auth = authStrategyFromEnv();
      const workspaceToken = await getWorkspaceToken(auth);
      return fetchLakebaseCredential(env.DATABRICKS_HOST.replace(/\/$/, ""), workspaceToken);
    })()
      .then((token) => { cachedLakebaseToken = token; return token; })
      .finally(() => { lakebaseRefreshPromise = null; });
  }
  return (await lakebaseRefreshPromise).value;
}
```

**Local dev refresh script** (`scripts/refresh-lakebase-token.ts`):

```typescript
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync, existsSync } from "node:fs";

const envFile = process.argv[2] ?? ".env.local";
const profile = process.env.DATABRICKS_CONFIG_PROFILE ?? "DEFAULT";
const raw = execSync(`databricks auth token --profile "${profile}" -o json`, { encoding: "utf-8" });
const parsed = JSON.parse(raw) as { access_token?: string };
if (!parsed.access_token) throw new Error("Failed to get access token from Databricks CLI");
if (!existsSync(envFile)) throw new Error(`Env file not found: ${envFile}`);

const content = readFileSync(envFile, "utf-8");
const tokenLine = `DATABRICKS_TOKEN="${parsed.access_token}"`;
const updated = content.includes("DATABRICKS_TOKEN=")
  ? content.replace(/^DATABRICKS_TOKEN=.*/m, tokenLine)
  : `${content.trimEnd()}\n${tokenLine}\n`;
writeFileSync(envFile, updated);
console.log(`Updated DATABRICKS_TOKEN in ${envFile}`);
```

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

**Migration with Lakebase credentials** — `drizzle-kit` cannot use `pg` password callbacks. Build a one-time URL:

```typescript
// scripts/db-migrate.ts
import { execSync } from "node:child_process";
import { getLakebasePostgresToken } from "@/lib/lakebase/tokens";

async function runMigrations() {
  const token = await getLakebasePostgresToken();
  const databaseUrl =
    `postgresql://${encodeURIComponent(env.PGUSER)}:${encodeURIComponent(token)}` +
    `@${env.PGHOST}:${env.PGPORT}/${env.PGDATABASE}?sslmode=${env.PGSSLMODE}`;
  execSync("npx drizzle-kit migrate", {
    stdio: "inherit",
    env: { ...process.env, DATABASE_URL: databaseUrl },
  });
}
runMigrations().catch((error) => { console.error(error); process.exit(1); });
```

**`drizzle.config.ts`** — conditional `dbCredentials` (only needed when `DATABASE_URL` is set by migration script):

```typescript
import { defineConfig } from "drizzle-kit";

export default defineConfig({
  schema: "./src/lib/*/schema.ts",
  out: "./src/lib/db/migrations",
  dialect: "postgresql",
  ...(process.env.DATABASE_URL && {
    dbCredentials: { url: process.env.DATABASE_URL },
  }),
});
```

**Commands:**
- Generate (local, no DB connection): `npx drizzle-kit generate`
- Migrate (needs credentials): `npx dotenv -e .env.local -- npx tsx scripts/db-migrate.ts`
