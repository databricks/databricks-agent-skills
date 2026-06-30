"""Generate synthetic data using Spark + dbldatagen (Databricks Labs Data Generator).

This is the recommended approach for ALL data generation tasks:
- Scales from thousands to millions of rows
- Declarative, parallel generation (no driver loops, no row-by-row UDFs)
- Direct write to Unity Catalog
- Works with serverless and classic compute

Uses ONLY the public dbldatagen API:
- `dbldatagen.DataGenerator` / `.withColumn(...)` / `.build()`
- `dbldatagen.distributions` for skew
- `dbldatagen.FakerTextFactory` for realistic names/companies/addresses

Prerequisites:
- Install dependencies locally: uv pip install dbldatagen faker databricks-connect
- Configure ~/.databrickscfg with serverless_compute_id = auto
"""
import sys
import os
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from datetime import datetime, timedelta

# =============================================================================
# CONFIGURATION
# =============================================================================
# Compute - Serverless strongly recommended
USE_SERVERLESS = True  # Set to False and provide CLUSTER_ID for classic compute
CLUSTER_ID = None  # Only used if USE_SERVERLESS=False

# Storage - Update these for your environment
CATALOG = "<YOUR_CATALOG>"  # REQUIRED: replace with your catalog
SCHEMA = "<YOUR_SCHEMA>"  # REQUIRED: replace with your schema
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Data sizes
N_CUSTOMERS = 10_000
N_ORDERS = 50_000
PARTITIONS = 16  # Adjust: 8 for <100K, 32 for 1M+

# Date range - last 6 months from today
END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=180)
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# Write mode - "overwrite" for one-time, "append" for incremental
WRITE_MODE = "overwrite"

# Bad data injection for testing data quality rules
INJECT_BAD_DATA = False  # Set to True to inject bad data
BAD_DATA_CONFIG = {
    "null_rate": 0.02,           # 2% nulls in required fields
    "outlier_rate": 0.01,        # 1% impossible values
    "orphan_fk_rate": 0.01,      # 1% orphan foreign keys
}

# Reproducibility - same seed => same data
SEED = 42

# Tier distribution: Free 60%, Pro 30%, Enterprise 10% (relative weights)
TIER_WEIGHTS = [60, 30, 10]

# Region distribution (relative weights)
REGION_WEIGHTS = [40, 25, 20, 15]

# Order status distribution (relative weights)
STATUS_VALUES = ["delivered", "shipped", "processing", "pending", "cancelled"]
STATUS_WEIGHTS = [65, 15, 10, 5, 5]

# =============================================================================
# SESSION CREATION
# =============================================================================

from databricks.connect import DatabricksSession

print("=" * 80)
print("CREATING SPARK SESSION")
print("=" * 80)

if USE_SERVERLESS:
    spark = DatabricksSession.builder.serverless(True).getOrCreate()
    print("Connected to serverless compute")
else:
    if not CLUSTER_ID:
        raise ValueError("CLUSTER_ID must be set when USE_SERVERLESS=False")
    spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
    print(f"Connected to cluster {CLUSTER_ID}")

# Import the public dbldatagen API (installed locally)
import dbldatagen as dg
import dbldatagen.distributions as dist
from faker.providers import person, company, address as faker_address

# One shared Faker text factory: default locale + the providers we use.
# The factory builds the Faker instance internally (no `from faker import Faker` needed).
FakerText = dg.FakerTextFactory(locale=["en_US"], providers=[person, company, faker_address])

# =============================================================================
# CREATE INFRASTRUCTURE
# =============================================================================
print("\nCreating infrastructure...")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
print(f"Infrastructure ready: {VOLUME_PATH}")

# =============================================================================
# GENERATE CUSTOMERS (Parent Table)
# =============================================================================
print(f"\nGenerating {N_CUSTOMERS:,} customers...")

