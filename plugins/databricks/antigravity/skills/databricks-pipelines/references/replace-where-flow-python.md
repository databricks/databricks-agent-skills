REPLACE WHERE flows in Spark Declarative Pipelines surgically recompute and overwrite a subset of a streaming table via a batch operation. Each refresh logically deletes rows in the target that match the predicate, re-evaluates the source DataFrame for that range, and inserts the new results. The rest of the table is untouched. They are useful for late-arriving data, upstream reprocessing, schema evolution, and rolling-window or partition-style refreshes — without streaming semantics like watermarks. Reach for a REPLACE WHERE flow only when each run overwrites a bounded recent window (e.g. the last N days, including to absorb late-arriving data); when the full result must stay consistent with the source rather than just a recent window, use a materialized view instead.

**API Reference:**

**@dp.table(replace_where=...) / @dlt.table(replace_where=...)** Defines a streaming table whose refresh is a REPLACE WHERE flow. The flow inherits the table's name.

```python
@dp.table(
    name="<target_table>",
    replace_where=<predicate>,
)
def <target_table>():
    return <DataFrame>
```

Parameters:

- `name` (str, optional): Target streaming table name. Defaults to the function name. The table is managed by this pipeline — you cannot point REPLACE WHERE at a table created outside this pipeline.
- `replace_where` (str | Column): Boolean predicate identifying the subset of rows to overwrite. **Required.** Accepts a string predicate (e.g. `"date >= date_add(current_date(), -7)"`) or a PySpark `Column` expression (e.g. `col("date") >= date_sub(current_date(), 7)`). Prefer base columns over aggregates / window outputs — base-column predicates push down into the source read.

The function returns the source DataFrame. You do NOT need to add the predicate to the DataFrame — the REPLACE WHERE predicate is automatically applied during refresh.

**Common Patterns:**

**Pattern 1: Rolling window refresh — string predicate**

```python
@dp.table(
    name="orders_enriched",
    replace_where="date >= date_add(current_timestamp(), -7)",
)
def orders_enriched():
    orders = spark.read.table("orders_fct").select(
        "order_id", "date", "region", "product_id", "qty", "price"
    )
    products = spark.read.table("product_dim")
    return orders.join(products, "product_id")
```

**Pattern 2: Rolling window refresh — Column expression predicate**

```python
from pyspark.sql import functions as F
from pyspark.sql.functions import col


@dp.table(
    replace_where=col("date") >= F.date_sub(F.current_date(), 7),
)
def orders_enriched():
    orders = spark.read.table("orders_fct")
    products = spark.read.table("product_dim")
    return orders.join(products, "product_id")
```

**Pattern 3: Unlimited-retention aggregate over a limited-retention source**

```python
@dp.table(
    name="events_agg",
    replace_where="date >= date_add(current_date(), -3)",
)
def events_agg():
    return (
        spark.read.table("events_raw")
        .groupBy("date", "key")
        .agg(F.sum("val").alias("agg"))
    )
```

**Pattern 4: Prevent recomputation when a dimension table changes**

```python
@dp.table(
    name="fact_dim_join",
    replace_where="date >= date_add(current_date(), -1)",
)
def fact_dim_join():
    facts = spark.read.table("fact_table")
    dims = spark.read.table("dim_users")
    return facts.join(dims, "user_id").select(
        facts["date"], facts["user_id"], dims["region"], facts["revenue"]
    )
# A change in dim_users.region only affects fact rows in the last 1 day.
# Older rows keep their previous region until a backfill is run.
```

**Pattern 5: Compound predicate on two columns**

Use `AND` to scope the refresh window by both a time range and a categorical value — useful when reprocessing a specific segment (e.g. a region with bad data) without touching the rest of the table.

String predicate form:

```python
@dp.table(
    name="regional_orders_daily",
    replace_where="date >= date_add(current_date(), -7) AND region = 'us-west'",
)
def regional_orders_daily():
    return (
        spark.read.table("orders")
        .groupBy("date", "region", "product_id")
        .agg(F.sum("amount").alias("total"))
    )
```

Column expression form:

```python
@dp.table(
    name="regional_orders_daily",
    replace_where=(col("date") >= F.date_sub(F.current_date(), 7)) & (col("region") == "us-west"),
)
def regional_orders_daily():
    return (
        spark.read.table("orders")
        .groupBy("date", "region", "product_id")
        .agg(F.sum("amount").alias("total"))
    )
```

