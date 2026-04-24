# Code Patterns Reference

Complete before/after code examples for every migration pattern from classic compute to serverless compute.

## RDD to DataFrame

All RDD APIs and `sc.*` methods are not supported on serverless (which uses the Spark Connect architecture). Replace with DataFrame operations.

### sc.parallelize

```python
# BEFORE:
rdd = sc.parallelize([1, 2, 3, 4, 5])
result = rdd.collect()

# AFTER:
df = spark.createDataFrame([(i,) for i in [1, 2, 3, 4, 5]], ["value"])
result = df.collect()
```

### rdd.map

```python
# BEFORE:
rdd = sc.parallelize([1, 2, 3])
mapped = rdd.map(lambda x: x * 2).collect()

# AFTER:
from pyspark.sql import functions as F
df = spark.createDataFrame([(1,), (2,), (3,)], ["value"])
result = df.select((F.col("value") * 2).alias("value")).collect()
```

### rdd.filter

```python
# BEFORE:
rdd = sc.parallelize([1, 2, 3, 4, 5])
filtered = rdd.filter(lambda x: x > 3).collect()

# AFTER:
from pyspark.sql import functions as F
df = spark.createDataFrame([(i,) for i in range(1, 6)], ["value"])
result = df.filter(F.col("value") > 3).collect()
```

### rdd.reduce

```python
# BEFORE:
rdd = sc.parallelize([1, 2, 3, 4, 5])
total = rdd.reduce(lambda a, b: a + b)

# AFTER:
from pyspark.sql import functions as F
df = spark.createDataFrame([(i,) for i in range(1, 6)], ["value"])
total = df.agg(F.sum("value")).collect()[0][0]
```

### rdd.flatMap

```python
# BEFORE:
rdd = sc.parallelize(["hello world", "foo bar"])
words = rdd.flatMap(lambda line: line.split(" ")).collect()

# AFTER:
from pyspark.sql import functions as F
df = spark.createDataFrame([("hello world",), ("foo bar",)], ["line"])
words = df.select(F.explode(F.split(F.col("line"), " ")).alias("word")).collect()
```

### rdd.groupByKey

```python
# BEFORE:
rdd = sc.parallelize([("a", 1), ("b", 2), ("a", 3)])
grouped = rdd.groupByKey().mapValues(list).collect()

# AFTER:
from pyspark.sql import functions as F
df = spark.createDataFrame([("a", 1), ("b", 2), ("a", 3)], ["key", "value"])
grouped = df.groupBy("key").agg(F.collect_list("value").alias("values")).collect()
```

### rdd.reduceByKey

```python
# BEFORE:
rdd = sc.parallelize([("a", 1), ("b", 2), ("a", 3)])
summed = rdd.reduceByKey(lambda a, b: a + b).collect()

# AFTER:
from pyspark.sql import functions as F
df = spark.createDataFrame([("a", 1), ("b", 2), ("a", 3)], ["key", "value"])
summed = df.groupBy("key").agg(F.sum("value").alias("value")).collect()
```

### rdd.mapPartitions to applyInPandas

```python
# BEFORE:
rdd = sc.parallelize(range(100), 4)
def process_partition(iterator):
    yield sum(iterator)
result = rdd.mapPartitions(process_partition).collect()

# AFTER:
import pandas as pd
from pyspark.sql import functions as F

def process_group(pdf: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"total": [pdf["id"].sum()]})

df = spark.range(100).repartition(4)
result = df.groupBy(F.spark_partition_id()).applyInPandas(
    process_group, schema="total long"
).collect()
```

### sc.textFile

```python
# BEFORE:
rdd = sc.textFile("/mnt/data/file.txt")
lines = rdd.collect()

# AFTER:
df = spark.read.text("/Volumes/catalog/schema/volume/file.txt")
lines = df.collect()
```

### sc.wholeTextFiles

```python
# BEFORE:
rdd = sc.wholeTextFiles("/mnt/data/directory/")
files = rdd.collect()

# AFTER:
df = spark.read.format("binaryFile").load("/Volumes/catalog/schema/volume/directory/")
files = df.collect()
```

