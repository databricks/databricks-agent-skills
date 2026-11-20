# Table → Materialized View & View → Temporary View

## DBT Table → SDP Materialized View

### DBT Input

**`models/marts/fct_daily_revenue.sql`**:

```sql
{{ config(materialized='table') }}

SELECT
    order_date,
    COUNT(*) AS total_orders,
    SUM(amount) AS total_revenue
FROM {{ ref('stg_orders') }}
WHERE status = 'completed'
GROUP BY order_date
```

### Migration IR Node

```yaml
- id: fct_daily_revenue
  source_path: models/marts/fct_daily_revenue.sql
  sdp_type: materialized_view
```

### SDP Output (SQL)

```sql
CREATE OR REFRESH MATERIALIZED VIEW fct_daily_revenue
AS SELECT
    order_date,
    COUNT(*) AS total_orders,
    SUM(amount) AS total_revenue
FROM stg_orders
WHERE status = 'completed'
GROUP BY order_date;
```

### SDP Output (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import count, sum as sum_

@dp.materialized_view()
def fct_daily_revenue():
    return (spark.read.table("stg_orders")
        .filter("status = 'completed'")
        .groupBy("order_date")
        .agg(
            count("*").alias("total_orders"),
            sum_("amount").alias("total_revenue")
        ))
```

### Key Notes

- `{{ config(materialized='table') }}` → `CREATE OR REFRESH MATERIALIZED VIEW` (full recompute on each pipeline refresh)
- `{{ ref('stg_orders') }}` → just `stg_orders` (SDP resolves intra-pipeline references)
- No `STREAM` keyword — materialized views use batch reads

---

## DBT View → SDP Temporary View

Use `temporary_view` when the model is only consumed within the pipeline (intermediate transformation). Use `materialized_view` if downstream consumers outside the pipeline need to query it.

### DBT Input

**`models/intermediate/int_enriched_orders.sql`**:

```sql
{{ config(materialized='view') }}

SELECT
    o.order_id,
    o.amount,
    o.order_date,
    c.customer_name,
    c.segment
FROM {{ ref('stg_orders') }} o
LEFT JOIN {{ ref('stg_customers') }} c ON o.customer_id = c.customer_id
```

### Migration IR Node

```yaml
- id: int_enriched_orders
  source_path: models/intermediate/int_enriched_orders.sql
  sdp_type: temporary_view
```

### SDP Output (SQL)

```sql
CREATE TEMPORARY VIEW int_enriched_orders AS
SELECT
    o.order_id,
    o.amount,
    o.order_date,
    c.customer_name,
    c.segment
FROM stg_orders o
LEFT JOIN stg_customers c ON o.customer_id = c.customer_id;
```

### SDP Output (Python)

```python
from pyspark import pipelines as dp

@dp.temporary_view()
def int_enriched_orders():
    orders = spark.read.table("stg_orders")
    customers = spark.read.table("stg_customers")
    return (orders
        .join(customers, orders.customer_id == customers.customer_id, "left")
        .select(
            orders.order_id,
            orders.amount,
            orders.order_date,
            customers.customer_name,
            customers.segment
        ))
```

### Key Notes

- Temporary views are **not persisted** — they exist only during pipeline execution
- Use `CREATE TEMPORARY VIEW` (not `CREATE OR REFRESH`)
- No expectations on temporary views — add them on the downstream tables that consume them
- `spark.read.table()` (not `readStream`) — temporary views use batch semantics

---

## DBT Ephemeral → SDP Temporary View or Inline CTE

DBT ephemeral models are inlined as CTEs at compile time. In SDP, convert them to temporary views (preferred) or inline the SQL into the consuming model.

### DBT Input

**`models/staging/stg_raw_events.sql`**:

```sql
{{ config(materialized='ephemeral') }}

SELECT
    event_id,
    LOWER(event_type) AS event_type,
    user_id,
    created_at
FROM {{ source('raw', 'events') }}
WHERE event_type IS NOT NULL
```

### Migration IR Node

```yaml
- id: stg_raw_events
  source_path: models/staging/stg_raw_events.sql
  sdp_type: temporary_view
  notes: 'Was ephemeral in DBT — converted to temporary_view for clarity'
```

### SDP Output (SQL)

```sql
CREATE TEMPORARY VIEW stg_raw_events AS
SELECT
    event_id,
    LOWER(event_type) AS event_type,
    user_id,
    created_at
FROM raw_catalog.raw_schema.events
WHERE event_type IS NOT NULL;
```
