Expectations apply data quality constraints to Lakeflow Spark Declarative Pipelines tables and views in SQL. They use SQL Boolean expressions to validate each record and take actions when constraints are violated.

## When to Use Expectations

- Apply within `CREATE OR REFRESH STREAMING TABLE`, `CREATE OR REFRESH MATERIALIZED VIEW`, or `CREATE LIVE VIEW` statements
- Use as optional clauses in table/view creation statements
- Stack multiple CONSTRAINT clauses (comma-separated) in a single statement

**Note on Temporary Views**: Use `CREATE LIVE VIEW` syntax when you need to include expectations with temporary views. The newer `CREATE TEMPORARY VIEW` syntax does not support CONSTRAINT clauses. `CREATE LIVE VIEW` is retained specifically for this use case, even though `CREATE TEMPORARY VIEW` is otherwise preferred for temporary views without expectations. See [temporary-view-sql.md](temporary-view-sql.md) for temporary views.

## Constraint Syntax

### Single Expectation (Warn)

**CONSTRAINT constraint_name EXPECT (condition)**

- Logs violations but allows invalid records to pass through
- Collects metrics for monitoring
- Invalid records are retained in target dataset

### Single Expectation (Drop)

**CONSTRAINT constraint_name EXPECT (condition) ON VIOLATION DROP ROW**

- Removes invalid records before writing to target
- Logs dropped record metrics
- Invalid records are excluded from target

### Single Expectation (Fail)

**CONSTRAINT constraint_name EXPECT (condition) ON VIOLATION FAIL UPDATE**

- Stops pipeline execution immediately on violation
- Requires manual intervention to resolve
- Transaction rolls back atomically

### Multiple Expectations

Multiple CONSTRAINT clauses can be stacked in a single CREATE statement using commas:

```sql
CREATE OR REFRESH STREAMING TABLE table_name(
  CONSTRAINT name1 EXPECT (condition1),
  CONSTRAINT name2 EXPECT (condition2) ON VIOLATION DROP ROW,
  CONSTRAINT name3 EXPECT (condition3) ON VIOLATION FAIL UPDATE
) AS SELECT ...
```

## Parameters

**constraint_name** (required)

- Unique identifier for the constraint within the dataset
- Should clearly communicate what is being validated
- Can be reused across different datasets

**condition** (required)

- SQL Boolean expression evaluated per record
- Must return true or false
- Can include SQL functions (e.g., year(), date(), CASE statements)
- Cannot contain Python functions or UDFs, external calls, or subqueries

## Usage Examples

### Basic Single Expectation

```sql
CREATE OR REFRESH STREAMING TABLE sales_data(
  CONSTRAINT valid_price EXPECT (price >= 0)
) AS
SELECT * FROM STREAM(raw_sales);
```

### Drop Invalid Records

```sql
CREATE OR REFRESH STREAMING TABLE customer_contacts(
  CONSTRAINT valid_email EXPECT (
    email IS NOT NULL AND email LIKE '%@%'
  ) ON VIOLATION DROP ROW
) AS
SELECT * FROM STREAM(raw_contacts);
```

### Fail on Critical Violations

```sql
CREATE OR REFRESH MATERIALIZED VIEW customer_master(
  CONSTRAINT required_id EXPECT (customer_id IS NOT NULL) ON VIOLATION FAIL UPDATE
) AS
SELECT * FROM raw_customers;
```

### Multiple Expectations

```sql
CREATE OR REFRESH STREAMING TABLE validated_customers(
  CONSTRAINT valid_age EXPECT (age >= 0 AND age <= 120),
  CONSTRAINT valid_country EXPECT (country_code IN ('US', 'CA', 'MX')),
  CONSTRAINT recent_date EXPECT (created_date >= '2020-01-01')
) AS
SELECT * FROM STREAM(raw_customers);
```

### Stacking Multiple Constraints with Different Actions

```sql
CREATE OR REFRESH STREAMING TABLE customers_clean
(
  CONSTRAINT valid_email EXPECT (email LIKE '%@%') ON VIOLATION DROP ROW,
  CONSTRAINT required_id EXPECT (id IS NOT NULL) ON VIOLATION FAIL UPDATE,
  CONSTRAINT valid_age EXPECT (age BETWEEN 0 AND 120)
)
COMMENT "Clean customer data with quality checks" AS
SELECT * FROM STREAM(raw_customers);
```

### With SQL Functions

```sql
CREATE OR REFRESH STREAMING TABLE transactions(
  CONSTRAINT valid_date EXPECT (year(transaction_date) >= 2020),
  CONSTRAINT non_negative_price EXPECT (price >= 0),
  CONSTRAINT valid_purchase_date EXPECT (transaction_date <= current_date())
) AS
SELECT * FROM STREAM(raw_transactions);
```

### Complex Business Logic

```sql
CREATE OR REFRESH MATERIALIZED VIEW active_subscriptions(
  CONSTRAINT valid_subscription_dates EXPECT (
    start_date <= end_date
    AND end_date <= current_date()
    AND start_date >= '2020-01-01'
  ) ON VIOLATION DROP ROW
) AS
SELECT * FROM subscriptions WHERE status = 'active';
```

### With Temporary Views

```sql
CREATE LIVE VIEW high_value_customers(
  CONSTRAINT valid_total EXPECT (total_purchases > 0)
)
COMMENT "Customers with total purchases over $1000" AS
SELECT
  customer_id,
  SUM(amount) AS total_purchases
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

- Per-expectation metrics are in the `flow_progress` events of the event log (`details.flow_progress.data_quality`); users also see them in the pipeline's data quality view
- Query the event log for detailed analytics
- Metrics available for `warn` and `drop` actions
- Metrics unavailable if pipeline fails or no updates occur

## Best Practices

- Use unique, descriptive names for each constraint; the names appear in the pipeline's data-quality metrics
- Apply `ON VIOLATION FAIL UPDATE` for critical business constraints
- Use `ON VIOLATION DROP ROW` for data cleansing operations where losing some rows is acceptable
- Use default (warn) behavior for monitoring optional quality metrics
- Keep constraint logic simple
