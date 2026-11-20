# Common Macro Expansions

## dbt_utils.surrogate_key

### DBT

```sql
SELECT
    {{ dbt_utils.surrogate_key(['order_id', 'product_id']) }} AS sk,
    order_id,
    product_id,
    quantity
FROM {{ ref('stg_order_items') }}
```

### SDP (SQL)

```sql
CREATE OR REFRESH MATERIALIZED VIEW order_items AS
SELECT
    sha2(concat_ws('|',
        COALESCE(CAST(order_id AS STRING), '_null_'),
        COALESCE(CAST(product_id AS STRING), '_null_')
    ), 256) AS sk,
    order_id,
    product_id,
    quantity
FROM stg_order_items;
```

### SDP (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import sha2, concat_ws, coalesce, col, lit

@dp.materialized_view()
def order_items():
    return (spark.read.table("stg_order_items")
        .withColumn("sk", sha2(concat_ws("|",
            coalesce(col("order_id").cast("string"), lit("_null_")),
            coalesce(col("product_id").cast("string"), lit("_null_"))
        ), 256))
        .select("sk", "order_id", "product_id", "quantity"))
```

---

## dbt_utils.date_spine

### DBT

```sql
{{ dbt_utils.date_spine(
    datepart="day",
    start_date="cast('2020-01-01' as date)",
    end_date="current_date()"
) }}
```

### SDP (SQL)

```sql
CREATE OR REFRESH MATERIALIZED VIEW date_spine AS
SELECT
    EXPLODE(SEQUENCE(
        CAST('2020-01-01' AS DATE),
        CURRENT_DATE(),
        INTERVAL 1 DAY
    )) AS date_day;
```

### SDP (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import explode, sequence, lit, current_date

@dp.materialized_view()
def date_spine():
    return (spark.range(1)
        .select(explode(sequence(
            lit("2020-01-01").cast("date"),
            current_date(),
            expr("interval 1 day")
        )).alias("date_day")))
```

---

## dbt_utils.pivot

### DBT

```sql
SELECT
    order_id,
    {{ dbt_utils.pivot('status', dbt_utils.get_column_values(ref('stg_order_items'), 'status')) }}
FROM {{ ref('stg_order_items') }}
GROUP BY order_id
```

### SDP (SQL)

If the pivot values are known statically:

```sql
CREATE OR REFRESH MATERIALIZED VIEW order_status_pivot AS
SELECT
    order_id,
    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS status_pending,
    SUM(CASE WHEN status = 'shipped' THEN 1 ELSE 0 END) AS status_shipped,
    SUM(CASE WHEN status = 'delivered' THEN 1 ELSE 0 END) AS status_delivered
FROM stg_order_items
GROUP BY order_id;
```

### SDP (Python)

Python's `.pivot()` handles dynamic values:

```python
from pyspark import pipelines as dp

@dp.materialized_view()
def order_status_pivot():
    return (spark.read.table("stg_order_items")
        .groupBy("order_id")
        .pivot("status")
        .count())
```

> **Note**: `dbt_utils.get_column_values()` dynamically queries the table at compile time. In SDP SQL, you must hard-code the values (or use Python's `.pivot()` which handles it dynamically). The IR `notes` field should list the known values if the research agent can determine them.

---

## dbt_utils.union_relations

### DBT

```sql
{{ dbt_utils.union_relations(
    relations=[ref('orders_us'), ref('orders_eu'), ref('orders_apac')]
) }}
```

### SDP (SQL)

```sql
CREATE OR REFRESH MATERIALIZED VIEW orders_all AS
SELECT *, 'orders_us' AS _source FROM orders_us
UNION ALL
SELECT *, 'orders_eu' AS _source FROM orders_eu
UNION ALL
SELECT *, 'orders_apac' AS _source FROM orders_apac;
```

---

## Incremental Merge → AUTO CDC

### DBT

```sql
{{ config(
    materialized='incremental',
    unique_key='order_id',
    incremental_strategy='merge',
    merge_update_columns=['status', 'amount', 'updated_at']
) }}

SELECT
    order_id,
    status,
    amount,
    updated_at
FROM {{ source('raw', 'orders') }}
{% if is_incremental() %}
WHERE updated_at > (SELECT max(updated_at) FROM {{ this }})
{% endif %}
```

### IR Node

```yaml
- id: orders_merged
  source_path: models/staging/orders_merged.sql
  sdp_type: auto_cdc
  sdp_cdc_hint: { scd_type: 1 }
  notes: 'merge strategy with unique_key=order_id, updated_at for sequence_by'
```

### SDP (SQL)

```sql
CREATE OR REFRESH STREAMING TABLE orders_merged;
CREATE FLOW orders_merge AS
  AUTO CDC INTO orders_merged
  FROM STREAM(raw_catalog.raw_schema.orders)
  KEYS (order_id)
  SEQUENCE BY updated_at
  STORED AS SCD TYPE 1;
```

> **Note on `merge_update_columns`**: AUTO CDC updates all columns by default. If the DBT model explicitly limits update columns, use `COLUMNS * EXCEPT (...)` to exclude columns that should not be overwritten. However, SDP's `EXCEPT` excludes from the _entire_ flow, not just updates — so this may need manual review.
