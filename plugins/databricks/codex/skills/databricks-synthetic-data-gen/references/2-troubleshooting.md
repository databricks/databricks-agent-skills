# Troubleshooting Guide

Common issues and solutions for synthetic data generation.

## Environment Issues

### ModuleNotFoundError: dbldatagen (or faker)

**Problem:** Dependencies not available in execution environment. `dbldatagen` is required, and
`faker` too if you use `FakerTextFactory`/`fakerText`.

**Solutions by execution mode:**

| Mode | Solution |
|------|----------|
| **DB Connect with Serverless** | Install libs locally (`uv pip install dbldatagen faker`), use `DatabricksSession.builder.serverless(True)` |
| **Databricks Runtime** | `%pip install dbldatagen faker` at the top of the notebook |
| **Classic cluster** | Use Databricks CLI to install libraries. `databricks libraries install --json '{"cluster_id": "<cluster_id>", "libraries": [{"pypi": {"package": "dbldatagen"}}, {"pypi": {"package": "faker"}}]}'` |

```python
# For DB Connect with serverless
from databricks.connect import DatabricksSession

# Install dependencies locally first: uv pip install dbldatagen faker
spark = DatabricksSession.builder.serverless(True).getOrCreate()
```

### serverless_compute_id error

**Problem:** Missing serverless configuration.

**Solution:** Add to `~/.databrickscfg`:

```ini
[DEFAULT]
host = https://your-workspace.cloud.databricks.com/
serverless_compute_id = auto
auth_type = databricks-cli
```

---

## Execution Issues

### CRITICAL: cache() and persist() NOT supported on serverless

**Problem:** Using `.cache()` or `.persist()` on serverless compute fails with:
```
AnalysisException: [NOT_SUPPORTED_WITH_SERVERLESS] PERSIST TABLE is not supported on serverless compute.
```

**Why this happens:** Serverless compute does not support caching DataFrames in memory. This is a fundamental limitation of the serverless architecture.

**Solution:** Write parent tables to Delta first, then read them back for FK joins:

```python
# BAD - will fail on serverless
customers_df = dg.DataGenerator(spark, name="customers", rows=N_CUSTOMERS, partitions=8).build()
customers_df.cache()  # ❌ FAILS: "PERSIST TABLE is not supported on serverless compute"

# GOOD - write to Delta, then read back
customers_df = dg.DataGenerator(spark, name="customers", rows=N_CUSTOMERS, partitions=8).build()
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers")  # ✓ Read from Delta
```

**Best practice for referential integrity:**
1. Generate parent table (e.g., customers)
2. Write to Delta table
3. Read back for FK lookup joins
4. Generate child tables (e.g., orders, tickets) with valid FKs
5. Write child tables to Delta

---

### Serverless job fails to start

**Possible causes:**
1. Workspace doesn't have serverless enabled
2. Unity Catalog permissions missing
3. Invalid environment configuration

**Solutions:**
```python
# Verify serverless is available
# Try creating a simple job first to test

# Check Unity Catalog permissions
spark.sql("SELECT current_catalog(), current_schema()")
```

### Classic cluster startup slow (3-8 minutes)

**Problem:** Clusters take time to start.

**Solution:** Switch to serverless:

```python
# Instead of:
# spark = DatabricksSession.builder.clusterId("xxx").getOrCreate()

# Use:
spark = DatabricksSession.builder.serverless(True).getOrCreate()
```

### "Either base environment or version must be provided"

**Problem:** Missing `client` in job environment spec.

**Solution:** Add `"client": "4"` to the spec:

```python
{
  "environments": [{
    "environment_key": "datagen_env",
    "spec": {
      "client": "4",  # Required!
      "dependencies": ["dbldatagen", "faker"]
    }
  }]
}
```

---

## Data Generation Issues

### AttributeError: 'function' object has no attribute 'partitionBy'

**Problem:** Using `F.window` instead of `Window` for analytical window functions.

```python
# WRONG - F.window is for time-based tumbling/sliding windows (streaming)
window_spec = F.window.partitionBy("account_id").orderBy("contact_id")
# Error: AttributeError: 'function' object has no attribute 'partitionBy'

# CORRECT - Window is for analytical window specifications
from pyspark.sql.window import Window
window_spec = Window.partitionBy("account_id").orderBy("contact_id")
```

**When to use Window:** For analytical functions like `row_number()`, `rank()`, `lead()`, `lag()`:

```python
from pyspark.sql.window import Window

# Mark first contact per account as primary
window_spec = Window.partitionBy("account_id").orderBy("contact_id")
contacts_df = contacts_df.withColumn(
    "is_primary",
    F.row_number().over(window_spec) == 1
)
```

---

### Generation is slow

**Problem:** Row-by-row Python UDFs (or driver loops) don't parallelize well.

**Solution:** Let dbldatagen generate columns declaratively — it builds the whole DataFrame in
parallel across `partitions`. Prefer `expr`, `template`, `values`/`weights`, and `distribution`
over UDFs. For names/addresses use the Faker plugin (`FakerTextFactory`) instead of hand-rolled UDFs:

```python
import dbldatagen as dg
from faker.providers import person

FakerText = dg.FakerTextFactory(locale=["en_US"], providers=[person])

spec = (
    dg.DataGenerator(spark, name="people", rows=1_000_000, partitions=64, randomSeed=42)
    .withColumn("name", "string", text=FakerText("name"))   # batched by dbldatagen
    .withColumn("status", "string", values=["active", "churned"], weights=[85, 15], random=True)
)
df = spec.build()
```

### Out of memory with large data

**Problem:** Not enough partitions for data size.

**Solution:** Increase `partitions` on the generator:

