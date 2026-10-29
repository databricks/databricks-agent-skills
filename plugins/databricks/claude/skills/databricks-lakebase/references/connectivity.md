# Lakebase Connectivity

## Authentication Methods

| Method | Token Lifetime | Best For |
|--------|---------------|----------|
| **OAuth tokens** | 1 hour (must refresh) | Interactive sessions, workspace-integrated apps |
| **Native Postgres passwords** | No expiry | Long-running processes, tools without token rotation |

**Connection timeouts:** 24h idle timeout is guaranteed. Max connection lifetime beyond 24h is not guaranteed — implement reconnection logic. Always use `sslmode=require`.

## Connection Patterns (Python)

> **JavaScript/TypeScript Databricks Apps** using AppKit get Lakebase connectivity via the `lakebase()` plugin — see the **`databricks-apps`** skill's [Lakebase guide](../../databricks-apps/references/appkit/lakebase.md).

### Pattern 1: Direct Connection (Scripts/Notebooks)

For one-off queries. Get a fresh token, connect, execute, close.

**Key parameters:**
```
host      = endpoint.status.hosts.host   (from get-endpoint)
dbname    = "databricks_postgres"         (or your database name)
user      = w.current_user.me().user_name
password  = w.postgres.generate_database_credential(endpoint=<name>).token
sslmode   = "require"
```

**Pattern (psycopg2 or psycopg3):**
```python
# 1. Get host from endpoint
endpoint = w.postgres.get_endpoint(name="projects/<ID>/branches/<BRANCH>/endpoints/<EP>")
host = endpoint.status.hosts.host

# 2. Generate OAuth token (valid 1 hour)
token = w.postgres.generate_database_credential(endpoint=endpoint.name).token

# 3. Connect
conn = psycopg.connect(host=host, dbname="databricks_postgres",
                        user=username, password=token, sslmode="require")
```

### Pattern 2: Connection Pool with Token Refresh (Production)

For long-running apps. Use SQLAlchemy engine with a `creator` callback that injects the current token. Refresh the token in a background loop before expiry.

**Key config:**
```
pool_size       = 5          (adjust to workload)
max_overflow    = 10
pool_pre_ping   = True       (detect stale connections)
pool_recycle    = 3600       (recycle connections hourly)
sslmode         = "require"
```

**Pattern:**
```python
# Token management: store current token in a mutable container
current_token = [generate_initial_token()]

# Background refresh: refresh before the 1-hour expiry.
# Official docs pattern: check expiry timestamp, refresh within 2 minutes of expiry.
# Alternative: refresh every 30-40 minutes (Lakebase team guidance).
def refresh_loop():
    while True:
        sleep(refresh_interval)
        current_token[0] = generate_new_token()

# SQLAlchemy engine: inject token at connect time
engine = create_engine(url, pool_size=5, pool_pre_ping=True)

@event.listens_for(engine, "do_connect")
def inject_token(dialect, conn_rec, cargs, cparams):
    cparams["password"] = current_token[0]
```

