# Lakebase Connectivity

## Authentication Methods

| Method | Token Lifetime | Best For |
|--------|---------------|----------|
| **OAuth tokens** | 1 hour (must refresh) | Interactive sessions, workspace-integrated apps |
| **Native Postgres passwords** | No expiry | Long-running processes, tools without token rotation |

**Connection timeouts:** 24h idle timeout is guaranteed. Max connection lifetime beyond 24h is not guaranteed — implement reconnection logic. Always use `sslmode=require`.

## Connection Patterns (Python)

> **JavaScript/TypeScript Databricks Apps** using AppKit get Lakebase connectivity fully auto-injected via `createLakebasePool()` — see the **`databricks-apps`** skill.

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

For production apps, combine with Pattern 2's token refresh loop and SQLAlchemy pooling. For the full app development workflow (scaffolding, tRPC, schema init), use the **`databricks-apps`** skill.

## Best Practices

- **Always use `sslmode=require`** — Lakebase requires SSL/TLS on all connections
- **Refresh tokens before expiry** — check expiry timestamp, refresh within 2 minutes; or refresh every 30-40 minutes
- **Use connection pooling** — avoid creating a new connection per request
- **Enable `pool_pre_ping`** — detects stale connections after scale-to-zero wake-up
- **Handle scale-to-zero reconnection** — first connection after idle may take ~100ms; implement retry
- **psycopg2 or psycopg3** — both work; psycopg3 recommended for new development (better async, pooling)

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

Each Databricks identity must have a matching Postgres role — the auto-created `authenticator` role assumes the caller's identity at query time.

**Create a role for Data API access:**

```sql
CREATE ROLE "user@example.com" LOGIN;
GRANT USAGE ON SCHEMA public TO "user@example.com";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "user@example.com";
```

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

### Configuration

Via the Data API UI: exposed schemas, max rows, CORS origins, OpenAPI spec.

### Unsupported PostgREST Features

Computed relationships, inner-join embedding, custom media type handlers, stripped-nulls, planned/estimated counts, transaction control via headers, EXPLAIN/trace, pre-request functions, GUCs, PostGIS auto-GeoJSON.