# Lookup + Expression + Update Strategy → AUTO CDC (SCD Type 2)

The canonical Informatica SCD2 pattern: a `Lookup` against the existing
dimension fetches the current row, an `Expression` compares old vs. new values
to derive a change flag, and an `Update Strategy` routes inserts/updates with
effective-date columns. All of that collapses into a single SDP `AUTO CDC`
flow with `STORED AS SCD TYPE 2`.

## Informatica Input

**`m_scd2_customer_dim.xml`** (PowerCenter, simplified):

```xml
<MAPPING NAME="m_scd2_customer_dim">
  <SOURCE NAME="SQ_STG_CUSTOMERS" DATABASETYPE="Oracle">
    <SOURCEFIELD NAME="CUST_ID"       DATATYPE="number" />
    <SOURCEFIELD NAME="CUST_NAME"     DATATYPE="string" />
    <SOURCEFIELD NAME="ADDRESS"       DATATYPE="string" />
    <SOURCEFIELD NAME="CITY"          DATATYPE="string" />
    <SOURCEFIELD NAME="STATE"         DATATYPE="string" />
    <SOURCEFIELD NAME="MODIFIED_DATE" DATATYPE="date" />
  </SOURCE>

  <TRANSFORMATION NAME="LKP_EXISTING_CUSTOMER" TYPE="Lookup">
    <LOOKUP_TABLE>DIM_CUSTOMERS</LOOKUP_TABLE>
    <LOOKUP_CONDITION>CUST_ID = IN_CUST_ID AND CURRENT_FLAG = 'Y'</LOOKUP_CONDITION>
    <TRANSFORMFIELD NAME="LKP_CUST_NAME"     PORTTYPE="OUTPUT" />
    <TRANSFORMFIELD NAME="LKP_ADDRESS"       PORTTYPE="OUTPUT" />
    <TRANSFORMFIELD NAME="LKP_SURROGATE_KEY" PORTTYPE="OUTPUT" />
  </TRANSFORMATION>

  <TRANSFORMATION NAME="EXP_SCD_CHECK" TYPE="Expression">
    <TRANSFORMFIELD NAME="V_CHANGE_FLAG" PORTTYPE="LOCAL VARIABLE"
                    EXPRESSION="IIF(CUST_NAME != LKP_CUST_NAME OR ADDRESS != LKP_ADDRESS, 'Y', 'N')" />
    <TRANSFORMFIELD NAME="UPDATE_STRATEGY" PORTTYPE="OUTPUT"
                    EXPRESSION="IIF(ISNULL(LKP_SURROGATE_KEY), 'DD_INSERT',
                                    IIF(V_CHANGE_FLAG = 'Y', 'DD_INSERT', 'DD_REJECT'))" />
  </TRANSFORMATION>

  <TRANSFORMATION NAME="UPD_SCD_STRATEGY" TYPE="UpdateStrategy">
    <STRATEGY>UPDATE_STRATEGY</STRATEGY>
  </TRANSFORMATION>

  <TARGET NAME="TGT_DIM_CUSTOMERS" DATABASETYPE="Oracle">
    <TARGETFIELD NAME="SURROGATE_KEY" />
    <TARGETFIELD NAME="CUST_ID" />
    <TARGETFIELD NAME="CUST_NAME" />
    <TARGETFIELD NAME="ADDRESS" />
    <TARGETFIELD NAME="CITY" />
    <TARGETFIELD NAME="STATE" />
    <TARGETFIELD NAME="EFF_START_DATE" />
    <TARGETFIELD NAME="EFF_END_DATE" />
    <TARGETFIELD NAME="CURRENT_FLAG" />
  </TARGET>
</MAPPING>
```

## Migration IR Node

History-tracking signals present: `EFF_START_DATE` / `EFF_END_DATE` /
`CURRENT_FLAG` columns on the target, Lookup-on-target with `CURRENT_FLAG = 'Y'`,
and an Expression that compares old vs. new values. → `auto_cdc` SCD Type 2.

```yaml
- id: dim_customers
  source_path: mappings/m_scd2_customer_dim.xml
  sdp_type: auto_cdc
  sdp_cdc_hint: { scd_type: 2 }
  notes: 'Lookup + Expression + Update Strategy → AUTO CDC SCD2. KEYS = CUST_ID (from LOOKUP_CONDITION); SEQUENCE BY = MODIFIED_DATE.'
```

The `SQ_STG_CUSTOMERS` source resolves to `raw_catalog.staging.sq_stg_customers`
via the top-level `sources:` mapping in the IR (see `ir-schema.yml`).

The Informatica SCD Type 2 pattern (Lookup → Expression → Update Strategy)
is replaced by a single AUTO CDC flow that automatically manages surrogate
keys, effective dates, and the current flag.

## SDP Output (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

@dp.temporary_view()
def stg_customers_cdc_source():
    return spark.readStream.table("raw_catalog.staging.sq_stg_customers")

dp.create_streaming_table("dim_customers")

dp.create_auto_cdc_flow(
    target="dim_customers",
    source="stg_customers_cdc_source",
    keys=["CUST_ID"],
    sequence_by=col("MODIFIED_DATE"),
    stored_as_scd_type=2,
)
```

## SDP Output (SQL)

```sql
CREATE OR REFRESH STREAMING TABLE dim_customers;

CREATE FLOW dim_customers_cdc AS
  AUTO CDC INTO dim_customers
  FROM STREAM(raw_catalog.staging.sq_stg_customers)
  KEYS (CUST_ID)
  SEQUENCE BY MODIFIED_DATE
  STORED AS SCD TYPE 2;
```

## Key Conversion Notes

- The entire (Lookup-on-target) + (Expression-compare) + (Update Strategy) trio collapses to one `AUTO CDC` flow — do NOT emit the lookup or change-flag logic; SDP detects changes automatically by comparing source to target on `KEYS`
- `KEYS` comes from the `<LOOKUP_CONDITION>` matching columns (here, `CUST_ID`). The `CURRENT_FLAG = 'Y'` clause is implicit in SDP's SCD2 semantics — drop it
- `SEQUENCE BY` is the timestamp ordering changes — typically `MODIFIED_DATE` / `UPDATED_AT` / `LAST_UPD`. If the source has no such column, flag the node `manual_review`
- `STORED AS SCD TYPE 2` automatically maintains `__START_AT`, `__END_AT` columns. If the original mapping wrote `EFF_START_DATE` / `EFF_END_DATE` / `CURRENT_FLAG`, downstream consumers may need to be updated to read the SDP-managed columns (note this in the IR)
- `SURROGATE_KEY` from the original mapping (typically populated by a Sequence Generator) is also managed automatically by SDP — drop the original column
- `LOCAL VARIABLE` ports (`V_CHANGE_FLAG`) are inlined into the OUTPUT port that consumes them; in this case the whole change-detection chain disappears in the SDP output because AUTO CDC handles it
- **Change-detection scope can diverge.** The original `V_CHANGE_FLAG` compared only `CUST_NAME` and `ADDRESS` — changes to `CITY` or `STATE` alone would NOT have produced a new SCD2 row. AUTO CDC treats any non-key column change as a new version. If the user needs to preserve the column-subset semantics, add `TRACK HISTORY ON (CUST_NAME, ADDRESS)` to the `CREATE FLOW` (where supported) or flag the node for `manual_review`
- If the Update Strategy includes `DD_DELETE`, add `APPLY AS DELETE WHEN <delete_signal>` — the source must carry a delete signal (operation column or `_is_deleted` flag) for this to work; flag for `manual_review` if no such column exists
