# Expression Transformation + Parameters → Derived Columns

A common entry pattern: a `Source` feeds an `Expression` that derives columns
(full name, normalized email, system timestamp), referencing a mapping variable
for a default value.

## Informatica Input

**`m_load_customers.xml`** (PowerCenter, simplified):

```xml
<MAPPING NAME="m_load_customers">
  <MAPPINGVARIABLE NAME="$$DEFAULT_DOMAIN" DATATYPE="String" DEFAULT="example.com" />

  <SOURCE NAME="SQ_CUSTOMERS" DATABASETYPE="Oracle">
    <SOURCEFIELD NAME="CUST_ID" DATATYPE="number" />
    <SOURCEFIELD NAME="FIRST_NAME" DATATYPE="string" />
    <SOURCEFIELD NAME="LAST_NAME" DATATYPE="string" />
    <SOURCEFIELD NAME="EMAIL" DATATYPE="string" />
    <SOURCEFIELD NAME="CREATED_DATE" DATATYPE="date" />
  </SOURCE>

  <TRANSFORMATION NAME="EXP_DERIVE_FIELDS" TYPE="Expression">
    <TRANSFORMFIELD NAME="CUST_ID" PORTTYPE="INPUT/OUTPUT" EXPRESSION="CUST_ID" />
    <TRANSFORMFIELD NAME="FULL_NAME" PORTTYPE="OUTPUT" EXPRESSION="FIRST_NAME || ' ' || LAST_NAME" />
    <TRANSFORMFIELD NAME="EMAIL_LOWER" PORTTYPE="OUTPUT"
                    EXPRESSION="IIF(ISNULL(EMAIL), 'unknown@' || $$DEFAULT_DOMAIN, LOWER(EMAIL))" />
    <TRANSFORMFIELD NAME="LOAD_DATE" PORTTYPE="OUTPUT" EXPRESSION="SYSDATE" />
  </TRANSFORMATION>

  <TARGET NAME="TGT_DIM_CUSTOMERS" DATABASETYPE="Oracle">
    <TARGETFIELD NAME="CUST_ID" />
    <TARGETFIELD NAME="FULL_NAME" />
    <TARGETFIELD NAME="EMAIL_LOWER" />
    <TARGETFIELD NAME="LOAD_DATE" />
  </TARGET>
</MAPPING>
```

## Migration IR Node

```yaml
- id: dim_customers
  source_path: mappings/m_load_customers.xml
  sdp_type: streaming_table
  notes: 'Source → Expression → Target with no aggregation and no Update Strategy → streaming_table (append-only).'
```

The `SQ_CUSTOMERS` source resolves to `raw_catalog.raw_schema.sq_customers`
via the top-level `sources:` mapping in the IR (see `ir-schema.yml`).

## SDP Output (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table()
def dim_customers():
    default_domain = spark.conf.get("default_domain", "example.com")
    return (
        spark.readStream.table("raw_catalog.raw_schema.sq_customers")
            .select(
                F.col("CUST_ID").alias("cust_id"),
                F.concat_ws(" ", F.col("FIRST_NAME"), F.col("LAST_NAME")).alias("full_name"),
                F.when(F.col("EMAIL").isNull(), F.concat(F.lit("unknown@"), F.lit(default_domain)))
                 .otherwise(F.lower(F.col("EMAIL")))
                 .alias("email_lower"),
                F.current_timestamp().alias("load_date"),
            )
    )
```

## SDP Output (SQL)

```sql
CREATE OR REFRESH STREAMING TABLE dim_customers AS
SELECT
    CUST_ID AS cust_id,
    CONCAT_WS(' ', FIRST_NAME, LAST_NAME) AS full_name,
    CASE WHEN EMAIL IS NULL THEN CONCAT('unknown@', :default_domain)
         ELSE LOWER(EMAIL) END AS email_lower,
    CURRENT_TIMESTAMP() AS load_date
FROM STREAM(raw_catalog.raw_schema.sq_customers);
```

## Key Conversion Notes

- `<MAPPINGVARIABLE>` → `:name` (SQL) or `spark.conf.get(...)` (Python); drop the `$$` prefix and lower-case. Declare `default_domain` on the pipeline (`parameters` for SQL, `configuration` for Python) with its `DEFAULT` value `example.com`
- `||` string concat → `concat()` / `concat_ws()` in PySpark. Spark SQL supports `||` as string concat directly (since 2.3), so keeping it is also fine when emitting SQL
- `IIF(cond, t, f)` → `when(cond, t).otherwise(f)` / `CASE WHEN ... END`
- `ISNULL(col)` → `col.isNull()` / `col IS NULL`
- `LOWER(col)` → `lower(col)` (same name, lower-case)
- `SYSDATE` → `current_timestamp()`
- `PORTTYPE="INPUT/OUTPUT"` is a pass-through — the column flows through unchanged; emit it in the `SELECT` list using the upstream value
