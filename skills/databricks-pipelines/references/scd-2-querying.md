# Querying SCD Type 2 Tables

How to read SCD Type 2 history tables produced by Auto CDC: current-state views, point-in-time queries, change analysis, and joining facts with historical dimensions. Examples in both SQL and Python.

For the CDC flow that *writes* these tables, see [auto-cdc.md](auto-cdc.md) and the per-language references.

---

## Temporal Columns

SCD Type 2 tables (from `stored_as_scd_type=2` / `STORED AS SCD TYPE 2`) include two system columns:

| Column | Meaning |
|--------|---------|
| `__START_AT` | When this version became effective (typically `sequence_by` value). |
| `__END_AT` | When this version expired. `NULL` for the current version. |

Both have the same type as the `SEQUENCE BY` / `sequence_by` column (usually `TIMESTAMP`).

**Rule of thumb**: `WHERE __END_AT IS NULL` selects only current rows. That's the most common filter — bake it into a materialized view if you query it often.

---

## Current State

```sql
-- All current records (materialize for repeated use)
CREATE OR REFRESH MATERIALIZED VIEW dim_customers_current AS
SELECT customer_id, customer_name, email, phone, address,
       __START_AT AS valid_from
FROM dim_customers
WHERE __END_AT IS NULL;

-- Single customer current row
SELECT *
FROM dim_customers
WHERE customer_id = '12345' AND __END_AT IS NULL;
```

```python
@dp.materialized_view(name="dim_customers_current")
def dim_customers_current():
    return (
        spark.read.table("dim_customers")
             .filter(F.col("__END_AT").isNull())
             .select("customer_id", "customer_name", "email", "phone", "address",
                     F.col("__START_AT").alias("valid_from"))
    )
```

---

## Point-in-Time Queries

State as it existed on a specific date. The inclusive-lower / exclusive-upper boundary matters — get it right or you'll double-count at the seam between versions.

```sql
-- Products as of 2024-01-01
CREATE OR REFRESH MATERIALIZED VIEW products_as_of_2024_01_01 AS
SELECT product_id, product_name, price, category,
       __START_AT, __END_AT
FROM products_history
WHERE __START_AT <= '2024-01-01'
  AND (__END_AT > '2024-01-01' OR __END_AT IS NULL);
```

```python
@dp.materialized_view(name="products_as_of_2024_01_01")
def products_as_of_2024_01_01():
    as_of = "2024-01-01"
    return (
        spark.read.table("products_history")
             .filter(F.col("__START_AT") <= as_of)
             .filter((F.col("__END_AT") > as_of) | F.col("__END_AT").isNull())
    )
```

**Boundary convention**: `[__START_AT, __END_AT)` — start is inclusive, end is exclusive. A version with `__END_AT = '2024-01-01'` is *not* the active version on 2024-01-01.

---

## Change Analysis

### All versions of one entity (history)

```sql
SELECT customer_id, customer_name, email, phone,
       __START_AT, __END_AT,
       COALESCE(DATEDIFF(DAY, __START_AT, __END_AT),
                DATEDIFF(DAY, __START_AT, CURRENT_TIMESTAMP())) AS days_active
FROM dim_customers
WHERE customer_id = '12345'
ORDER BY __START_AT DESC;
```

```python
def customer_history(customer_id: str):
    return (
        spark.read.table("dim_customers")
             .filter(F.col("customer_id") == customer_id)
             .withColumn("days_active",
                 F.coalesce(F.datediff("__END_AT", "__START_AT"),
                            F.datediff(F.current_timestamp(), "__START_AT")))
             .orderBy(F.col("__START_AT").desc())
    )
```

### Changes within a time period

```sql
-- Customers who changed during Q1 2024 (excluding the original version)
SELECT customer_id, customer_name,
       __START_AT AS change_timestamp,
       'UPDATE'   AS change_type
FROM dim_customers c
WHERE __START_AT BETWEEN '2024-01-01' AND '2024-03-31'
  AND __START_AT != (
    SELECT MIN(__START_AT) FROM dim_customers c2
    WHERE c2.customer_id = c.customer_id
  )
ORDER BY __START_AT;
```

```python
@dp.materialized_view(name="customer_changes_q1_2024")
def customer_changes_q1_2024():
    history = spark.read.table("dim_customers")
    first_seen = (history.groupBy("customer_id")
                         .agg(F.min("__START_AT").alias("first_start")))
    return (
        history.join(first_seen, "customer_id")
               .filter(F.col("__START_AT").between("2024-01-01", "2024-03-31"))
               .filter(F.col("__START_AT") != F.col("first_start"))
               .select("customer_id", "customer_name",
                       F.col("__START_AT").alias("change_timestamp"),
                       F.lit("UPDATE").alias("change_type"))
    )
```

---

## Joining Facts with Historical Dimensions

### As-of-transaction-time (canonical)

For each fact row, pick the dimension version that was active at the transaction's event time. This is the common case for revenue-correct gold tables.

```sql
CREATE OR REFRESH MATERIALIZED VIEW sales_with_historical_prices AS
SELECT s.sale_id, s.product_id, s.sale_date, s.quantity,
       p.product_name,
       p.price AS unit_price_at_sale_time,
       s.quantity * p.price AS calculated_amount,
       p.category
FROM sales_fact s
INNER JOIN products_history p
  ON s.product_id = p.product_id
 AND s.sale_date  >= p.__START_AT
 AND (s.sale_date < p.__END_AT OR p.__END_AT IS NULL);
```

