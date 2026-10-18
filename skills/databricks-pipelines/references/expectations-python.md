# Expectations (Python)

Data-quality constraints stacked above `@dp.materialized_view()` / `@dp.table()` / `@dp.temporary_view()` functions. Each constraint is a SQL Boolean string evaluated per row.

Legacy `@dlt.expect*` decorators still parse but should be migrated to `@dp.expect*` (same names, same semantics) — see [SKILL.md Legacy DLT Syntax](../SKILL.md#legacy-dlt-syntax--always-migrate).

## Decorators

| Decorator | Action on violation |
|---|---|
| `@dp.expect(name, condition)` | Warn — invalid rows pass through, metrics logged. |
| `@dp.expect_or_drop(name, condition)` | Drop violating rows before write. |
| `@dp.expect_or_fail(name, condition)` | Fail the pipeline atomically on first violation. |
| `@dp.expect_all({name: cond, ...})` | Warn, multiple at once. |
| `@dp.expect_all_or_drop({name: cond, ...})` | Drop, multiple at once. |
| `@dp.expect_all_or_fail({name: cond, ...})` | Fail, multiple at once. |

- `name` (str) — unique within the dataset; appears in metrics.
- `condition` (str) — a SQL Boolean expression. Built-ins are fine. **No** Python UDFs, external calls, or subqueries.

## Patterns

### Single decorator

```python
@dp.materialized_view()
@dp.expect_or_drop("valid_email", "email IS NOT NULL AND email LIKE '%@%'")
def customer_contacts():
    return spark.read.table("raw_contacts")
```

`@dp.expect("name", "cond")` (warn) and `@dp.expect_or_fail(...)` (fail) follow the same shape.

### Multiple expectations, same action — use `expect_all`

```python
@dp.materialized_view()
@dp.expect_all({
    "valid_age":     "age >= 0 AND age <= 120",
    "valid_country": "country_code IN ('US', 'CA', 'MX')",
    "recent_date":   "created_date >= '2020-01-01'",
})
def validated_customers():
    return spark.read.table("raw_customers")
```

### Multiple expectations, mixed actions — stack decorators

```python
@dp.materialized_view(comment="Clean customer data")
@dp.expect_or_drop("valid_email", "email LIKE '%@%'")
@dp.expect_or_fail("required_id", "id IS NOT NULL")
@dp.expect("valid_age", "age BETWEEN 0 AND 120")
def customers_clean():
    return spark.read.table("raw_customers")
```

### Temporary view with expectations

```python
@dp.temporary_view(name="high_value_customers")
@dp.expect("valid_total", "total_purchases > 0")
def high_value_view():
    return (spark.read.table("orders")
                 .groupBy("customer_id")
                 .agg(F.sum("amount").alias("total_purchases"))
                 .filter("total_purchases > 1000"))
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

## Best Practices

- Unique, descriptive names — they appear in metrics.
- `expect_or_fail` for critical business invariants.
- `expect_or_drop` for cleansing operations.
- `expect` (warn) for measuring soft quality without blocking.
- Group same-action constraints in `expect_all*` rather than stacking many decorators.
- Predicate is a SQL string — no Python UDFs, subqueries, external calls.
