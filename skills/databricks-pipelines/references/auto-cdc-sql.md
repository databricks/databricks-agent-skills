# Auto CDC (SQL)

`AUTO CDC INTO` processes CDC events from a streaming source into a target streaming table. SCD Type 1 (latest) or Type 2 (history). The target must be pre-created.

> SQL only supports CDC from streaming sources (`AUTO CDC INTO`). For periodic-snapshot CDC, use Python's `dp.create_auto_cdc_from_snapshot_flow()` — see [auto-cdc-python.md](auto-cdc-python.md).

## Syntax

```sql
CREATE OR REFRESH STREAMING TABLE <target_table>;

CREATE FLOW <flow_name> AS AUTO CDC INTO <target_table>
FROM STREAM(<source_table_or_view>)
KEYS (<key1>, <key2>, ...)
[IGNORE NULL UPDATES]
[APPLY AS DELETE WHEN <condition>]
[APPLY AS TRUNCATE WHEN <condition>]                 -- SCD Type 1 only
SEQUENCE BY <col_or_struct>
[COLUMNS {<col_list> | * EXCEPT (<col_list>)}]
[STORED AS {SCD TYPE 1 | SCD TYPE 2}]                -- default Type 1
[TRACK HISTORY ON {<col_list> | * EXCEPT (<col_list>)}]   -- SCD Type 2 only
```

Clause notes:

- `FROM STREAM(...)` accepts only a table/view identifier — **NOT a subquery**. Pre-filter via a temp view if needed.
- `KEYS` — required primary key columns for row identification.
- `IGNORE NULL UPDATES` — NULL values won't overwrite existing non-NULL values.
- `APPLY AS DELETE WHEN` / `APPLY AS TRUNCATE WHEN` — order matters in the SQL: put both **before** `SEQUENCE BY` or the parser fails.
- `SEQUENCE BY` — single column, or `STRUCT(ts_col, tiebreaker_col)` for multi-column ordering.
- `COLUMNS * EXCEPT (...)` — only list columns that exist in the source (omit `_rescued_data` unless bronze rescued data).
- `STORED AS SCD TYPE 2` adds `__START_AT` and `__END_AT` system columns to the target. If you supply an explicit target schema, include them with the same type as `SEQUENCE BY`.
- `TRACK HISTORY ON cols` — Type 2 only; only listed columns trigger new history rows. Others get in-place Type-1 updates.

For querying Type 2 history tables, see [scd-2-querying.md](scd-2-querying.md).

## Patterns

### Basic (SCD Type 1, default)

```sql
CREATE OR REFRESH STREAMING TABLE users;

CREATE FLOW user_flow AS AUTO CDC INTO users
FROM STREAM(user_changes)
KEYS (user_id)
SEQUENCE BY updated_at;
```

### Pre-filter via temporary view (when the source needs transformation)

```sql
CREATE OR REFRESH TEMPORARY VIEW filtered_changes AS
SELECT * FROM source_table WHERE status = 'active';

CREATE OR REFRESH STREAMING TABLE active_records;

CREATE FLOW active_flow AS AUTO CDC INTO active_records
FROM STREAM(filtered_changes)
KEYS (record_id)
SEQUENCE BY updated_at;
```

### Explicit deletes + ignore NULL updates

```sql
CREATE FLOW order_flow AS AUTO CDC INTO orders
FROM STREAM(order_events)
KEYS (order_id)
IGNORE NULL UPDATES
APPLY AS DELETE WHEN operation = 'DELETE'
SEQUENCE BY event_timestamp;
```

### SCD Type 2 (full history)

```sql
CREATE FLOW customer_flow AS AUTO CDC INTO customer_history
FROM STREAM(customer_changes)
KEYS (customer_id)
SEQUENCE BY changed_at
STORED AS SCD TYPE 2;
```

Variants: `TRACK HISTORY ON balance, status` (only those columns trigger new rows) or `TRACK HISTORY ON * EXCEPT (last_login, view_count)` (track everything except).

### Selective columns

`COLUMNS account_id, balance, status` (include list) or `COLUMNS * EXCEPT (internal_notes, temp_field)` (exclude list).

### Multi-column sequencing

```sql
SEQUENCE BY STRUCT(event_timestamp, event_id)    -- order by ts first, break ties with id
```

### TRUNCATE support (SCD Type 1 only)

```sql
APPLY AS TRUNCATE WHEN operation = 'TRUNCATE'
SEQUENCE BY event_timestamp
STORED AS SCD TYPE 1;
```