The engine pushes both conditions into the source read — only rows matching both `date` and `region` are scanned and replaced.

**Pattern 6: Block full refresh on a table**

A `FULL REFRESH` clears the table and re-runs the flow with its current predicate, which can shrink the table to just the predicate window. To prevent this:

```python
@dp.table(
    name="orders_enriched",
    table_properties={"pipelines.reset.allowed": "false"},
    replace_where="date >= date_add(current_timestamp(), -7)",
)
def orders_enriched():
    return spark.read.table("orders_fct").join(
        spark.read.table("product_dim"), "product_id"
    )
```

**Pattern 7: Aggregate with a "recompute the last N days" window**

When the requirement combines an aggregate ("sum per property per month") with a precise "recompute only the last N days" window, scope `replace_where` on the **raw event-date column** (`check_in`), and keep that column in the table grain so the predicate can target it. Aggregating only by a coarse bucket (e.g. `month`) leaves no day-level column to predicate on, forcing a `month`-bucket predicate that recomputes whole months instead of the last N days.

```python
@dp.table(
    name="property_revenue",
    replace_where="check_in >= date_add(current_date(), -7)",
)
def property_revenue():
    bookings = spark.read.table("bookings")
    properties = spark.read.table("properties")
    return (
        bookings.join(properties, "property_id")
        # group by check_in (day grain) so replace_where scopes exactly the last 7 days
        .groupBy("property_id", "title", "check_in")
        .agg(F.sum("total_amount").alias("revenue"))
    )
```

For a per-month rollup, build a downstream Materialized View over this table; do not collapse to a month bucket here (e.g. `replace_where` on `month >= date_trunc('month', date_add(current_date(), -7))`), which recomputes whole months instead of the last 7 days.

**Pattern 8: Convert a Materialized View when schema evolution triggers full recompute**

A user has a daily aggregate Materialized View. **Adding a new column to the MV definition triggers a full recompute of all history** (e.g. from `2024-01-01` onward) — that one-time cost is too expensive. They only need the new column populated on **future** refreshes and are fine leaving older rows `NULL`. Source data can arrive up to **one week** late.

Before — Materialized View (schema change forces a full historical recompute):

```python
@dp.materialized_view(name="daily_revenue_by_region")
def daily_revenue_by_region():
    orders = spark.read.table("orders")
    customers = spark.read.table("customers")
    products = spark.read.table("products")
    return (
        orders.join(customers, "customer_id")
        .join(products, "product_id")
        .where(F.col("order_date") >= F.lit("2024-01-01"))
        .groupBy("order_date", "region", "category")
        .agg(
            F.sum(F.col("qty") * F.col("price")).alias("revenue"),
            F.count("*").alias("order_count"),
        )
    )
```

After — REPLACE WHERE flow (overwrite at most the last 7 days; history outside the window is untouched):

```python
@dp.table(
    name="daily_revenue_by_region",
    table_properties={"pipelines.reset.allowed": "false"},
    replace_where="order_date >= date_add(current_date(), -7)",
)
def daily_revenue_by_region():
    orders = spark.read.table("orders")
    customers = spark.read.table("customers")
    products = spark.read.table("products")
    return (
        orders.join(customers, "customer_id")
        .join(products, "product_id")
        .groupBy("order_date", "region", "category")
        .agg(
            F.sum(F.col("qty") * F.col("price")).alias("revenue"),
            F.count("*").alias("order_count"),
        )
    )
# Adding a new column recomputes at most the last 7 days; older rows keep NULL until backfilled via DML.
```

This is a good conversion because `order_date` appears in the `groupBy`, a 7-day lookback comfortably covers late-arriving records, and the bounded overwrite aligns with the user's tolerance for `NULL` values on historical rows. Do not repeat the `order_date >= …` condition in a DataFrame filter — the `replace_where` predicate is pushed down automatically. Note that reusing the same name for the REPLACE WHERE flow as the previous materialized view requires dropping the existing materialized view table first. Also be aware that dropping the MV and creating a fresh streaming table means the first refresh will only populate the last 7 days of data — months of existing aggregates are not preserved automatically, so a backfill is required if that history needs to be retained.

---

## Backfills

