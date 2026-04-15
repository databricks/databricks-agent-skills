---
name: databricks-lakebase
description: "Manage Lakebase Postgres Autoscaling projects, branches, and endpoints via Databricks CLI. Use when asked to create, configure, or manage Lakebase Postgres databases, projects, branches, computes, or endpoints."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Lakebase Postgres Autoscaling

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Lakebase is Databricks' serverless Postgres-compatible database (similar to Neon), available on both AWS and Azure. It provides fully managed OLTP storage with autoscaling, branching, and scale-to-zero.

> **Autoscaling by Default (March 2026):** All new Lakebase instances are now created as Autoscaling projects. The `/database/` APIs now create autoscaling instances behind the scenes — new instances created via `/database/` API can be managed by both `/database/` and `/postgres/` APIs. Existing provisioned instances are unchanged.

**Compliance:** Autoscaling supports the compliance security profile for HIPAA, C5, TISAX, or None. Other compliance standards are not currently supported.

Manage Lakebase Postgres projects, branches, endpoints, and databases via `databricks postgres` CLI commands.

| Feature | Description |
|---------|-------------|
| **Autoscaling Compute** | 0.5–32 CU autoscaling (dynamic) and 36–112 CU fixed-size (no autoscaling), with ~2 GB RAM per CU |
| **Scale-to-Zero** | Compute suspends after configurable inactivity timeout (default 5 min) |
| **Branching** | Copy-on-write isolated database environments for dev/test |
| **Instant Restore** | Point-in-time restore within configured window (up to 30 days) |
| **OAuth Authentication** | Token-based auth via Databricks SDK (1-hour expiry) |
| **High Availability** | 1 primary + 1–3 secondaries across AZs with automatic failover |
| **Data API** | PostgREST-compatible HTTP API for CRUD operations (Autoscaling only) |
| **Cloud Support** | AWS and Azure (GA on both) |
| **Reverse ETL** | Sync data from Delta tables to PostgreSQL via synced tables |

## Quick links

- [computes.md](references/computes.md) — Compute sizing, autoscaling configuration, and scale-to-zero details
- [connection-patterns.md](references/connection-patterns.md) — Connection pooling, token refresh, and DNS workarounds
- [reverse-etl.md](references/reverse-etl.md) — Synced tables from Delta Lake to Lakebase with data type mapping
- [high-availability.md](references/high-availability.md) — HA configuration, failover behavior, and replica types
- [data-api.md](references/data-api.md) — PostgREST-compatible HTTP API for CRUD operations


## Resource Hierarchy

```
Project (top-level container)
  └── Branch (isolated database environment, copy-on-write)
        ├── Endpoint (read-write or read-only)
        ├── Database (standard Postgres DB)
        └── Role (Postgres role)
```

- **Project**: Top-level container. Creating one auto-provisions a `production` branch and a `primary` read-write endpoint.
- **Branch**: Isolated database environment sharing storage with parent (copy-on-write). States: `READY`, `ARCHIVED`.
- **Endpoint** (called **Compute** in the Lakebase UI): Compute resource powering a branch. Types: `ENDPOINT_TYPE_READ_WRITE`, `ENDPOINT_TYPE_READ_ONLY` (read replica).
- **Database**: Standard Postgres database within a branch. Default: `databricks_postgres`.
- **Role**: Postgres role within a branch. Manage roles via `databricks postgres create-role -h`.

### Resource Name Formats

| Resource | Format |
|----------|--------|
| Project | `projects/{project_id}` |
| Branch | `projects/{project_id}/branches/{branch_id}` |
| Endpoint | `projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}` |
| Database | `projects/{project_id}/branches/{branch_id}/databases/{database_id}` |

All IDs: 1-63 characters, start with lowercase letter, lowercase letters/numbers/hyphens only (RFC 1123).

## CLI Discovery — ALWAYS Do This First

> **Note:** "Lakebase" is the product name; the CLI command group is `postgres`. All commands use `databricks postgres ...`.

**Do NOT guess command syntax.** Discover available commands and their usage dynamically:

```bash
# List all postgres subcommands
databricks postgres -h

# Get detailed usage for any subcommand (flags, args, JSON fields)
databricks postgres <subcommand> -h
```

Run `databricks postgres -h` before constructing any command. Run `databricks postgres <subcommand> -h` to discover exact flags, positional arguments, and JSON spec fields for that subcommand.

## Create a Project

> **Do NOT list projects before creating.**

```bash
databricks postgres create-project <PROJECT_ID> \
  --json '{"spec": {"display_name": "<DISPLAY_NAME>"}}' \
  --profile <PROFILE>
```

