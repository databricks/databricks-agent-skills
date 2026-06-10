# Materialized Views (SQL)

Batch processing with full refresh or incremental computation. For streaming tables (incremental streaming), see [streaming-table-sql.md](streaming-table-sql.md).

## Syntax

```sql
CREATE OR REFRESH [PRIVATE] MATERIALIZED VIEW view_name
  [ ( col_name col_type [NOT NULL] [COMMENT '...'] [column_constraint | MASK clause]
      [, ...]
      [, CONSTRAINT name EXPECT (cond) [ON VIOLATION DROP ROW | FAIL UPDATE]]
      [, table_constraint] ) ]
  [ PARTITIONED BY (col, ...) | CLUSTER BY (col, ...) ]   -- prefer CLUSTER BY
  [ LOCATION path ]                                       -- Hive metastore only
  [ COMMENT '...' ]
  [ TBLPROPERTIES (key = value, ...) ]
  [ WITH ROW FILTER func_name ON (col, ...) ]
  AS query
```

Clause notes (same semantics as streaming tables — see [streaming-table-sql.md](streaming-table-sql.md) for the detailed treatment of `PRIVATE`, `MASK`, `WITH ROW FILTER`, and informational table constraints):

- `query` must NOT use `STREAM(...)` — MVs are batch. Streaming reads belong in a streaming table.
- PRIMARY KEY requires explicit `NOT NULL`.
- Generated columns supported via `col TYPE GENERATED ALWAYS AS (expr)`.
- Identity columns, default columns, and explicit `OPTIMIZE` / `VACUUM` are not supported (the pipeline handles maintenance).
- Non-column expressions in the SELECT list require explicit aliases.
- Sum aggregates over a nullable column return `0` (not NULL) when only NULLs remain.

## Incremental refresh

MVs use incremental refresh automatically when possible. Falls back to full recompute otherwise.

**Requirements**: serverless pipeline, source is Delta / MV / streaming table, row tracking enabled on sources (for ops marked below).

| SQL operation | Support | Notes |
|---|---|---|
| `SELECT` expressions | Yes | Deterministic built-ins / immutable UDFs. Requires row tracking. |
| `WHERE`, `HAVING` | Yes | Requires row tracking. |
| `GROUP BY`, `WITH`, `QUALIFY` | Yes | — |
| `UNION ALL` | Yes | Requires row tracking. |
| `INNER` / `LEFT` / `RIGHT` / `FULL OUTER JOIN` | Yes | Requires row tracking. |
| `OVER` (window functions) | Yes | Must specify `PARTITION BY`. |
| Expectations | Partial | Views-with-expectations and `DROP ROW` on `NOT NULL` columns are exceptions. |
| Non-deterministic functions | Limited | `current_date()` etc. allowed in `WHERE` only. |
| Non-Delta sources | No | Volumes, external locations, foreign catalogs not supported. |

Enable `delta.enableRowTracking = true`, `delta.enableChangeDataFeed = true`, and deletion vectors on source tables for the best incremental coverage. For exactly-once semantics (Kafka, Auto Loader), use a streaming table instead.

## Patterns

### Aggregation with Liquid Clustering

```sql
CREATE OR REFRESH MATERIALIZED VIEW daily_sales_summary
CLUSTER BY (sale_date, region)
AS
SELECT DATE(order_timestamp) AS sale_date, region,
       COUNT(*) AS order_count, SUM(amount) AS total_revenue
FROM raw.orders
GROUP BY DATE(order_timestamp), region;
```

### Generated column

```sql
CREATE OR REFRESH MATERIALIZED VIEW orders_with_day (
  order_datetime    STRING,
  order_day_of_week STRING GENERATED ALWAYS AS (dayofweek(order_datetime)),
  customer_id       BIGINT,
  amount            DECIMAL(10,2)
)
CLUSTER BY (order_day_of_week, customer_id)
AS SELECT order_datetime, customer_id, amount FROM raw.orders;
```

### Row filter (UC, Public Preview)

```sql
CREATE OR REFRESH MATERIALIZED VIEW employees (
  emp_id INT, emp_name STRING, dept STRING, salary DECIMAL(10,2)
)
WITH ROW FILTER my_catalog.my_schema.filter_by_dept ON (dept)
AS SELECT * FROM source.employees;
```

### Column masking (UC, Public Preview)

```sql
CREATE OR REFRESH MATERIALIZED VIEW users_with_masked_ssn (
  user_id BIGINT,
  ssn     STRING MASK catalog.schema.ssn_mask_fn USING COLUMNS (region),
  region  STRING
)
AS SELECT user_id, ssn, region FROM raw.users;
```