For a one-time backfill or correction, do NOT change the table definition — a single pipeline update can override the REPLACE WHERE predicate just for that run, without persisting the change or affecting future runs. Start the update with `"replace_where_overrides": [{"flow_name": "<flow name>", "predicate_override": "<predicate>"}]` in the request body.

---

## Incremental refresh (Serverless pipelines only)

On serverless compute, even when your replace-where window covers the last N days, Databricks automatically figures out what actually changed in your source tables since the last run and reprocesses only those rows — not the entire N-day window every time. For example, with a daily flow and predicate `check_in >= date_add(current_date(), -7)`: if only today's rows changed, Databricks reprocesses just today's data. The previous 6 days of results already in the target stay exactly as they are.

This happens with no extra configuration. If Databricks can't determine what changed (see below), it falls back to scanning the full window. Results are always correct either way — the fast path just saves compute. Even when a refresh is not incremental, REPLACE WHERE still only overwrites rows in the replace window — anything outside the predicate is left untouched.

### When incremental refresh applies

All three conditions must hold:

- The pipeline runs on **Serverless**.
- The query shape is supported (no unsupported operators in the DataFrame transformations).
- The REPLACE WHERE predicate is eligible (see below).

Do not tell users "serverless means only changed rows are reprocessed" without all these conditions being met.

### Making predicates incrementalizable

The predicate must satisfy all four conditions:

1. **Pushable to a source.** The predicate must reference a column from a source table directly — not a derived value (aggregate, window function, etc.). A predicate on a computed column (e.g. the output of `.agg(...)`) cannot be evaluated until after the aggregation, so it cannot be pushed to the source and disables incremental refresh for that run. The `replace_where` predicate references output columns, so keep pass-through source columns in the output when you want pushdown/incrementalization.

2. **No external DMLs in the window.** If DML was run directly on the target table touching rows in the current window, that refresh falls back once; subsequent refreshes return to the incremental path.

3. **No missing rows from the previous window.** Incremental refresh is ineligible when the current window covers rows the previous refresh excluded. This passes automatically for rolling predicates (e.g. `check_in >= date_add(current_date(), -7)`) — the previous run already covered everything the current run covers. It fails when the predicate is widened backward into history; that one refresh falls back, then subsequent runs return to incremental.

4. **Deterministic predicate.** Temporal functions (`current_date()`, `current_timestamp()`) are fine. `rand()` or random UUIDs disable incremental refresh.

### Best practices for incrementalizable queries

**Prefer open-ended ranges (`>=`) over closed ranges (`AND ... <=`).** A lower-bound-only predicate stays on the incremental fast path indefinitely. A closed upper bound like `AND date <= current_date()` moves each day, which can re-introduce previously excluded rows and trigger a one-off full recomputation of the window:

```python
# Incremental-friendly: open lower bound
@dp.table(replace_where="date >= date_add(current_date(), -7)")

# Can trigger a one-off fallback: upper bound moves each day
@dp.table(replace_where="date >= date_add(current_date(), -7) AND date <= current_date()")
```

**Include the predicate column in the groupBy.** For aggregations, including the predicate column in `groupBy` lets incremental refresh push the predicate below the aggregation — only the rows in the changed window are scanned:

```python
# Incremental refresh can push predicate below aggregation: check_in in groupBy
@dp.table(replace_where="check_in >= date_add(current_date(), -7)")
def property_revenue():
    return (
        spark.read.table("bookings")
        .join(spark.read.table("properties"), "property_id")
        .groupBy("property_id", "title", "check_in")  # check_in in groupBy
        .agg(F.sum("total_amount").alias("revenue"))
    )

# Incremental refresh must aggregate over full source: check_in not in groupBy
@dp.table(replace_where="check_in >= date_add(current_date(), -7)")
def property_revenue():
    return (
        spark.read.table("bookings")
        .join(spark.read.table("properties"), "property_id")
        .groupBy("property_id", "title")  # check_in dropped, predicate cannot push down
        .agg(F.sum("total_amount").alias("revenue"))
    )
```

**For joins, expose the predicate column to all sources.** Incremental refresh pushes the predicate to whichever sources expose it. Joining on the predicate column lets incremental refresh prune both sides of the join:

```python
# Incremental refresh prunes both sides: date is in the join key
@dp.table(replace_where="date >= date_add(current_date(), -7)")
def enriched_facts():
    facts = spark.read.table("fact_table")
    dims = spark.read.table("dim_users")
    return facts.join(dims, ["date", "user_id"])
```

