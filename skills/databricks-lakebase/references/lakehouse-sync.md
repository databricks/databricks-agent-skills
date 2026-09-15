# Lakehouse Sync: CDC from Lakebase to Unity Catalog

Lakehouse Sync continuously streams changes **from** Lakebase Postgres **into** Unity Catalog Delta tables using Change Data Capture (CDC). Each synced table produces an SCD Type 2 history table in Unity Catalog, giving you a full audit trail queryable from the lakehouse.

This is the reverse direction from synced tables (which go UC → Lakebase). No external compute, pipelines, or jobs are required — it is a native Lakebase feature.

## When to Use

- Analyze operational data (orders, user activity, support tickets) in the lakehouse
- Need a historical record of every insert, update, and delete from Postgres tables
- Join operational data with analytics data in Spark, SQL, or BI tools
- Feed Lakebase data into downstream pipelines or ML models

## History Tables

For each synced table, a Delta history table is created in Unity Catalog:

```
lb_<table_name>_history
```

Each row includes CDC metadata columns:

| Column | Type | Description |
|--------|------|-------------|
| `_pg_change_type` | TEXT | `insert`, `update_preimage`, `update_postimage`, or `delete` |
| `_pg_lsn` | BIGINT | Postgres Log Sequence Number for ordering changes |
| `_pg_xid` | INTEGER | Postgres Transaction ID |
| `_timestamp` | TIMESTAMP | When the sync processed the change (without timezone) |
| `_sort_by` | BIGINT | Monotonic sort key for ordering all changes |

## Enablement