- Auto-creates: `production` branch + `primary` read-write endpoint (1 CU min/max, scale-to-zero)
- Long-running operation; the CLI waits for completion by default. Use `--no-wait` to return immediately.
- Run `databricks postgres create-project -h` for all available spec fields (e.g. `pg_version`).

After creation, verify the auto-provisioned resources:

```bash
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>
databricks postgres list-endpoints projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
databricks postgres list-databases projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

### Updating a Project

Updates require specifying which fields to modify:

```bash
databricks postgres update-project projects/<PROJECT_ID> spec.display_name \
  --json '{"spec": {"display_name": "My Updated Application"}}' \
  --profile <PROFILE>
```

### Deleting a Project

**WARNING:** Permanent — deletes all branches, computes, databases, roles, and data. Delete all synced tables first. **Do not delete without explicit permission from user.**

```bash
databricks postgres delete-project projects/<PROJECT_ID> --profile <PROFILE>
```

## Autoscaling

Endpoints use **compute units (CU)** for autoscaling (~2 GB RAM per CU). Configure min/max CU via `create-endpoint` or `update-endpoint`. Run `databricks postgres create-endpoint -h` to see all spec fields.

**Autoscale range:** 0.5–32 CU (dynamic). **Fixed-size:** 36–112 CU (no autoscaling). Max − Min cannot exceed 16 CU. Scale-to-zero is enabled by default (5 min inactivity timeout). See [computes.md](references/computes.md) for sizing tables, scale-to-zero behavior, and configuration details.

```bash
# Create endpoint with autoscaling
databricks postgres create-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID> <ENDPOINT_ID> \
  --json '{
    "spec": {
      "endpoint_type": "ENDPOINT_TYPE_READ_WRITE",
      "autoscaling_limit_min_cu": 2.0,
      "autoscaling_limit_max_cu": 8.0
    }
  }' --profile <PROFILE>

# Resize existing endpoint
databricks postgres update-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  "spec.autoscaling_limit_min_cu,spec.autoscaling_limit_max_cu" \
  --json '{"spec": {"autoscaling_limit_min_cu": 2.0, "autoscaling_limit_max_cu": 8.0}}' \
  --profile <PROFILE>
```

## High Availability

Lakebase supports HA with 1 primary + 1–3 secondary compute instances across availability zones. GA on both AWS and Azure.

- **Failover:** Automatic — primary connection string routes to promoted secondary transparently. All committed transactions are preserved; active connections must reconnect.
- **Connection strings:** Primary (`{endpoint-id}.database.{region}.databricks.com`) for read-write; read-only (`{endpoint-id}-ro.database.{region}.databricks.com`) routes to readable secondaries.
- **Constraints:** Scale-to-zero is **not supported** with HA. Max autoscaling spread remains 16 CU. Secondaries always scale to at least primary size.

**HA secondaries vs read replicas:** Secondaries participate in failover and share sizing with the primary. Read replicas are independent, read-only endpoints that do not participate in failover. Both can coexist on the same branch.

See [high-availability.md](references/high-availability.md) for configuration details, failover semantics, and best practices.

## Branches

Branches are copy-on-write snapshots of an existing branch. Use them for **experimentation**: testing schema migrations, trying queries, or previewing data changes — without affecting production.

```bash
databricks postgres create-branch projects/<PROJECT_ID> <BRANCH_ID> \
  --json '{
    "spec": {
      "source_branch": "projects/<PROJECT_ID>/branches/<SOURCE_BRANCH_ID>",
      "no_expiry": true
    }
  }' --profile <PROFILE>
```

Branches require an expiration policy: use `"no_expiry": true` for permanent branches, or `"ttl": "<seconds>s"` for ephemeral branches (max 30 days).

**Limits:** Max 10 unarchived branches per project. Max 500 total branches. Max 1,000 projects per workspace. Logical data: 8 TB per branch.

**Recommended TTL by use case:**

| Use Case | TTL | JSON |
|----------|-----|------|
| CI/CD environments | 2–4 hours | `"ttl": "14400s"` |
| Demos | 24–48 hours | `"ttl": "172800s"` |
| Feature development | 1–7 days | `"ttl": "604800s"` |
| Long-term testing | Up to 30 days | `"ttl": "2592000s"` |

### Branch from a Point in Time

Create a branch from a specific past state (within the restore window) for recovery or historical analysis. Run `databricks postgres create-branch -h` for the time specification fields.

### Resetting a Branch

Reset completely replaces a branch's data and schema with the latest from its parent. Local changes are lost. Root branches (like `production`) and branches with children cannot be reset.

```bash
databricks postgres reset-branch projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

### Protecting and Deleting Branches

When done experimenting, delete the branch. Protected branches must be unprotected first -- use `update-branch` to set `spec.is_protected` to `false`, then delete:

