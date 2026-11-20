Auto CDC in Spark Declarative Pipelines processes change data capture (CDC) events from streaming sources or snapshots.

**API Reference:**

**dp.create_auto_cdc_flow() / dlt.create_auto_cdc_flow()**
Applies CDC operations (inserts, updates, deletes) from a streaming source to a target table. Supports SCD Type 1 (latest) and Type 2 (history). Does NOT return a value - call at top level without assignment.

`apply_changes()` and `apply_changes_from_snapshot()` are the older, deprecated names for these functions. Write every new flow with `create_auto_cdc_*`, including in files that `import dlt` or already call `apply_changes()` (use `dlt.create_auto_cdc_flow()` there). Leave existing calls unchanged unless asked.

```python
dp.create_auto_cdc_flow(
  target="<target-table>",
  source="<source-table-name>",
  keys=["key1", "key2"],
  sequence_by="<sequence-column>",
  ignore_null_updates=False,
  apply_as_deletes=None,
  apply_as_truncates=None,
  column_list=None,
  except_column_list=None,
  stored_as_scd_type=1,
  system_sequence_by=None,
  track_history_column_list=None,
  track_history_except_column_list=None,
  columns_to_update=None,
  ignore_null_updates_column_list=None,
  ignore_null_updates_except_column_list=None,
  name=None,
  once=False
)
```

Parameters:

- `target` (str): Target table name (must exist, create with `dp.create_streaming_table()`). **Required.**
- `source` (str): Source table name with CDC events. **Required.**
- `keys` (list): Primary key columns for row identification. **Required.**
- `sequence_by` (str | Column): Column for ordering events (timestamp, version). **Required.** Accepts a string column name or a `Column` expression. For multi-column sequencing, use `struct("col1", "col2")` to order by multiple columns.
- `ignore_null_updates` (bool): If True, NULL values won't overwrite existing non-NULL values
- `apply_as_deletes` (str or Column): Expression identifying delete operations. Use `expr("op = 'D'")` (Column) or `"op = 'D'"` (string).
- `apply_as_truncates` (str or Column): Expression identifying truncate operations. Use `expr("op = 'TRUNCATE'")` (Column) or `"op = 'TRUNCATE'"` (string). Supported only for SCD Type 1.
- `column_list` (list): Columns to include (mutually exclusive with `except_column_list`)
- `except_column_list` (list): Columns to exclude
- `stored_as_scd_type` (int or str): `1` for latest values (default), `2` for full history with `__START_AT`/`__END_AT` columns, or `"bitemporal"` for two-axis history (Beta, DBR 17.3+) — see Pattern 8
- `system_sequence_by` (str): System-time sequencing column. **Required when `stored_as_scd_type="bitemporal"`**; ignored for SCD Type 1/2
- `track_history_column_list` (list): For SCD Type 2, columns to track history for (others use Type 1)
- `track_history_except_column_list` (list): For SCD Type 2, columns to exclude from history tracking
- `columns_to_update` (str | Column): Name of a source column (type `ARRAY<STRING>`) that lists, per change record, exactly which columns to write — for partial updates where events carry only the columns that changed. Listed columns are written from the source (including explicit NULLs); unlisted columns keep their existing target value. Mutually exclusive with `ignore_null_updates*`. Not supported with `stored_as_scd_type="bitemporal"`. See Pattern 9.
- `ignore_null_updates_column_list` (list): Subset of columns for which NULLs are ignored (keep the existing value); all other columns apply NULLs. SQL: `IGNORE NULL UPDATES ON (...)`.
- `ignore_null_updates_except_column_list` (list): Inverse of the above — every column except these ignores NULLs. SQL: `IGNORE NULL UPDATES ON * EXCEPT (...)`.
- `name` (str): Flow name (for multiple flows to same target)
- `once` (bool): Process once and stop (default: False)

**dp.create_auto_cdc_from_snapshot_flow() / dlt.create_auto_cdc_from_snapshot_flow()**
Applies CDC from full snapshots by comparing to previous state. Automatically infers inserts, updates, deletes.

```python
dp.create_auto_cdc_from_snapshot_flow(
  target="<target-table>",
  source=<source-table-name-or-callable>,
  keys=["key1", "key2"],
  stored_as_scd_type=1,
  track_history_column_list=None,
  track_history_except_column_list=None
)
```

Parameters:

