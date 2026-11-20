# Filter + Mapping Variables → Streaming Table

A `Source` → `Filter` → `Target` mapping with parameters substituted into the
source schema and the filter condition.

## Informatica Input

**`m_load_transactions.xml`** (PowerCenter, simplified):

```xml
<MAPPING NAME="m_load_transactions">
  <MAPPINGVARIABLE NAME="$$SRC_CATALOG" DATATYPE="String" DEFAULT="prod_catalog" />
  <MAPPINGVARIABLE NAME="$$SRC_SCHEMA" DATATYPE="String" DEFAULT="production" />
  <MAPPINGVARIABLE NAME="$$LOAD_DATE" DATATYPE="Date/Time" />
  <MAPPINGVARIABLE NAME="$$REGION_FILTER" DATATYPE="String" DEFAULT="US" />

  <SOURCE NAME="SQ_TRANSACTIONS" DATABASETYPE="Oracle" OWNERNAME="$$SRC_CATALOG.$$SRC_SCHEMA">
    <SOURCEFIELD NAME="TXN_ID" DATATYPE="number" />
    <SOURCEFIELD NAME="ACCOUNT_ID" DATATYPE="number" />
    <SOURCEFIELD NAME="AMOUNT" DATATYPE="number" />
    <SOURCEFIELD NAME="TXN_DATE" DATATYPE="date" />
    <SOURCEFIELD NAME="REGION" DATATYPE="string" />
  </SOURCE>

  <TRANSFORMATION NAME="FIL_BY_REGION" TYPE="Filter">
    <CONDITION>REGION = $$REGION_FILTER AND TXN_DATE >= $$LOAD_DATE</CONDITION>
  </TRANSFORMATION>

  <TARGET NAME="TGT_TRANSACTIONS" DATABASETYPE="Oracle">
    <TARGETFIELD NAME="TXN_ID" />
    <TARGETFIELD NAME="ACCOUNT_ID" />
    <TARGETFIELD NAME="AMOUNT" />
    <TARGETFIELD NAME="TXN_DATE" />
    <TARGETFIELD NAME="REGION" />
  </TARGET>
</MAPPING>
```

## Migration IR Node

```yaml
- id: transactions
  source_path: mappings/m_load_transactions.xml
  sdp_type: streaming_table
  notes: 'Source → Filter → Target, append-only → streaming_table'
```

## SDP Output (SQL)

```sql
-- Mapping variables become SQL named parameters (:name). Declare them in the pipeline
-- `parameters` field with their defaults (src_catalog=prod_catalog, src_schema=production,
-- region_filter=US); $$LOAD_DATE has no Informatica default, so declare it with an empty
-- value for the user to set. Identifier-position params (catalog/schema/table) use IDENTIFIER().
CREATE OR REFRESH STREAMING TABLE transactions
COMMENT 'Transactions filtered by region and load date, migrated from m_load_transactions.'
AS SELECT * FROM STREAM(IDENTIFIER(:src_catalog || '.' || :src_schema || '.sq_transactions'))
WHERE REGION = :region_filter AND TXN_DATE >= CAST(:load_date AS DATE);
```

## SDP Output (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(comment="Transactions filtered by region and load date, migrated from m_load_transactions.")
def transactions():
    src_catalog = spark.conf.get("src_catalog")
    src_schema = spark.conf.get("src_schema", "production")
    region_filter = spark.conf.get("region_filter", "US")
    load_date = spark.conf.get("load_date")  # no Informatica default
    return (
        spark.readStream.table(f"{src_catalog}.{src_schema}.sq_transactions")
            .where(F.col("REGION") == region_filter)
            .where(F.col("TXN_DATE") >= F.lit(load_date).cast("date"))
    )
```

## Key Conversion Notes

- `OWNERNAME="$$SRC_CATALOG.$$SRC_SCHEMA"` is an identifier position → SQL wraps the params in `IDENTIFIER(:src_catalog || '.' || :src_schema || '.sq_transactions')`; Python builds the name with an f-string. A bare `:param` cannot be a table name.
- `<MAPPINGVARIABLE>` with `DEFAULT` → declared default on the pipeline (`parameters` field for SQL, `configuration` for Python) and the second argument to `spark.conf.get(...)` in Python. SQL parameters must be declared or analysis fails.
- `<TRANSFORMATION TYPE="Filter">` `<CONDITION>` → `WHERE` clause / `.where(...)`
- Append-only Source → Filter → Target pattern → `streaming_table` with `FROM STREAM(...)` / `readStream`
- Each parameter value arrives as a `STRING`. Cast at the use site for the date comparison: `CAST(:load_date AS DATE)` (SQL) / `F.lit(load_date).cast("date")` (Python) so it compares as a date and not a string