```python
# For large datasets (1M+ rows)
spec = dg.DataGenerator(spark, name="big", rows=N_CUSTOMERS, partitions=64, randomSeed=42)
```

| Data Size | Recommended Partitions |
|-----------|----------------------|
| < 100K | 8 |
| 100K - 500K | 16 |
| 500K - 1M | 32 |
| 1M+ | 64+ |

### Context corrupted on classic cluster

**Problem:** Stale execution context.

**Solution:** Create fresh context (omit context_id), reinstall libraries:

```python
# Don't reuse context_id if you see strange errors
# Let it create a new context
```

### Referential integrity violations

**Problem:** Foreign keys reference non-existent parent records.

**Solution:** Sample the FK from the parent's surrogate-key range, write the parent
to Delta, then read it back for joins:

```python
# 1. Generate and WRITE parent table (do NOT use cache with serverless!)
customers_df = (
    dg.DataGenerator(spark, name="customers", rows=N_CUSTOMERS, partitions=8, randomSeed=42)
    .withColumn("customer_sk", "long", expr="id")   # References the built-in sequential 'id' column
    .withColumn("tier", "string", values=["Free", "Pro", "Enterprise"], weights=[60, 30, 10], random=True)
    .build()
)
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 2. Read back for FK lookups
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers").select("customer_sk", "tier")

# 3. Generate child table with FK in the valid parent key range
orders_df = (
    dg.DataGenerator(spark, name="orders", rows=N_ORDERS, partitions=16, randomSeed=42)
    .withColumn("customer_sk", "long", minValue=0, maxValue=N_CUSTOMERS - 1, random=True)
    .build()
    .join(customer_lookup, on="customer_sk", how="inner")
)
```

> **WARNING:** Do NOT use `.cache()` or `.persist()` with serverless compute. See the dedicated section above.

---

## Data Quality Issues

### Uniform distributions (unrealistic)

**Problem:** All customers have similar order counts, amounts are evenly distributed.

**Solution:** Apply a `distribution=` to the column instead of leaving it uniform:

```python
import dbldatagen.distributions as dist

# BAD - uniform (no distribution)
.withColumn("amount", "double", minValue=10, maxValue=1000, random=True)

# GOOD - skewed, realistic
.withColumn("amount", "double", minValue=10, maxValue=1000, random=True,
            distribution=dist.Gamma(1.0, 2.0))
```

### Missing time-based patterns

**Problem:** Data doesn't reflect weekday/weekend or seasonal patterns.

**Solution:** Weight time buckets so volume clusters realistically, then derive the timestamp:

```python
# Cluster events into business hours
.withColumn("hour", "int", values=list(range(24)),
            weights=[1,1,1,1,1,1,2,4,8,10,10,9,8,9,10,9,7,5,3,2,2,1,1,1],
            random=True, omit=True)
.withColumn("event_ts", "timestamp", baseColumn="hour",
            expr="date'2025-06-01' + make_interval(0,0,0,0,hour,0,0)")
```

For weekend/holiday dips, weight a day-of-week or day bucket the same way, or post-filter the built
DataFrame with a Spark `expr` (e.g. `dayofweek(event_ts) IN (1,7)`).

### Incoherent row attributes

**Problem:** Enterprise customer has low-value orders, critical ticket has slow resolution.

**Solution:** Correlate attributes with `baseColumn` + `expr` so each derives from the previous:

```python
# Priority based on tier
.withColumn("priority", "string", baseColumn="tier",
            expr="CASE WHEN tier='Enterprise' THEN (CASE WHEN rand()<0.4 THEN 'Critical' ELSE 'High' END) "
                 "ELSE (CASE WHEN rand()<0.6 THEN 'Medium' ELSE 'Low' END) END")
# Resolution scaled by priority
.withColumn("resolution_hours", "double", baseColumn="priority",
            expr="round(CASE priority WHEN 'Critical' THEN rand()*4 WHEN 'High' THEN rand()*12 "
                 "WHEN 'Medium' THEN rand()*36 ELSE rand()*72 END, 1)")
```

---

## Validation Steps

After generation, validate using SQL queries via Databricks CLI:

```bash
# Set your warehouse ID
WAREHOUSE_ID="your-warehouse-id"
VOLUME_PATH="/Volumes/CATALOG/SCHEMA/raw_data"

# 1. Check row counts
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT 'customers' as table_name, COUNT(*) as row_count FROM parquet.\`${VOLUME_PATH}/customers\`
UNION ALL
SELECT 'orders', COUNT(*) FROM parquet.\`${VOLUME_PATH}/orders\`
"

# 2. Preview schema and sample data
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
DESCRIBE SELECT * FROM parquet.\`${VOLUME_PATH}/customers\`
"

databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT * FROM parquet.\`${VOLUME_PATH}/customers\` LIMIT 5
"

# 3. Verify distributions
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT tier, COUNT(*) as count, ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) as pct
FROM parquet.\`${VOLUME_PATH}/customers\`
GROUP BY tier ORDER BY tier
"

# 4. Check amount statistics
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT
  MIN(amount) as min_amount,
  MAX(amount) as max_amount,
  ROUND(AVG(amount), 2) as avg_amount,
  ROUND(STDDEV(amount), 2) as stddev_amount
FROM parquet.\`${VOLUME_PATH}/orders\`
"

# 5. Check referential integrity
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT COUNT(*) as orphan_orders
FROM parquet.\`${VOLUME_PATH}/orders\` o
LEFT JOIN parquet.\`${VOLUME_PATH}/customers\` c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL
"

# 6. Verify date range
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT MIN(order_date) as min_date, MAX(order_date) as max_date
FROM parquet.\`${VOLUME_PATH}/orders\`
"
```