- `target` (str): Target table name (must exist). **Required.**
- `source` (str or callable): **Required.** Can be one of:
  - **String**: Source table name containing the full snapshot (most common)
  - **Callable**: Function for processing historical snapshots with type `SnapshotAndVersionFunction = Callable[[SnapshotVersion], SnapshotAndVersion]`
    - `SnapshotVersion = Union[int, str, float, bytes, datetime.datetime, datetime.date, decimal.Decimal]`
    - `SnapshotAndVersion = Optional[Tuple[DataFrame, SnapshotVersion]]`
    - Function receives the latest processed snapshot version (or None for first run)
    - Must return `None` when no more snapshots to process
    - Must return tuple of `(DataFrame, SnapshotVersion)` for next snapshot to process
    - Snapshot version is used to track progress and must be comparable/orderable
- `keys` (list): Primary key columns. **Required.**
- `stored_as_scd_type` (int): `1` for latest (default), `2` for history
- `track_history_column_list` (list): Columns to track history for (SCD Type 2)
- `track_history_except_column_list` (list): Columns to exclude from history tracking

**Use create_auto_cdc_flow when:** Processing streaming CDC events from transaction logs, Kafka, Delta change feeds
**Use create_auto_cdc_from_snapshot_flow when:** Processing periodic full snapshots (daily dumps, batch extracts)

**Common Patterns:**

**Pattern 1: Basic CDC flow from streaming source**

```python
# Step 1: Create target table
dp.create_streaming_table(name="users")

# Step 2: Define CDC flow (source must be a table name)
dp.create_auto_cdc_flow(
    target="users",
    source="user_changes",
    keys=["user_id"],
    sequence_by="updated_at"
)
```

**Pattern 2: CDC flow with upstream transformation**

```python
# Step 1: Define view with transformation (source preprocessing)
@dp.temporary_view()
def filtered_user_changes():
    return (
        spark.readStream.table("raw_user_changes")
        .filter("user_id IS NOT NULL")
    )

# Step 2: Create target table
dp.create_streaming_table(name="users")

# Step 3: Define CDC flow using the view as source
dp.create_auto_cdc_flow(
    target="users",
    source="filtered_user_changes",  # References the view name
    keys=["user_id"],
    sequence_by="updated_at"
)
# Note: Use distinct names for view and target for clarity
# Note: If "raw_user_changes"  is defined in the pipeline and no additional transformations or expectations are needed,
#  source="raw_user_changes" can be used directly
```

**Pattern 3: CDC with explicit deletes and truncates**

```python
from pyspark.sql.functions import expr

dp.create_streaming_table(name="orders")

dp.create_auto_cdc_flow(
    target="orders",
    source="order_events",
    keys=["order_id"],
    sequence_by="event_timestamp",
    apply_as_deletes=expr("operation = 'DELETE'"),
    apply_as_truncates=expr("operation = 'TRUNCATE'"),
    ignore_null_updates=True
)
```

**Pattern 4: SCD Type 2 (Historical tracking)**

```python
dp.create_streaming_table(name="customer_history")

dp.create_auto_cdc_flow(
    target="customer_history",
    source="source.customer_changes",
    keys=["customer_id"],
    sequence_by="changed_at",
    stored_as_scd_type=2  # Track full history
)
# Target will include __START_AT and __END_AT columns
```

**Pattern 5: Snapshot-based CDC (Simple - table source)**

```python
dp.create_streaming_table(name="products")

@dp.materialized_view(name="product_snapshot")
def product_snapshot():
    return spark.read.table("source.daily_product_dump")

dp.create_auto_cdc_from_snapshot_flow(
    target="products",
    source="product_snapshot",  # String table name - most common
    keys=["product_id"],
    stored_as_scd_type=1
)
```

**Pattern 6: Snapshot-based CDC (Advanced - callable for historical snapshots)**

```python
dp.create_streaming_table(name="products")

# Define a callable to process historical snapshots sequentially
def next_snapshot_and_version(latest_snapshot_version: Optional[int]) -> Optional[Tuple[DataFrame, int]]:
    if latest_snapshot_version is None:
        return (spark.read.load("products.csv"), 1)
    else:
        return None

dp.create_auto_cdc_from_snapshot_flow(
    target="products",
    source=next_snapshot_and_version,  # Callable function for historical processing
    keys=["product_id"],
    stored_as_scd_type=1
)
```

**Pattern 7: Selective column tracking**

```python
dp.create_streaming_table(name="accounts")

dp.create_auto_cdc_flow(
    target="accounts",
    source="account_changes",
    keys=["account_id"],
    sequence_by="modified_at",
    stored_as_scd_type=2,
    track_history_column_list=["balance", "status"],  # Only track history for these columns
    ignore_null_updates=True
)
```

**Pattern 8: Bitemporal CDC (Beta — two time axes)**

