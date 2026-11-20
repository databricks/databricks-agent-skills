# Snapshot → AUTO CDC

## DBT Input: Timestamp Strategy

**`snapshots/users_snapshot.sql`**:

```sql
{% snapshot users_snapshot %}
{{ config(
    unique_key='user_id',
    strategy='timestamp',
    updated_at='updated_at',
    target_schema='snapshots'
) }}
SELECT * FROM {{ source('raw', 'users') }}
{% endsnapshot %}
```

### Migration IR Node

```yaml
- id: users_snapshot
  source_path: snapshots/users_snapshot.sql
  sdp_type: auto_cdc
  sdp_cdc_hint: { scd_type: 2 }
  notes: 'timestamp-strategy snapshot, use updated_at as sequence_by'
```

### SDP Output (SQL)

```sql
CREATE OR REFRESH STREAMING TABLE users_snapshot;
CREATE FLOW users_snapshot_cdc AS
  AUTO CDC INTO users_snapshot
  FROM STREAM(raw_catalog.raw_schema.users)
  KEYS (user_id)
  SEQUENCE BY updated_at
  STORED AS SCD TYPE 2;
```

### SDP Output (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

@dp.temporary_view()
def users_cdc_source():
    return spark.readStream.table("raw_catalog.raw_schema.users")

dp.create_streaming_table("users_snapshot")
dp.create_auto_cdc_flow(
    target="users_snapshot",
    source="users_cdc_source",
    keys=["user_id"],
    sequence_by=col("updated_at"),
    stored_as_scd_type=2
)
```

---

## DBT Input: Check Strategy

**`snapshots/products_snapshot.sql`**:

```sql
{% snapshot products_snapshot %}
{{ config(
    unique_key='product_id',
    strategy='check',
    check_cols='all',
    target_schema='snapshots'
) }}
SELECT product_id, name, status
FROM {{ source('raw', 'products') }}
WHERE snapshot_version = (
  SELECT MAX(snapshot_version) FROM {{ source('raw', 'products') }}
)
{% endsnapshot %}
```

### Migration IR Node

```yaml
- id: products_snapshot
  source_path: snapshots/products_snapshot.sql
  sdp_type: auto_cdc_snapshot
  output_format: sql
  sdp_cdc_hint: { scd_type: 2 }
  source_meta:
    snapshot_version_column: snapshot_version
    snapshot_versions_are_complete: true
    snapshot_versions_are_immutable: true
  notes: "check strategy (check_cols='all') over the latest complete snapshot"
```

### SDP Output (SQL, when the source has a snapshot version)

This form is safe because the DBT query exposes only one current snapshot while the underlying source retains immutable, complete snapshots under an orderable `snapshot_version`. The metadata column is not part of the DBT snapshot output or `check_cols='all'`; it is used only by `WITH VERSION`. If the source exposes only complete current state, SQL without `WITH VERSION` is valid for an initial load into an empty target; use `AUTO CDC ONCE` to make that one-time intent explicit. To preserve recurring DBT snapshot behavior without a retained version source, use the current-state Python form below and flag the missing SQL version source for manual review. If the source contains partial batches, neither snapshot API is safe until the migration reconstructs complete snapshots.

```sql
CREATE OR REFRESH STREAMING TABLE products_snapshot;

CREATE FLOW products_snapshot_cdc
AS AUTO CDC INTO products_snapshot
FROM SNAPSHOT (
  SELECT product_id, name, status
  FROM raw_catalog.raw_schema.products
  WHERE snapshot_version = (
    SELECT version FROM current_snapshot_version()
  )
)
WITH VERSION (
  SELECT snapshot_version AS version
  FROM (
    SELECT DISTINCT snapshot_version
    FROM raw_catalog.raw_schema.products
  )
  WHERE (
    NOT EXISTS (SELECT 1 FROM last_snapshot_version())
    OR snapshot_version > (SELECT version FROM last_snapshot_version())
  )
  ORDER BY snapshot_version
  LIMIT 1
)
KEYS (product_id)
STORED AS SCD TYPE 2;
```

### SDP Output (Python, retained versioned source)

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

@dp.temporary_view()
def products_snapshot_source():
    source = spark.read.table("raw_catalog.raw_schema.products")
    return (
        source
        .withColumn(
            "_latest_snapshot_version",
            F.max("snapshot_version").over(Window.partitionBy())
        )
        .where(F.col("snapshot_version") == F.col("_latest_snapshot_version"))
        .select("product_id", "name", "status")
    )

dp.create_streaming_table("products_snapshot")
dp.create_auto_cdc_from_snapshot_flow(
    target="products_snapshot",
    source="products_snapshot_source",
    keys=["product_id"],
    stored_as_scd_type=2
)
```

