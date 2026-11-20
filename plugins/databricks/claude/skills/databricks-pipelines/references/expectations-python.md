Expectations apply data quality constraints to Lakeflow Spark Declarative Pipelines tables and views in Python. They use SQL Boolean expressions to validate each record and take actions when constraints are violated.

## When to Use Expectations

- Apply to `@dp.materialized_view()`/`@dp.table()`/`@dlt.table()`/`@dp.temporary_view()`/`@dp.view()`/`@dlt.view()` decorated functions
- Use on streaming tables, materialized views, or temporary views
- Stack multiple expectation decorators above the dataset function
- Prefer `@dp.expect*` in new code; the `@dlt.expect*` forms have the same names and semantics. Keep existing `@dlt.expect*` code unless the user asks to migrate (see [dlt-migration.md](dlt-migration.md))

## Decorator Types

### Single Expectation Decorators

**@dp.expect(description, constraint)** (or **@dlt.expect(description, constraint)**)

- Logs violations but allows invalid records to pass through
- Collects metrics for monitoring

**@dp.expect_or_drop(description, constraint)** (or **@dlt.expect_or_drop(description, constraint)**)

- Removes invalid records before writing to target
- Logs dropped record metrics

**@dp.expect_or_fail(description, constraint)** (or **@dlt.expect_or_fail(description, constraint)**)

- Stops pipeline execution immediately on violation
- Requires manual intervention to resolve
- Transaction rolls back atomically

### Multiple Expectations Decorators

**@dp.expect_all({description: constraint, ...})** (or **@dlt.expect_all({description: constraint, ...})**)

- Applies multiple warn-level expectations
- Takes dictionary of description-constraint pairs

**@dp.expect_all_or_drop({description: constraint, ...})** (or **@dlt.expect_all_or_drop({description: constraint, ...})**)

- Applies multiple drop-level expectations
- Records dropped if any constraint fails

**@dp.expect_all_or_fail({description: constraint, ...})** (or **@dlt.expect_all_or_fail({description: constraint, ...})**)

- Applies multiple fail-level expectations
- Pipeline stops if any constraint fails

## Parameters

**description** (str, required)

- Unique identifier for the constraint within the dataset
- Should clearly communicate what is being validated
- Can be reused across different datasets

**constraint** (str, required)

- SQL Boolean expression evaluated per record
- Must return true or false
- Cannot contain Python functions or UDFs, external calls, or subqueries; SQL built-in functions are fine
- Cannot include subqueries in constraint logic

## Usage Examples

All variants below work on both the `table`, `materialized_view` or `view` decorators.

### Basic Single Expectation

```python
@dp.materialized_view()
@dp.expect("valid_price", "price >= 0")
def sales_data():
    return spark.read.table("raw_sales")

@dp.table()
@dp.expect("valid_price", "price >= 0")
def sales_data():
    return spark.read.table("raw_sales")
```

### Drop Invalid Records

```python
@dp.materialized_view()
@dp.expect_or_drop("valid_email", "email IS NOT NULL AND email LIKE '%@%'")
def customer_contacts():
    return spark.read.table("raw_contacts")
```

### Fail on Critical Violations

```python
@dp.materialized_view()
@dp.expect_or_fail("required_id", "customer_id IS NOT NULL")
def customer_master():
    return spark.read.table("raw_customers")
```

### Multiple Expectations

```python
@dp.materialized_view()
@dp.expect_all({
    "valid_age": "age >= 0 AND age <= 120",
    "valid_country": "country_code IN ('US', 'CA', 'MX')",
    "recent_date": "created_date >= '2020-01-01'"
})
def validated_customers():
    return spark.read.table("raw_customers")
```

### Stacking Multiple Decorators

```python
@dp.materialized_view(
    comment="Clean customer data with quality checks"
)
@dp.expect_or_drop("valid_email", "email LIKE '%@%'")
@dp.expect_or_fail("required_id", "id IS NOT NULL")
@dp.expect("valid_age", "age BETWEEN 0 AND 120")
def customers_clean():
    return spark.read.table("raw_customers")
```

### With Views