### rdd.sortByKey

```python
# BEFORE:
rdd = sc.parallelize([("b", 2), ("a", 1), ("c", 3)])
sorted_rdd = rdd.sortByKey().collect()

# AFTER:
df = spark.createDataFrame([("b", 2), ("a", 1), ("c", 3)], ["key", "value"])
sorted_df = df.orderBy("key").collect()
```

### rdd.join

```python
# BEFORE:
rdd1 = sc.parallelize([("a", 1), ("b", 2)])
rdd2 = sc.parallelize([("a", "x"), ("b", "y")])
joined = rdd1.join(rdd2).collect()

# AFTER:
df1 = spark.createDataFrame([("a", 1), ("b", 2)], ["key", "val1"])
df2 = spark.createDataFrame([("a", "x"), ("b", "y")], ["key", "val2"])
joined = df1.join(df2, "key").collect()
```

### SparkContext.getOrCreate()

```python
# BEFORE:
from pyspark import SparkContext
sc = SparkContext.getOrCreate()
data = sc.parallelize([1, 2, 3, 4, 5])
result = data.map(lambda x: x * 2).collect()

# AFTER (serverless — SparkContext.getOrCreate() raises RuntimeError):
# Use the pre-existing `spark` SparkSession directly
df = spark.createDataFrame([(i,) for i in [1, 2, 3, 4, 5]], ["value"])
from pyspark.sql import functions as F
result = df.select((F.col("value") * 2).alias("value")).collect()

# For simple ranges, spark.range() is even simpler:
df = spark.range(1, 6)  # Creates DataFrame with column "id" = [1, 2, 3, 4, 5]
```

## %run Inlining

When `%run ./relative/path` causes issues in serverless job tasks, inline the referenced notebook or convert to an absolute path.

### Inlining a Config Notebook

```python
# BEFORE (main notebook):
# Cell 1:
# %run ./config

# Cell 2:
df = spark.table(f"{catalog}.{schema}.orders")
result = df.filter(f"region = '{region}'")

# Where ./config notebook contains:
# catalog = "main"
# schema = "sales"
# region = "US"
# FEATURE_FLAG_V2 = True

# AFTER (inline the config — preferred when <500 lines):
# Cell 1:
catalog = "main"
schema = "sales"
region = "US"
FEATURE_FLAG_V2 = True

# Cell 2:
df = spark.table(f"{catalog}.{schema}.orders")
result = df.filter(f"region = '{region}'")
```

### Converting to Absolute Path

```python
# BEFORE:
# %run ./utils/helpers

# AFTER (when the notebook is too large to inline):
dbutils.notebook.run("<workspace_path>/utils/helpers", timeout_seconds=300)
# Note: Variables defined in the called notebook are NOT available in the caller
# when using dbutils.notebook.run(). Use dbutils.notebook.exit() to return a value.
```

## DBFS to Volumes

### Reading Files (Spark)

```python
# BEFORE:
df = spark.read.csv("dbfs:/mnt/datalake/sales/data.csv", header=True)

# AFTER:
df = spark.read.csv("/Volumes/main/sales/raw_data/data.csv", header=True)
```

### Reading Files (Pandas)

```python
# BEFORE:
import pandas as pd
pdf = pd.read_csv("/dbfs/mnt/datalake/sales/data.csv")

# AFTER:
import pandas as pd
pdf = pd.read_csv("/Volumes/main/sales/raw_data/data.csv")
```

### Writing Files

```python
# BEFORE:
df.write.parquet("dbfs:/mnt/datalake/output/results.parquet")

# AFTER:
df.write.parquet("/Volumes/main/analytics/output/results.parquet")
```

### Listing Files

```python
# BEFORE:
files = dbutils.fs.ls("dbfs:/mnt/datalake/sales/")

# AFTER:
files = dbutils.fs.ls("/Volumes/main/sales/raw_data/")
```

### Replacing Mounts with External Volumes

