# Validation Expression + Router → SDP Expectations

The classic Informatica data-quality pattern: an `Expression` computes
`IS_VALID_*` flags, a `Router` splits "good" from "bad" rows. Collapse to
declarative expectations rather than preserving the flag-based pattern.

## Informatica Input

**`m_load_orders_validated.xml`** (PowerCenter, simplified):

```xml
<MAPPING NAME="m_load_orders_validated">
  <SOURCE NAME="SQ_RAW_ORDERS" DATABASETYPE="Oracle">
    <SOURCEFIELD NAME="ORDER_ID" DATATYPE="number" NULLABLE="NOT NULL" />
    <SOURCEFIELD NAME="CUSTOMER_ID" DATATYPE="number" NULLABLE="NOT NULL" />
    <SOURCEFIELD NAME="ORDER_AMOUNT" DATATYPE="number" PRECISION="10" SCALE="2" />
    <SOURCEFIELD NAME="ORDER_DATE" DATATYPE="date" />
    <SOURCEFIELD NAME="EMAIL" DATATYPE="string" />
    <SOURCEFIELD NAME="STATUS" DATATYPE="string" />
  </SOURCE>

  <TRANSFORMATION NAME="EXP_VALIDATE" TYPE="Expression">
    <TRANSFORMFIELD NAME="IS_VALID_AMOUNT" PORTTYPE="OUTPUT" EXPRESSION="IIF(ORDER_AMOUNT > 0, 1, 0)" />
    <TRANSFORMFIELD NAME="IS_VALID_EMAIL" PORTTYPE="OUTPUT" EXPRESSION="IIF(INSTR(EMAIL, '@') > 0, 1, 0)" />
  </TRANSFORMATION>

  <TRANSFORMATION NAME="RTR_QUALITY_CHECK" TYPE="Router">
    <GROUP NAME="GOOD_RECORDS" CONDITION="IS_VALID_AMOUNT = 1 AND IS_VALID_EMAIL = 1" />
    <GROUP NAME="BAD_RECORDS" CONDITION="IS_VALID_AMOUNT = 0 OR IS_VALID_EMAIL = 0" />
  </TRANSFORMATION>

  <TARGET NAME="TGT_ORDERS_CLEAN" DATABASETYPE="Oracle">
    <TARGETFIELD NAME="ORDER_ID" NULLABLE="NOT NULL" />
    <TARGETFIELD NAME="CUSTOMER_ID" NULLABLE="NOT NULL" />
    <TARGETFIELD NAME="ORDER_AMOUNT" />
    <TARGETFIELD NAME="ORDER_DATE" />
    <TARGETFIELD NAME="EMAIL" />
    <TARGETFIELD NAME="STATUS" />
  </TARGET>

  <TARGET NAME="TGT_ORDERS_REJECTED" DATABASETYPE="Oracle" />
</MAPPING>
```

## Migration IR Nodes

The Router fans out to two targets — each becomes its own IR node.

```yaml
- id: orders_clean
  source_path: mappings/m_load_orders_validated.xml
  sdp_type: streaming_table
  notes: 'Good-records branch of RTR_QUALITY_CHECK collapsed into declarative expectations'

- id: orders_rejected
  source_path: mappings/m_load_orders_validated.xml
  sdp_type: streaming_table
  notes: 'Bad-records branch of RTR_QUALITY_CHECK — preserved for analyst review'
```

## SDP Output (SQL)

```sql
-- Good-records target with validation rules from EXP_VALIDATE + RTR_QUALITY_CHECK
-- merged into expectations. NOT NULL constraints from source/target fields
-- become drop-row expectations.
CREATE OR REFRESH STREAMING TABLE orders_clean (
  CONSTRAINT valid_order_id    EXPECT (ORDER_ID    IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_customer_id EXPECT (CUSTOMER_ID IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT valid_amount      EXPECT (ORDER_AMOUNT > 0)        ON VIOLATION DROP ROW,
  CONSTRAINT valid_email       EXPECT (EMAIL LIKE '%@%')        ON VIOLATION DROP ROW
)
COMMENT 'Validated orders: rows violating quality rules are dropped.'
AS SELECT * FROM STREAM(raw_catalog.raw_schema.sq_raw_orders);

-- Rejected-records target keeps the rows that fail any of the same rules,
-- so analysts can inspect them.
CREATE OR REFRESH STREAMING TABLE orders_rejected
COMMENT 'Rejected orders that failed one or more quality checks.'
AS SELECT * FROM STREAM(raw_catalog.raw_schema.sq_raw_orders)
WHERE ORDER_ID IS NULL
   OR CUSTOMER_ID IS NULL
   OR ORDER_AMOUNT <= 0
   OR EMAIL NOT LIKE '%@%';
```

## SDP Output (Python)

```python
from pyspark import pipelines as dp

@dp.table(comment="Validated orders: rows violating quality rules are dropped.")
@dp.expect_or_drop("valid_order_id",    "ORDER_ID IS NOT NULL")
@dp.expect_or_drop("valid_customer_id", "CUSTOMER_ID IS NOT NULL")
@dp.expect_or_drop("valid_amount",      "ORDER_AMOUNT > 0")
@dp.expect_or_drop("valid_email",       "EMAIL LIKE '%@%'")
def orders_clean():
    return spark.readStream.table("raw_catalog.raw_schema.sq_raw_orders")

@dp.table(comment="Rejected orders that failed one or more quality checks.")
def orders_rejected():
    return (
        spark.readStream.table("raw_catalog.raw_schema.sq_raw_orders")
            .where(
                "ORDER_ID IS NULL OR CUSTOMER_ID IS NULL "
                "OR ORDER_AMOUNT <= 0 OR EMAIL NOT LIKE '%@%'"
            )
    )
```

## Key Conversion Notes

- `<SOURCEFIELD NULLABLE="NOT NULL">` / `<TARGETFIELD NULLABLE="NOT NULL">` → `CONSTRAINT EXPECT (col IS NOT NULL) ON VIOLATION DROP ROW`
- `IS_VALID_*` flag + Router → drop the flag column entirely; emit the condition directly as an expectation
- Router DEFAULT / BAD group → an additional IR node that selects the negated condition, preserving rejected rows for analyst review
- `INSTR(EMAIL, '@') > 0` → `EMAIL LIKE '%@%'` (clearer for substring presence) or `locate('@', EMAIL) > 0`
- The Router's GOOD group condition is implicitly captured in the expectations — do NOT also emit it as a `WHERE` clause (that would double-filter)
