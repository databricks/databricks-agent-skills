# Streaming Tables (Python)

Streaming tables enable incremental processing of continuously arriving data. For materialized views (batch with `spark.read`), see [materialized-view-python.md](materialized-view-python.md).

## `@dp.table()` — streaming or batch depending on return type

```python
@dp.table(
    name="<name>",
    comment="<comment>",
    spark_conf={...},
    table_properties={...},
    path="<storage-location>",
    cluster_by=["<col>", ...],       # Liquid Clustering — preferred
    cluster_by_auto=True,             # let Databricks pick keys
    partition_cols=["<col>"],         # legacy, prefer cluster_by — see performance.md#liquid-clustering
    schema="col1 TYPE, ...",          # supports GENERATED ALWAYS AS, MASK clauses, PK/FK constraints
    row_filter="ROW FILTER my_catalog.my_schema.func ON (col)",   # Public Preview
    private=False,                    # True = pipeline-scoped, not published to UC
)
def my_table():
    return spark.readStream.table("source.data")     # streaming → streaming table
    # or spark.read.table(...)                        # batch → materialized view (prefer @dp.materialized_view)
```

`row_filter` notes: `func_name` must be a SQL UDF in UC returning BOOLEAN; rows are dropped when it returns FALSE/NULL. Forces full refresh of downstream MVs. Cannot define the UDF inside the pipeline.

## `dp.create_streaming_table()` — empty target for flows

Use when one target is fed by multiple `@dp.append_flow`s or by `dp.create_auto_cdc_flow()`. Call at top level; does NOT return a value.

```python
dp.create_streaming_table(
    name="<table-name>",
    cluster_by=[...],
    schema="...",
    expect_all={"name": "cond"},                # warn
    expect_all_or_drop={"name": "cond"},        # drop row
    expect_all_or_fail={"name": "cond"},        # fail update
    row_filter="...",
)
```

Same parameters as `@dp.table()` except `private`, plus the three `expect_all*` dicts.

## `@dp.append_flow()` — fan multiple sources into one table

```python
@dp.append_flow(target="<target>", name="<flow_name>", once=False)
def my_flow():
    return spark.readStream.table("source.data")    # once=False → streaming
    # or spark.read.table("archive.historical")     # once=True  → batch (one-shot)
```

- `target` (required): name of the target table (created via `dp.create_streaming_table()`).
- `name`: defaults to the function name. Use distinct names when multiple flows target the same table.
- `once=True`: one-shot batch. Use `spark.read`, NOT `cloudFiles` (Auto Loader is streaming-only).
- `spark_conf`: per-flow Spark config (e.g. `{"spark.sql.shuffle.partitions": "10"}`).

## Single source vs multi-source

- **Single source** → `@dp.table()` with `spark.readStream.*` and the transformation in the function body. Continuous processing is automatic.
- **Multi-source / AUTO CDC target** → `dp.create_streaming_table(...)` (empty target) + one `@dp.append_flow` per source (or `dp.create_auto_cdc_flow` for CDC).

Don't combine: don't have both an `@dp.table` definition AND a separate `@dp.append_flow` targeting it — the decorator already handles continuous processing, the flow is redundant.

## Common Patterns

### Auto Loader + filter

```python
@dp.table()
def bronze():
    return (spark.readStream.format("cloudFiles")
                 .option("cloudFiles.format", "json").load("/path/to/data"))

@dp.table()
def silver():
    return spark.readStream.table("bronze").filter("id IS NOT NULL")
```

### Multi-source append

```python
dp.create_streaming_table(name="all_events")

@dp.append_flow(target="all_events", name="mobile")
def mobile():
    return spark.readStream.table("mobile.events")
# Add @dp.append_flow(target="all_events", name="web") ... for additional sources.
```

### Backfill + live stream into the same table

```python
dp.create_streaming_table(name="transactions")

@dp.append_flow(target="transactions", name="live_stream")
def live_transactions():
    return spark.readStream.table("source.transactions")

@dp.append_flow(target="transactions", name="historical_backfill", once=True)
def backfill_transactions():
    return spark.read.table("archive.historical_transactions")   # batch, no cloudFiles
```

### Row filter for data security

```python
@dp.table(
    name="employees",
    schema="emp_id INT, emp_name STRING, dept STRING, salary DECIMAL(10,2)",
    row_filter="ROW FILTER my_catalog.my_schema.filter_by_dept ON (dept)",
)
def employees():
    return spark.readStream.table("source.employees")
```

### Stream-static join (enrich with dimension)

```python
@dp.table()
def enriched_transactions():
    transactions = spark.readStream.table("transactions")
    customers    = spark.read.table("customers")            # static snapshot at stream start
    return transactions.join(customers, transactions.customer_id == customers.id)
```

### Reading from a streaming table that has updates/deletes

```python
@dp.table()
def downstream():
    return spark.readStream.option("skipChangeCommits", "true").table("upstream_with_deletes")
```

Without `skipChangeCommits`, update/delete commits on the upstream (e.g. GDPR purges, Auto CDC targets) cause errors.

## Key rules

- Streaming tables use `spark.readStream`; MVs use `spark.read`.
- Never `.writeStream`, `.start()`, or pass checkpoint options — Databricks manages them.
- Generated columns, masks, and PK/FK constraints require an explicit `schema=`.
- Row filters on source tables force full refresh of downstream MVs.