**For window functions, include the predicate column in `partitionBy`.** A predicate can be pushed below a window only when its column is part of the window partition. A column used only in `orderBy` is not sufficient: filtering it first can change the rows in a partition and therefore change the window result.

```python
from pyspark.sql.window import Window


# Incremental refresh can push the predicate: transaction_date is in the window partition
@dp.table(replace_where="transaction_date >= date_add(current_date(), -7)")
def latest_transactions_by_date():
    window_spec = Window.partitionBy("transaction_id", "transaction_date").orderBy(
        F.col("event_ts").desc()
    )
    return (
        spark.read.table("transactions")
        .withColumn("_row_number", F.row_number().over(window_spec))
        .where(F.col("_row_number") == 1)
        .drop("_row_number")
    )


# Incremental refresh cannot push the predicate: transaction_date is only an ordering column
@dp.table(replace_where="transaction_date >= date_add(current_date(), -7)")
def latest_transactions():
    window_spec = Window.partitionBy("transaction_id").orderBy(F.col("transaction_date").desc())
    return (
        spark.read.table("transactions")
        .withColumn("_row_number", F.row_number().over(window_spec))
        .where(F.col("_row_number") == 1)
        .drop("_row_number")
    )
```

### Diagnose fallback to full recomputation

When a refresh falls back to full recomputation, the `planning_information` event reports the reason. Common values:

- `EXTERNAL_CHANGE_IN_REPLACE_WINDOW`: An external DML modified rows in the current replace window.
- `REPLACE_WHERE_NOT_DETERMINISTIC`: The current predicate uses non-deterministic expressions.
- `PRIOR_REPLACE_WHERE_NOT_DETERMINISTIC`: The previous refresh used a non-deterministic predicate, so the previous window cannot be replayed.
- `STALE_TARGET_DATA_IN_WINDOW`: The replace-where window expanded. Incrementalization is blocked when either (1) the **target** already has stale data in the expanded region (e.g., from an earlier refresh with a wider predicate — incremental refresh would leave those rows untouched), or (2) the predicate changed across updates and the new window includes rows that were excluded by the previous predicate and were never written to the target (the target is differentially stale — incremental refresh cannot compute correct deltas).
- `CANNOT_PUSH_PREDICATE`: The replace where predicate could not be pushed down to at least one source, so a full scan would be required on that source to determine which rows fall inside the replace window.
- `REPLACE_WHERE_BACKFILL`: The update is a backfill (one-off predicate override) used to populate historical data or correct prior writes, rather than a refresh of the configured replace where window. Backfills run as a full recompute over the override predicate.

---

**Best Practices:**

- **Predicate on base columns, not aggregates or window outputs.** A predicate on `date` is pushed down so the engine reads only the relevant subset. A predicate on a derived value cannot be pushed down and forces a full recompute every refresh.
- **Scope a "last N days" window on the raw date column, not a truncated bucket.** The predicate is evaluated against the *target* table, so the column must exist there. When the requirement is "recompute the last N days", keep the raw event-date column at the table's grain and scope it directly — `replace_where="check_in >= date_add(current_date(), -7)"`. Do NOT collapse the date into a coarser bucket and predicate on that — e.g. `replace_where="booking_month >= date_trunc('month', date_add(current_date(), -7))"` recomputes whole months, overshoots the requested 7-day window, and only works if the table is month-grained. If you aggregate per month, retain the raw date column so the day-level predicate still applies.
- **Pick the refresh window deliberately.** Cover all expected late-arriving data and reprocessing, but no more — the predicate range determines how much data each refresh rebuilds.
- **Block full refresh if history would be lost.** Set `table_properties={"pipelines.reset.allowed": "false"}` when a full refresh would shrink the table to just the predicate window.

---

**KEY RULES:**

- `replace_where` accepts a string predicate or a `Column` expression. Both are valid.
- Do NOT add the REPLACE WHERE predicate to the DataFrame returned by the function — it is applied automatically during refresh.
- The target table must be created inside this pipeline. You cannot target an externally created table.
- One REPLACE WHERE flow per target. The target cannot also be the target of an AUTO CDC or APPEND flow — multiflow is not supported for REPLACE WHERE.
- Expectations are not supported on tables that are the target of a REPLACE WHERE flow.
- For a one-time backfill, override the predicate for a single update instead of editing the table definition (see Backfills above).
