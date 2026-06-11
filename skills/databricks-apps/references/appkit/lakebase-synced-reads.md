# Lakebase Synced Reads (Read-only)

**Capability:** `reads_synced` — low-latency reads of Unity Catalog / Delta data materialized into Lakebase Postgres.

**Not OLTP CRUD.** App-owned writes use [Lakebase OLTP](lakebase-oltp.md) (`writes_oltp`). Warehouse dashboards use [SQL Queries](sql-queries.md) (`reads_warehouse`).

**Pattern selection:** [Data Patterns](data-patterns.md). Create synced tables and grant SP access via the **`databricks-lakebase`** skill — [synced-tables.md](../../../databricks-lakebase/references/synced-tables.md).

> **Agentic mode:** the synced tables, SP grants, and `PG*` env vars already exist / are injected. **Skip** *Scaffolding* and all `databricks-lakebase` handoffs — do not create synced tables or grant access. Just write the read-only routes. See [Environments](environments.md).

## Architecture

```
Delta gold tables  →  Synced tables (read-only)  →  App reads via appkit.lakebase.query()
App writes         →  Lakebase OLTP tables        →  optional Lakehouse Sync → Delta
```

Use synced reads when data is curated in Delta, changes relatively slowly, and must be served at OLTP latency — lookups, catalogs, operational consoles on gold tables.

> **Security:** Synced tables do not propagate Unity Catalog fine-grained access control (row/column masks). If UC FGAC is critical, use warehouse SQL with user authorization instead.

## Scaffolding

Same plugin and `--set` flags as OLTP — `--features lakebase` + three `lakebase.postgres.{project,branch,database}` values from manifest. **No deploy-first for schema init** — synced tables already exist after the sync pipeline runs.

Hybrid apps often combine `reads_synced` + `writes_oltp` + `reads_warehouse` — use separate tables/routes for each; never write to synced tables.

## How it works

Synced tables (via `databricks postgres create-synced-table`) appear as regular Postgres tables. Use `appkit.lakebase.query()` in Express routes — **read-only**.

| | OLTP CRUD tables | Synced tables |
|--|------------------|---------------|
| Created by | App SP (`CREATE TABLE`) | Sync pipeline |
| Owned by | SP role | System role (`databricks_writer_*`) |
| Operations | Read + Write | **Read-only** |
| Schema init | App in `onPluginsReady` | Exists after sync |
| Deploy-first | **Yes** (SP must own schema) | No |

**Permission grant:** App SP has `CAN_CONNECT_AND_CREATE` but not `pg_read_all_data`. Project owner must grant SELECT on synced tables — see **`databricks-lakebase`** skill (Grant app SP access to synced tables).

## Example route

```typescript
// Inside onPluginsReady → appkit.server.extend((app) => { ... })
app.get("/api/top-pickups", async (_req, res) => {
  const { rows } = await appkit.lakebase.query(`
    SELECT pickup_zip, COUNT(*) AS trip_count, AVG(fare_amount) AS avg_fare
    FROM public.nyc_trips
    GROUP BY pickup_zip
    ORDER BY trip_count DESC
    LIMIT 10
  `);
  res.json(rows);
});
```

## Rules

- **Never write to synced tables** — corrupts sync state.
- **Never** put synced-table SELECT in `config/queries/` — those files are warehouse-only.
- **Never** `useAnalyticsQuery` for Lakebase data.
- Mixed patterns: read synced tables; write to separate app-owned OLTP tables — see [Lakebase OLTP](lakebase-oltp.md).
