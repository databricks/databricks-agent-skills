---
name: databricks-lakebase
description: "Manage Lakebase Postgres Autoscaling projects, branches, and endpoints via Databricks CLI. Use when asked to create, configure, or manage Lakebase Postgres databases, projects, branches, computes, or endpoints."
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "0.1.0"
parent: databricks
---

# Lakebase Postgres Autoscaling

**FIRST**: Use the parent `databricks` skill for CLI basics, authentication, and profile selection.

Lakebase is Databricks' serverless Postgres-compatible database (similar to Neon). It provides fully managed OLTP storage with autoscaling, branching, and scale-to-zero.

Manage Lakebase Postgres projects, branches, endpoints, and databases via `databricks postgres` CLI commands.

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

## CLI Command Reference

> **Note:** "Lakebase" is the product name; the CLI command group is `postgres`. All commands use `databricks postgres ...`.

| Command | Description |
|---------|-------------|
| `create-project` | Create a new project (auto-provisions `production` branch + `primary` endpoint) |
| `get-project` | Get project details |
| `list-projects` | List all projects in the workspace |
| `delete-project` | Delete a project |
| `create-branch` | Create a copy-on-write branch from an existing branch |
| `list-branches` | List branches in a project |
| `get-branch` | Get branch details |
| `update-branch` | Update branch settings (e.g. `is_protected`) |
| `delete-branch` | Delete a branch |
| `create-endpoint` | Create an endpoint (compute) on a branch |
| `list-endpoints` | List endpoints on a branch |
| `get-endpoint` | Get endpoint details (includes connection info) |
| `update-endpoint` | Update endpoint settings (e.g. min/max CU) |
| `delete-endpoint` | Delete an endpoint |
| `list-databases` | List databases in a branch |
| `create-role` | Create a Postgres role |

For detailed flags and JSON spec fields for any command, run `databricks postgres <subcommand> -h`.

## Create a Project

> **Do NOT list projects before creating.** When building a new app, create a new Lakebase project directly.
> Do NOT run `databricks postgres list-projects` first — it returns all projects in the workspace and is
> not needed for new app creation.

```bash
databricks postgres create-project <PROJECT_ID> \
  --json '{"spec": {"display_name": "<DISPLAY_NAME>"}}' \
  --profile <PROFILE>
```

- Auto-creates: `production` branch + `primary` read-write endpoint (1 CU min/max, scale-to-zero)
- Long-running operation; the CLI waits for completion by default. Use `--no-wait` to return immediately.
- Run `databricks postgres create-project -h` for all available spec fields (e.g. `pg_version`).

After creation, every project has:
- **Branch**: always `production` → full name: `projects/<PROJECT_ID>/branches/production`
- **Database**: auto-generated name → **MUST** run `list-databases` to discover:
  ```bash
  databricks postgres list-databases projects/<PROJECT_ID>/branches/production --profile <PROFILE>
  ```
- **Endpoint**: always `primary` → full name: `projects/<PROJECT_ID>/branches/production/endpoints/primary`

Skip `list-branches` and `list-endpoints` — the defaults are always `production` and `primary`.

## Autoscaling

Endpoints use **compute units (CU)** for autoscaling. Configure min/max CU via `create-endpoint` or `update-endpoint`. Run `databricks postgres create-endpoint -h` to see all spec fields.

Scale-to-zero is enabled by default. When idle, compute scales down to zero; it resumes in seconds on next connection.

## Branches

Branches are copy-on-write snapshots of an existing branch. Use them for **experimentation**: testing schema migrations, trying queries, or previewing data changes -- without affecting production.

```bash
databricks postgres create-branch projects/<PROJECT_ID> <BRANCH_ID> \
  --json '{
    "spec": {
      "source_branch": "projects/<PROJECT_ID>/branches/<SOURCE_BRANCH_ID>",
      "no_expiry": true
    }
  }' --profile <PROFILE>
```

Branches require an expiration policy: use `"no_expiry": true` for permanent branches.

When done experimenting, delete the branch. Protected branches must be unprotected first -- use `update-branch` to set `spec.is_protected` to `false`, then delete:

```bash
# Step 1 — unprotect
databricks postgres update-branch projects/<PROJECT_ID>/branches/<BRANCH_ID> \
  --json '{"spec": {"is_protected": false}}' --profile <PROFILE>

# Step 2 — delete (run -h to confirm positional arg format for your CLI version)
databricks postgres delete-branch projects/<PROJECT_ID>/branches/<BRANCH_ID> \
  --profile <PROFILE>
```

**Never delete the `production` branch** — it is the authoritative branch auto-provisioned at project creation.

## What's Next

### Build a Databricks App

After creating a Lakebase project, scaffold a Databricks App connected to it.

**Step 1 — Use the known branch name.** The branch is always `production`:
```
projects/<PROJECT_ID>/branches/production
```

**Step 2 — Discover database name** (auto-generated, must query):

```bash
databricks postgres list-databases projects/<PROJECT_ID>/branches/production --profile <PROFILE>
```

Use the `.name` field from the output (e.g. `projects/<PROJECT_ID>/branches/production/databases/<DB_ID>`).

**Step 3 — Scaffold the app** with the `lakebase` feature (include `--version` for the AppKit version):

```bash
databricks apps init --name <APP_NAME> --version <APPKIT_VERSION> \
  --features lakebase \
  --set "lakebase.postgres.branch=projects/<PROJECT_ID>/branches/production" \
  --set "lakebase.postgres.database=<DATABASE_NAME>" \
  --run none --profile <PROFILE>
```

Where `<DATABASE_NAME>` is the full resource name from Step 2 and `<APPKIT_VERSION>` is the desired AppKit version (e.g. `0.20.0`). The `--version` flag is **required** when using plugins like `lakebase` that are only available in specific AppKit versions.

For the full app development workflow, use the **`databricks-apps`** skill.

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

## Troubleshooting

| Error | Solution |
|-------|----------|
| `cannot configure default credentials` | Use `--profile` flag or authenticate first |
| `PERMISSION_DENIED` | Check workspace permissions |
| Protected branch cannot be deleted | `update-branch` to set `spec.is_protected` to `false` first |
| Long-running operation timeout | Use `--no-wait` and poll with `get-operation` |
