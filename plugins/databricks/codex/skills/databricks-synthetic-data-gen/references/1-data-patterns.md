# Data Patterns Guide

Creating realistic synthetic data that tells a story.

> **Note:** This guide provides principles and simplified examples. Actual implementations should be more sophisticated — use domain-specific distributions, realistic business rules, and correlations that reflect the user's actual use case. Ask clarifying questions to understand the business context before generating.

## Core Principles

### 1. Data Must Be Interesting

Synthetic data should reveal patterns humans can see in dashboards and ML models can learn from:

- **Visible trends** — Revenue growth, seasonal spikes, degradation over time
- **Actionable segments** — Clear differences between customer tiers, regions, product categories
- **Anomalies to detect** — Fraud patterns, equipment failures, churn signals
- **Correlations to discover** — Higher tier = more spend, faster resolution = better CSAT

**Anti-pattern:** Uniform random data with no story — useless for demos and ML.

### 2. Non-Uniform Distributions

Real data is never uniformly distributed. Use appropriate distributions:

| Distribution | When to Use | Examples |
|--------------|-------------|----------|
| **Log-normal** | Monetary values, sizes | Order amounts, salaries, file sizes |
| **Pareto (80/20)** | Popularity, wealth | 20% of customers = 80% of revenue |
| **Exponential** | Time between events | Support resolution time, session duration |
| **Weighted categorical** | Skewed categories | Status (70% complete, 5% failed), tiers |

dbldatagen applies a distribution to a column's random draw via the `distribution=` option
(`import dbldatagen.distributions as dist`). Supported: `Normal`, `Gamma`, `Beta`, `Exponential`.

```python
import dbldatagen as dg
import dbldatagen.distributions as dist

spec = (
    dg.DataGenerator(spark, name="amounts", rows=100_000, partitions=8, randomSeed=42)
    # Use Gamma for right-tailed distributions like amounts
    .withColumn("order_amount", "decimal(10,2)", minValue=5, maxValue=25_000,
                random=True, distribution=dist.Gamma(1.0, 2.0))
    # Use Exponential for waiting times
    .withColumn("resolution_hours", "double", minValue=0, maxValue=240,
                random=True, distribution=dist.Exponential(rate=1.0 / 24))
)

# Exponentiate a standard normal via expr for true log-normal distributions
spec = (
    dg.DataGenerator(spark, name="ln", rows=100_000, partitions=8, randomSeed=42)
    .withColumn("_z", "double", minValue=-1, maxValue=1, random=True,
                distribution=dist.Normal(0.0, 1.0), omit=True)   # hidden helper column
    .withColumn("amount", "double", baseColumn="_z",
                expr="round(exp(5.5 + 0.8 * _z), 2)")            # ~$245 median
)
```

### 3. Row Coherence

Attributes within a row must make business sense together. Generate correlated attributes in a single UDF for example:

| If This... | Then This... |
|------------|--------------|
| Enterprise tier | Higher order amounts, more activity, priority support |
| Critical priority | Faster resolution, more interactions |
| Older equipment | Higher failure rate, more anomalies |
| Large transaction + unusual hour | Higher fraud probability |
| Fast resolution | Higher CSAT score |

In dbldatagen, chain `baseColumn` + `expr` when columns derive from other columns 
in the same dataset. The generator resolves the dependency order automatically:

```python
spec = (
    dg.DataGenerator(spark, name="tickets", rows=80_000, partitions=8, randomSeed=42)
    .withColumn("tier", "string", values=["Free", "Pro", "Enterprise"],
                weights=[60, 30, 10], random=True)
    # Priority depends on tier
    .withColumn("priority", "string", baseColumn="tier",
                expr="CASE WHEN tier='Enterprise' AND rand()<0.3 THEN 'Critical' ELSE 'Medium' END")
    # Resolution depends on priority
    .withColumn("resolution_hours", "double", baseColumn="priority",
                expr="round(CASE priority WHEN 'Critical' THEN rand()*4 ELSE rand()*36 END, 1)")
    # CSAT depends on resolution
    .withColumn("csat", "int", baseColumn="resolution_hours",
                expr="CASE WHEN resolution_hours<4 THEN 5 WHEN resolution_hours<24 THEN 3 ELSE 2 END")
)
```

### 4. The 80/20 Rule

Apply power-law distributions where appropriate:

