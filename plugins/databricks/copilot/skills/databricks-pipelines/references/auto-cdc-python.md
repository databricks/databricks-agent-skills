# Auto CDC (Python)

CDC from streaming events (`dp.create_auto_cdc_flow`) or periodic snapshots (`dp.create_auto_cdc_from_snapshot_flow`). Both write into a pre-created streaming table.

Use streaming when CDC events arrive continuously (transaction logs, Kafka, Delta change feeds). Use snapshot when the source is a full dump compared to the previous state (daily extracts, batch exports).

Legacy aliases `dp.apply_changes()` / `dp.apply_changes_from_snapshot()` still parse but should be migrated (see [SKILL.md Legacy DLT Syntax](../SKILL.md#legacy-dlt-syntax--always-migrate)).

For querying SCD Type 2 history tables, see [scd-2-querying.md](scd-2-querying.md).

## `dp.create_auto_cdc_flow(...)`

Call at top level — does NOT return a value.

```python
dp.create_auto_cdc_flow(
    target="<target_table>",                  # required — pre-created via dp.create_streaming_table()
    source="<source_table_or_view>",          # required — string name (table or @dp.temporary_view)
    keys=["key1", "key2"],                    # required — primary key columns
    sequence_by="<col>",                       # required — string col name, or col("ts"), or struct("ts","id")
    stored_as_scd_type=1,                     # 1 (default) = latest values; 2 = history with __START_AT/__END_AT
    ignore_null_updates=False,                # NULL values won't overwrite non-NULL existing
    apply_as_deletes=None,                    # expr("op = 'D'") or "op = 'D'"
    apply_as_truncates=None,                  # SCD Type 1 only
    column_list=None,                          # include list — mutually exclusive with except_column_list
    except_column_list=None,                  # exclude list
    track_history_column_list=None,           # SCD Type 2: cols that trigger new history rows
    track_history_except_column_list=None,    # SCD Type 2: cols that DON'T trigger new history rows
    name=None,                                 # flow name (multiple flows to one target)
    once=False,
)
```

`source` must be a table/view identifier (string) — NOT a DataFrame. To pre-filter, define a `@dp.temporary_view()` and reference its name. Don't materialize a streaming table just for filtering — temp view is preferred.

## `dp.create_auto_cdc_from_snapshot_flow(...)`

```python
dp.create_auto_cdc_from_snapshot_flow(
    target="<target_table>",
    source="<snapshot_table>",                # OR callable (see below)
    keys=["product_id"],
    stored_as_scd_type=1,
    track_history_column_list=None,
    track_history_except_column_list=None,
)
```

`source` accepts a string (most common — name of a table holding the latest snapshot) or a callable for historical snapshot replay:

```python
def next_snapshot_and_version(latest_version: Optional[int]) -> Optional[Tuple[DataFrame, int]]:
    # Receives the last processed snapshot version (None on first run).
    # Return (DataFrame, version) for the next snapshot, or None when caught up.
    if latest_version is None:
        return (spark.read.load("products_v1.csv"), 1)
    return None
```

Version must be a comparable scalar (`int`, `str`, `float`, `bytes`, `datetime`, `date`, `Decimal`).

## Patterns

### Basic (SCD Type 1)

```python
dp.create_streaming_table(name="users")
dp.create_auto_cdc_flow(target="users", source="user_changes",
                        keys=["user_id"], sequence_by="updated_at")
```

### With pre-filtering via temp view

```python
@dp.temporary_view()
def filtered_user_changes():
    return spark.readStream.table("raw_user_changes").filter("user_id IS NOT NULL")

dp.create_streaming_table(name="users")
dp.create_auto_cdc_flow(target="users", source="filtered_user_changes",
                        keys=["user_id"], sequence_by="updated_at")
```

### Explicit deletes + truncates + ignore-null

```python
from pyspark.sql.functions import expr

dp.create_auto_cdc_flow(
    target="orders", source="order_events", keys=["order_id"],
    sequence_by="event_timestamp",
    apply_as_deletes=expr("operation = 'DELETE'"),
    apply_as_truncates=expr("operation = 'TRUNCATE'"),    # SCD Type 1 only
    ignore_null_updates=True,
)
```

### SCD Type 2 with selective history tracking

```python
dp.create_auto_cdc_flow(
    target="accounts", source="account_changes", keys=["account_id"],
    sequence_by="modified_at",
    stored_as_scd_type=2,
    track_history_column_list=["balance", "status"],   # only these trigger new history rows
)
```

Use `track_history_except_column_list=[...]` for the inverse.

### Snapshot-based (table source)

```python
@dp.materialized_view(name="product_snapshot")
def product_snapshot():
    return spark.read.table("source.daily_product_dump")

dp.create_streaming_table(name="products")
dp.create_auto_cdc_from_snapshot_flow(
    target="products", source="product_snapshot",
    keys=["product_id"], stored_as_scd_type=1,
)
```

## Key rules

- Create the target with `dp.create_streaming_table()` first.
- `dp.create_auto_cdc_flow()` does NOT return a value — call at top level.
- `source` is a string table/view name, never a DataFrame. Pre-process via `@dp.temporary_view()`.
- SCD Type 2 adds `__START_AT` / `__END_AT` columns with the same type as `sequence_by`. If you supply an explicit target schema, include them.
- `sequence_by` accepts string column name OR `col("ts")` — both work. Use `struct("ts", "id")` for multi-column ordering.