```bash
# Step 1 — unprotect
databricks postgres update-branch projects/<PROJECT_ID>/branches/<BRANCH_ID> \
  --json '{"spec": {"is_protected": false}}' --profile <PROFILE>

# Step 2 — delete (run -h to confirm positional arg format for your CLI version)
databricks postgres delete-branch projects/<PROJECT_ID>/branches/<BRANCH_ID> \
  --profile <PROFILE>
```

**Never delete the `production` branch** — it is the authoritative branch auto-provisioned at project creation. Cannot delete branches with child branches (delete children first).

## Connecting to Lakebase

Lakebase supports two authentication methods:

| Method | Token Lifetime | Best For |
|--------|---------------|----------|
| **OAuth tokens** | 1 hour (must refresh) | Interactive sessions, workspace-integrated apps |
| **Native Postgres passwords** | No expiry | Long-running processes, tools without token rotation |

**Connection timeouts:** 24-hour idle timeout, 3-day maximum connection lifetime.

### Get Connection Details

```bash
# Get endpoint host and connection info
databricks postgres get-endpoint \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  --profile <PROFILE>
```

See [connection-patterns.md](references/connection-patterns.md) for connection pooling, token refresh, and DNS workarounds.  
**Always use `sslmode=require`.** Tokens expire after 1 hour — production apps must implement token refresh. 


## Reverse ETL (Synced Tables)

Sync data from Unity Catalog Delta tables into Lakebase as PostgreSQL tables for OLTP access patterns.

| Sync Mode | Description | Best For |
|-----------|-------------|----------|
| **Snapshot** | One-time full copy | Initial setup, small tables |
| **Triggered** | Scheduled updates on demand | Dashboards updated hourly/daily |
| **Continuous** | Real-time streaming (~seconds latency) | Live applications |

**Triggered and Continuous modes require Change Data Feed (CDF) on the source table:**

**Performance:** ~150 rows/sec per CU (continuous/triggered), ~2,000 rows/sec per CU (snapshot). Each synced table uses up to 16 connections. 8 TB total across all synced tables; recommend < 1 TB per table requiring refreshes.

See [reverse-etl.md](references/reverse-etl.md) for data type mapping, capacity planning, and examples.

## What's Next

### Build a Databricks App

After creating a Lakebase project, scaffold a Databricks App connected to it.

**Step 1 — Discover branch name** (use `.name` from a `READY` branch):

```bash
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>
```

**Step 2 — Discover database name** (use `.name` from the desired database; `<BRANCH_ID>` is the branch ID, not the full resource name):

```bash
databricks postgres list-databases projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

**Step 3 — Scaffold the app** with the `lakebase` feature:

```bash
databricks apps init --name <APP_NAME> \
  --features lakebase \
  --set "lakebase.postgres.branch=<BRANCH_NAME>" \
  --set "lakebase.postgres.database=<DATABASE_NAME>" \
  --run none --profile <PROFILE>
```

Where `<BRANCH_NAME>` is the full resource name (e.g. `projects/<PROJECT_ID>/branches/<BRANCH_ID>`) and `<DATABASE_NAME>` is the full resource name (e.g. `projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DB_ID>`).

For the full app development workflow, use the **`databricks-apps`** skill.

### Schema Permissions for Deployed Apps

When a Lakebase database is used by a deployed Databricks App, the app's Service Principal has `CAN_CONNECT_AND_CREATE` permission, which means it can create new objects but **cannot access any existing schemas or tables** (including `public`). The SP must create the schema itself to become its owner.

**ALWAYS deploy the app before running it locally.** This is the #1 source of Lakebase permission errors.

When deployed, the app's Service Principal runs the schema initialization SQL (e.g. `CREATE SCHEMA IF NOT EXISTS app_data`), creating the schema and tables — and becoming their **owner**. Only the owner (or a superuser) can access those objects.

**If you run locally first**, your personal credentials create the schema and become the owner. The deployed Service Principal then **cannot access it** — even though it has `CAN_CONNECT_AND_CREATE` — because it didn't create it and cannot access existing schemas.

**Correct workflow:**
1. **Deploy first**: `databricks apps deploy <APP_NAME> --profile <PROFILE>` — verify with `databricks apps get <APP_NAME> --profile <PROFILE>` that the app is deployed before proceeding
2. **Grant local access** *(if needed)*: if you're not the project creator, assign `databricks_superuser` to your identity via the Lakebase UI. Project creators already have sufficient access.
3. **Develop locally**: your credentials get DML access (SELECT/INSERT/UPDATE/DELETE) to SP-owned schemas

> **Note:** Project creators already have access to SP-owned schemas. Other team members need `databricks_superuser` (grants full DML but **not DDL**). If you need to alter the schema during local development, redeploy the app to apply DDL changes.

**If you already ran locally first** and hit `permission denied` after deploying: the schema is owned by your personal credentials, not the SP. **⚠️ Do NOT drop the schema without asking the user first** — dropping it (`DROP SCHEMA <name> CASCADE`) **deletes all data** in that schema. Ask the user how they'd like to proceed:
- **Option A (destructive):** Drop the schema and redeploy so the SP recreates it. Only safe if the schema has no valuable data.
- **Option B (manual):** The user can reassign ownership or manually grant the SP access, preserving existing data.

### Other Workflows

**Connect a Postgres client**
Get the connection string from the endpoint, then connect with psql, DBeaver, or any standard Postgres client.

```bash
databricks postgres get-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>
```

**Manage roles and permissions**
Create Postgres roles and grant access to databases or schemas.

```bash
databricks postgres create-role -h   # discover role spec fields
```

**Add a read-only endpoint**
Create a read replica for analytics or reporting workloads to avoid contention on the primary read-write endpoint.

```bash
databricks postgres create-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID> <ENDPOINT_ID> \
  --json '{"spec": {"type": "ENDPOINT_TYPE_READ_ONLY"}}' --profile <PROFILE>
