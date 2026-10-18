# Expectations (SQL)

Data-quality constraints inside `CREATE OR REFRESH STREAMING TABLE` / `MATERIALIZED VIEW` / `CREATE LIVE VIEW`. Each constraint is a SQL Boolean expression evaluated per row; the action on violation is `(default)` warn, `DROP ROW`, or `FAIL UPDATE`.

> `CREATE TEMPORARY VIEW` does NOT support `CONSTRAINT` clauses. Use `CREATE LIVE VIEW` for the edge case of "temporary view with expectations" — see [temporary-view-sql.md#using-expectations-with-temporary-views](temporary-view-sql.md#using-expectations-with-temporary-views).

## Syntax

```sql
CREATE OR REFRESH STREAMING TABLE table_name (
  CONSTRAINT name1 EXPECT (cond1),                                  -- warn (default)
  CONSTRAINT name2 EXPECT (cond2) ON VIOLATION DROP ROW,            -- drop violating rows
  CONSTRAINT name3 EXPECT (cond3) ON VIOLATION FAIL UPDATE          -- fail pipeline on first violation
) AS SELECT ...
```

- `constraint_name` must be unique within the dataset; describes what's validated.
- `condition` is a SQL Boolean expression. Built-in functions (`year(...)`, `current_date()`, `CASE`, ...) are fine. **No** Python UDFs, external calls, or subqueries.
- Multiple `CONSTRAINT` clauses are stacked comma-separated and each can have a different action.
- Action semantics:
  - **warn (default)**: violations logged, invalid rows still written to the target. Metrics collected.
  - **`DROP ROW`**: violating rows dropped before write. Metrics collected.
  - **`FAIL UPDATE`**: first violation fails the pipeline atomically; transaction rolls back. Requires manual fix.

## Patterns

### Mixed actions in one dataset

```sql
CREATE OR REFRESH STREAMING TABLE customers_clean (
  CONSTRAINT valid_email EXPECT (email LIKE '%@%')      ON VIOLATION DROP ROW,
  CONSTRAINT required_id EXPECT (id IS NOT NULL)        ON VIOLATION FAIL UPDATE,
  CONSTRAINT valid_age   EXPECT (age BETWEEN 0 AND 120)                          -- warn only
) AS SELECT * FROM STREAM(raw_customers);
```

### With SQL functions / complex predicates

```sql
CREATE OR REFRESH STREAMING TABLE transactions (
  CONSTRAINT valid_date          EXPECT (year(transaction_date) >= 2020),
  CONSTRAINT non_negative_price  EXPECT (price >= 0),
  CONSTRAINT recent_purchase     EXPECT (transaction_date <= current_date())
) AS SELECT * FROM STREAM(raw_transactions);

CREATE OR REFRESH MATERIALIZED VIEW active_subscriptions (
  CONSTRAINT valid_dates EXPECT (
    start_date <= end_date
    AND end_date <= current_date()
    AND start_date >= '2020-01-01'
  ) ON VIOLATION DROP ROW
) AS SELECT * FROM subscriptions WHERE status = 'active';
```

### Temporary view + expectation (only via `CREATE LIVE VIEW`)

```sql
CREATE LIVE VIEW high_value_customers (
  CONSTRAINT valid_total EXPECT (total_purchases > 0)
) AS
SELECT customer_id, SUM(amount) AS total_purchases
FROM orders
GROUP BY customer_id
HAVING total_purchases > 1000;
```

## Aggregate Expectations

Expectations are evaluated per row, so dataset-level checks (row counts over a window, freshness, sum or ratio thresholds) cannot be attached directly to the dataset being checked. Instead, compute the aggregate in a **private materialized view** that reads the upstream dataset, and put the expectation on the MV's output row.

- Use `PRIVATE` so the check MV is not published to Unity Catalog.
- Use `REFRESH POLICY INCREMENTAL` by default so the check is maintained incrementally instead of rescanning the upstream on every update.
- Read the upstream as a batch source (no `STREAM(...)`), even when the upstream is a streaming table.
- Use warn (default) or `ON VIOLATION FAIL UPDATE`. Don't use `DROP ROW`: it would only drop the aggregate row, since the upstream dataset is already written.
- Keep the query incrementalizable: time functions such as `current_date()` are only incrementalizable in `WHERE`, and `SUM`/`AVG` over `FLOAT`/`DOUBLE` forces a full recompute (cast to `DECIMAL`).

A failed check does not gate the rest of the pipeline. In a triggered pipeline, `FAIL UPDATE` fails and rolls back only the check MV's flow: the upstream and other flows still commit, and datasets that read the check MV don't wait for it. In a continuous pipeline it stops the check flow and its dependents. To block downstream work on a failed check, put the check and the downstream work in separate pipelines and chain them with a job task dependency.

### Row count over a time window

Streaming table `events` is fed by one or more append flows; fail if fewer than 1000 events arrived in the last 7 days:

```sql
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW events_last_7_days_check (
  CONSTRAINT min_weekly_events EXPECT (event_count >= 1000) ON VIOLATION FAIL UPDATE
)
REFRESH POLICY INCREMENTAL
AS SELECT COUNT(*) AS event_count
FROM events
WHERE event_date > date_sub(current_date(), 7);
```

### Multiple aggregate checks in one MV

```sql
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW orders_quality_check (
  CONSTRAINT non_empty EXPECT (total_orders > 0) ON VIOLATION FAIL UPDATE,
  CONSTRAINT low_null_customer_rate EXPECT (null_customer_orders <= 0.01 * total_orders)
)
REFRESH POLICY INCREMENTAL
AS SELECT
  COUNT(*) AS total_orders,
  COUNT(CASE WHEN customer_id IS NULL THEN 1 END) AS null_customer_orders
FROM orders;
```

### Foreign key checks

Table-level `FOREIGN KEY` constraints are informational and not enforced. To fail an update on orphaned keys, left anti join the FK table to the PK table in a private MV so only orphans remain. The MV stays empty while the data is valid, and the expectation metrics count the orphans.

- Filter out null FKs if the column is nullable. For composite keys, join on every key column.
- Use one check MV per FK relationship.

```sql
CREATE OR REFRESH PRIVATE MATERIALIZED VIEW orders_customer_fk_check (
  CONSTRAINT orders_customer_fk_valid EXPECT (has_matching_customer) ON VIOLATION FAIL UPDATE
)
REFRESH POLICY INCREMENTAL
AS SELECT o.customer_id, false AS has_matching_customer
FROM orders o LEFT ANTI JOIN customers c ON o.customer_id = c.customer_id
WHERE o.customer_id IS NOT NULL;
```

## Monitoring

Metrics show up in the pipeline UI **Data quality** tab and the event log. Available for `warn` and `DROP ROW` actions. Unavailable if the pipeline fails before completion.

## Best Practices

- Unique, descriptive constraint names — they appear in metrics.
- `FAIL UPDATE` for critical business invariants (anything that should never reach downstream consumers).
- `DROP ROW` for data-cleansing operations where you accept some loss.
- Default (warn) for soft quality metrics you want to *measure* without blocking.
- Keep the predicate simple — no Python, no subqueries, no UDFs.
