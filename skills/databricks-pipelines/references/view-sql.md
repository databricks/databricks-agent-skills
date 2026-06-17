# Persistent Views (SQL, UC)

`CREATE VIEW` publishes a virtual table to Unity Catalog. Unlike `CREATE TEMPORARY VIEW` (pipeline-private), persistent views are accessible outside the pipeline and persist in the catalog. The query runs on access — no data is stored.

For pipeline-private views, use `CREATE TEMPORARY VIEW` ([temporary-view-sql.md](temporary-view-sql.md)). For materialized output, use `CREATE OR REFRESH MATERIALIZED VIEW` ([materialized-view-sql.md](materialized-view-sql.md)).

## Syntax

```sql
CREATE VIEW view_name
  [COMMENT 'view_comment']
  [TBLPROPERTIES (key = 'value', ...)]
AS query           -- must be batch (no STREAM)
```

## Example

```sql
CREATE VIEW valid_orders
COMMENT 'Orders with valid data for analysis'
TBLPROPERTIES ('quality' = 'silver', 'owner' = 'analytics-team')
AS SELECT *
FROM raw.orders
WHERE order_id IS NOT NULL
  AND customer_id IS NOT NULL
  AND order_date IS NOT NULL;
```

Downstream MVs can reference `valid_orders` directly.

## Key rules

- Not materialized — query runs on access.
- Published to UC; requires UC pipeline with default publishing mode.
- Batch only — no `STREAM(...)`.
- No `CONSTRAINT` clauses (no expectations).
- No explicit column-list-with-COMMENT syntax — comment at the view level only.
- Permissions: `SELECT` on source tables, `CREATE TABLE` on the target schema.
