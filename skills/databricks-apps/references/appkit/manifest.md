# App Manifest (`app.yaml`)

The `app.yaml` manifest declares the runtime command, environment variables, and **resource dependencies** for a Databricks App. Resources are configured at deploy time — never hardcode workspace-specific IDs.

## Supported Resource Types

| Type | Description | Auto-set env vars |
|------|-------------|-------------------|
| `sql_warehouse` | Databricks SQL Warehouse for analytics queries | Warehouse ID |
| `database` | Lakebase PostgreSQL instance | `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGSSLMODE`, `LAKEBASE_ENDPOINT` |
| `serving_endpoint` | Model serving endpoint | Endpoint name |
| `job` | Databricks Job | Job ID |
| `secret` | Databricks Secret | Secret value |
| `volume` | Unity Catalog Volume | Volume path |

## Example: Analytics app

```yaml
command: ["node", "dist/server/server.js"]
env:
  - name: NODE_ENV
    value: production
resources:
  - name: sql-warehouse
    sql_warehouse:
      id: auto
      permission: CAN_USE
```

## Example: Lakebase app

```yaml
command: ["node", "dist/server/server.js"]
env:
  - name: NODE_ENV
    value: production
resources:
  - name: database
    database:
      id: auto
      permission: CAN_MANAGE
```

When the `database` resource is declared, Databricks automatically sets all `PG*` and `LAKEBASE_ENDPOINT` env vars at runtime. **Do not** manually set these in the `env` section.

## Example: App with both warehouse and Lakebase

```yaml
command: ["node", "dist/server/server.js"]
env:
  - name: NODE_ENV
    value: production
resources:
  - name: sql-warehouse
    sql_warehouse:
      id: auto
      permission: CAN_USE
  - name: database
    database:
      id: auto
      permission: CAN_MANAGE
```

## Example: App with model serving endpoint

```yaml
command: ["node", "dist/server/server.js"]
env:
  - name: NODE_ENV
    value: production
resources:
  - name: serving-endpoint
    serving_endpoint:
      name: auto
      permission: CAN_QUERY
```

## Key Rules

- **Never hardcode workspace-specific resource IDs** in `app.yaml` — use `id: auto` or `name: auto` so admins configure actual instances at deploy time via the UI or `databricks apps deploy`
- **`id: auto` vs `name: auto`**: Most resources are referenced by numeric ID (`sql_warehouse`, `database`, `job`, `secret`, `volume`) — use `id: auto`. Serving endpoints are referenced by their string name — use `name: auto`. Using the wrong field type will cause a deployment error.
- **Resource keys** (the `name:` field under each resource entry) become the display label in the deployment UI where admins select the actual resource instance
- Resources are configured during deployment — the app code reads their values from auto-set env vars at runtime
- Run `databricks apps validate` to check manifest + code consistency before deploying

## Validation

```bash
databricks apps validate --profile <PROFILE>
```

This checks that:
- `app.yaml` syntax is valid
- Declared resources match what the app code expects
- Build output is present and complete

Always run validation before `databricks apps deploy`.