```python
# Beta (DBR 17.3+): tracks BOTH business time (when the fact was true) and
# system time (when we recorded it), correcting out-of-order changes.
dp.create_streaming_table(name="account_balances")

dp.create_auto_cdc_flow(
    target="account_balances",
    source="balance_changes",
    keys=["account_id"],
    sequence_by="effective_at",        # business time
    system_sequence_by="ingested_at",  # system time (REQUIRED for bitemporal)
    stored_as_scd_type="bitemporal"
)
# Target includes __START_AT/__END_AT (business time) and
# __SYSTEM_START_AT/__SYSTEM_END_AT (system time). Old beliefs are closed by
# setting __SYSTEM_END_AT, never physically deleted.
```

**Pattern 9: Partial updates (only update the changed columns; apply explicit NULLs)**

```python
# When change events carry only the columns that changed (the rest arrive NULL),
# a status column tells AUTO CDC which columns to write per record. Unlisted
# columns keep their existing value; explicitly-cleared columns are written as NULL.
dp.create_streaming_table(name="customers")

dp.create_auto_cdc_flow(
    target="customers",
    source="customer_changes",
    keys=["id"],
    sequence_by="event_ts",
    apply_as_deletes="operation = 'DELETE'",
    stored_as_scd_type=1,
    columns_to_update="updatedColumns",  # ARRAY<STRING> per row: which columns to write
)
```

Prefer this over a blanket `ignore_null_updates=True`, which cannot tell a column that
was absent from a change apart from one that was intentionally set to NULL. To name the
subset in pipeline code instead of per-row, use
`ignore_null_updates_column_list=["country"]` (only `country` keeps its existing value on
NULL) or `ignore_null_updates_except_column_list=["age"]` (every column except `age`
keeps its existing value on NULL).

---

## SCD Type 1 vs Type 2 vs Bitemporal Guide

### Quick Decision

| Question                           | Answer                   |
| ---------------------------------- | ------------------------ |
| Need to query historical values?   | **SCD Type 2**           |
| Only need current/latest state?    | **SCD Type 1**           |
| Need to deduplicate incoming data? | **SCD Type 1**           |
| Need audit trail of changes?       | **SCD Type 2**           |
| Building star schema dimensions?   | **SCD Type 2** (usually) |
| Need as-of-system-time queries?    | **Bitemporal** (Beta)    |
| Source has two timestamps with different semantic meaning? | **Bitemporal** (Beta) |

**Recognizing bitemporal from the source schema.** Users rarely ask for "bitemporal" by name — they describe two timestamps. Whenever the source carries two timestamps with genuinely different semantic meaning, raise bitemporal as an option even if the request never mentions CDC, SCD, or history — including a plain "load this table" ask. Explain the payoff (as-of-system-time queries — "what did we believe at time T?") and let the user choose; do not silently upgrade a plain ingestion request.

The engine's two axes are business time (`sequence_by`) and system time (`system_sequence_by`). The pattern is one timestamp for *when the fact holds in the domain* and another for *when the system learned or recorded it*, which surfaces under many domain vocabularies:

- `effective_at` + `ingested_at`, `event_time` + `load_time`, `as_of_date` + `received_at`
- trade date + booking date; policy effective date + endorsement entry date
- observation/measurement time + chart-entry or lab-report time
- period a correction applies to + the run that issued the correction (restatements, amended filings, retroactive adjustments)
- any "we found out later that the value back then was actually different" framing

Map whichever column means "true in the domain" to `sequence_by` and whichever means "recorded by us" to `system_sequence_by`. If it is unclear which is which, ask rather than guessing.

Two timestamps alone are **not** sufficient. Do NOT use bitemporal when:

