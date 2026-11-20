# Filter + Joiner + Aggregator → Materialized View

A multi-stage pipeline: filter orders, join with products, aggregate. Two
IR nodes — one for the filtered orders (`temporary_view`), one for the
aggregated result (`materialized_view`).

## Informatica Input

**`m_daily_sales_summary.xml`** (PowerCenter, simplified):

```xml
<MAPPING NAME="m_daily_sales_summary">
  <SOURCE NAME="SQ_ORDERS" DATABASETYPE="Oracle">
    <SOURCEFIELD NAME="ORDER_ID" DATATYPE="number" />
    <SOURCEFIELD NAME="PRODUCT_ID" DATATYPE="number" />
    <SOURCEFIELD NAME="QUANTITY" DATATYPE="number" />
    <SOURCEFIELD NAME="ORDER_DATE" DATATYPE="date" />
    <SOURCEFIELD NAME="STATUS" DATATYPE="string" />
  </SOURCE>

  <SOURCE NAME="SQ_PRODUCTS" DATABASETYPE="Oracle">
    <SOURCEFIELD NAME="PRODUCT_ID" DATATYPE="number" />
    <SOURCEFIELD NAME="PRODUCT_NAME" DATATYPE="string" />
    <SOURCEFIELD NAME="UNIT_PRICE" DATATYPE="number" />
    <SOURCEFIELD NAME="CATEGORY" DATATYPE="string" />
  </SOURCE>

  <TRANSFORMATION NAME="FIL_COMPLETED_ORDERS" TYPE="Filter">
    <CONDITION>STATUS = 'COMPLETED'</CONDITION>
  </TRANSFORMATION>

  <TRANSFORMATION NAME="JNR_ORDERS_PRODUCTS" TYPE="Joiner">
    <JOIN_TYPE>INNER</JOIN_TYPE>
    <JOIN_CONDITION>ORDERS.PRODUCT_ID = PRODUCTS.PRODUCT_ID</JOIN_CONDITION>
  </TRANSFORMATION>

  <TRANSFORMATION NAME="AGG_DAILY_SALES" TYPE="Aggregator">
    <GROUP_BY>ORDER_DATE, PRODUCT_NAME, CATEGORY</GROUP_BY>
    <TRANSFORMFIELD NAME="TOTAL_QUANTITY" EXPRESSION="SUM(QUANTITY)" />
    <TRANSFORMFIELD NAME="TOTAL_REVENUE" EXPRESSION="SUM(QUANTITY * UNIT_PRICE)" />
  </TRANSFORMATION>

  <TARGET NAME="TGT_DAILY_SALES_SUMMARY" DATABASETYPE="Oracle">
    <TARGETFIELD NAME="ORDER_DATE" />
    <TARGETFIELD NAME="PRODUCT_NAME" />
    <TARGETFIELD NAME="CATEGORY" />
    <TARGETFIELD NAME="TOTAL_QUANTITY" />
    <TARGETFIELD NAME="TOTAL_REVENUE" />
  </TARGET>
</MAPPING>
```

## Migration IR Nodes

The Filter step is split out as a `temporary_view` so the aggregation reads
filtered data directly. The Aggregator forces `materialized_view` on the final
target.

```yaml
- id: completed_orders
  source_path: mappings/m_daily_sales_summary.xml
  sdp_type: temporary_view
  notes: 'FIL_COMPLETED_ORDERS — intermediate filter; pipeline-private'

- id: daily_sales_summary
  source_path: mappings/m_daily_sales_summary.xml
  sdp_type: materialized_view
  notes: 'Joiner + Aggregator on completed_orders — full recompute on each refresh'
```

## SDP Output (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.temporary_view()
def completed_orders():
    return (
        spark.read.table("raw_catalog.raw_schema.sq_orders")
            .where(F.col("STATUS") == "COMPLETED")
    )

@dp.materialized_view(comment="Daily sales aggregated by product and category.")
def daily_sales_summary():
    orders = spark.read.table("completed_orders")
    products = spark.read.table("raw_catalog.raw_schema.sq_products")
    return (
        orders.join(products, on="PRODUCT_ID", how="inner")
              .groupBy("ORDER_DATE", "PRODUCT_NAME", "CATEGORY")
              .agg(
                  F.sum("QUANTITY").alias("total_quantity"),
                  F.sum(F.col("QUANTITY") * F.col("UNIT_PRICE")).alias("total_revenue"),
              )
    )
```

## SDP Output (SQL)

```sql
CREATE TEMPORARY VIEW completed_orders AS
SELECT * FROM raw_catalog.raw_schema.sq_orders WHERE STATUS = 'COMPLETED';

CREATE OR REFRESH MATERIALIZED VIEW daily_sales_summary
COMMENT 'Daily sales aggregated by product and category.'
AS SELECT
    o.ORDER_DATE,
    p.PRODUCT_NAME,
    p.CATEGORY,
    SUM(o.QUANTITY) AS total_quantity,
    SUM(o.QUANTITY * p.UNIT_PRICE) AS total_revenue
FROM completed_orders o
INNER JOIN raw_catalog.raw_schema.sq_products p ON o.PRODUCT_ID = p.PRODUCT_ID
GROUP BY o.ORDER_DATE, p.PRODUCT_NAME, p.CATEGORY;
```

## Key Conversion Notes

- Filter as a separate IR node → `temporary_view` (pipeline-private intermediate)
- Aggregator forces `materialized_view` (batch full recompute, not streaming)
- `<JOIN_TYPE>INNER</JOIN_TYPE>` → `INNER JOIN` / `.join(..., how="inner")`. In Informatica, **Detail** is the driving side (left); **Master** is the lookup side (right). When the XML doesn't make the role explicit, treat the first listed source as Detail
- `<GROUP_BY>` ports → `GROUP BY` / `.groupBy(...)`
- Aggregator's `Sorted Input` option (when present) has no Spark equivalent — omit it
- Intra-pipeline references (`completed_orders` from `daily_sales_summary`) use the bare table name; only fully qualify external UC tables
