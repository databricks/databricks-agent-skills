# Namespace & objects (Unity Catalog)

## When to use this reference

Use this doc when you need to:

- Navigate the 3-level namespace (`catalog.schema.table`)
- Inventory catalogs/schemas/tables quickly
- Search metadata at scale via `information_schema`
- Decide between managed vs external tables, and understand view types

## Core model: 3-level namespace

- **Fully-qualified**: `catalog.schema.table`
- Most governance and discovery flows require the ability to traverse the namespace (often `USE CATALOG` + `USE SCHEMA`, and sometimes `BROWSE`).

## CLI discovery (fastest for inventory)

Always include `--profile <PROFILE>`.

```bash
# list catalogs
databricks catalogs list --profile <PROFILE>

# list schemas in a catalog (⚠️ positional arg)
databricks schemas list <CATALOG> --profile <PROFILE>

# list tables in a schema (⚠️ positional args)
databricks tables list <CATALOG> <SCHEMA> --profile <PROFILE>

# inspect a table
databricks tables get <CATALOG>.<SCHEMA>.<TABLE> --profile <PROFILE>
```

### CLI gotcha: positional args

Many UC commands use **positional** arguments (e.g. `schemas list <CATALOG>`). Do not invent flags like `--catalog-name` unless `--help` shows them.

## SQL discovery via `information_schema` (best for search)

Run on a SQL warehouse.

```sql
-- Find tables by name pattern
SELECT table_catalog, table_schema, table_name
FROM system.information_schema.tables
WHERE lower(table_name) LIKE '%customer%';

-- Find columns across the lakehouse (handy for “where is field X?”)
SELECT table_catalog, table_schema, table_name, column_name, data_type
FROM system.information_schema.columns
WHERE lower(column_name) LIKE '%email%';

-- Inspect columns for one table
SELECT column_name, data_type, is_nullable, comment
FROM system.information_schema.columns
WHERE table_catalog = '<CATALOG>'
  AND table_schema  = '<SCHEMA>'
  AND table_name    = '<TABLE>'
ORDER BY ordinal_position;
```

If `system.information_schema` is unavailable, fall back to per-catalog `information_schema` (availability varies by workspace and configuration).

## Managed vs external tables (decision guide)

- **Managed tables**: simplest ops; UC controls the storage lifecycle.
- **External tables**: data lives in customer-controlled cloud storage; common for shared paths, multi-tool interoperability, and explicit storage ownership.

Default to **managed** unless you have a specific requirement to own the underlying storage path and lifecycle.

## Views, materialized views, metric views (quick mental model)

- **Views**: computed at query time; no storage of results.
- **Materialized views**: persisted results to accelerate repeated workloads (refresh semantics vary).
- **Metric views**: newer abstraction; verify feature availability and semantics in the target workspace before relying on it.
