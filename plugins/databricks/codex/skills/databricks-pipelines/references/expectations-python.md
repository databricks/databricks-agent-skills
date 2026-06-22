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

## Best Practices

- Unique, descriptive names — they appear in metrics.
- `expect_or_fail` for critical business invariants.
- `expect_or_drop` for cleansing operations.
- `expect` (warn) for measuring soft quality without blocking.
- Group same-action constraints in `expect_all*` rather than stacking many decorators.
- Predicate is a SQL string — no Python UDFs, subqueries, external calls.
