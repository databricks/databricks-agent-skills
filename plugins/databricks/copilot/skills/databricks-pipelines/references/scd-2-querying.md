# Querying SCD Type 2 Tables

How to read SCD Type 2 history tables produced by Auto CDC: current-state views, point-in-time queries, change analysis, and joining facts with historical dimensions. SQL is shown as canonical; Python translates via `spark.read.table(...).filter(F.col("__END_AT").isNull())` etc.

For the CDC flow that *writes* these tables, see [auto-cdc-python.md](auto-cdc-python.md) / [auto-cdc-sql.md](auto-cdc-sql.md).

## Temporal Columns

SCD Type 2 tables (from `stored_as_scd_type=2` / `STORED AS SCD TYPE 2`) include two system columns:

| Column | Meaning |
|--------|---------|
| `__START_AT` | When this version became effective (typically the `sequence_by` value). |
| `__END_AT` | When this version expired. `NULL` for the current version. |

Both have the same type as the `SEQUENCE BY` / `sequence_by` column (usually `TIMESTAMP`).

**Rule of thumb**: `WHERE __END_AT IS NULL` selects only current rows. That's the most common filter — bake it into a materialized view if you query it often.

## Current State

```sql
CREATE OR REFRESH MATERIALIZED VIEW dim_customers_current AS
SELECT customer_id, customer_name, email, phone, address,
       __START_AT AS valid_from
FROM dim_customers
WHERE __END_AT IS NULL;
```

For a single entity: `WHERE customer_id = '12345' AND __END_AT IS NULL`.

## Point-in-Time Queries

State as it existed on a specific date. **Boundary convention**: `[__START_AT, __END_AT)` — start inclusive, end exclusive. Get this wrong and you'll either drop the seam row or double-count it.

```sql
CREATE OR REFRESH MATERIALIZED VIEW products_as_of_2024_01_01 AS
SELECT product_id, product_name, price, category, __START_AT, __END_AT
FROM products_history
WHERE __START_AT <= '2024-01-01'
  AND (__END_AT > '2024-01-01' OR __END_AT IS NULL);
```

## Change Analysis

### All versions of one entity

```sql
SELECT customer_id, customer_name, email, phone,
       __START_AT, __END_AT,
       COALESCE(DATEDIFF(DAY, __START_AT, __END_AT),
                DATEDIFF(DAY, __START_AT, CURRENT_TIMESTAMP())) AS days_active
FROM dim_customers
WHERE customer_id = '12345'
ORDER BY __START_AT DESC;
```

### Changes within a period (excluding the original version per entity)

```sql
SELECT customer_id, customer_name,
       __START_AT AS change_timestamp,
       'UPDATE'   AS change_type
FROM dim_customers c
WHERE __START_AT BETWEEN '2024-01-01' AND '2024-03-31'
  AND __START_AT != (SELECT MIN(__START_AT) FROM dim_customers c2
                     WHERE c2.customer_id = c.customer_id)
ORDER BY __START_AT;
```

## Joining Facts with Historical Dimensions

### As-of-transaction-time (canonical for revenue-correct gold)

For each fact row, pick the dimension version that was active at the transaction's event time.

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

### With the current dimension (ignore history)

When attributes are *labels* (always-current product name, region label), not values that drive the math.

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

**When to use which**: as-of-time for revenue, billing, and audit; current-dim for operational dashboards where attributes are labels.

## Optimization

**Pre-filter into MVs** for repeated queries on history tables:

```sql
CREATE OR REFRESH MATERIALIZED VIEW dim_products_current AS
SELECT * FROM products_history WHERE __END_AT IS NULL;

CREATE OR REFRESH MATERIALIZED VIEW product_change_stats AS
SELECT product_id, COUNT(*) AS version_count,
       MIN(__START_AT) AS first_seen, MAX(__START_AT) AS last_updated
FROM products_history
GROUP BY product_id;
```

**Cluster the history table on lookup key + time**: `CLUSTER BY (product_id, __START_AT)`. Accelerates both entity lookups and point-in-time scans. See [performance.md#cluster-key-selection-by-layer](performance.md#cluster-key-selection-by-layer).

## Best Practices

1. **Filter `__END_AT IS NULL` for "current"** — never compare `__START_AT` against `MAX(__START_AT)` per entity. Slower and breaks under concurrent updates.
2. **Inclusive-lower / exclusive-upper** for point-in-time joins (`__START_AT <= D AND (__END_AT > D OR __END_AT IS NULL)`).
3. **Materialize repeated filters.** A `dim_*_current` MV is cheaper than re-filtering history on every downstream read.
4. **High-precision `SEQUENCE BY`.** Sub-second collisions cause non-deterministic ordering — use microsecond timestamps or `STRUCT(ts, tiebreaker)`.
5. **`TRACK HISTORY ON` only columns that need versions** on wide tables (other columns get Type-1 in-place updates without creating new history rows).

## Common Issues

| Issue | Cause / Fix |
|-------|-------------|
| Multiple rows for the same key | Missing `__END_AT IS NULL` filter. |
| Point-in-time returns no rows at the boundary | Wrong inclusive/exclusive — use `__START_AT <= D AND (__END_AT > D OR __END_AT IS NULL)`. |
| Point-in-time double-counts at the boundary | Used `__END_AT >= D` instead of `__END_AT > D`. |
| Slow temporal join | Materialize current-state MV; cluster history on `(entity_key, __START_AT)`. |
| Unexpected duplicates per business key per moment | Multiple changes at the same `sequence_by` value — higher-precision sequence column or `STRUCT(ts, tiebreaker)`. |
| `__START_AT` / `__END_AT` columns missing | Source table isn't SCD Type 2 (Type 1 has no temporal columns). |
