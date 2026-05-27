# Streaming Tables (SQL)

Streaming tables enable incremental processing of continuously arriving data. For materialized views (batch), see [materialized-view-sql.md](materialized-view-sql.md).

## Syntax

```sql
CREATE OR REFRESH [PRIVATE] STREAMING TABLE table_name
  [ ( col_name col_type [NOT NULL] [COMMENT '...'] [column_constraint | MASK clause]
      [, ...]
      [, CONSTRAINT name EXPECT (cond) [ON VIOLATION DROP ROW | FAIL UPDATE]]
      [, table_constraint] ) ]
  [ PARTITIONED BY (col, ...) | CLUSTER BY (col, ...) ]   -- prefer CLUSTER BY
  [ LOCATION path ]
  [ COMMENT 'view_comment' ]
  [ TBLPROPERTIES (key = value, ...) ]
  [ WITH ROW FILTER func_name ON (col, ...) ]
  [ AS query ]
```

Key clause notes:

- `PRIVATE` — pipeline-scoped, not published to the catalog. Use for internal staging.
- `CLUSTER BY (...)` — Liquid Clustering, mutually exclusive with `PARTITIONED BY`. Always prefer.
- `MASK catalog.schema.mask_fn USING COLUMNS (other_col)` — UC column masking (Public Preview).
- `WITH ROW FILTER func ON (col, ...)` — UC row filter (Public Preview). `func` must be a UC SQL UDF returning BOOLEAN; rows are dropped when it returns FALSE/NULL. Forces full refresh of downstream MVs. Cannot define the UDF inside the pipeline.
- `CONSTRAINT ... EXPECT (...)` — see [expectations-sql.md](expectations-sql.md).
- Table-level constraints (primary key, foreign key) are **informational only** — not enforced. Useful as query-optimizer hints and documentation.

## `STREAM(...)` source

Streaming queries require `FROM STREAM(table_name)` for table sources (function form, with parens) or `FROM STREAM read_files(...)` / `STREAM read_kafka(...)` for function sources (no extra parens). Batch reads (no `STREAM`) fail in a streaming table definition.

## Single source vs multi-source

**Single source — `CREATE OR REFRESH STREAMING TABLE ... AS SELECT ...`**: handles continuous processing automatically. No separate flow. Most common case.

```sql
CREATE OR REFRESH STREAMING TABLE events_stream
AS SELECT * FROM STREAM(source_catalog.schema.events);
```

**Multi-source — empty `CREATE OR REFRESH STREAMING TABLE` + `CREATE FLOW`s**: required to fan multiple sources into one table, or to use `AUTO CDC INTO` (see [auto-cdc-sql.md](auto-cdc-sql.md)).

```sql
CREATE OR REFRESH STREAMING TABLE all_events (
  event_id STRING, event_type STRING, event_timestamp TIMESTAMP, source STRING
);

CREATE FLOW mobile_flow AS INSERT INTO all_events BY NAME
SELECT event_id, event_type, event_timestamp, 'mobile' AS source
FROM STREAM(mobile.events);
-- Add CREATE FLOW web_flow ... etc. for additional sources.
```

**Never** combine `AS SELECT` and `CREATE FLOW` on the same target — the `AS SELECT` already provides continuous processing, the flow is redundant.

## `CREATE FLOW` syntax

```sql
CREATE FLOW flow_name [COMMENT '...'] AS
INSERT INTO [ONCE] target_table BY NAME query
```

- Default (no `ONCE`): continuous flow. Query must use `STREAM(...)`.
- `ONCE`: one-shot batch flow. Query must NOT use `STREAM(...)`. Re-executes on full refresh.
- One target can have many flows, each with a distinct `flow_name`.

## Common Patterns

### Auto Loader + filter (single source)

```sql
CREATE OR REFRESH STREAMING TABLE bronze
AS SELECT * FROM STREAM read_files('/path/to/data', format => 'json');

CREATE OR REFRESH STREAMING TABLE silver
AS SELECT * FROM STREAM(bronze) WHERE id IS NOT NULL;
```

### Row filter for data security

```sql
CREATE OR REFRESH STREAMING TABLE employees (
  emp_id INT, emp_name STRING, dept STRING, salary DECIMAL(10,2)
)
WITH ROW FILTER my_catalog.my_schema.filter_by_dept ON (dept)
AS SELECT * FROM STREAM(source.employees);
```

Column masking via `MASK fn USING COLUMNS (other_col)` follows the same shape inside the column definition.

### Private staging table

```sql
CREATE OR REFRESH PRIVATE STREAMING TABLE staging_events
AS SELECT * FROM STREAM(raw_events) WHERE event_type IS NOT NULL;
```

### Backfill + live stream into the same table

```sql
CREATE OR REFRESH STREAMING TABLE transactions (
  transaction_id STRING, customer_id STRING, amount DECIMAL(10,2), transaction_date TIMESTAMP
);

CREATE FLOW live_stream AS INSERT INTO transactions
SELECT * FROM STREAM(source.transactions);

CREATE FLOW historical_backfill AS INSERT INTO ONCE transactions
SELECT * FROM archive.historical_transactions;          -- no STREAM = batch
```

### Stream-static join (enrich with dimension)

```sql
CREATE OR REFRESH STREAMING TABLE enriched_transactions
AS SELECT t.*, c.name, c.email
FROM STREAM(transactions) t
JOIN customers c ON t.customer_id = c.id;
```

`customers` is read as a static snapshot at stream start; `transactions` is read incrementally.

### Reading from a streaming table that has updates/deletes

```sql
CREATE OR REFRESH STREAMING TABLE downstream
AS SELECT * FROM STREAM read_stream("upstream_with_deletes", skipChangeCommits => true);
```

`skipChangeCommits` ignores update/delete commits on the upstream (e.g. GDPR purges, Auto CDC targets). Without it, change commits cause errors.

## Key rules

- Streaming queries require `STREAM(...)` (or `STREAM read_files(...)` / etc.). Batch reads inside a streaming-table definition fail.
- `ALTER TABLE` is not supported — use `CREATE OR REFRESH` to redefine, or `ALTER STREAMING TABLE` for table-level adjustments.
- Generated columns, identity columns, and default columns are not supported.
- Row filters on source tables force full refresh of downstream MVs.
- Only the table owner can refresh; table renaming and ownership changes are prohibited.
- `CLUSTER BY` over `PARTITIONED BY` for new tables.