```python
# BEFORE:
dbutils.fs.mount(source="s3://my-bucket/data/", mount_point="/mnt/datalake")
df = spark.read.csv("/mnt/datalake/file.csv")

# AFTER (one-time SQL setup):
# CREATE EXTERNAL VOLUME main.data.raw_files LOCATION 's3://my-bucket/data/';
# Then in code:
df = spark.read.csv("/Volumes/main/data/raw_files/file.csv")
```

### Non-Sequential File Writes (Excel, Images, etc.)

Some libraries require writing to local disk first. Use `/local_disk0/tmp/` as a staging area:

```python
import xlsxwriter
from shutil import copyfile

# Write to local temp
workbook = xlsxwriter.Workbook('/local_disk0/tmp/report.xlsx')
worksheet = workbook.add_worksheet()
worksheet.write('A1', 'Report Title')
# ... more writes ...
workbook.close()

# Copy to Volumes
copyfile('/local_disk0/tmp/report.xlsx', '/Volumes/main/reports/output/report.xlsx')
```

### Volume Limitations to Know

- `dbutils.fs` operations on Volumes work from the driver only (not from executors/RDDs)
- Use `dbutils.fs.mv` instead of `%sh mv` when moving files between Volumes
- Temporary files should use `/local_disk0/tmp/` (cleaned up when session ends)

## SparkContext to SparkSession

### broadcast to broadcast join

```python
# BEFORE:
lookup = sc.broadcast({"US": "United States", "UK": "United Kingdom"})
# ... use in UDF or RDD operation

# AFTER:
from pyspark.sql.functions import broadcast
lookup_df = spark.createDataFrame(
    [("US", "United States"), ("UK", "United Kingdom")],
    ["code", "name"])
result = main_df.join(broadcast(lookup_df), main_df.country_code == lookup_df.code)
```

### accumulator to DataFrame aggregation

```python
# BEFORE:
error_count = sc.accumulator(0)
def process(row):
    if row.status == "error":
        error_count.add(1)
rdd.foreach(process)
print(f"Errors: {error_count.value}")

# AFTER:
error_count = df.filter(F.col("status") == "error").count()
print(f"Errors: {error_count}")

# For multiple aggregations:
stats = df.agg(
    F.count(F.when(F.col("status") == "error", 1)).alias("error_count"),
    F.sum("amount").alias("total_amount"),
    F.count("*").alias("total_rows")
).collect()[0]
```

### sqlContext.sql to spark.sql

```python
# BEFORE:
result = sqlContext.sql("SELECT * FROM hive_metastore.default.my_table")

# AFTER:
result = spark.sql("SELECT * FROM main.my_schema.my_table")
```

### sc.hadoopConfiguration to UC External Locations

```python
# BEFORE:
sc.hadoopConfiguration.set("fs.s3a.access.key", "AKIAEXAMPLE")
sc.hadoopConfiguration.set("fs.s3a.secret.key", dbutils.secrets.get("scope", "key"))
df = spark.read.parquet("s3a://bucket/path/")

# AFTER (no credential config needed — UC handles auth):
df = spark.read.parquet("s3://bucket/path/")
# Or via Volumes:
df = spark.read.parquet("/Volumes/main/data/volume/path/")
```

### sc.getConf to spark.conf.get

```python
# BEFORE:
value = sc.getConf().get("spark.sql.shuffle.partitions")

# AFTER:
value = spark.conf.get("spark.sql.shuffle.partitions")
```

## Cache/Persist to Remove or Materialize

### Simple Cache Removal

```python
# BEFORE:
df = spark.read.parquet(path)
df.cache()
df.count()  # Materialize cache
result1 = df.filter("status = 'active'")
result2 = df.groupBy("region").agg(F.sum("revenue"))

# AFTER (just remove .cache()):
df = spark.read.parquet(path)
result1 = df.filter("status = 'active'")
result2 = df.groupBy("region").agg(F.sum("revenue"))
# df.cache is not yet supported — native support coming soon
# For now, materialize expensive intermediate results to Delta (see below)
```

### Materialize Expensive Intermediate Results