- both columns order the *same* axis and exist only to break ties → multi-column sequencing, `sequence_by=struct("ts", "id")`
- one is a key/id and the other a timestamp → ordinary SCD Type 1/2
- they are `created_at` + `updated_at` on the same record → ordinary SCD Type 1/2 (the record's own lifecycle, not two independent axes)

Bitemporal requires two *independent* axes: a late-arriving correction must be able to change what was believed at a past business time without changing that business time.

### Comparison

| Aspect                  | SCD Type 1                   | SCD Type 2                     | Bitemporal (Beta)                                           |
| ----------------------- | ---------------------------- | ------------------------------ | ----------------------------------------------------------- |
| History preserved       | No                           | Yes (business time)            | Yes (business + system time)                                |
| `__START_AT`/`__END_AT` | No                           | Yes                            | Yes, plus `__SYSTEM_START_AT`/`__SYSTEM_END_AT`             |
| Storage cost            | Lower                        | Higher                         | Highest                                                     |
| Query complexity        | Simple                       | Needs `WHERE __END_AT IS NULL` | Two-axis filter (see below)                                 |
| Use case                | Deduplication, current state | History, audit, point-in-time  | History, audit, point-in-time, "what did we know and when"  |
| Python syntax           | `stored_as_scd_type=1`       | `stored_as_scd_type=2`         | `stored_as_scd_type="bitemporal"` + `system_sequence_by`    |

### Querying SCD Type 2 Tables

SCD Type 2 tables have multiple rows per key. Use `__START_AT`/`__END_AT` to select the right version. See [scd-2-querying.md](scd-2-querying.md) for more query patterns.

**Current state only:**

```python
df = spark.table("dim_customers").filter("__END_AT IS NULL")
```

**Point-in-time lookup:**

```python
from pyspark.sql.functions import col, lit

df = spark.table("dim_customers").filter(
    (col("__START_AT") <= lit("2024-06-01")) &
    ((col("__END_AT") > lit("2024-06-01")) | col("__END_AT").isNull())
)
```

**Temporal join (join facts to the dimension version active at event time):**

```python
from pyspark.sql.functions import col

fact_sales = spark.table("fact_sales")
dim_customers = spark.table("dim_customers")

result = fact_sales.join(
    dim_customers,
    on=(
        (fact_sales["customer_id"] == dim_customers["customer_id"]) &
        (fact_sales["sale_date"] >= dim_customers["__START_AT"]) &
        ((fact_sales["sale_date"] < dim_customers["__END_AT"]) | dim_customers["__END_AT"].isNull())
    ),
    how="left"
)
```

### Querying Bitemporal Tables

Bitemporal tables carry two validity ranges; filter on both axes.

**Current belief about the current state** (the everyday view):

```python
df = spark.table("account_balances").filter("__END_AT IS NULL AND __SYSTEM_END_AT IS NULL")
```

**As-of query — what we believed at system time `S` about business time `B`:**

```python
from pyspark.sql.functions import col, lit

as_of = spark.table("account_balances").filter(
    (col("__START_AT") <= lit(B)) & ((col("__END_AT") > lit(B)) | col("__END_AT").isNull()) &
    (col("__SYSTEM_START_AT") <= lit(S)) & ((col("__SYSTEM_END_AT") > lit(S)) | col("__SYSTEM_END_AT").isNull())
)
```

### SCD Best Practices

1. **Clean data first** — apply validation and type casting before AUTO CDC
2. **Choose wisely** — use Type 2 only when history is needed (higher storage)
3. **Use track_history_column_list** — limit version triggers to important columns
4. **Include delete handling** — add `apply_as_deletes=expr("op = 'D'")` for logical deletes
5. **Meaningful sequence_by** — use timestamp that reflects true chronological order

---

**KEY RULES:**

- Create target with `dp.create_streaming_table()` before defining CDC flow
- `dp.create_auto_cdc_flow()` does NOT return a value - call it at top level without assigning to a variable
- `source` must be a table name (string) - use `@dp.temporary_view()` to preprocess/filter/transform data before CDC processing. A temporary view is the **preferred** approach for source preprocessing (not a streaming table)
- SCD Type 2 adds `__START_AT` and `__END_AT` columns for validity tracking
- When specifying the schema of the target table for SCD Type 2, you must also include the `__START_AT` and `__END_AT` columns with the same data type as the `sequence_by` field
- **Bitemporal (Beta, DBR 17.3+)**: set `stored_as_scd_type="bitemporal"` and provide `system_sequence_by`. It adds `__SYSTEM_START_AT`/`__SYSTEM_END_AT` on top of `__START_AT`/`__END_AT` — do NOT invent names like `valid_from`/`valid_to`/`txn_from`
- **Offer bitemporal whenever the source has two timestamps with different semantic meaning** — one for when the fact holds in the domain, the other for when the system learned or recorded it — even if the user never says CDC, SCD, history, or bitemporal. Examples include trade vs booking date, observation vs chart-entry time, event time vs recording time. Two timestamps that only break ties on one axis are multi-column sequencing instead; see "Recognizing bitemporal from the source schema" above
- Bitemporal does NOT support `ignore_null_updates`, `apply_as_truncates`, `track_history_column_list`/`track_history_except_column_list`, `columns_to_update`, or multiple flows into the same target
- **Partial updates** (events carrying only the columns that changed): use `columns_to_update` (a per-row `ARRAY<STRING>` status column) so unlisted columns are preserved and explicit NULLs are still applied. Do NOT hand-roll a sentinel value plus a cleanup view.
- `columns_to_update` and `ignore_null_updates*` are mutually exclusive; the status column must be a non-null `ARRAY<STRING>` for upsert rows.
- Nested struct paths in the status column (e.g. `"address.city"`) are supported; a top-level struct name (e.g. `"address"`) updates all of its sub-fields.