```

**Access Lakebase via Data API (HTTP)**
Lakebase provides a PostgREST-compatible REST API for HTTP-based CRUD operations on Postgres tables. Uses Databricks OAuth authentication. Available for Autoscaling projects only. See [data-api.md](references/data-api.md) for setup, authentication, and usage examples.

## Key Differences from Lakebase Provisioned

> **Note:** All new Lakebase instances default to Autoscaling as of March 2026. Existing provisioned instances remain operational. At a future date, you will be able to upgrade provisioned instances to autoscaling.

| Aspect | Provisioned | Autoscaling |
|--------|-------------|-------------|
| SDK module | `w.database` | `w.postgres` |
| CLI command group | `databricks database` | `databricks postgres` |
| Top-level resource | Instance | Project |
| Capacity | CU_1, CU_2, CU_4, CU_8 (16 GB/CU) | 0.5–112 CU (2 GB/CU) |
| Branching | Not supported | Full branching support |
| Scale-to-zero | Not supported | Configurable timeout |
| High Availability | Readable secondaries | HA with 1–3 secondaries + read replicas |
| Data API | Not available | PostgREST-compatible HTTP API |
| Cloud support | AWS | AWS and Azure |
| Operations | Direct SDK calls | Long-running operations (LRO) |

### Migrating Provisioned to Autoscaling

**Current method:** Use `pg_dump` and `pg_restore` (standard Postgres tools) to export data from a provisioned instance and import into a new autoscaling project.

1. Create a new autoscaling project: `databricks postgres create-project`
2. Export from provisioned: `pg_dump` from the provisioned instance
3. Import to autoscaling: `pg_restore` into the new project
4. Update application connection strings to the new endpoint
5. Verify data integrity and delete the provisioned instance when ready

## Troubleshooting

| Error | Solution |
|-------|----------|
| `cannot configure default credentials` | Use `--profile` flag or authenticate first |
| `PERMISSION_DENIED` | Check workspace permissions |
| `permission denied for schema <name>` | Schema owned by another role. Deploy the app first so the SP creates and owns the schema. See **Schema Permissions for Deployed Apps** above |
| Protected branch cannot be deleted | `update-branch` to set `spec.is_protected` to `false` first |
| Long-running operation timeout | Use `--no-wait` and poll with `get-operation` |
| Token expired during long query | Implement token refresh loop; tokens expire after 1 hour. See [connection-patterns.md](references/connection-patterns.md) |
| Connection refused after scale-to-zero | Compute wakes automatically; reactivation takes a few hundred ms; implement retry logic |
| Branch deletion blocked by children | Delete child branches first; cannot delete branches with children |
| Autoscaling range too wide | Max − Min cannot exceed 16 CU (e.g., 2–18 CU is valid, 0.5–32 CU is not) |
| SSL required error | Always use `sslmode=require` in connection string |
| Update mask required | All update operations require specifying fields to modify (see `update-*` subcommand `-h`) |
| Connection closed after 24h idle | All connections have a 24-hour idle timeout and 3-day max lifetime; implement retry logic |

## SDK and Version Requirements

- **Databricks CLI**: >= v0.294.0
- **Databricks SDK for Python**: >= 0.81.0 (for `w.postgres` module)
- **psycopg**: 3.x (supports `hostaddr` parameter for DNS workaround)
- **SQLAlchemy**: 2.x with `postgresql+psycopg` driver
- **Postgres versions**: 16 and 17 (default: PG 17 via `databricks postgres` API; PG 16 via `databricks database` API)

```python
%pip install -U "databricks-sdk>=0.81.0" "psycopg[binary]>=3.0" sqlalchemy
```