Lakehouse Sync is programmable via the CLI and SDK (**Beta** — `databricks postgres *-cdf-config` / `w.postgres.*_cdf_config`, CLI >= v1.9 / databricks-sdk >= ~0.135). Creating a **CDF config** is what turns the sync on: it captures the change data feed for a Postgres schema and materializes each table as an `lb_<table>_history` Delta table in Unity Catalog with the CDC columns shown [above](#history-tables). It works at the **schema level** — one config covers all current and future tables in that schema. (The workspace UI — branch overview → "Lakehouse sync" tab → **Start Sync** — does the same thing.)

**CLI** — `PARENT` is the database **resource path**, not the Postgres database name (see the gotcha below):

```bash
# Create a CDF config: replicate Postgres schema `public` into UC catalog.schema.
# Args are positional: PARENT CATALOG SCHEMA POSTGRES_SCHEMA. Long-running; waits by default.
databricks postgres create-cdf-config \
  projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DATABASE_ID> \
  <UC_CATALOG> <UC_SCHEMA> public \
  --cdf-config-id <id> --profile <PROFILE>

# Check / manage
databricks postgres list-cdf-configs   projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DATABASE_ID> --profile <PROFILE>
databricks postgres list-cdf-statuses  projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DATABASE_ID> --profile <PROFILE>
databricks postgres get-cdf-status     <CDF_CONFIG_RESOURCE_NAME> --profile <PROFILE>
databricks postgres delete-cdf-config  <CDF_CONFIG_RESOURCE_NAME> --profile <PROFILE>
```

**SDK** — the config lives in `databricks.sdk.service.postgres` (not Unity Catalog):

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import CdfConfig

w = WorkspaceClient(profile="<PROFILE>")
db = "projects/<PROJECT_ID>/branches/<BRANCH_ID>/databases/<DATABASE_ID>"   # resource path

w.postgres.create_cdf_config(
    parent=db,
    cdf_config=CdfConfig(catalog="<UC_CATALOG>", schema="<UC_SCHEMA>", postgres_schema="public"),
    cdf_config_id="<id>")

# poll until tables are ONLINE
w.postgres.list_cdf_statuses(parent=db)
# also: get_cdf_config / get_cdf_status / list_cdf_configs / delete_cdf_config
```

Once `ONLINE`, the CDC history tables exist in UC — one `lb_<table>_history` per source table, carrying the CDC columns documented above:

```sql
SELECT _pg_change_type, _pg_lsn, _timestamp, *
FROM <UC_CATALOG>.<UC_SCHEMA>.lb_<table>_history
ORDER BY _sort_by DESC;
```

**Gotchas:**

- **`parent`/`PARENT` is the database RESOURCE path** (`projects/<p>/branches/<b>/databases/<DATABASE_ID>`), **not** the Postgres database name you connect with (`databricks_postgres`). The resource id (e.g. `db-...`) differs from the connect name — resolve it with `databricks postgres list-databases projects/<p>/branches/<b>` and match on `status.postgres_database`. Passing the connect name yields a misleading `NotFound: database not found`.
- **The destination UC catalog + schema must already exist** — the API does not create them, and a missing one fails with `Schema '<cat>.<schema>' does not exist`.
- **`list-cdf-configs` / `list-cdf-statuses` return `NotFound` (404) when none exist**, not an empty list — in the SDK, catch `databricks.sdk.errors.platform.NotFound`.

## Prerequisites

- Lakebase Autoscaling project running **Postgres 17**
- Tables must reside in the `databricks_postgres` database
- `REPLICA IDENTITY FULL` must be set on all source tables:

```sql
ALTER TABLE <table_name> REPLICA IDENTITY FULL;
```

- Verify replica identity:

```sql
SELECT n.nspname AS table_schema,
       c.relname AS table_name,
       CASE c.relreplident
         WHEN 'd' THEN 'default'
         WHEN 'n' THEN 'nothing'
         WHEN 'f' THEN 'full'
         WHEN 'i' THEN 'index'
       END AS replica_identity
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = 'public'
ORDER BY n.nspname, c.relname;
```

- **Permissions:** CAN MANAGE on source project; USE CATALOG + USE SCHEMA + CREATE TABLE on destination
- Catalogs with default storage are **unsupported**

## Supported Data Types

`bool`, `int2`, `int4`, `int8`, `text`, `varchar`, `bpchar`, `jsonb`, `numeric`, `date`, `timestamp`, `timestamptz`, `real`, `float4`, `float8`, plus enum types (`typcategory = 'E'`).

Check for unsupported types:

```sql
SELECT c.table_schema, c.table_name, c.column_name, c.udt_name AS data_type
FROM information_schema.columns c
JOIN pg_catalog.pg_type t ON t.typname = c.udt_name
WHERE c.table_schema = 'public'
  AND NOT (
    c.udt_name IN (
      'bool', 'int2', 'int4', 'int8', 'text', 'varchar', 'bpchar',
      'jsonb', 'numeric', 'date', 'timestamp', 'timestamptz',
      'real', 'float4', 'float8'
    )
    OR t.typcategory = 'E'
  )
ORDER BY c.table_schema, c.table_name, c.ordinal_position;
```

## Monitoring

Check active syncs from Postgres (the `wal2delta` schema only exists after Lakehouse Sync has been enabled):

```sql
SELECT * FROM wal2delta.tables;
```

## Querying History Tables

**Latest state of each row** (deduplicated current state):

```sql
SELECT *
FROM (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY <primary_key> ORDER BY _pg_lsn DESC) AS rn
  FROM <catalog>.<schema>.lb_<table_name>_history
  WHERE _pg_change_type IN ('insert', 'update_postimage', 'delete')
)
WHERE rn = 1
  AND _pg_change_type != 'delete';
```

**Full change history for a record:**

```sql
SELECT *
FROM <catalog>.<schema>.lb_<table_name>_history
WHERE <primary_key> = <value>
ORDER BY _pg_lsn;
```

## Schema Changes

If you need to change a synced table's schema in Postgres, you can use the rename-and-swap pattern. Note: this is community guidance — the official behavior is that column changes (add, drop, type change) trigger a full resnapshot of the affected table.

```sql
CREATE TABLE <table>_v2 (
  id INT PRIMARY KEY,
  name TEXT,
  new_column TEXT
);

ALTER TABLE <table>_v2 REPLICA IDENTITY FULL;

INSERT INTO <table>_v2 SELECT *, NULL FROM <table>;

BEGIN;
ALTER TABLE <table> RENAME TO <table>_backup;
ALTER TABLE <table>_v2 RENAME TO <table>;
COMMIT;
```

## Limitations

- Partitioned tables are not supported
- Disabling and re-enabling sync does **not** re-snapshot — missing changes are lost permanently
- Available on AWS, Azure, and GCP.

## Cross-references

- For building Silver/Gold layers from CDC history tables, see [medallion-from-cdc.md](medallion-from-cdc.md)
- For syncing in the reverse direction (UC → Lakebase), see [synced-tables.md](synced-tables.md)
