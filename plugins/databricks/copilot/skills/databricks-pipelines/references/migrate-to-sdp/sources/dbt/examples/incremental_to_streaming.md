# Incremental (Append) → Streaming Table

## DBT Input

**`models/staging/stg_orders.sql`**:

```sql
{{ config(materialized='incremental') }}

SELECT
    id AS order_id,
    user_id,
    order_date,
    status,
    amount
FROM {{ source('raw', 'orders') }}
{% if is_incremental() %}
WHERE order_date > (SELECT max(order_date) FROM {{ this }})
{% endif %}
```

**`schema.yml`**:

```yaml
models:
  - name: stg_orders
    columns:
      - name: order_id
        tests: [not_null]
      - name: amount
        tests: [not_null]
```

## Migration IR Node

```yaml
- id: stg_orders
  source_path: models/staging/stg_orders.sql
  sdp_type: streaming_table
```

## SDP Output (SQL)

```sql
CREATE OR REFRESH STREAMING TABLE stg_orders(
  CONSTRAINT not_null_order_id EXPECT (order_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT not_null_amount EXPECT (amount IS NOT NULL) ON VIOLATION DROP ROW
)
AS SELECT
    id AS order_id,
    user_id,
    order_date,
    status,
    amount
FROM STREAM raw_catalog.raw_schema.orders;
```

## SDP Output (Python)

```python
from pyspark import pipelines as dp

@dp.table()
@dp.expect_or_drop("not_null_order_id", "order_id IS NOT NULL")
@dp.expect_or_drop("not_null_amount", "amount IS NOT NULL")
def stg_orders():
    return (spark.readStream.table("raw_catalog.raw_schema.orders")
        .selectExpr(
            "id AS order_id",
            "user_id",
            "order_date",
            "status",
            "amount"
        ))
```

## Key Conversion Notes

- `{% if is_incremental() %}` block is **removed entirely** — SDP streaming tables handle incrementality automatically (exactly-once append semantics)
- `{{ this }}` is removed — SDP manages self-references internally
- `{{ source('raw', 'orders') }}` → resolved from IR's `sources[]` mapping
- Schema tests → `CONSTRAINT EXPECT` clauses on the table definition
- `{{ config() }}` block is stripped — the SDP type is determined by the IR
