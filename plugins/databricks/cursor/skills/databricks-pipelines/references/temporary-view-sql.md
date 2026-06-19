# Temporary Views (SQL)

Pipeline-scoped logical datasets — not materialized, not published to UC. Used for shared intermediate transformations that drive multiple downstream tables.

```sql
CREATE TEMPORARY VIEW view_name
  [ (col_name [COMMENT 'col_comment'], ...) ]
  [ COMMENT 'view_comment' ]
  [ TBLPROPERTIES (key = 'value', ...) ]
AS query           -- batch or streaming
```

## Example

```sql
-- Shared filtering logic, consumed by multiple downstream MVs
CREATE TEMPORARY VIEW valid_events
AS SELECT * FROM raw.events
WHERE event_type IS NOT NULL AND timestamp IS NOT NULL;

CREATE OR REFRESH MATERIALIZED VIEW user_events
AS SELECT * FROM valid_events WHERE event_type = 'user_action';
-- Other downstream MVs follow the same shape.
```

Streaming source: `CREATE TEMPORARY VIEW ... AS SELECT ... FROM STREAM(bronze.events) WHERE ...` — downstream STs read via `FROM STREAM(view_name)`.

## Using Expectations with Temporary Views

`CREATE TEMPORARY VIEW` does NOT support `CONSTRAINT` clauses. For the rare case where you need expectations on a temp view, use `CREATE LIVE VIEW` (older syntax, retained for this purpose):

```sql
CREATE LIVE VIEW view_name (
  CONSTRAINT constraint_name EXPECT (condition) [ON VIOLATION DROP ROW | FAIL UPDATE]
) AS query
```

See [expectations-sql.md](expectations-sql.md) for the full constraint semantics. Otherwise, prefer attaching the constraint to a downstream streaming table or MV.

## Key rules

- Computed on demand — not materialized.
- Pipeline-scoped — not published to UC, gone after pipeline run.
- Reference downstream as `FROM view_name` (batch) or `FROM STREAM(view_name)` (streaming).
- Temp view name shadows a same-named catalog object inside the pipeline.
- For UC-published views, use `CREATE VIEW` ([view-sql.md](view-sql.md)).