- **20% of customers** generate 80% of orders/revenue
- **20% of products** account for 80% of sales
- **20% of support agents** handle 80% of tickets

Implementation: Skew FKs by drawing from a non-uniform distribution.

```python
# Use a Gamma distribution to skew FK values
.withColumn("customer_sk", "long", minValue=0, maxValue=N_CUSTOMERS - 1,
            random=True, distribution=dist.Gamma(0.4, 1.0))
```

### 5. Time-Based Patterns

Most data has temporal patterns:

- **Weekday vs weekend** — B2B drops on weekends, B2C peaks
- **Business hours** — Support tickets cluster 9am-5pm
- **Seasonality** — Q4 retail spike, summer travel peak
- **Trends** — Growth over time, degradation curves

Bias *when* events happen by weighting time buckets, then derive the timestamp from the bucket.
The example below clusters tickets into business hours and skews volume toward weekdays:

```python
.withColumn("hour", "int", values=list(range(24)),
            weights=[1,1,1,1,1,1,2,4,8,10,10,9,8,9,10,9,7,5,3,2,2,1,1,1],  # 9am–5pm peak
            random=True, omit=True)
.withColumn("day_offset", "int", minValue=0, maxValue=179, random=True,
            distribution=dist.Normal(60, 30), omit=True)  # volume ramps over the window
.withColumn("event_ts", "timestamp", baseColumn=["day_offset", "hour"],
            expr="date_add(timestamp'2025-01-01 00:00:00', day_offset) + make_interval(0,0,0,0,hour,0,0)")
```

For holiday/seasonal spikes, weight a month or week-of-year bucket the same way, or post-filter
the built DataFrame with a Spark `expr` multiplier.

### 6. ML-Ready Data

If data will train ML models, ensure:

- **Signal exists** — The patterns you want the model to learn are present
- **Noise is realistic** — Not too clean (overfitting) or too noisy (unlearnable)
- **Class balance** — Fraud at 0.1-1%, not 50/50 (unrealistic)
- **Temporal validity** — Train/test split respects time (no future leakage)

## Referential Integrity

Give the parent a surrogate key over `0..N-1`, draw the child's FK from that same range (valid by
construction), then write the parent to Delta and read it back to attach parent attributes:

```python
# 1. # 1. Generate and write parent table with surrogate keys from 0..N-1
customers_df = (
    dg.DataGenerator(spark, name="customers", rows=N_CUSTOMERS, partitions=8, randomSeed=42)
    .withColumn("customer_id", "string", baseColumn="id",  # References the built-in sequential 'id' column
                expr="concat('CUST-', lpad(cast(id as string), 5, '0'))")
    # ... other attributes ...
    .build()
)
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 2. Read back for FK joins (NOT cache - unsupported on serverless)
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers").select("customer_id", "tier")

# 3. Generate child table with FKs drawn from the parent key range
orders_df = (
    dg.DataGenerator(spark, name="orders", rows=N_ORDERS, partitions=16, randomSeed=42)
    .withColumn("customer_sk", "long", minValue=0, maxValue=N_CUSTOMERS - 1, random=True, omit=True)
    .withColumn("customer_id", "string", baseColumn="customer_sk",  # References the 'customer_sk' column
                expr="concat('CUST-', lpad(cast(customer_sk as string), 5, '0'))")
    .build()
)
orders_with_fk = orders_df.join(customer_lookup, on="customer_id", how="inner")
```

## Data Volume

Generate enough rows so patterns survive aggregation:

| Analysis Type | Minimum Rows | Rationale |
|---------------|--------------|-----------|
| Daily dashboard | 50-100/day | Trends visible after weekly rollup |
| Category comparison | 500+ per category | Statistical significance |
| ML training | 10K-100K+ | Enough signal for model learning |
| Customer-level | 5-20 events/customer | Individual patterns visible |

**Rule of thumb:** If you'll GROUP BY a column, ensure each group has 100+ rows.

---

## Remember

These are guiding principles, not templates. Real implementations should:
- Reflect the user's specific business domain and terminology
- Use realistic parameter values (research typical ranges for the industry)
- Include edge cases relevant to the use case (returns, cancellations, failures)
- Have more complex correlations than shown in examples above
- **Never use flat/uniform distributions** — categories, tiers, regions, statuses should always be skewed (e.g., 60/30/10 not 33/33/33)