For a complete async implementation with FastAPI integration, see [Databricks docs: Connect to Lakebase](https://docs.databricks.com/aws/en/oltp/projects/authentication).

### Pattern 3: Static URL (Local Development)

> **Local dev only.** Store the URL in a `.env` file excluded from version control — never commit real credentials or paste them into shell history. Do not use this pattern in production; use OAuth token refresh (Pattern 1/2) instead.

```bash
# .env (add to .gitignore)
LAKEBASE_PG_URL="postgresql://user:password@host:5432/database?sslmode=require"
```

```python
import os
url = os.environ["LAKEBASE_PG_URL"]
engine = create_engine(url, pool_size=5)
```

### Pattern 4: Databricks App (Python)

For Python apps deployed on Databricks (FastAPI, Flask, Streamlit). Platform injects env vars automatically when the app has a Lakebase database resource.

**Auto-injected env vars (set at deploy time):**

| Variable | Description |
|----------|-------------|
| `PGHOST` | Lakebase hostname |
| `PGPORT` | Port (default 5432) |
| `PGDATABASE` | Database name |
| `PGUSER` | Service principal client ID |
| `PGSSLMODE` | SSL mode (`require`) |
| `LAKEBASE_ENDPOINT` | Endpoint resource path |

**Pattern:**
```python
import os
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Generate OAuth token using platform-injected endpoint
token = w.postgres.generate_database_credential(
    endpoint=os.environ["LAKEBASE_ENDPOINT"]
).token

# Connect using platform-injected env vars
conn = psycopg.connect(
    host=os.environ["PGHOST"],
    port=int(os.environ.get("PGPORT", "5432")),
    dbname=os.environ["PGDATABASE"],
    user=os.environ["PGUSER"],
    password=token,
    sslmode="require",
)
```

For production apps, combine with Pattern 2's token refresh loop and SQLAlchemy pooling. For the full app development workflow (scaffolding, custom endpoints, schema init), use the **`databricks-apps`** skill.

### Pattern 5: Off-Platform Apps (TypeScript/Node.js)

For apps running outside Databricks (external servers, local dev, CI/CD), use the `@databricks/lakebase` package — it works standalone without AppKit and handles OAuth token refresh, SSL, and connection pooling automatically.

```typescript
import { createLakebasePool } from "@databricks/lakebase";

const pool = createLakebasePool({ host, database, endpoint });
const { rows } = await pool.query("SELECT * FROM my_table LIMIT 10");
```

For full configuration, auth chain, and SSL details, run `npm view @databricks/lakebase readme`.

## Best Practices

- **Always use `sslmode=require`** — Lakebase requires SSL/TLS on all connections
- **Refresh tokens before expiry** — check expiry timestamp, refresh within 2 minutes; or refresh every 30-40 minutes
- **Use connection pooling** — avoid creating a new connection per request
- **Enable `pool_pre_ping`** — detects stale connections after scale-to-zero wake-up
- **Handle scale-to-zero reconnection** — first connection after idle may take ~100ms; implement retry
- **psycopg2 or psycopg3** — both work; psycopg3 recommended for new development (better async, pooling)

## Many Users: Roles and RLS at Scale

A branch holds at most **500 Postgres roles**. Past that, `create-role` fails with `roles limit exceeded; limit:"500"`.

One role per Databricks identity is fine for people and service principals that connect directly (psql, notebooks, jobs). It is the wrong design for an app's end users: it works in testing, then fails in production once the user count reaches the limit, and every per-user role needs its own connections, so pooling does not help.

### Recommended: the app connects as its service principal, RLS reads the user from a setting

The app connects with its own service principal over a shared pool. For each request, it puts the end user's identity in a transaction-local setting. Policies read that setting. In Databricks Apps, the user's email is in the `x-forwarded-email` request header, set by the Apps proxy.

```sql
-- Run once. The app SP usually owns its tables, and an owner bypasses RLS unless it is forced.
ALTER TABLE app.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.orders FORCE ROW LEVEL SECURITY;
CREATE POLICY per_user ON app.orders
  -- NULLIF: after a pooled transaction ends, the setting reads '' (not NULL); treat '' as "no user"
  USING (owner_email = (SELECT NULLIF(current_setting('app.user', true), '')));
```

```python
user = request.headers.get("x-forwarded-email")  # set by the Databricks Apps proxy
if not user:
    raise PermissionError("no authenticated user")  # never run the query without an identity
# pool: a psycopg 3 psycopg_pool.ConnectionPool
with pool.connection() as conn, conn.transaction():
    # is_local=true: the value ends with the transaction, so it cannot leak to the next pooled request
    conn.execute("SELECT set_config('app.user', %s, true)", (user,))
    rows = conn.execute("SELECT * FROM app.orders").fetchall()
```

With the SQLAlchemy engine from Pattern 2, the same transaction is:

```python
from sqlalchemy import text

with engine.begin() as conn:
    conn.execute(text("SELECT set_config('app.user', :user, true)"), {"user": user})
    rows = conn.execute(text("SELECT * FROM app.orders")).fetchall()
```

- Always wrap the setting in `NULLIF(..., '')`. On a fresh connection, `current_setting('app.user', true)` returns NULL. But once any transaction on that pooled connection has set it, later transactions read `''`. Without `NULLIF`, a request that forgets to set the user matches every row whose key is `''`.
- Test it: on one connection, set the user in one transaction, commit, then query without setting it. The policy must return 0 rows.
- Run that test as a role without `BYPASSRLS` (`GRANT <ROLE> TO CURRENT_USER WITH SET TRUE;` then `SET ROLE <ROLE>;`), never as the project owner. The project owner and `databricks_superuser` bypass RLS even with `FORCE`, so they see every row.
- The database trusts the app to set `app.user`. Only the app may send SQL on this connection; never pass user-written SQL through it.
- The app SP must not have `BYPASSRLS` or `databricks_superuser`.
- `FORCE` also applies to jobs and data migrations that run as the SP. With no user set, `UPDATE` and `DELETE` change 0 rows and `SELECT` returns none (DDL still works). Run them under their own role with its own policy, or set `app.user` for the rows they own.
- The policy also checks new rows: an `INSERT` of a row for another user fails with `new row violates row-level security policy`.

### Alternative: one group role, RLS on `system_user`

Use this when the database itself must take each user's identity from their token. Create a role for a Databricks group (`identity_type: GROUP`). Any member connects with their **own** OAuth token and uses the group name as the Postgres user. `current_user` is the group; `system_user` still holds the member's identity. The cost: each user's token needs its own connection, so connections are not shared across users.

```bash
databricks postgres create-role projects/<PROJECT_ID>/branches/<BRANCH_ID> \
  --role-id app-users \
  --json '{"spec": {"identity_type": "GROUP", "postgres_role": "<DATABRICKS_GROUP_NAME>", "auth_method": "LAKEBASE_OAUTH_V1"}}' \
  --profile <PROFILE>
```

```sql
-- Grants go to the group role, not to each user
GRANT USAGE ON SCHEMA app TO "<DATABRICKS_GROUP_NAME>";
GRANT SELECT ON app.orders TO "<DATABRICKS_GROUP_NAME>";

-- system_user looks like 'password:user@example.com'; take the part after the colon
ALTER TABLE app.orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY per_user ON app.orders
  USING (owner_email = split_part(system_user, ':', 2));
```

```python
# Each connection uses the end user's own token, with the group as the Postgres user
conn = psycopg.connect(host=host, dbname="databricks_postgres", user="<DATABRICKS_GROUP_NAME>",
                       password=user_token, sslmode="require")
```

- A token for an identity outside the group is refused at login (`OAuth: User is not authorized`).
- RLS on `current_user` does **not** work here: it returns the group name, so it matches no user's rows.
- `system_user` is set at login and does not change on `SET ROLE`. If the app logs in once as its own role and switches with `SET ROLE <user>`, `system_user` is the app's identity for every user. Pass each user's token on their connection instead (in Databricks Apps, the user token from user authorization).

## Data API

PostgREST-compatible HTTP API for CRUD operations on Postgres tables. **Autoscaling only.**

### Enabling

1. Navigate to **Data API** in the Lakebase project UI
2. Click **Enable Data API** — auto-creates the `authenticator` role and `pgrst` schema
3. The `public` schema is exposed by default

### Authentication

All requests require a Databricks OAuth bearer token:

```
Authorization: Bearer <databricks-oauth-token>
```

Each Databricks identity must have a matching Postgres role — the auto-created `authenticator` role assumes the caller's identity at query time. Every one of those roles counts toward the 500-roles-per-branch limit, so plan for the number of distinct callers (see [Many Users: Roles and RLS at Scale](#many-users-roles-and-rls-at-scale)).

**Create a role for Data API access** (run as the project owner in the SQL Editor or `psql`; a role added in the **Roles & Databases** UI cannot be granted to `authenticator`):

```sql
CREATE EXTENSION IF NOT EXISTS databricks_auth;
-- <ROLE> is the user's email, or the service principal's application ID
SELECT databricks_create_role('<ROLE>', 'USER');   -- service principal: ('<ROLE>', 'SERVICE_PRINCIPAL')
GRANT "<ROLE>" TO authenticator;                    -- lets the Data API act as this identity

-- Grant only the schema, tables, and operations this caller needs
GRANT USAGE ON SCHEMA <SCHEMA> TO "<ROLE>";
GRANT SELECT ON <SCHEMA>.<TABLE> TO "<ROLE>";
```

- Without `GRANT "<ROLE>" TO authenticator`, every request fails with `permission denied to set role`.
- Do not use `CREATE ROLE "<ROLE>" LOGIN`: it makes a plain Postgres role with no Databricks login (auth method `NO_LOGIN`).
- Do not grant `ON ALL TABLES IN SCHEMA public`. `public` also holds Lakebase internal objects (`databricks_list_roles`, `databricks_auth_metrics`, `databricks_synced_table_managers`), and that grant covers them too.
- Add `INSERT`, `UPDATE`, or `DELETE` only on tables the caller writes. If an inserted table uses a sequence, also grant `USAGE` on that sequence.
- Do not use the project owner's identity, and do not give the caller `BYPASSRLS` or `databricks_superuser`: RLS does not apply to them.

**Function-only access.** The caller can run one function and read no tables. Create the role and the `authenticator` grant as above, then grant only the function:

```sql
CREATE FUNCTION <SCHEMA>.order_count() RETURNS bigint
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = pg_catalog, pg_temp
  AS $$ SELECT count(*) FROM <SCHEMA>.orders $$;
REVOKE EXECUTE ON FUNCTION <SCHEMA>.order_count() FROM PUBLIC;   -- by default, every role can run a new function
GRANT USAGE ON SCHEMA <SCHEMA> TO "<ROLE>";
GRANT EXECUTE ON FUNCTION <SCHEMA>.order_count() TO "<ROLE>";
```

Call it as an RPC with HTTP `POST`.

`SECURITY DEFINER` runs the function as its owner. If the owner bypasses RLS (the project owner does), the function sees every row, not only the caller's. Use it only for results every caller may see, such as a total, or have it owned by a role without `BYPASSRLS`.

- `SECURITY DEFINER` runs the function as its owner. RLS inside it is checked against the owner, and `current_user` inside it is the owner, not the caller. Return only data that every granted caller may see.
- Always `REVOKE EXECUTE ... FROM PUBLIC`. Without it, any role with `USAGE` on the schema can call the function.
- Keep the `SET search_path` line, so names in the function cannot resolve to objects that a caller created.

### CRUD Operations

```bash
# GET — query with filters, pagination, ordering
curl -H "Authorization: Bearer $TOKEN" "$DATA_API_URL/public/users?age=gt.21&limit=10&order=created_at.desc"

# POST — insert
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}' "$DATA_API_URL/public/users"

# PATCH — update (filter required)
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"status": "inactive"}' "$DATA_API_URL/public/users?id=eq.42"

# DELETE (filter required)
curl -X DELETE -H "Authorization: Bearer $TOKEN" "$DATA_API_URL/public/users?id=eq.42"
```

### Row-Level Security (RLS)

Strongly recommended for multi-tenant data. Policies use `current_user` (the authenticated Databricks email).

```sql
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON users USING (email = current_user);
```

**Views bypass RLS unless they use `security_invoker`.** By default, Postgres checks RLS on a view's tables as the view **owner**, not the caller. If the owner is the table owner, the project owner, or `databricks_superuser`, every caller with `SELECT` on the view sees all rows. `FORCE ROW LEVEL SECURITY` does not fix this when the view owner has `BYPASSRLS`, and the project owner does.

```sql
CREATE VIEW user_summary WITH (security_invoker = true) AS SELECT id, email FROM users;
GRANT SELECT ON user_summary, users TO "<ROLE>";   -- the view runs with the caller's privileges, so the caller needs the base table too
ALTER VIEW <VIEW_NAME> SET (security_invoker = true);   -- fix an existing view

-- Views in the exposed schema without security_invoker. Must return no rows for a dedicated API schema;
-- in public it also lists Lakebase internal views (databricks_list_roles and others)
SELECT c.oid::regclass AS view_name FROM pg_class c
WHERE c.relkind = 'v' AND c.relnamespace = '<SCHEMA>'::regnamespace
  AND NOT coalesce('security_invoker=true' = ANY (c.reloptions), false);
```

- Do not expose a materialized view over an RLS table. It stores the owner's result, so every caller sees all rows, and Postgres does not accept `security_invoker` on it.
- Test isolation as a caller role without `BYPASSRLS`, never as the project owner. The owner sees every row.

### Configuration

Via the Data API UI: exposed schemas, max rows, CORS origins, OpenAPI spec.

**Required before production.** The defaults are open:

- **CORS allowed origins:** the default is empty, and empty means **all origins** (`*`), not none. The status can read `["none"]` while the API answers any origin with `*`. List the exact origins of your app (for example, `https://app.example.com`). A local dev server (`http://localhost:<PORT>`) is a separate origin; add it only on a dev branch.
- **Maximum rows:** the default is empty, so a response has no row limit. Set a limit, and page in clients.
- **Exposed schemas:** the default is `public`. Expose only the schema you built for the API.

CORS limits only browsers. Grants and RLS still control what each token can read.

The same settings with the Python SDK (tested with databricks-sdk 0.133.0):

```python
from databricks.sdk.service.postgres import DataApi, DataApiDataApiSpec
from databricks.sdk.common.types.fieldmask import FieldMask

w.postgres.update_data_api(
    name="projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DATABASE_ID>/data-api",
    data_api=DataApi(spec=DataApiDataApiSpec(
        db_schemas=["<SCHEMA>"], db_max_rows=1000,
        server_cors_allowed_origins=["https://app.example.com"])),
    update_mask=FieldMask(field_mask=["spec.db_schemas", "spec.db_max_rows", "spec.server_cors_allowed_origins"]),
).wait()
```

### Unsupported PostgREST Features

Computed relationships, inner-join embedding, custom media type handlers, stripped-nulls, planned/estimated counts, transaction control via headers, EXPLAIN/trace, pre-request functions, GUCs, PostGIS auto-GeoJSON.