---
name: databricks-lakebase
description: "Databricks Lakebase Postgres: projects, scaling, connectivity, Lakebase synced tables, and Data API. Use when asked about Lakebase databases, OLTP storage, or connecting apps to Postgres on Databricks."
compatibility: Requires databricks CLI (>= v0.294.0)
metadata:
  version: "0.2.0"
parent: databricks-core
---

# Lakebase Postgres Autoscaling

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, and profile selection.

Lakebase is Databricks' serverless Postgres-compatible database, available on AWS and Azure (GA) and on GCP (Beta). It provides fully managed OLTP storage with autoscaling, branching, and scale-to-zero.

**Regions:** Lakebase runs only in the commercial regions listed in [Region availability](https://docs.databricks.com/oltp/projects/manage-projects#availability) (check the page for the user's cloud). It isn't available on AWS GovCloud, and the Azure list has no Azure Government or Azure China regions. If the workspace is in one of these clouds or an unlisted region, tell the user that Lakebase isn't available there. Don't try to create a project.

> **Provisioned Lakebase no longer exists. Never create it.** The old Provisioned tier (static, non-scalable Postgres; `databricks database` CLI / `w.database` SDK) is being migrated to Autoscaling over summer 2026, with no customer action required. Lakebase today is Autoscaling-only (`databricks postgres` / `w.postgres`). Do not attempt to create Provisioned instances; if a user asks for one, tell them Provisioned instances don't exist anymore and point them to Autoscaling. Treat the legacy `database` resource key in app configs as retired, and migrate to the `postgres` resource key. For the legacy DAB `synced_database_tables` resource, use the `postgres_synced_tables` bundle resource or the `databricks postgres create-synced-table` CLI flow instead (see the Common Issues row and `references/synced-tables.md`).

For context when reading older configs or docs, here is how the retired Provisioned tier maps to Autoscaling:

| Aspect | Provisioned (retired) | Autoscaling (current) |
|--------|-----------------------|-----------------------|
| CLI group | `databricks database` | `databricks postgres` |
| Top-level resource | Instance | Project |
| Capacity | CU_1–CU_8 (16 GB/CU) | 0.5–112 CU (2 GB/CU) |
| Branching | Not supported | Full support |
| Scale-to-zero | Not supported | Configurable |
| HA | Readable secondaries | 1–3 secondaries + read replicas |
| Data API | Not available | PostgREST HTTP API |
| Cloud | AWS only | AWS and Azure (GA), GCP (Beta) |

**Compliance:** Supports HIPAA, C5, TISAX, or None. Before any PHI goes into Lakebase, apply the HIPAA gate below.

## HIPAA Gate (PHI)

HIPAA coverage comes from the workspace: the compliance security profile with the HIPAA standard, plus a Business Associate Agreement. Confirm both with the user before PHI goes in. Then:

- **Preview features:** do not use a Preview or Beta feature (for example, Lakehouse Sync) for PHI unless it is listed for your region in [Regional support for features](https://docs.databricks.com/aws/en/security/privacy/hipaa). Check the list each time.
- **Existing projects:** a project that was running when HIPAA was turned on has no HIPAA audit logging until its compute restarts. Databricks does not restart it for you. Restart each compute.
- **No PHI in metadata:** never put PHI in database, schema, table, column, or role names, in tags, or in other customer-defined fields. These appear in audit logs and system metadata, and Databricks cannot remove them later.
- **No PHI in SQL text:** pass PHI values as query parameters, never as literals. Audit logs record statement text.
- **No PHI in logs or tickets:** keep PHI out of app logs, error messages, screenshots, diagnostic output, and support requests.
- **Least privilege:** grant each role only the schemas, tables, and operations it needs.

Sources: [HIPAA compliance for Lakebase](https://docs.databricks.com/aws/en/oltp/projects/hipaa-compliance), [Enable HIPAA compliance](https://docs.databricks.com/aws/en/oltp/projects/enable-hipaa-compliance).

## Row-Level Security and Data API: Must-Follow Rules

Apply these whenever a design has per-user rows, RLS, or the Data API. Details and tests are in [connectivity.md](references/connectivity.md).

- **Many end users:** a branch holds at most 500 Postgres roles. Never create one role per app user. The app connects as its service principal over a pool and sets the user per transaction: `SELECT set_config('app.user', $1, true)`.
- **RLS on a setting:** wrap it in `NULLIF`: `USING (owner_email = (SELECT NULLIF(current_setting('app.user', true), '')))`. On a reused pooled connection, an unset value reads `''`, not NULL. Also run `ALTER TABLE ... FORCE ROW LEVEL SECURITY`, because the table owner bypasses RLS otherwise.
- **Testing RLS:** never test as the project owner or `databricks_superuser`, and never grant `databricks_superuser` to a teammate for local work. Both bypass RLS. Use a role with only `USAGE` on the app's schema and the table privileges it needs.
- **Views over RLS tables:** create them `WITH (security_invoker = true)`, and grant the caller `SELECT` on the base table too. A default view checks RLS as its owner, so every caller sees all rows.
- **Data API before production:** the defaults are open. Empty CORS origins means **all** origins, and empty maximum rows means no limit. Set the exact app origins and a row limit, and expose only the schema built for the API, not `public`.

## Capabilities

- **Project lifecycle** -- create, update, delete Lakebase Postgres Autoscaling projects
- **Branching** -- copy-on-write branches with TTL, point-in-time recovery, and reset
- **Compute scaling** -- autoscale 0.5--64 CU, fixed up to 112 CU, scale-to-zero
- **High availability** -- 1 primary + 1--3 secondaries, automatic failover
- **PostgreSQL connectivity** -- OAuth token refresh, connection pooling, SSL
- **Data API** -- PostgREST-compatible HTTP CRUD (Autoscaling only)
- **Lakebase synced tables** -- sync Unity Catalog Delta tables into Postgres (previously known as Reverse ETL)
- **Databricks App integration** -- scaffold apps with Lakebase feature, deploy-first workflow
- **Cloud support** -- AWS and Azure (GA), GCP (Beta)

**Reference docs:**
- [computes-and-scaling.md](references/computes-and-scaling.md) — Sizing, endpoint management, scale-to-zero, HA
- [connectivity.md](references/connectivity.md) — Connection patterns, token refresh, Data API
- [synced-tables.md](references/synced-tables.md) — Lakebase synced tables, data type mapping, capacity planning
- [lakehouse-sync.md](references/lakehouse-sync.md) — CDC from Lakebase Postgres to Unity Catalog Delta tables (programmable via `databricks postgres *-cdf-config` / `w.postgres.*_cdf_config`, Beta)
- [pgvector.md](references/pgvector.md) — Vector similarity search with pgvector extension
- [off-platform.md](references/off-platform.md) — Off-platform Lakebase (NOT Databricks Apps): external Node.js apps connecting via `@databricks/lakebase`, env management, token refresh, Drizzle ORM

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
- **Endpoint** (called **Compute** in UI): Compute resource powering a branch. Types: `ENDPOINT_TYPE_READ_WRITE`, `ENDPOINT_TYPE_READ_ONLY`.
- **Database**: Standard Postgres database within a branch. Default: `databricks_postgres`.
- **Role**: Postgres role within a branch.

### Resource Name Formats

| Resource | Format |
|----------|--------|
| Project | `projects/{project_id}` |
| Branch | `projects/{project_id}/branches/{branch_id}` |
| Endpoint | `projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}` |
| Database | `projects/{project_id}/branches/{branch_id}/databases/{database_id}` |

All IDs: 1-63 characters, start with lowercase letter, lowercase letters/numbers/hyphens only (RFC 1123).

## CLI Discovery -- ALWAYS Do This First

> **Note:** "Lakebase" is the product name; the CLI command group is `postgres`. All commands use `databricks postgres ...`.

**Do NOT guess command syntax.** Discover available commands dynamically:

```bash
databricks postgres -h                    # List all subcommands
databricks postgres <subcommand> -h       # Flags, args, JSON fields
```

## Create a Project

> **First decide: reuse or create.** When building or attaching to an app, ask the user whether to reuse an existing project/branch/database — list them with `databricks postgres list-projects` (then `list-branches` / `list-databases`), let the user pick, and confirm which schema the app will own — or create a new project. Only skip listing and create directly when the user explicitly asked for a brand-new project.

```bash
databricks postgres create-project <PROJECT_ID> \
  --json '{"spec": {"display_name": "<DISPLAY_NAME>"}}' \
  --profile <PROFILE>
```

Auto-creates: `production` branch + `primary` read-write endpoint with scale-to-zero on (24 h timeout). The documented default size is 8–16 CU (autoscaling), but a project created with the CLI can get a 1 CU min/max endpoint instead. Check the size with `get-endpoint` and resize with `update-endpoint` if the workload needs more. Long-running operation; CLI waits by default. Use `--no-wait` to return immediately.

After creation, verify:

```bash
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>
databricks postgres list-endpoints projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
databricks postgres list-databases projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>
```

**Extract connection values from JSON output:**

| Value | JSON path | Used for |
|-------|-----------|----------|
| Endpoint host | `status.hosts.host` | `PGHOST`, `lakebase.postgres.host` |
| Endpoint resource path | `name` | `LAKEBASE_ENDPOINT`, `lakebase.postgres.endpointPath` |
| Database resource path | `name` | `lakebase.postgres.database` |
| PostgreSQL database name | `status.postgres_database` | `PGDATABASE`, `lakebase.postgres.databaseName` |

### Updating a Project

```bash
databricks postgres update-project projects/<PROJECT_ID> spec.display_name \
  --json '{"spec": {"display_name": "My Updated Application"}}' \
  --profile <PROFILE>
```

### Deleting a Project

**WARNING:** Permanent -- deletes all branches, computes, databases, roles, and data. **Do not delete without explicit user permission.**

```bash
databricks postgres delete-project projects/<PROJECT_ID> --profile <PROFILE>
```

## Autoscaling

Endpoints use **compute units (CU)** (~2 GB RAM per CU). Range: 0.5--64 CU (autoscaling or fixed), 65--112 CU (fixed only). Scale-to-zero enabled by default on every branch, including `production` (24 h timeout; computes ≤ 32 CU only).

See [computes-and-scaling.md](references/computes-and-scaling.md) for sizing tables, endpoint CRUD, and configuration details.

## Branches

Branches are copy-on-write snapshots. Use for testing schema migrations, trying queries, or previewing data changes without affecting production.

```bash
databricks postgres create-branch projects/<PROJECT_ID> <BRANCH_ID> \
  --json '{"spec": {"source_branch": "projects/<PROJECT_ID>/branches/<SOURCE>", "no_expiry": true}}' \
  --profile <PROFILE>
```

Branches require an expiration policy: `"no_expiry": true` for permanent, or `"ttl": "<seconds>s"` (max 30 days).

**Limits:** 500 branches per project. Per-branch storage quota is adjustable on request (contact Databricks Support). 500 Postgres roles per branch. 1,000 projects per workspace. For apps with many end users, do not create one role per user; see "Many Users: Roles and RLS at Scale" in [connectivity.md](references/connectivity.md).

| Use Case | TTL |
|----------|-----|
| CI/CD environments | 2--4 hours (`"ttl": "14400s"`) |
| Demos | 24--48 hours (`"ttl": "172800s"`) |
| Feature development | 1--7 days (`"ttl": "604800s"`) |
| Long-term testing | Up to 30 days (`"ttl": "2592000s"`) |

**Point-in-time branching:** Create from a past state (within restore window) for recovery. The time specification fields live inside the `--json` spec (`spec.source_branch_time`, `spec.source_branch_lsn`), not as top-level `create-branch` flags.

**Reset:** Replaces branch data and schema with the latest from its parent. Local changes are lost. Root branches and branches with children cannot be reset; protected branches (`spec.is_protected`) cannot be reset either.

**Reset is UI-only — there is no `databricks postgres reset-branch` CLI command and no API/SDK method for it.** In the Lakebase App, go to the project's **Branches** page, click the menu next to the branch, and select **Reset from parent**.

CLI workarounds:
- **Delete + recreate:** `delete-branch`, then `create-branch` with `spec.source_branch` set to the parent (unprotect via `update-branch` first if protected).
- **Point-in-time:** `create-branch` with `spec.source_branch_time` or `spec.source_branch_lsn`. Timestamp-based *reset* is not supported; use PITR branching instead.

**Delete:** Protected branches must be unprotected first (`update-branch` to set `spec.is_protected` to `false`). Cannot delete branches with children. **Never delete the `production` branch.**

## What's Next

### Build a Databricks App

After creating a project, scaffold a connected Databricks App:

```bash
# 1. Get branch name
databricks postgres list-branches projects/<PROJECT_ID> --profile <PROFILE>

# 2. Get database name
databricks postgres list-databases projects/<PROJECT_ID>/branches/<BRANCH_ID> --profile <PROFILE>

# 3. Scaffold with lakebase feature
databricks apps init --name <APP_NAME> --features lakebase \
  --set "lakebase.postgres.branch=<BRANCH_NAME>" \
  --set "lakebase.postgres.database=<DATABASE_NAME>" \
  --run none --profile <PROFILE>
```

For the full app workflow, use the **`databricks-apps`** skill.

### Attach Lakebase to an existing app

`apps init --features lakebase` (above) wires the database at scaffold time. To
attach a project to an **existing** app, update its resources.

**Use the `postgres` resource key** — its fields are `branch` + `database`
(full resource paths from the table above). The legacy `database` key
(`instance_name` + `database_name`) is deprecated; using it fails with
`Database instance <name> does not exist`. Get the exact paths from
`list-branches` / `list-databases` (the DB name is often hyphenated, e.g.
`databricks-postgres`).

Update the app's resources with **`databricks apps create-update`** — the method to use for any app (the older `databricks apps update` is legacy and can't change resources for an app in a space). `update_mask=resources` replaces the whole `resources` array, so read the app's current resources and **merge** the new one in (or you'll detach the rest). Pass everything in `--json`; only `APP_NAME` is positional:

```bash
databricks apps create-update <APP_NAME> --json @update.json --profile <PROFILE>   # waits for completion; --no-wait to return early
```

```json
{
  "update_mask": "resources",
  "app": {
    "resources": [
      {
        "name": "postgres",
        "postgres": {
          "branch": "projects/<PROJECT_ID>/branches/<BRANCH_ID>",
          "database": "projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DATABASE_ID>",
          "permission": "CAN_CONNECT_AND_CREATE"
        }
      }
    ]
  }
}
```

**Confirm the branch/database with the user — don't default to `production` silently.** The app's service principal must be able to create and **own** the schema(s) it uses there, so avoid a branch/database where those schema names are already owned by a user (the SP will hit `permission denied … 42501`) — a fresh/dedicated branch, or a new app-owned schema, is cleanest. See **Schema Permissions for Deployed Apps** below for the full ownership model.

### Schema Permissions for Deployed Apps

The app's Service Principal has `CAN_CONNECT_AND_CREATE` -- it can create new objects but **cannot access existing schemas**. The SP must create the schema to become its owner.

**ALWAYS deploy the app before running it locally.** This is the #1 source of Lakebase permission errors.

**Correct workflow:**
1. **Deploy first**: `databricks apps deploy <APP_NAME> --profile <PROFILE>`
2. **Grant local access** *(if needed)*: give your own identity a role with access to the app's schema only (SQL below). Do **not** assign `databricks_superuser` for this. Project creators already have access.
3. **Develop locally**: your role can use only the schema and tables you granted

```sql
-- Run as the project owner. If a GRANT fails with "permission denied", run the GRANTs as the schema owner (the app's SP).
CREATE EXTENSION IF NOT EXISTS databricks_auth;
SELECT databricks_create_role('<YOUR_EMAIL>', 'USER');
GRANT USAGE ON SCHEMA <APP_SCHEMA> TO "<YOUR_EMAIL>";
GRANT SELECT, INSERT, UPDATE, DELETE ON <APP_SCHEMA>.<TABLE> TO "<YOUR_EMAIL>";   -- one line per table the app uses
GRANT USAGE ON SEQUENCE <SEQUENCE> TO "<YOUR_EMAIL>";   -- per SERIAL/identity column you insert into; name: SELECT pg_get_serial_sequence('<APP_SCHEMA>.<TABLE>', '<COLUMN>')
```

- This role cannot create or change schemas or tables. The app's startup DDL fails with `permission denied`, even `CREATE SCHEMA IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` on objects that already exist. The deployed app's SP creates and migrates the schema. Locally, skip the DDL when your role lacks `CREATE` on the schema (`has_schema_privilege('<APP_SCHEMA>', 'CREATE')`).
- A table added later needs its own GRANT.

> **The project owner and `databricks_superuser` bypass RLS**, even with `FORCE ROW LEVEL SECURITY` (both have `BYPASSRLS`). A query as either one returns every row, so it cannot show that a policy works. Test isolation as a role without `BYPASSRLS`: `GRANT <ROLE> TO CURRENT_USER WITH SET TRUE;`, then `SET ROLE <ROLE>;`, then run the app's queries.

**If you already ran locally first** and hit `permission denied`: the schema is owned by your credentials, not the SP. **Do NOT drop the schema without asking the user** -- dropping it deletes all data.

Ask the user to choose:
- **(A) Drop and redeploy:** `databricks psql --project <PROJECT_ID> -- -c "DROP SCHEMA IF EXISTS <SCHEMA_NAME> CASCADE;"`, then `databricks apps deploy` from the app directory. The SP recreates the schema on startup.
- **(B) Export first, then drop and redeploy:** export via `pg_dump` (use connection details from `databricks postgres get-endpoint`; see **Other Workflows** below for HOST and TOKEN) or copy tables to a temp schema using `databricks psql --project <PROJECT_ID>`, then do option A. After the SP recreates the schema on redeploy, restore with `pg_restore` or re-INSERT from the temp schema.

### Other Workflows

```bash
# Connect a Postgres client -- get connection string
databricks postgres get-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>

# Manage roles
databricks postgres create-role -h

# Add a read replica
databricks postgres create-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID> <ENDPOINT_ID> \
  --json '{"spec": {"type": "ENDPOINT_TYPE_READ_ONLY"}}' --profile <PROFILE>
```

**Run SQL against Lakebase** (GRANT, CREATE INDEX, etc.):
```bash
# 1. Get endpoint host
databricks postgres get-endpoint projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> --profile <PROFILE>

# 2. Generate OAuth token
databricks postgres generate-database-credential \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID> \
  --profile <PROFILE>

# 3. Connect (use token from step 2 as password, host from step 1)
PGPASSWORD='<TOKEN>' psql "host=<HOST> user=<USERNAME> dbname=databricks_postgres sslmode=require"
```

> **Note:** `generate-database-credential` requires the **endpoint** resource path (`.../endpoints/<ENDPOINT_ID>`), not a database or branch path.

**Scriptable version** (single copy-paste, useful for agents):
```bash
EP=projects/<PROJECT_ID>/branches/<BRANCH_ID>/endpoints/<ENDPOINT_ID>
# get-endpoint JSON shape: {"status": {"hosts": {"host": "<HOSTNAME>"}, ...}, ...}
HOST=$(databricks postgres get-endpoint $EP --profile <PROFILE> -o json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['hosts']['host'])")
TOKEN=$(databricks postgres generate-database-credential $EP --profile <PROFILE> -o json \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
PGPASSWORD="$TOKEN" psql "host=$HOST user=<USERNAME> dbname=databricks_postgres sslmode=require"
```

**Grant app SP access to synced tables** (run after sync is ONLINE and the app is deployed, as the identity that created the synced table: it holds `SELECT ... WITH GRANT OPTION`, while `databricks_writer_<n>` owns the table):
```sql
-- <SCHEMA>.<SYNCED_TABLE>: the last two parts of the synced table ID <UC_CATALOG>.<SCHEMA>.<TABLE>
GRANT USAGE ON SCHEMA <SCHEMA> TO "<SP_CLIENT_ID>";
GRANT SELECT ON <SCHEMA>.<SYNCED_TABLE> TO "<SP_CLIENT_ID>";   -- one line per synced table; never ALL TABLES IN SCHEMA public (it also covers Lakebase internal objects)
```
Run the `GRANT SELECT` again after each new synced table reaches ONLINE. `ALTER DEFAULT PRIVILEGES` does not help here: it covers only tables that its own role creates later, and synced tables are owned by `databricks_writer_<dbid>`.
For least-privilege, consider syncing into a dedicated schema instead of `public` so the grant is scoped to synced data only.

Get SP client ID: `databricks apps get <APP_NAME> --profile <PROFILE>` → `service_principal_client_id` field.

**Data API:** PostgREST-compatible HTTP CRUD on Postgres tables. See [connectivity.md](references/connectivity.md).
**Synced Tables:** Sync Delta tables into Lakebase. See [synced-tables.md](references/synced-tables.md).

## PostgreSQL Extensions

Lakebase supports PostgreSQL extensions (e.g., `pgvector` for vector embeddings, `pg_stat_statements` for query statistics). See the [full list of supported extensions](https://docs.databricks.com/aws/en/oltp/projects/extensions).

```sql
-- List available extensions
SELECT * FROM pg_available_extensions ORDER BY name;

-- Install an extension
CREATE EXTENSION IF NOT EXISTS <extension_name>;
```

For vector embeddings with pgvector, see [pgvector.md](references/pgvector.md).

## Troubleshooting

| Error | Solution |
|-------|----------|
| `cannot configure default credentials` | Use `--profile` flag or authenticate first |
| `PERMISSION_DENIED` | Check workspace permissions |
| `permission denied for schema` | Schema owned by another role. If app not yet deployed: deploy first so the SP creates and owns the schema. If deployed but hitting this error (dev ran locally first): warn user about data loss, offer to export first (`pg_dump` with connection details from `databricks postgres get-endpoint`, or temp schema copy via `databricks psql`), then `DROP SCHEMA IF EXISTS <SCHEMA_NAME> CASCADE` + redeploy. |
| Protected branch won't delete | `update-branch` to set `spec.is_protected` to `false` first |
| Long-running operation timeout | Use `--no-wait` and poll with `get-operation` |
| New connections fail ~1 h after app start | OAuth token was fetched once at startup. Expiry is checked only at login, so open connections keep working; refresh the token before it expires and pass the current one to each new connection (see [token refresh](references/connectivity.md#pattern-2-connection-pool-with-token-refresh-production)) |
| Connection refused after scale-to-zero | Compute is waking up; retry with a short backoff (see [scale-to-zero](references/computes-and-scaling.md#scale-to-zero)) |
| Branch deletion blocked | Delete child branches first |
| Autoscaling range too wide | Max - Min cannot exceed 16 CU |
| SSL required error | Always use `sslmode=require` |
| Update mask required | All `update-*` operations require specifying fields (see `-h`) |
| Connection closed by server | Connections idle for 24 h are closed, and connections alive for more than 3 days may be closed regardless of activity. Use pool health checks and a max lifetime; implement retry. |
| DNS resolution fails (macOS) | Python `socket.getaddrinfo()` fails with long hostnames. Use `dig` to resolve IP, pass via `hostaddr` param alongside `host` (for TLS SNI). See [connectivity.md](references/connectivity.md). |
| `storage_catalog` pipeline failure | `new_pipeline_spec.storage_catalog` must be a regular UC catalog, not the Lakebase catalog. DLT cannot write event logs to Postgres-backed schemas. |
| Synced table CDF error | Triggered/Continuous need a change data feed. Enable CDF on the source (`ALTER TABLE ... SET TBLPROPERTIES (delta.enableChangeDataFeed = true)`), use a source that [Automatic change data feed](https://docs.databricks.com/tables/features/change-data-feed) supports, or use Snapshot mode. |
| Sync permissions error | Ensure `USE CATALOG`/`USE SCHEMA` on source table and `CREATE TABLE` in storage catalog |
| Synced table null bytes | Null bytes (0x00) in STRING/ARRAY/MAP/STRUCT columns cause sync failures. Sanitize source data: `REPLACE(col, CAST(CHAR(0) AS STRING), '')` |
| Synced table data modified | Only read queries, indexes, and DROP TABLE allowed on synced tables in Postgres. Modifications break sync pipeline. |
| DABs `synced_database_tables` | Deprecated — maps to a legacy API and fails on current Lakebase. Use the `postgres_synced_tables` bundle resource (Beta, CLI v1.0.0+) or the `databricks postgres create-synced-table` CLI instead. |

## SDK and Version Requirements

| Component | Minimum Version |
|-----------|----------------|
| Databricks CLI | >= v0.294.0 |
| Databricks SDK for Python | >= 0.81.0 (for `w.postgres` module) |
| psycopg | 2.x or 3.x (3.x recommended for async/pooling) |
| Postgres | 16, 17, or 18 (default: PG 17) |
