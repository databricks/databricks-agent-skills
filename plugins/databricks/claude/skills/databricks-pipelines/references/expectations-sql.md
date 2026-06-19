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

## Monitoring

Metrics show up in the pipeline UI **Data quality** tab and the event log. Available for `warn` and `DROP ROW` actions. Unavailable if the pipeline fails before completion.

## Best Practices

- Unique, descriptive constraint names — they appear in metrics.
- `FAIL UPDATE` for critical business invariants (anything that should never reach downstream consumers).
- `DROP ROW` for data-cleansing operations where you accept some loss.
- Default (warn) for soft quality metrics you want to *measure* without blocking.
- Keep the predicate simple — no Python, no subqueries, no UDFs.