### SDP Output (SQL, one-time initial current-state snapshot)

This form is valid only when the target has no data or snapshot state. `ONCE` makes the one-time lifecycle explicit.

```sql
CREATE OR REFRESH STREAMING TABLE products_snapshot;

CREATE FLOW products_snapshot_initial
AS AUTO CDC ONCE INTO products_snapshot
FROM SNAPSHOT (
  SELECT product_id, name, status
  FROM raw_catalog.raw_schema.products_current
)
KEYS (product_id)
STORED AS SCD TYPE 2;
```

### SDP Output (Python, recurring complete current-state snapshot without version metadata)

```python
from pyspark import pipelines as dp

@dp.temporary_view()
def products_snapshot_source():
    return (
        spark.read.table("raw_catalog.raw_schema.products_current")
        .select("product_id", "name", "status")
    )

dp.create_streaming_table("products_snapshot")
dp.create_auto_cdc_from_snapshot_flow(
    target="products_snapshot",
    source="products_snapshot_source",
    keys=["product_id"],
    stored_as_scd_type=2
)
```

---

## DBT Input: Snapshot with Hard Deletes

**`snapshots/accounts_snapshot.sql`**:

```sql
{% snapshot accounts_snapshot %}
{{ config(
    unique_key='account_id',
    strategy='timestamp',
    updated_at='modified_at',
    invalidate_hard_deletes=True
) }}
SELECT * FROM {{ source('raw', 'accounts') }}
{% endsnapshot %}
```

### Migration IR Node

```yaml
- id: accounts_snapshot
  source_path: snapshots/accounts_snapshot.sql
  sdp_type: auto_cdc
  sdp_cdc_hint: { scd_type: 2 }
  notes: 'invalidate_hard_deletes=True — need apply_as_deletes logic'
```

### SDP Output (SQL)

```sql
CREATE OR REFRESH STREAMING TABLE accounts_snapshot;
CREATE FLOW accounts_snapshot_cdc AS
  AUTO CDC INTO accounts_snapshot
  FROM STREAM(raw_catalog.raw_schema.accounts)
  KEYS (account_id)
  SEQUENCE BY modified_at
  APPLY AS DELETE WHEN _is_deleted = true
  STORED AS SCD TYPE 2;
```

> **Note**: DBT's `invalidate_hard_deletes` works by comparing snapshots to detect missing rows. In SDP, the source must provide a delete signal (e.g., a `_is_deleted` column or a CDC operation column). The generate agent should check the source schema and add a note if no delete signal is available — this may require manual intervention.

---

## Key Conversion Notes

| DBT Snapshot Config                   | SDP Mapping                                                    |
| ------------------------------------- | -------------------------------------------------------------- |
| `strategy='timestamp'` + `updated_at` | `AUTO CDC INTO ... SEQUENCE BY updated_at`                     |
| `strategy='check'` + `check_cols`     | Versioned SQL for recurring immutable snapshots; unversioned SQL `ONCE` for an initial empty target; Python for recurring complete current state; reconstruct partial batches first |
| `unique_key`                          | `KEYS (...)` in AUTO CDC                                       |
| `invalidate_hard_deletes=True`        | `APPLY AS DELETE WHEN ...` (requires delete signal in source)  |
| SCD Type 2 (default for snapshots)    | `STORED AS SCD TYPE 2` (adds `__START_AT`, `__END_AT` columns) |
