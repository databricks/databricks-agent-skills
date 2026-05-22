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

**Lakehouse Sync is UI-only** — configured via the "Lakehouse sync" tab in the branch overview, not via CLI or API. It operates at the **schema level**: once enabled, all current and future tables in that schema sync to Unity Catalog.

Navigate to: **Catalog** → your Autoscaling project → branch → **Lakehouse Sync** → **Start Sync**, then select the source database/schema, destination catalog/schema, and tables.

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
