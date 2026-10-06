# Auto CDC (SQL)

Auto CDC processes streaming CDC events or compares consecutive periodic complete snapshots to maintain a target streaming table. Both forms support SCD Type 1 (latest) and Type 2 (history).

## Streaming source syntax

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
CREATE TEMPORARY VIEW filtered_changes AS
SELECT * FROM STREAM source_table WHERE status = 'active';

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

---

## Snapshot sources

Use `AUTO CDC ... FROM SNAPSHOT` when each source read is a complete snapshot, such as a periodic table export or the next full file in a landing zone. The engine compares each snapshot with the previously committed snapshot and derives inserts, updates, and deletes.

SQL snapshot CDC requires DBR 18.3 or later. On older runtimes, use Python `dp.create_auto_cdc_from_snapshot_flow`.

Do not model complete snapshots as a change-event stream. Snapshot CDC does not use the flow-level `WHERE` or `SEQUENCE BY` clauses; filters can still appear inside the snapshot query, and cross-snapshot ordering comes from `WITH VERSION (...)`.

### Standalone named flow

Use this form when the target is declared separately and the flow needs a name. A target supports at most one snapshot flow. Where snapshot and regular Auto CDC interoperability is enabled, regular Auto CDC flows can coexist with that snapshot flow.

```sql
CREATE OR REFRESH STREAMING TABLE <target_table>;

CREATE [OR REFRESH] FLOW [IF NOT EXISTS] <flow_name>
AS AUTO CDC [ONCE] INTO <target_table>
FROM SNAPSHOT (<snapshot_query>)
[WITH VERSION (<version_query>)]
KEYS (<key1>, <key2>)
[STORED AS {SCD TYPE 1 | SCD TYPE 2}]
[TRACK HISTORY ON {<column_list> | * EXCEPT (<except_column_list>)}];
```

`OR REFRESH` and `IF NOT EXISTS` are mutually exclusive.

### Embedded anonymous flow

Use this form to create the target and its anonymous flow together:

```sql
CREATE STREAMING TABLE [IF NOT EXISTS] <target_table>
FLOW AUTO CDC [ONCE]
FROM SNAPSHOT (<snapshot_query>)
[WITH VERSION (<version_query>)]
KEYS (<key1>, <key2>)
[STORED AS {SCD TYPE 1 | SCD TYPE 2}]
[TRACK HISTORY ON {<column_list> | * EXCEPT (<except_column_list>)}];
```

### Snapshot version lifecycle

- `FROM SNAPSHOT (<snapshot_query>)` reads the complete snapshot selected by `WITH VERSION`.
- `WITH VERSION (<version_query>)` is optional. It must return exactly one orderable column and zero or one rows. The value can be a scalar or a `STRUCT` whose fields are all orderable.
- When the version query returns one row, the engine exposes it through `current_snapshot_version()`, evaluates and commits the snapshot query, then persists that version for `last_snapshot_version()`.
- The engine repeats the selection and commit cycle in one pipeline update until the version query returns zero rows. Each committed version must compare strictly greater than the previous version.
- `last_snapshot_version()` is valid only inside `WITH VERSION (...)`. It returns zero rows before the first successful commit or after a full refresh, otherwise one row containing the most recently committed version.
- `current_snapshot_version()` is valid only inside `FROM SNAPSHOT (...)` when the flow declares `WITH VERSION (...)`.
- The version column name and data type must remain unchanged across updates. A full refresh clears the persisted version state.
- Aggregate version queries must return zero rows when no version remains. Filter null aggregates with `HAVING MAX(<version_column>) IS NOT NULL`.
- Without `WITH VERSION`, the first update can succeed only when the target has no data or persisted snapshot state. Use `ONCE` for an intentional one-time snapshot or `WITH VERSION` for recurring snapshots.
- `ONCE` processes all versions currently available, records completion after at least one snapshot commits, and remains idle on later incremental updates. A full refresh clears completion.
- Snapshot CDC supports SCD Type 1 and Type 2. Bitemporal snapshot CDC is not supported.

### One-time initial snapshot

```sql
CREATE OR REFRESH STREAMING TABLE users;

CREATE FLOW users_snapshot_flow
AS AUTO CDC ONCE INTO users
FROM SNAPSHOT (
  SELECT * FROM catalog.schema.users_snapshot
)
KEYS (user_id)
STORED AS SCD TYPE 1;
```

### Process complete snapshot files in order

```sql
CREATE OR REFRESH STREAMING TABLE orders;

CREATE FLOW orders_snapshot_flow
AS AUTO CDC INTO orders
FROM SNAPSHOT (
  SELECT order_id, product, quantity, order_date
  FROM read_files('s3://landing/orders/', format => 'json')
  WHERE _metadata.file_path = (
    SELECT version.path FROM current_snapshot_version()
  )
)
WITH VERSION (
  SELECT struct(modification_time, path) AS version
  FROM list_files('s3://landing/orders/')
  WHERE (
    NOT EXISTS (SELECT 1 FROM last_snapshot_version())
    OR struct(modification_time, path) >
       (SELECT version FROM last_snapshot_version())
  )
  ORDER BY modification_time, path
  LIMIT 1
)
KEYS (order_id)
STORED AS SCD TYPE 2;
```

### Snapshot-specific errors

- More than one version row, more than one version column, or a null version: `INVALID_AUTO_CDC_FROM_SNAPSHOT_VERSION_QUERY`.
- A non-orderable version type: `APPLY_CHANGES_FROM_SNAPSHOT_ERROR.SNAPSHOT_VERSION_NOT_SORTABLE`.
- A version equal to or lower than the last committed version: `APPLY_CHANGES_FROM_SNAPSHOT_ERROR.OUT_OF_ORDER_SNAPSHOT_VERSION`.
- A changed version column name or data type: `AUTO_CDC_FROM_SNAPSHOT_VERSION_SCHEMA_CHANGED`.
- Existing target data or snapshot state without `WITH VERSION`: `AUTO_CDC_FROM_SNAPSHOT_NON_EMPTY_TARGET_WITHOUT_VERSION`.
- A snapshot-version function outside its permitted clause: `INVALID_USAGE_OF_SNAPSHOT_VERSION_FUNCTION`.

Prefer query-form `FROM SNAPSHOT (<snapshot_query>)`. The legacy identifier-only form `FROM SNAPSHOT <source>` is deprecated.