customers_spec = (
    dg.DataGenerator(spark, name="customers", rows=N_CUSTOMERS, partitions=PARTITIONS,
                     randomSeed=SEED, randomSeedMethod="hash_fieldname")
    # Surrogate key 0..N-1 (the implicit contiguous seed column) — stable join key
    .withColumn("customer_sk", "long", expr="id")
    # Business key derived from the surrogate
    .withColumn("customer_id", "string", baseColumn="customer_sk",
                expr="concat('CUST-', lpad(cast(customer_sk as string), 5, '0'))")
    # Realistic text via the Faker provider factory
    .withColumn("name", "string", text=FakerText("name"))
    .withColumn("company", "string", text=FakerText("company"))
    .withColumn("address", "string", text=FakerText("address"))
    # Email derived from the generated name (name as base column)
    .withColumn("email", "string", baseColumn="name",
                expr="concat(lower(regexp_replace(name, '[^A-Za-z]+', '.')), '@example.com')")
    # Skewed categories (never uniform) — weights are relative frequencies
    .withColumn("tier", "string", values=["Free", "Pro", "Enterprise"],
                weights=TIER_WEIGHTS, random=True)
    .withColumn("region", "string", values=["North", "South", "East", "West"],
                weights=REGION_WEIGHTS, random=True)
    # Account created within 2 years before the analysis window
    .withColumn("created_at", "date",
                data_range=dg.DateRange(
                    (START_DATE - timedelta(days=730)).strftime(DATE_FMT),
                    START_DATE.strftime(DATE_FMT),
                    "days=1"),
                random=True)
    # Tier-based ARR via a log-normal (exp of a standard normal) — long tail, always positive.
    # The omitted helper column '_z' keeps ARR reproducible under randomSeed.
    # Enterprise ~ $1800, Pro ~ $245, Free ~ $55 median.
    .withColumn("_z", "double", minValue=-1, maxValue=1, random=True,
                distribution=dist.Normal(0.0, 1.0), omit=True)
    .withColumn("arr", "double", baseColumn=["tier", "_z"],
                expr="round(CASE tier WHEN 'Enterprise' THEN exp(7.5 + 0.8 * _z) "
                     "WHEN 'Pro' THEN exp(5.5 + 0.7 * _z) ELSE exp(4.0 + 0.6 * _z) END, 2)")
)

customers_df = customers_spec.build()

# Save customers as raw Parquet
customers_df.write.mode(WRITE_MODE).parquet(f"{VOLUME_PATH}/customers")
print(f"  Saved customers to {VOLUME_PATH}/customers")

# =============================================================================
# GENERATE ORDERS (Child Table with Referential Integrity)
# =============================================================================
print(f"\nGenerating {N_ORDERS:,} orders with referential integrity...")

# Write a customer lookup to a temp Delta table (no .cache() on serverless!)
customers_tmp_table = f"{CATALOG}.{SCHEMA}._tmp_customers_lookup"
(customers_df.select("customer_sk", "customer_id", "tier")
 .write.mode("overwrite").saveAsTable(customers_tmp_table))
customer_lookup = spark.table(customers_tmp_table)

# Generate orders. The FK (customer_sk) is drawn from the parent key range, so every
# value is valid by construction. A Gamma distribution skews it 80/20 (a few customers
# place most orders).
orders_spec = (
    dg.DataGenerator(spark, name="orders", rows=N_ORDERS, partitions=PARTITIONS,
                     randomSeed=SEED, randomSeedMethod="hash_fieldname")
    .withColumn("order_id", "string", baseColumn="id",
                expr="concat('ORD-', lpad(cast(id as string), 6, '0'))")
    .withColumn("customer_sk", "long", minValue=0, maxValue=N_CUSTOMERS - 1,
                random=True, distribution=dist.Gamma(0.4, 1.0))
    .withColumn("status", "string", values=STATUS_VALUES, weights=STATUS_WEIGHTS, random=True)
    .withColumn("order_date", "date",
                data_range=dg.DateRange(START_DATE.strftime(DATE_FMT),
                                        END_DATE.strftime(DATE_FMT), "days=1"),
                random=True)
)
orders_df = orders_spec.build()