```python
@dp.materialized_view(name="sales_with_historical_prices")
def sales_with_historical_prices():
    sales    = spark.read.table("sales_fact")
    products = spark.read.table("products_history")
    return (
        sales.join(
            products,
            (sales.product_id == products.product_id) &
            (sales.sale_date  >= products.__START_AT) &
            ((sales.sale_date <  products.__END_AT) | products.__END_AT.isNull()),
            "inner",
        )
        .select(sales.sale_id, sales.product_id, sales.sale_date, sales.quantity,
                products.product_name,
                products.price.alias("unit_price_at_sale_time"),
                (sales.quantity * products.price).alias("calculated_amount"),
                products.category)
    )
```

### With the current dimension (ignore history)

For reports that should always reflect today's attribute values (regardless of when the sale happened), join against the current row only.

```sql
CREATE OR REFRESH MATERIALIZED VIEW sales_with_current_prices AS
SELECT s.sale_id, s.product_id, s.sale_date, s.quantity,
       s.amount        AS amount_at_sale,
       p.product_name  AS current_product_name,
       p.price         AS current_price
FROM sales_fact s
INNER JOIN products_history p
  ON s.product_id = p.product_id
 AND p.__END_AT IS NULL;
```

```python
@dp.materialized_view(name="sales_with_current_prices")
def sales_with_current_prices():
    sales            = spark.read.table("sales_fact")
    products_current = spark.read.table("products_history").filter(F.col("__END_AT").isNull())
    return (
        sales.join(products_current, "product_id", "inner")
             .select("sale_id", "product_id", "sale_date", "quantity",
                     sales.amount.alias("amount_at_sale"),
                     products_current.product_name.alias("current_product_name"),
                     products_current.price.alias("current_price"))
    )
```

**Choosing between the two**: as-of-time for revenue, billing, and audit; current-dim for operational dashboards where attributes are *labels*, not values that drive the math.

---

## Optimization Patterns

### Pre-filter materialized views

Querying the full history table for "current" repeatedly is wasteful. Bake the `__END_AT IS NULL` filter into an MV:

```sql
CREATE OR REFRESH MATERIALIZED VIEW dim_products_current AS
SELECT * FROM products_history WHERE __END_AT IS NULL;

CREATE OR REFRESH MATERIALIZED VIEW dim_recent_changes AS
SELECT * FROM products_history
WHERE __START_AT >= CURRENT_DATE() - INTERVAL 90 DAYS;

CREATE OR REFRESH MATERIALIZED VIEW product_change_stats AS
SELECT product_id,
       COUNT(*)             AS version_count,
       MIN(__START_AT)      AS first_seen,
       MAX(__START_AT)      AS last_updated
FROM products_history
GROUP BY product_id;
```

```python
@dp.materialized_view(name="dim_products_current")
def dim_products_current():
    return spark.read.table("products_history").filter(F.col("__END_AT").isNull())
```

### Cluster on lookup keys + time

```sql
CREATE OR REFRESH STREAMING TABLE products_history
CLUSTER BY (product_id, __START_AT)
...
```

Clustering on `product_id` accelerates entity lookups; adding `__START_AT` helps point-in-time scans. See [performance.md](performance.md#cluster-key-selection-by-layer) for the full layer-by-layer key guide.

---

## Best Practices

1. **Filter `__END_AT IS NULL` for "current"** — never compare `__START_AT` against `MAX(__START_AT)` per entity. It's slower and breaks under concurrent updates.
2. **Use inclusive-lower / exclusive-upper** for point-in-time joins. Mismatched boundaries either drop the seam row or double-count it.
3. **Materialize repeated filters.** A `dim_*_current` MV is cheaper than re-filtering the history table on every downstream read.
4. **Make `SEQUENCE BY` high-precision.** Sub-second collisions (multiple changes at the same `updated_at`) cause non-deterministic ordering; prefer microsecond timestamps or compose with a tiebreaker via `STRUCT(timestamp, id)`.
5. **For wide history tables, `TRACK HISTORY ON` only the columns that need versions.** Other columns get Type-1 in-place updates and don't create new history rows. See [auto-cdc-python.md](auto-cdc-python.md) / [auto-cdc-sql.md](auto-cdc-sql.md).

---

## Common Issues

| Issue | Cause / Fix |
|-------|-------------|
| Multiple rows for the same key | Missing `__END_AT IS NULL` filter. |
| Point-in-time query returns no rows at the boundary | Wrong inclusive/exclusive — use `__START_AT <= D AND (__END_AT > D OR __END_AT IS NULL)`. |
| Point-in-time query double-counts at the boundary | Used `__END_AT >= D` instead of `__END_AT > D`. |
| Slow temporal join | Materialize current-state MV; cluster history on `(entity_key, __START_AT)`. |
| Unexpected duplicates per business key per moment | Multiple changes at the same `sequence_by` value — use a higher-precision sequence column or `STRUCT(ts, tiebreaker)`. |
| `__START_AT` / `__END_AT` columns missing | Source table isn't SCD Type 2 (Type 1 doesn't have temporals). |
