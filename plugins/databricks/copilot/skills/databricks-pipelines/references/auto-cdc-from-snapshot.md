# AUTO CDC FROM SNAPSHOT

Use `AUTO CDC ... FROM SNAPSHOT` when each source read is a complete snapshot, such as a periodic table export or the next file in a landing zone. The engine compares each snapshot with the previously committed snapshot and derives inserts, updates, and deletes.

SQL snapshot CDC requires DBR 18.3 or later. If it is unavailable in the selected release, use Python `dp.create_auto_cdc_from_snapshot_flow` in a Lakeflow pipeline.

Do not model a complete snapshot as a change-event stream. Snapshot CDC does not support the flow-level `WHERE` or `SEQUENCE BY` clauses; filters can still appear inside `snapshot_query`. Cross-snapshot ordering comes from `WITH VERSION (...)`.

## Syntax

### Standalone named flow

Use this form when the target is declared separately and the flow needs a name:

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

The embedded form creates the target and its anonymous flow together:

```sql
CREATE [OR REFRESH] STREAMING TABLE [IF NOT EXISTS] <target_table>
FLOW AUTO CDC [ONCE]
FROM SNAPSHOT (<snapshot_query>)
[WITH VERSION (<version_query>)]
KEYS (<key1>, <key2>)
[STORED AS {SCD TYPE 1 | SCD TYPE 2}]
[TRACK HISTORY ON {<column_list> | * EXCEPT (<except_column_list>)}];
```

`OR REFRESH` and `IF NOT EXISTS` are mutually exclusive.

To process versions that arrive later, reevaluate the flow by rerunning its `CREATE OR REFRESH` statement or by running `REFRESH STREAMING TABLE <target_table>`. A new pipeline update also reevaluates the flow.

A destination supports at most one `AUTO CDC FROM SNAPSHOT` flow. Where ACFS/Auto CDC interoperability is enabled, that snapshot flow may coexist with regular Auto CDC flows that write to the same destination.

## Two-phase snapshot selection

- `FROM SNAPSHOT (<snapshot_query>)` is required. It reads the complete snapshot for the version selected by `WITH VERSION`.
- `WITH VERSION (<version_query>)` is optional. It must return exactly one orderable column and zero or one rows. The value can be a scalar or a `STRUCT` whose fields are all orderable.
- When the version query returns one row, the engine exposes it through `current_snapshot_version()`, evaluates and commits the snapshot query, then persists that version for `last_snapshot_version()`.
- The engine repeats this process in one update until the version query returns zero rows. Each committed version must be strictly greater than the previous version.
- `last_snapshot_version()` is valid only inside `WITH VERSION (...)`. It returns zero rows before the first successful snapshot commit or after a full refresh, otherwise one row with the most recently committed version.
- `current_snapshot_version()` is valid only inside `FROM SNAPSHOT (...)` when the flow declares `WITH VERSION (...)`. It returns the version selected for the current iteration.
- Both version functions return a one-column relation whose column name and type match the version query output. Name that output explicitly, for example `SELECT snapshot_version AS version`, and use the same name when selecting from either function. For a struct version, access fields with dot notation.
- Keep the version output type unchanged across incremental updates. A full refresh clears the persisted snapshot state and permits a new type.
- Aggregate version queries must return zero rows when no version remains. Filter null aggregates with `HAVING MAX(<version_column>) IS NOT NULL`.

Use `WITH VERSION` for every recurring snapshot source:

```sql
CREATE OR REFRESH STREAMING TABLE inventory_history
FLOW AUTO CDC
FROM SNAPSHOT (
  SELECT product_id, quantity, updated_at
  FROM catalog.schema.inventory_snapshots
  WHERE snapshot_version = (
    SELECT version FROM current_snapshot_version()
  )
)
WITH VERSION (
  SELECT version
  FROM (
    SELECT DISTINCT snapshot_version AS version
    FROM catalog.schema.inventory_snapshots
  )
  WHERE (
    NOT EXISTS (SELECT 1 FROM last_snapshot_version())
    OR version > (SELECT version FROM last_snapshot_version())
  )
  ORDER BY version
  LIMIT 1
)
KEYS (product_id)
STORED AS SCD TYPE 2;
```

For snapshots stored as one file per version, use a `STRUCT` so modification time orders versions and path breaks ties:

```sql
CREATE OR REFRESH STREAMING TABLE orders
FLOW AUTO CDC
FROM SNAPSHOT (
  SELECT order_id, product, quantity, order_date
  FROM read_files('/Volumes/catalog/schema/landing/orders/', format => 'json')
  WHERE _metadata.file_path = (
    SELECT version.path FROM current_snapshot_version()
  )
)
WITH VERSION (
  SELECT struct(modification_time, path) AS version
  FROM list_files('/Volumes/catalog/schema/landing/orders/')
  WHERE (
    NOT EXISTS (SELECT 1 FROM last_snapshot_version())
    OR struct(modification_time, path) > (
      SELECT version FROM last_snapshot_version()
    )
  )
  ORDER BY modification_time, path
  LIMIT 1
)
KEYS (order_id)
STORED AS SCD TYPE 2;
```

## One-time snapshots and `ONCE`

Without `WITH VERSION`, the first update can succeed when the target has no data or snapshot state, but the next incremental update fails with `AUTO_CDC_FROM_SNAPSHOT_NON_EMPTY_TARGET_WITHOUT_VERSION`. Use `ONCE` for an intentional one-shot snapshot or `WITH VERSION` for recurring snapshots.

`ONCE` processes versions until the version query returns zero rows, records completion after at least one snapshot commits, and is skipped on later incremental updates. If its first version query returns zero rows, it remains eligible for a later update. A full refresh clears completion and makes it eligible again.

```sql
CREATE OR REFRESH STREAMING TABLE users
FLOW AUTO CDC ONCE
FROM SNAPSHOT (
  SELECT * FROM catalog.schema.users_snapshot
)
KEYS (user_id)
STORED AS SCD TYPE 1;
```

## Constraints and errors

- Snapshot CDC supports SCD Type 1 and SCD Type 2. It does not support `STORED AS BITEMPORAL`.
- For snapshot SCD Type 2, `__START_AT` and `__END_AT` use the version output type. Without `WITH VERSION`, the implicit version type is `TIMESTAMP`.
- Each snapshot must contain at most one row for each `KEYS` value.
- Duplicate rows for one key in a snapshot: `APPLY_CHANGES_FROM_SNAPSHOT_ERROR.DUPLICATE_KEY_VIOLATION`.
- More than one version row, more than one version column, or a null version: `INVALID_AUTO_CDC_FROM_SNAPSHOT_VERSION_QUERY`.
- A non-orderable version type: `APPLY_CHANGES_FROM_SNAPSHOT_ERROR.SNAPSHOT_VERSION_NOT_SORTABLE`.
- A version that is equal to or lower than the last committed version: `APPLY_CHANGES_FROM_SNAPSHOT_ERROR.OUT_OF_ORDER_SNAPSHOT_VERSION`.
- A changed version output type: `AUTO_CDC_FROM_SNAPSHOT_VERSION_SCHEMA_CHANGED`.
- Existing target data or snapshot state without `WITH VERSION`: `AUTO_CDC_FROM_SNAPSHOT_NON_EMPTY_TARGET_WITHOUT_VERSION`.
- A snapshot-version function outside its permitted clause: `INVALID_USAGE_OF_SNAPSHOT_VERSION_FUNCTION`.

Prefer the query form `FROM SNAPSHOT (<snapshot_query>)`. The legacy identifier-only form `FROM SNAPSHOT <source>` is deprecated.
