# Lakebase Data API

## Overview

The Lakebase Data API is a PostgREST-compatible RESTful interface that automatically exposes Postgres tables and functions as HTTP endpoints. It supports CRUD operations and RPC calls via standard HTTP verbs without requiring custom backend code. **Available for Autoscaling projects only.**

## Enabling the Data API

1. Navigate to the **Data API** page in your Lakebase project UI
2. Click **Enable Data API** — this auto-creates the `authenticator` role and configures the internal `pgrst` schema
3. The `public` schema is exposed by default; configure additional exposed schemas via the UI

The Data API URL is displayed in the UI after enabling. Callers append the schema name to the base URL.

## Authentication

All requests require a **Databricks OAuth bearer token** in the `Authorization` header. JWT-based and anonymous access are not supported.

```
Authorization: Bearer <databricks-oauth-token>
```

Each Databricks identity (user, service principal, group) must have a **matching Postgres role** — the `authenticator` role assumes the caller's role at query time.

### Creating Roles for Data API Access

Create a Postgres role for each identity that needs Data API access:

```sql
-- Via SQL (connect to the Lakebase database)
CREATE ROLE "user@example.com" LOGIN;
GRANT USAGE ON SCHEMA public TO "user@example.com";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "user@example.com";
```

Roles can also be created via the Lakebase UI, Python SDK, or REST API. The role **must not** be the database owner.

## Basic Usage

### Query data (GET)

```bash
# Get all rows from a table
curl -H "Authorization: Bearer $TOKEN" \
  "$DATA_API_URL/public/users"

# Filter rows
curl -H "Authorization: Bearer $TOKEN" \
  "$DATA_API_URL/public/users?age=gt.21&status=eq.active"

# Select specific columns
curl -H "Authorization: Bearer $TOKEN" \
  "$DATA_API_URL/public/users?select=id,name,email"

# Pagination
curl -H "Authorization: Bearer $TOKEN" \
  "$DATA_API_URL/public/users?limit=10&offset=20"

# Ordering
curl -H "Authorization: Bearer $TOKEN" \
  "$DATA_API_URL/public/users?order=created_at.desc"
```

### Insert data (POST)

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}' \
  "$DATA_API_URL/public/users"
```

### Update data (PATCH)

```bash
curl -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "inactive"}' \
  "$DATA_API_URL/public/users?id=eq.42"
```

### Delete data (DELETE)

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  "$DATA_API_URL/public/users?id=eq.42"
```

## Row-Level Security (RLS)

RLS is **strongly recommended** for multi-tenant or sensitive data. Once enabled, rows are invisible by default until policies are added.

```sql
-- Enable RLS on a table
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see their own rows
CREATE POLICY user_isolation ON users
  USING (email = current_user);
```

Policies use `current_user` (the authenticated Databricks email) to implement tenant isolation, user-owned data, team-based access, and role-based read/write distinctions.

## Configuration

The Data API UI provides settings for:
- **Exposed schemas** — which schemas are accessible via the API
- **Max rows** — limit response size to prevent performance degradation
- **CORS** — configure allowed origins for browser-based access
- **OpenAPI spec** — optionally publish an OpenAPI schema for client generation

## Unsupported PostgREST Features

The following PostgREST features are not supported or only partially supported in the Lakebase Data API:

- Computed relationships and inner-join embedding hints (`!inner`)
- Custom media type handlers and stripped-nulls formatting
- Planned and estimated count options
- Transaction control via preference headers
- Query plan exposure (`EXPLAIN`) and trace header propagation
- Pre-request functions and application settings (GUCs)
- PostGIS automatic GeoJSON formatting

Lakebase provides its own observability mechanisms in place of PostgREST's built-in query plan endpoints.
