---
name: databricks-synthetic-data-gen
description: "Generate realistic synthetic data using Spark + dbldatagen (Databricks Labs Data Generator, strongly recommended). Supports serverless execution, multiple output formats (Parquet/JSON/CSV/Delta), and scales from thousands to millions of rows. For small datasets (<10K rows), can optionally generate locally and upload to volumes. Use when user mentions 'synthetic data', 'test data', 'generate data', 'demo dataset', 'dbldatagen', or 'sample data'."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

> Catalog and schema are **always user-supplied** — never default to any value. If the user hasn't provided them, ask. For any UC write, **always create the schema if it doesn't exist** before writing data.

# Databricks Synthetic Data Generation

Generate realistic, story-driven synthetic data for Databricks using **Spark + [dbldatagen](https://databrickslabs.github.io/dbldatagen/public_docs/index.html)** (the Databricks Labs Data Generator — strongly recommended).

> **Use the public `dbldatagen` API.** Import the top-level package (`import dbldatagen as dg`) and its public submodules (`dbldatagen.distributions`, `dbldatagen.constraints`). Everything below is built from the public API.

## Data Must Tell a Business Story

Synthetic data should demonstrate how Databricks helps solve real business problems.

**The pattern:** Something goes wrong → business impact ($) → analyze root cause → identify affected customers → fix and prevent.

**Key principles:**
- **Problem → Impact → Analysis → Solution** — Include an incident, anomaly, or issue that causes measurable business impact. The data lets you find the root cause and act on it.
- **Industry-relevant but simple** — Use domain terms (e.g., "SLA breach", "churn", "stockout") but keep the schema easy to understand. A few tables, clear relationships.
- **Business metrics with $ impact** — Revenue, MRR, cost, conversion rate. Every story needs a dollar sign to show why it matters.
- **Tables explain each other** — Ticket spike? Incident table shows the outage. Revenue drop? Churn table shows who left and why. All data connects.
- **Actionable insights** — Data should answer: What happened? Who's affected? How much did it cost? How do we prevent it?

**Why no flat distributions:** Uniform data has no story — no spikes, no anomalies, no cohort, no 20/80, no skew, nothing to investigate. It can't show Databricks' value for root cause analysis.

## References

| When | Guide |
|------|-------|
| User mentions **ML model training** or complex time patterns | [references/1-data-patterns.md](references/1-data-patterns.md) — ML-ready data, time multipliers, row coherence |
| Errors during generation | [references/2-troubleshooting.md](references/2-troubleshooting.md) — Fixing common issues |

## Critical Rules

1. **Data tells a story** — Something goes wrong, impacts $, can be analyzed and fixed. Show Databricks value.
2. **All data serves the story** — Every table and column must be coherent and usable in dashboards or ML models. No orphan data, no random noise — if it doesn't help explain or plot a futur dashboard or predict, don't generate it.
3. **Industry terms, simple schema** — Use domain-specific vocabulary but keep it easy to understand (few tables, clear relationships)
4. **Never uniform distributions** — Skewed categories, log-normal amounts, 80/20 patterns. Flat = no story = useless
5. **Enough data for trends** — ~100K+ rows for main tables so patterns survive aggregation
6. **Ask for catalog/schema** — Never default, always confirm before generating
7. **Present plan for approval** — Show tables, distributions, assumptions before writing code
8. **Parent tables first** — Generate parent tables, write to Delta, then create children with valid FKs
9. **Use Spark + dbldatagen** — Scalable, parallel, declarative. Build a `dg.DataGenerator` spec and `.build()` it into a Spark DataFrame. Use a `pandas_udf` only for logic dbldatagen can't express
10. **Use Databricks Connect Serverless by default to generate data** — Update databricks-connect on python 3.12 if required (avoid using execute_code unless instructed to not use Databricks Connect)
11. **No `.cache()` or `.persist()`** — Not supported on serverless. Write to Delta, read back for joins
12. **No Python loops or `.collect()`** — Use Spark parallelism and dbldatagen specs. No driver-side iteration, avoid Pandas↔Spark conversions

## Generation Planning Workflow

**Before generating any code, you MUST present a plan for user approval.**

### ⚠️ MUST DO: Confirm Catalog Before Proceeding

**You MUST explicitly ask the user which catalog to use.** Do not assume or proceed without confirmation.

Example prompt to user:
> "Which Unity Catalog should I use for this data?"

When presenting your plan, always show the selected catalog prominently:
```
📍 Output Location: catalog_name.schema_name
   Volume: /Volumes/catalog_name/schema_name/raw_data/
```

This makes it easy for the user to spot and correct if needed.

### Step 1: Gather Requirements

Ask the user about:
- **Catalog/Schema** — Which catalog to use?
- **Domain** — E-commerce, support tickets, IoT, financial? (Use industry terms)

**If user doesn't specify a story:** Propose one. Don't generate bland data — suggest an incident, anomaly, or trend that shows Databricks value (e.g., "I'll include a system outage that causes ticket spike and churn — this lets you demo root cause analysis").

### Step 2: Present Plan with Story

Show a clear specification with **the business story and your assumptions surfaced**:

```
📍 Output Location: {user_catalog}.support_demo
   Volume: /Volumes/{user_catalog}/support_demo/raw_data/

📖 Story: A payment system outage causes support ticket spike. Resolution times
   degrade, enterprise customers churn, revenue drops $2.3M. With Databricks we
   identify the root cause, affected customers, and prevent future impact.
```

| Table | Description | Rows | Key Assumptions |
|-------|-------------|------|-----------------|
| customers | Customer profiles with tier, MRR | 10,000 | Enterprise 10% but 60% of revenue |
| tickets | Support tickets with priority, resolution_time | 80,000 | Spike during outage, SLA breaches |
| incidents | System events (outages, deployments) | 50 | Payment outage mid-month |
| churn_events | Customer cancellations with reason | 500 | Spike after poor support experience |

**Business metrics:**
- `customers.mrr` — Revenue at risk ($)
- `tickets.resolution_hours` — SLA performance
- `churn_events.lost_mrr` — Churn impact ($)

**The story this data tells:**
- Incident table shows payment outage on March 15
- Tickets spike 5x during outage, resolution time degrades from 4h → 18h
- Enterprise customers with SLA breaches churn 3 weeks later
- Total impact: $2.3M lost MRR, traceable to one incident
- **Databricks value:** Root cause analysis, identify at-risk customers, build alerting

**Ask user**: "Does this story work? Any adjustments?"

### Step 3: Ask About Data Features

- [x] Skew (non-uniform distributions) - **Enabled by default**
- [x] Joins (referential integrity) - **Enabled by default**
- [ ] Bad data injection (for data quality testing)
- [ ] Multi-language text
- [ ] Incremental mode (append instead of overwrite)

### Pre-Generation Checklist

- [ ] **Catalog confirmed** - User explicitly approved which catalog to use
- [ ] Output location shown prominently in plan (easy to spot/change)
- [ ] Table specification shown and approved
- [ ] Assumptions about distributions confirmed
- [ ] User confirmed compute preference (Databricks Connect on serverless recommended)
- [ ] Data features selected

**Do NOT proceed to code generation until user approves the plan, including the catalog.**

### Post-Generation Validation

Use `databricks experimental aitools tools query` to validate generated data (row counts, distributions, referential integrity). Query parquet files directly:

```bash
databricks experimental aitools tools query --warehouse $WAREHOUSE_ID "
SELECT COUNT(*) FROM parquet.\`/Volumes/CATALOG/SCHEMA/raw_data/customers\`
"
```

See [references/2-troubleshooting.md](references/2-troubleshooting.md) for full validation examples.

## Use Databricks Connect + dbldatagen Pattern

A `DataGenerator` spec declares each column; `.build()` returns a Spark DataFrame. No UDFs, no driver loops — generation is fully distributed across `partitions`. Install `dbldatagen` and `faker` locally first (see Setup).

```python
from databricks.connect import DatabricksSession
import dbldatagen as dg
import dbldatagen.distributions as dist
from faker.providers import company, person  # providers we draw from

# Setup serverless Spark session (deps installed locally)
spark = DatabricksSession.builder.serverless(True).getOrCreate()

CATALOG, SCHEMA = "<YOUR_CATALOG>", "<YOUR_SCHEMA>"  # always user-supplied
N_CUSTOMERS = 10_000

# One shared Faker text factory: default locale + the providers we use.
# The factory builds the Faker instance internally (no `from faker import Faker` needed).
FakerText = dg.FakerTextFactory(locale=["en_US"], providers=[person, company])

customers = (
    dg.DataGenerator(spark, name="customers", rows=N_CUSTOMERS, partitions=8,
                     randomSeed=42, randomSeedMethod="hash_fieldname")
    # surrogate key 0..N-1 (the implicit contiguous seed column) — drives FK joins
    .withColumn("customer_sk", "long", expr="id")
    # business key derived from the surrogate
    .withColumn("customer_id", "string", baseColumn="customer_sk",
                expr="concat('CUST-', lpad(cast(customer_sk as string), 5, '0'))")
    # realistic text via the shared Faker provider factory
    .withColumn("name", "string", text=FakerText("name"))
    .withColumn("company", "string", text=FakerText("company"))
    # email derived from the generated name (name as base column)
    .withColumn("email", "string", baseColumn="name",
                expr="concat(lower(replace(name, ' ', '.')), '@example.com')")
    # skewed categories — NEVER uniform (weights are relative)
    .withColumn("tier", "string", values=["Free", "Pro", "Enterprise"],
                weights=[60, 30, 10], random=True)
    .withColumn("region", "string", values=["North", "South", "East", "West"],
                weights=[40, 25, 20, 15], random=True)
    # right-skewed ARR correlated to tier: log-normal = exp() of a standard normal.
    # The hidden helper column (_z, omit=True) is computed and reusable as a base column.
    .withColumn("_z", "double", minValue=-1, maxValue=1, random=True,
                distribution=dist.Normal(0.0, 1.0), omit=True)
    .withColumn("arr", "double", baseColumn=["tier", "_z"],
                expr="round(CASE tier WHEN 'Enterprise' THEN exp(7.5 + 0.8 * _z) "
                     "WHEN 'Pro' THEN exp(5.5 + 0.7 * _z) ELSE exp(4.0 + 0.6 * _z) END, 2)")
    .withColumn("created_at", "date",
                data_range=dg.DateRange("2023-01-01 00:00:00", "2024-12-31 00:00:00", "days=1"),
                random=True)
)
customers_df = customers.build()

# Write to Volume as Parquet (default for raw data)
# Path is a folder with table name: /Volumes/catalog/schema/raw_data/customers/
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
customers_df.write.mode("overwrite").parquet(f"/Volumes/{CATALOG}/{SCHEMA}/raw_data/customers")
```

**Partitions by scale:** `dg.DataGenerator(..., rows=N, partitions=P)`
- <100K rows: 8 partitions
- 100K-500K: 16 partitions
- 500K-1M: 32 partitions
- 1M+: 64+ partitions

**Output formats:**
- **Parquet to Volume** (default): `df.write.parquet("/Volumes/.../raw_data/table")` — raw data for pipelines
- **Delta Table**: `df.write.saveAsTable("catalog.schema.table")` — if user wants queryable tables
- **JSON/CSV**: small dimension tables, replicate legacy systems

## Performance Rules

Generated scripts must be highly performant. **Never** do these:

| Anti-Pattern | Why It's Slow | Do This Instead |
|--------------|---------------|-----------------|
| Python loops on driver | Single-threaded, no parallelism | Declare columns in a `dg.DataGenerator` spec and `.build()` |
| `.collect()` then iterate | Brings all data to driver memory | Keep data in Spark, use DataFrame ops |
| Pandas → Spark → Pandas | Serialization overhead, defeats distribution | Stay in Spark; let dbldatagen generate columns |
| Read/write temp files | Unnecessary I/O | Chain DataFrame transformations |
| Scalar UDFs | Row-by-row processing | Use dbldatagen `expr`/`template`/`text`; `pandas_udf` only when unavoidable |

**Good pattern:** `dg.DataGenerator(rows, partitions)` → declarative `.withColumn(...)` specs → `.build()` → write directly

## Common Patterns

All snippets use the public `dbldatagen` API (`import dbldatagen as dg`, `import dbldatagen.distributions as dist`).

### Weighted Categories (never uniform)
`weights` are relative frequencies — they don't need to sum to 100:
```python
.withColumn("tier", "string", values=["Free", "Pro", "Enterprise"],
            weights=[60, 30, 10], random=True)
```

### Skewed / Long-Tailed Amounts
Apply a continuous distribution to a numeric range — `Gamma`/`Exponential` give the always-positive long tail you'd want from log-normal:
```python
.withColumn("order_amount", "decimal(10,2)", minValue=5, maxValue=25_000,
            random=True, distribution=dist.Gamma(1.0, 2.0))
```
For a true log-normal, generate over a normal and exponentiate via `expr`:
```python
.withColumn("amount", "double", minValue=-1, maxValue=1, random=True,
            distribution=dist.Normal(0.0, 1.0), omit=True)        # standard normal, hidden
.withColumn("arr", "double", baseColumn="amount",
            expr="round(exp(5.5 + 0.8 * amount), 2)")             # median ~$245
```

### Coherent Rows (correlated attributes via `expr` + `baseColumn`)
Derive dependent columns from earlier ones so each row makes business sense — no UDF needed:
```python
.withColumn("priority", "string", values=["Critical", "High", "Medium", "Low"],
            weights=[5, 15, 50, 30], random=True)
.withColumn("resolution_hours", "double", baseColumn="priority",
            expr="round(CASE priority WHEN 'Critical' THEN rand()*8 "
                 "WHEN 'High' THEN rand()*24 WHEN 'Medium' THEN rand()*72 "
                 "ELSE rand()*120 END, 1)")
.withColumn("csat", "int", baseColumn="resolution_hours",
            expr="CASE WHEN resolution_hours<4 THEN 5 WHEN resolution_hours<24 THEN 4 "
                 "WHEN resolution_hours<72 THEN 3 ELSE 2 END")
```

### Date / Timestamp Range (Last 6 Months)
Use `dg.DateRange(begin, end, interval)` with the `data_range` option:
```python
from datetime import datetime, timedelta
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)
FMT = "%Y-%m-%d %H:%M:%S"

.withColumn("order_ts", "timestamp",
            data_range=dg.DateRange(START_DATE.strftime(FMT), END_DATE.strftime(FMT), "minutes=30"),
            random=True)
```

### Realistic Text (Faker provider plugin)
Build one `FakerTextFactory` with a default locale and the faker providers you need, then reuse it:
```python
from faker.providers import person, company, internet
FakerText = dg.FakerTextFactory(locale=["en_US"], providers=[person, company, internet])

.withColumn("name", "string", text=FakerText("name"))  # uses the 'person' provider
.withColumn("company", "string", text=FakerText("company"))  # uses the 'company' provider
.withColumn("ip", "string", text=FakerText("ipv4_private"))  # uses the 'internet' provider
```
dbldatagen alternatives that need no library: 
* `template=r"\w.\w@\w.com"` (templated text)
* `text=dg.ILText(paragraphs=(1, 3), sentences=(2, 5))` (lorem-ipsum free text).

### Infrastructure (always create in script)
```python
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

### Referential Integrity (FK pattern)
Generate the FK as an integer over the parent's surrogate-key range so **every value is valid by construction**, then write the parent to Delta and read it back to attach coherent parent attributes (no `.cache()` on serverless):
```python
# 1. Parent table: surrogate key 0..N-1, then write to Delta
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")

# 2. Child table: FK drawn from the parent key range (valid by construction).
#    A distribution skews it 80/20 (a few customers place most orders).
orders_df = (
    dg.DataGenerator(spark, name="orders", rows=N_ORDERS, partitions=16, randomSeed=42)
    .withColumn("order_id", "string",
                expr="concat('ORD-', lpad(cast(id as string), 8, '0'))", baseColumn="id")
    .withColumn("customer_sk", "long", minValue=0, maxValue=N_CUSTOMERS - 1,
                random=True, distribution=dist.Gamma(0.4, 1.0))
    .build()
)

# 3. Join to the parent (read back from Delta) to pull coherent parent attributes
customer_lookup = spark.table(f"{CATALOG}.{SCHEMA}.customers").select("customer_sk", "customer_id", "tier")
orders_with_fk = orders_df.join(customer_lookup, on="customer_sk", how="inner")
```

## Setup

Requires Python 3.12 and databricks-connect>=16.4. Install dependencies locally with `uv`:

```bash
uv pip install "databricks-connect>=16.4,<17.4" dbldatagen faker
```

## Related Skills

- **databricks-unity-catalog** — Managing catalogs, schemas, and volumes
- **databricks-dabs** — DABs for production deployment

## Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: dbldatagen` (or `faker`) | Install locally: `uv pip install dbldatagen faker` |
| `FakerText`/provider not found | Pass the provider to `dg.FakerTextFactory(providers=[...])` and import it from `faker.providers` |
| All rows identical / not random | Set `random=True` on the column (default is deterministic), or set `randomSeed`/`randomSeedMethod` on the generator |
| Out of memory | Increase `partitions` in `dg.DataGenerator(..., partitions=P)` |
| Referential integrity errors | Draw the FK from the parent key range (`minValue=0, maxValue=N-1`); write parent to Delta first, read back to join attributes |
| `PERSIST TABLE is not supported on serverless` | **NEVER use `.cache()` or `.persist()` with serverless** - write to Delta table first, then read back |
| `F.window` vs `Window` confusion | Use `from pyspark.sql.window import Window` for `row_number()`, `rank()`, etc. `F.window` is for streaming only. |
| Broadcast variables not supported | **NEVER use `spark.sparkContext.broadcast()` with serverless** |

See [references/2-troubleshooting.md](references/2-troubleshooting.md) for full troubleshooting guide.
