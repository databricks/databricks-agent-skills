# Migration Guide: DLT → SDP

Two migration paths:

1. **DLT Python → SDP Python** (`dlt` → `dp`): same language, new API.
2. **DLT Python → SDP SQL**: convert to SQL when the logic is mostly relational.

If 80%+ of the pipeline is SQL-expressible (filters, aggregations, joins, CDC, Auto Loader), prefer SDP SQL. Stay in Python when there are complex UDFs, external API calls, custom libraries, or ML inference.

---

## Migration Path 1: DLT Python → SDP Python

### Mapping

| Concept | Legacy (`dlt`) | Modern (`dp`) |
|---------|---------------|---------------|
| Import | `import dlt` | `from pyspark import pipelines as dp` |
| Streaming table | `@dlt.table()` returning streaming DF | `@dp.table()` returning streaming DF |
| Materialized view | `@dlt.table()` returning batch DF | `@dp.materialized_view()` (preferred) |
| Temporary view | `@dlt.view()` | `@dp.temporary_view()` |
| Read batch | `dlt.read("t")` | `spark.read.table("t")` |
| Read stream | `dlt.read_stream("t")` | `spark.readStream.table("t")` |
| Expectations | `@dlt.expect*` | `@dp.expect*` (same names) |
| CDC | `dlt.apply_changes(...)` | `dp.create_auto_cdc_flow(...)` |
| Snapshot CDC | `dlt.apply_changes_from_snapshot(...)` | `dp.create_auto_cdc_from_snapshot_flow(...)` |
| Create empty target | `dlt.create_streaming_table(...)` | `dp.create_streaming_table(...)` |
| Partitioning | `partition_cols=["date"]` | `cluster_by=["date", ...]` (Liquid Clustering) |
| File metadata | `input_file_name()` | `F.col("_metadata.file_path")` |
| Pipeline target | `target=` parameter | `schema=` parameter |
| Read-source prefix | `LIVE.<name>` | Bare name (modern pipelines reject `LIVE.`) |

### Behavioral changes to watch for in CDC

- `apply_changes(...)` → `create_auto_cdc_flow(...)`. Same parameters EXCEPT:
  - `sequence_by` accepts string OR `col(...)`; either works.
  - `stored_as_scd_type` is **integer `2`** for Type 2, **string `"1"`** for Type 1.

```python
# Legacy
dlt.apply_changes(target="dim_customers", source="customers_cdc",
                  keys=["customer_id"], sequence_by="updated_at",
                  stored_as_scd_type="2")

# Modern
dp.create_auto_cdc_flow(target="dim_customers", source="customers_cdc",
                        keys=["customer_id"], sequence_by=F.col("updated_at"),
                        stored_as_scd_type=2)
```

---

## Migration Path 2: DLT Python → SDP SQL

### Streaming table with Auto Loader

```python
# DLT Python
@dlt.table(name="bronze_sales", comment="Raw sales")
def bronze_sales():
    return (spark.readStream.format("cloudFiles")
                 .option("cloudFiles.format", "json")
                 .load("/Volumes/cat/sch/raw/sales")
                 .withColumn("_ingested_at", F.current_timestamp()))
```

```sql
-- SDP SQL
CREATE OR REFRESH STREAMING TABLE bronze_sales
COMMENT 'Raw sales' AS
SELECT *, current_timestamp() AS _ingested_at
FROM STREAM read_files('/Volumes/cat/sch/raw/sales', format => 'json');
```

### Filter / cast / select

DLT Python `dlt.read_stream("bronze_sales").withColumn("amount", ...cast("decimal(10,2)")).filter(...)` becomes:

```sql
CREATE OR REFRESH STREAMING TABLE silver_sales AS
SELECT sale_id, customer_id,
       CAST(amount AS DECIMAL(10,2)) AS amount,
       CAST(sale_date AS DATE) AS sale_date
FROM STREAM(bronze_sales)
WHERE amount > 0 AND sale_id IS NOT NULL;
```

### SCD Type 2

```sql
CREATE OR REFRESH STREAMING TABLE customers_history;

CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO customers_history
FROM STREAM(customers_cdc_clean)
KEYS (customer_id)
APPLY AS DELETE WHEN operation = 'DELETE'
SEQUENCE BY event_timestamp
COLUMNS * EXCEPT (operation, _ingested_at, _source_file)
STORED AS SCD TYPE 2;
```

Put `APPLY AS DELETE WHEN` **before** `SEQUENCE BY`. Only list columns in `COLUMNS * EXCEPT (...)` that exist in the source — `_rescued_data` should only appear if bronze uses rescue data.

### Expectations

Three options for `@dlt.expect_or_drop("valid_amount", "amount > 0")`:

```sql
-- 1. Constraint (closest equivalent, with metrics)
CREATE OR REFRESH STREAMING TABLE silver_sales (
  CONSTRAINT valid_amount EXPECT (amount > 0) ON VIOLATION DROP ROW
) AS SELECT * FROM STREAM(bronze_sales);

-- 2. WHERE filter (no metrics, simplest)
... WHERE amount > 0

-- 3. Quarantine pattern (full audit trail; route bad rows to a side table) —
-- see streaming-patterns.md#rescue-data-quarantine
```

### UDFs

Simple UDFs (categorisation, math) translate to SQL `CASE`:

```sql
SELECT *,
  CASE WHEN amount > 1000 THEN 'High'
       WHEN amount > 100  THEN 'Medium'
       ELSE 'Low' END AS category
FROM sales;
```

Keep complex UDFs (external APIs, custom algorithms, ML inference) in Python with the modern `dp` API.

---

## Migration Order (by layer)

1. **Bronze (ingestion)** — `cloudFiles` → `read_files()` (or keep `cloudFiles` with `dp`).
2. **Silver (cleansing)** — `dlt.expect*` → WHERE clause or `dp.expect*`.
3. **Gold (aggregations)** — usually straightforward port.
4. **CDC/SCD** — `apply_changes(...)` → `AUTO CDC INTO` (SQL) or `dp.create_auto_cdc_flow(...)` (Python).

Run old and new in parallel during cutover and diff outputs before retiring the old pipeline.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| `sequence_by` type error | Both string and `col("column")` work — confirm the column exists in the source. |
| `stored_as_scd_type` rejected | Integer `2` for Type 2, string `"1"` for Type 1. Don't quote `2`. |
| UDF doesn't translate cleanly | Keep in Python, or refactor into SQL built-ins. |
| Performance regressed | Replace `partition_cols` with `cluster_by` (Liquid Clustering). |
| Schema evolution different | Use `mode => 'PERMISSIVE'` in `read_files()` or rely on rescued-data column. |
| `AUTO CDC` parse error at `APPLY` | Put `APPLY AS DELETE WHEN` before `SEQUENCE BY`. |

---

## Related

- [python-basics.md](python-basics.md) — modern `dp` API reference
- [auto-cdc-python.md](auto-cdc-python.md) / [auto-cdc-sql.md](auto-cdc-sql.md) — full CDC API
- [SKILL.md](../SKILL.md#legacy-dlt-syntax--always-migrate) — Legacy DLT Syntax mapping table