```python
# BEFORE:
expensive_df = (spark.read.parquet(path)
    .join(other_df, "key")
    .groupBy("region").agg(F.sum("amount").alias("total")))
expensive_df.cache()
report1 = expensive_df.filter("total > 1000")
report2 = expensive_df.orderBy("total")

# AFTER (materialize to Delta for explicit reuse):
expensive_df = (spark.read.parquet(path)
    .join(other_df, "key")
    .groupBy("region").agg(F.sum("amount").alias("total")))
expensive_df.write.format("delta").mode("overwrite").saveAsTable("main.scratch.region_totals")
intermediate = spark.table("main.scratch.region_totals")
report1 = intermediate.filter("total > 1000")
report2 = intermediate.orderBy("total")
```

### SQL Cache Removal

```sql
-- BEFORE:
CACHE TABLE my_temp_table;
SELECT * FROM my_temp_table WHERE status = 'active';

-- AFTER (just remove CACHE TABLE):
SELECT * FROM my_temp_table WHERE status = 'active';
```

## HMS to Unity Catalog

### HMS Federation (Bridge Approach)

Use when you need existing code to keep working while planning a full migration:

```sql
-- One-time setup: create federation connection
CREATE CONNECTION hms_connection TYPE hive_metastore;
CREATE FOREIGN CATALOG hms_catalog USING CONNECTION hms_connection;

-- Existing queries work with a catalog prefix:
SELECT * FROM hms_catalog.default.my_table;
```

### Direct Migration

```sql
-- Migrate a table:
CREATE TABLE main.sales.customers AS
  SELECT * FROM hive_metastore.default.customers;

-- For Delta tables, use SYNC to avoid data copy:
-- (preserves the underlying data files)
SYNC TABLE main.sales.customers
FROM hive_metastore.default.customers;
```

### Update Code References

```python
# BEFORE (2-level namespace):
df = spark.table("my_database.my_table")

# AFTER (3-level namespace with UC):
df = spark.table("main.my_database.my_table")

# Set default catalog to avoid changing every reference:
spark.sql("USE CATALOG main")
df = spark.table("my_database.my_table")  # Now resolves to main.my_database.my_table
```

### Automation with UCX