```python
from pyspark.sql import functions as F

@dp.view(
    name="high_value_customers",
    comment="Customers with total purchases over $1000"
)
@dp.expect("valid_total", "total_purchases > 0")
def high_value_view():
    return spark.read.table("orders") \
        .groupBy("customer_id") \
        .agg(F.sum("amount").alias("total_purchases")) \
        .filter("total_purchases > 1000")
```

## Aggregate Expectations

Expectations are evaluated per row, so dataset-level checks (row counts over a window, freshness, sum or ratio thresholds) cannot be attached directly to the dataset being checked. Instead, compute the aggregate in a **private materialized view** that reads the upstream dataset, and put the expectation on the MV's output row.

- Use `private=True` so the check MV is not published to Unity Catalog.
- Use `refresh_policy="incremental"` by default so the check is maintained incrementally instead of rescanning the upstream on every update.
- Read the upstream with `spark.read` (not `spark.readStream`), even when the upstream is a streaming table.
- Use `expect` (warn) or `expect_or_fail`. Don't use `expect_or_drop`: it would only drop the aggregate row, since the upstream dataset is already written.
- Keep the query incrementalizable: time functions such as `current_date()` are only incrementalizable in filters, and `sum`/`avg` over `FLOAT`/`DOUBLE` forces a full recompute (cast to `DECIMAL`).

A failed check does not gate the rest of the pipeline. In a triggered pipeline, `expect_or_fail` fails and rolls back only the check MV's flow: the upstream and other flows still commit, and datasets that read the check MV don't wait for it. In a continuous pipeline it stops the check flow and its dependents. To block downstream work on a failed check, put the check and the downstream work in separate pipelines and chain them with a job task dependency.

### Row count over a time window

Streaming table `events` is fed by one or more append flows; fail if fewer than 1000 events arrived in the last 7 days:

```python
from pyspark.sql import functions as F

@dp.materialized_view(private=True, refresh_policy="incremental")
@dp.expect_or_fail("min_weekly_events", "event_count >= 1000")
def events_last_7_days_check():
    return (spark.read.table("events")
                 .where("event_date > date_sub(current_date(), 7)")
                 .agg(F.count("*").alias("event_count")))
```

### Multiple aggregate checks in one MV

```python
from pyspark.sql import functions as F

@dp.materialized_view(private=True, refresh_policy="incremental")
@dp.expect_or_fail("non_empty", "total_orders > 0")
@dp.expect("low_null_customer_rate", "null_customer_orders <= 0.01 * total_orders")
def orders_quality_check():
    return (spark.read.table("orders")
                 .agg(F.count("*").alias("total_orders"),
                      F.count(F.when(F.col("customer_id").isNull(), 1)).alias("null_customer_orders")))
```

### Foreign key checks

Table-level `FOREIGN KEY` constraints are informational and not enforced. To fail an update on orphaned keys, left anti join the FK table to the PK table in a private MV so only orphans remain. The MV stays empty while the data is valid, and the expectation metrics count the orphans.

- Filter out null FKs if the column is nullable. For composite keys, join on every key column.
- Use one check MV per FK relationship.

```python
from pyspark.sql import functions as F

@dp.materialized_view(private=True, refresh_policy="incremental")
@dp.expect_or_fail("orders_customer_fk_valid", "has_matching_customer")
def orders_customer_fk_check():
    return (spark.read.table("orders")
                 .where("customer_id IS NOT NULL")
                 .join(spark.read.table("customers"), "customer_id", "left_anti")
                 .select("customer_id", F.lit(False).alias("has_matching_customer")))
```

## Monitoring

- Per-expectation metrics are in the `flow_progress` events of the event log (`details.flow_progress.data_quality`); users also see them in the pipeline's data quality view
- Query the event log for detailed analytics
- Metrics available for `expect` (warn) and `expect_or_drop` actions
- Metrics unavailable if pipeline fails or no updates occur

## Best Practices

- Use unique, descriptive names for each expectation; the names appear in the pipeline's data-quality metrics
- Apply `expect_or_fail` for critical business constraints
- Use `expect_or_drop` for data cleansing operations where losing some rows is acceptable
- Use `expect` for monitoring optional quality metrics
- Keep constraint logic simple and SQL-based only
- Group related expectations using `expect_all` variants