# Join to the parent (read back from Delta) to attach valid customer_id + tier
orders_with_fk = orders_df.join(customer_lookup, on="customer_sk", how="inner")

# Tier-based amount (log-normal), coherent with the customer's tier
orders_with_fk = orders_with_fk.withColumn(
    "amount",
    F.round(
        F.expr(
            "CASE tier "
            "WHEN 'Enterprise' THEN exp(7.5 + 0.8 * randn()) "
            "WHEN 'Pro' THEN exp(5.5 + 0.7 * randn()) "
            "ELSE exp(4.0 + 0.6 * randn()) END"
        ),
        2,
    ),
)

# =============================================================================
# INJECT BAD DATA (OPTIONAL)
# =============================================================================
if INJECT_BAD_DATA:
    print("\nInjecting bad data for quality testing...")

    # Calculate counts
    null_count = int(N_ORDERS * BAD_DATA_CONFIG["null_rate"])
    outlier_count = int(N_ORDERS * BAD_DATA_CONFIG["outlier_rate"])
    orphan_count = int(N_ORDERS * BAD_DATA_CONFIG["orphan_fk_rate"])

    # Add a row number to target specific rows (no cache/persist on serverless)
    orders_with_fk = orders_with_fk.withColumn(
        "row_num",
        F.row_number().over(Window.orderBy(F.monotonically_increasing_id()))
    )

    # Inject nulls in customer_id for the first null_count rows
    orders_with_fk = orders_with_fk.withColumn(
        "customer_id",
        F.when(F.col("row_num") <= null_count, None).otherwise(F.col("customer_id"))
    )

    # Inject negative amounts for the next outlier_count rows
    orders_with_fk = orders_with_fk.withColumn(
        "amount",
        F.when(
            (F.col("row_num") > null_count) & (F.col("row_num") <= null_count + outlier_count),
            F.lit(-999.99)
        ).otherwise(F.col("amount"))
    )

    # Inject orphan FKs for the next orphan_count rows
    orders_with_fk = orders_with_fk.withColumn(
        "customer_id",
        F.when(
            (F.col("row_num") > null_count + outlier_count) &
            (F.col("row_num") <= null_count + outlier_count + orphan_count),
            F.lit("CUST-NONEXISTENT")
        ).otherwise(F.col("customer_id"))
    )

    orders_with_fk = orders_with_fk.drop("row_num")

    print(f"  Injected {null_count} null customer_ids")
    print(f"  Injected {outlier_count} negative amounts")
    print(f"  Injected {orphan_count} orphan foreign keys")

# Drop join-only columns (not needed in final output)
orders_final = orders_with_fk.drop("tier", "customer_sk")

# Save orders
orders_final.write.mode(WRITE_MODE).parquet(f"{VOLUME_PATH}/orders")
print(f"  Saved orders to {VOLUME_PATH}/orders")

# =============================================================================
# CLEANUP AND SUMMARY
# =============================================================================
spark.sql(f"DROP TABLE IF EXISTS {customers_tmp_table}")

print("\n" + "=" * 80)
print("GENERATION COMPLETE")
print("=" * 80)
print(f"Catalog: {CATALOG}")
print(f"Schema: {SCHEMA}")
print(f"Volume: {VOLUME_PATH}")
print(f"\nGenerated data:")
print(f"  - customers: {N_CUSTOMERS:,} rows")
print(f"  - orders: {N_ORDERS:,} rows")
if INJECT_BAD_DATA:
    print(f"  - Bad data injected: nulls, outliers, orphan FKs")
print(f"\nDate range: {START_DATE.date()} to {END_DATE.date()}")
print("=" * 80)