For large-scale migrations, use the [UCX tool](https://github.com/databrickslabs/ucx) to automate HMS to UC migration:
- Scans all notebooks, jobs, and tables for HMS references
- Generates migration scripts
- Handles table, view, and function migration

## Init Scripts to Environments

### Basic Library Installation

```
# BEFORE (init script):
#!/bin/bash
pip install numpy==2.2.2 pandas==2.2.3 scikit-learn==1.4.0
pip install /dbfs/libs/my_package-1.0.0.whl

# AFTER (Environment panel or requirements.txt):
numpy==2.2.2
pandas==2.2.3
scikit-learn==1.4.0
/Volumes/main/libs/packages/my_package-1.0.0-py3-none-any.whl
```

### Private Packages

```
# BEFORE (init script):
#!/bin/bash
pip install --index-url https://pypi.example.com/simple/ my-internal-package==1.0.0

# AFTER (Environment panel):
# Configure private PyPI mirror in workspace admin settings
# Then add to Environment:
my-internal-package==1.0.0
```

### Workspace Utility Packages

```
# BEFORE (init script installing shared utils):
#!/bin/bash
pip install /dbfs/shared/utils-1.0.0.whl

# AFTER (use workspace files):
# Upload package to workspace:
#   /Workspace/shared/helper_utils/ (with pyproject.toml)
# Add to Environment:
/Workspace/shared/helper_utils
```

### Init Script with apt install to Environment Spec

```bash
# BEFORE (init script — setup_ml.sh):
#!/bin/bash
apt-get update
apt-get install -y libgomp1 python3-opencv tesseract-ocr
pip install mlflow==2.12.1 scikit-learn==1.3.0 xgboost==2.0.3
pip install opencv-python==4.9.0.80
pip install /dbfs/libs/internal_ml_utils-2.0.0.whl
export MODEL_REGISTRY=production
```

```json
// AFTER (Serverless Environment spec):
{
  "environment_key": "ml_env",
  "spec": {
    "client": "2",
    "dependencies": [
      "mlflow==2.12.1",
      "scikit-learn==1.3.0",
      "xgboost==2.0.3",
      "opencv-python==4.9.0.80",
      "pytesseract==0.3.10",
      "/Volumes/<your_catalog>/libs/packages/internal_ml_utils-2.0.0.whl"
    ]
  }
}
// Notes:
// - libgomp1: bundled with xgboost pip package — no separate install needed
// - python3-opencv → opencv-python (pip equivalent)
// - tesseract-ocr → pytesseract (pip wrapper; the OCR engine itself is NOT
//   available on serverless — if Tesseract binary is required, this is a
//   Category 3 blocker)
// - DBFS wheel path → moved to Volumes
// - export MODEL_REGISTRY=production → pass as job parameter, read with
//   dbutils.widgets.get("model_registry")
// - ML runtime is NOT available on serverless — all ML libs must be listed
//   explicitly in dependencies
```

### Critical Rules for Environments

- **Never install PySpark** as a dependency — this breaks the serverless session
- **Always pin versions** for reproducibility (`numpy==2.2.2`, not just `numpy`)
- Place wheel files in UC Volumes, not DBFS
- Admins can configure default package repositories in workspace settings
- **ML runtime is NOT available** on serverless — list all ML libraries (mlflow, scikit-learn, xgboost, hyperopt, tensorflow, torch, etc.) explicitly in the environment spec

## Custom JDBC to Alternatives

### Lakehouse Federation (Recommended)

Query external databases in place with predicate pushdown:

```sql
-- One-time setup:
CREATE CONNECTION pg_connection TYPE POSTGRESQL
OPTIONS (
    host 'db.example.com',
    port '5432',
    user secret('scope', 'pg-user'),
    password secret('scope', 'pg-password')
);

CREATE FOREIGN CATALOG pg_catalog
USING CONNECTION pg_connection
OPTIONS (database 'mydb');

-- Query directly (pushdown to remote DB):
SELECT * FROM pg_catalog.public.customers WHERE region = 'US';
```

Supported connection types: MySQL, PostgreSQL, Oracle, Redshift, SQL Server, BigQuery, Snowflake, Databricks-to-Databricks, and more.

### Built-in JDBC (No Custom JARs)

Works on serverless for common databases without custom driver JARs:

```python
df = (spark.read.format("jdbc")
    .option("url", "jdbc:postgresql://host:5432/mydb")
    .option("dbtable", "public.customers")
    .option("user", dbutils.secrets.get("scope", "user"))
    .option("password", dbutils.secrets.get("scope", "password"))
    .load())
```

### PySpark Custom Data Sources

For unsupported formats, implement a PySpark data source:

```python
from pyspark.sql.datasource import DataSource, DataSourceReader
from pyspark.sql.types import StructType, StructField, StringType

class MyCustomReader(DataSourceReader):
    def __init__(self, schema, options):
        self.options = options

    def read(self, partition):
        # Implement your read logic here
        yield ("row1_col1", "row1_col2")

class MyCustomSource(DataSource):
    @classmethod
    def name(cls):
        return "my_custom_source"

    def schema(self):
        return StructType([
            StructField("col1", StringType()),
            StructField("col2", StringType())
        ])

    def reader(self, schema):
        return MyCustomReader(schema, self.options)

# Register and use:
spark.dataSource.register(MyCustomSource)
df = spark.read.format("my_custom_source").option("key", "value").load()
```

## Query Profile (Spark UI Replacement)

### Interactive Usage

Serverless compute does not have a Spark UI. Use **Query Profile** instead:

1. Run your query in a notebook
2. Click **"See performance"** under the cell output
3. Click **"See query profile"** for the full execution DAG

### Key Features

- **Top Operators**: Identify the most expensive operations
- **Scan Statistics**: Row counts, bytes read per table scan
- **Shuffle Statistics**: Data shuffled between stages
- **Export/Import**: Share profiles as JSON via the kebab menu

### Programmatic Plan Analysis

```python
# Physical plan
df.explain(True)

# Extended plan with statistics
df.explain("extended")

# Cost-based plan
df.explain("cost")

# Formatted plan
df.explain("formatted")
```

### Runtime Detection

Detect whether code is running on serverless to conditionally use Query Profile vs Spark UI:

```python
import os
is_serverless = os.getenv("IS_SERVERLESS", "").lower() == "true"

if is_serverless:
    # Use explain() for plan analysis
    df.explain(True)
else:
    # Can also use Spark UI on classic
    df.explain(True)
```

## Global Temporary View to Session-Scoped Temporary View

`CREATE GLOBAL TEMPORARY VIEW` is not supported on serverless. Global temp views use a special `global_temp` database that doesn't exist on serverless. Replace with session-scoped temporary views.

```python
# BEFORE (Classic)
spark.sql("CREATE GLOBAL TEMPORARY VIEW monthly_stats AS SELECT month, SUM(revenue) FROM sales GROUP BY month")
result = spark.sql("SELECT * FROM global_temp.monthly_stats")

# AFTER (Serverless)
spark.sql("CREATE OR REPLACE TEMPORARY VIEW monthly_stats AS SELECT month, SUM(revenue) FROM sales GROUP BY month")
result = spark.sql("SELECT * FROM monthly_stats")
```

## os.environ Restrictions

On serverless, the environment is managed by the platform. Variables like `SPARK_HOME`, `JAVA_HOME`, and custom env vars set via cluster configs are NOT available. Direct `os.environ["VAR"]` will raise `KeyError`.

```python
# BEFORE (Classic) — crashes on serverless with KeyError
spark_home = os.environ["SPARK_HOME"]
java_home = os.environ["JAVA_HOME"]
custom_var = os.environ["MY_CUSTOM_VAR"]

# AFTER (Serverless)
import os
spark_home = os.environ.get("SPARK_HOME", "N/A")  # Not guaranteed on serverless
java_home = os.environ.get("JAVA_HOME", "/usr/lib/jvm/default")
custom_var = dbutils.widgets.get("MY_CUSTOM_VAR")  # Use widget parameter instead
# Or for Spark-specific info:
spark_version = spark.version  # "14.3" etc.
```

## Hive Variable Substitution to SQL Session Variables

Hive variable substitution (`SET hivevar:name = value` + `${hivevar:name}`) is not supported on serverless. The Spark Connect backend doesn't process Hive variable interpolation. Replace with SQL session variables (available in DBR 14.1+).

```sql
-- BEFORE (Classic) — uses Hive variable substitution
SET hivevar:target_date = '2024-01-01';
SET hivevar:min_amount = 100;
SELECT * FROM transactions 
WHERE date >= '${hivevar:target_date}' 
AND amount > ${hivevar:min_amount};

-- AFTER (Serverless) — uses SQL session variables (DBR 14.1+)
DECLARE OR REPLACE VARIABLE target_date STRING = '2024-01-01';
DECLARE OR REPLACE VARIABLE min_amount INT = 100;
SELECT * FROM transactions 
WHERE date >= target_date 
AND amount > min_amount;
```

For Python notebooks, use Python variables and f-strings instead of Hive substitution:

```python
# BEFORE (Classic) — Hive substitution in spark.sql
spark.sql("SET hivevar:target_date = '2024-01-01'")
result = spark.sql("SELECT * FROM transactions WHERE date >= '${hivevar:target_date}'")

# AFTER (Serverless) — Python f-strings
target_date = '2024-01-01'
result = spark.sql(f"SELECT * FROM transactions WHERE date >= '{target_date}'")
```

## Documentation

- Serverless limitations: https://docs.databricks.com/en/compute/serverless/limitations
- Spark Connect vs classic: https://docs.databricks.com/en/spark/connect-vs-classic
- UC Volumes: https://docs.databricks.com/en/volumes/volume-files
- UC external locations: https://docs.databricks.com/en/connect/unity-catalog/external-locations.html
- UC upgrade guide: https://docs.databricks.com/en/data-governance/unity-catalog/upgrade/
- Serverless dependencies: https://docs.databricks.com/en/compute/serverless/dependencies
- Lakehouse Federation: https://docs.databricks.com/en/query-federation/
- Query Profile: https://docs.databricks.com/en/sql/user/queries/query-profile.html
- PySpark data sources: https://docs.databricks.com/en/pyspark/datasource.html
