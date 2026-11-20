REPLACE WHERE flows in Spark Declarative Pipelines surgically recompute and overwrite a subset of a streaming table via a batch operation. Each refresh logically deletes rows in the target that match the predicate, re-evaluates the SELECT for that range, and inserts the new results. The rest of the table is untouched. They are useful for late-arriving data, upstream reprocessing, schema evolution, and rolling-window or partition-style refreshes — without streaming semantics like watermarks. Reach for a REPLACE WHERE flow only when each run overwrites a bounded recent window (e.g. the last N days, including to absorb late-arriving data); when the full result must stay consistent with the source rather than just a recent window, use a materialized view instead.

**API Reference:**

**Inline syntax (preferred):** The target table and flow are defined together. The flow inherits the table's name.

```sql
CREATE STREAMING TABLE <target_table>
FLOW REPLACE WHERE <predicate> BY NAME
SELECT ...;
```

**Long form (`CREATE FLOW`):** Equivalent to the inline form. Useful when you want to declare the target separately or pair multiple flow-related statements next to a table.

```sql
CREATE STREAMING TABLE <target_table>;

CREATE FLOW <flow_name> AS
INSERT INTO <target_table> BY NAME
REPLACE WHERE <predicate>
SELECT ...;
```

Parameters:

- `<target_table>` (identifier): Streaming table managed by this pipeline. Must be defined inside this pipeline — you cannot point a REPLACE WHERE flow at a table created outside of it. **Required.**
- `<predicate>` (boolean expression): The subset of rows to overwrite. Evaluated against the target table; the same predicate is automatically pushed into the source query for the refresh. Prefer base columns (e.g. `date`) over aggregates or window outputs. **Required.**
- `BY NAME`: Required. Columns from the SELECT are matched to the target by column name, not position.
- `<flow_name>` (identifier, long form only): Identifier for the standalone flow. **Required for `CREATE FLOW` syntax.**

**Common Patterns:**

**Pattern 1: Rolling window refresh**

```sql
CREATE STREAMING TABLE orders_enriched
FLOW REPLACE WHERE date >= date_add(current_timestamp(), -7) BY NAME
SELECT
  o.order_id, o.date, o.region, p.product_name, o.qty, o.price
FROM orders_fct o
JOIN product_dim p ON o.product_id = p.product_id;
```

**Pattern 2: Long form with separate target declaration**

```sql
CREATE STREAMING TABLE orders_enriched;

CREATE FLOW orders_enriched AS
INSERT INTO orders_enriched BY NAME
REPLACE WHERE date >= date_add(current_timestamp(), -7)
SELECT
  o.order_id, o.date, o.region, p.product_name, o.qty, o.price
FROM orders_fct o
JOIN product_dim p ON o.product_id = p.product_id;
```

**Pattern 3: Unlimited-retention aggregate over a limited-retention source**

```sql
CREATE STREAMING TABLE events_agg
FLOW REPLACE WHERE date >= date_add(current_date(), -3) BY NAME
SELECT date, key, SUM(val) AS agg
FROM events_raw
GROUP BY ALL;
```

**Pattern 4: Prevent recomputation when a dimension table changes**

```sql
CREATE STREAMING TABLE fact_dim_join
FLOW REPLACE WHERE date >= date_add(current_date(), -1) BY NAME
SELECT f.date, f.user_id, d.region, f.revenue
FROM fact_table f
JOIN dim_users d ON f.user_id = d.user_id;
-- A change in dim_users.region only affects fact rows in the last 1 day.
-- Older rows keep their previous region until a backfill is run.
```

**Pattern 5: Evolve the table schema without recomputing all history**

```sql
CREATE STREAMING TABLE clickstream_daily
FLOW REPLACE WHERE event_date >= date_add(current_date(), -7) BY NAME
SELECT
  event_date,
  page_id,
  COUNT(*) AS clicks,
  COUNT(DISTINCT user_id) AS uniq_users
FROM clickstream_raw
GROUP BY ALL;
-- uniq_users populates for the last 7 days going forward.
-- Older rows have NULL for uniq_users until a backfill is run.
```

**Pattern 6: Compound predicate on two columns**

Use `AND` to scope the refresh window by both a time range and a categorical value — useful when reprocessing a specific segment (e.g. a region with bad data) without touching the rest of the table:

```sql
CREATE STREAMING TABLE regional_orders_daily
FLOW REPLACE WHERE date >= date_add(current_date(), -7) AND region = 'us-west' BY NAME
SELECT date, region, product_id, SUM(amount) AS total
FROM orders
GROUP BY date, region, product_id;
```

The engine pushes both conditions into the source read — only rows matching both `date` and `region` are scanned and replaced.

**Pattern 7: Block full refresh on a table**

A `FULL REFRESH` clears the table and re-runs the flow with its current predicate, which can shrink the table to just the predicate window. To prevent this:

```sql
CREATE STREAMING TABLE orders_enriched
TBLPROPERTIES(pipelines.reset.allowed = "false")
FLOW REPLACE WHERE date >= date_add(current_timestamp(), -7) BY NAME
SELECT ...;
```

**Pattern 8: Aggregate with a "recompute the last N days" window**

When the requirement combines an aggregate ("sum per property per month") with a precise "recompute only the last N days" window, scope the predicate on the **raw event-date column** (`check_in`), and keep that column in the table grain so the predicate can target it. Aggregating only by a coarse bucket (e.g. a truncated `booking_month`) leaves no day-level column to predicate on, forcing a month-bucket predicate that recomputes whole months instead of the last N days.

```sql
CREATE STREAMING TABLE property_revenue
FLOW REPLACE WHERE check_in >= date_add(current_date(), -7) BY NAME
SELECT p.title AS property_name, b.check_in, SUM(b.total_amount) AS revenue
FROM bookings b
JOIN properties p ON b.property_id = p.property_id
-- group by check_in (day grain) so REPLACE WHERE scopes exactly the last 7 days
GROUP BY p.title, b.check_in;
```

For a per-month rollup, build a downstream Materialized View over this table; do not GROUP BY a truncated month bucket and predicate on it (e.g. `REPLACE WHERE booking_month >= date_trunc('month', date_add(current_date(), -7))`), which recomputes whole months instead of the last 7 days.

**Pattern 9: Convert a Materialized View when schema evolution triggers full recompute**

A user has a daily aggregate Materialized View. **Adding a new column to the MV definition triggers a full recompute of all history** (e.g. from `2024-01-01` onward) — that one-time cost is too expensive. They only need the new column populated on **future** refreshes and are fine leaving older rows `NULL`. Source data can arrive up to **one week** late.

Before — Materialized View (schema change forces a full historical recompute):

```sql
CREATE OR REFRESH MATERIALIZED VIEW daily_revenue_by_region AS
SELECT
  o.order_date,
  c.region,
  p.category,
  SUM(o.qty * o.price) AS revenue,
  COUNT(*) AS order_count
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN products p ON o.product_id = p.product_id
WHERE o.order_date >= DATE '2024-01-01'
GROUP BY o.order_date, c.region, p.category;
```

After — REPLACE WHERE flow (overwrite at most the last 7 days; history outside the window is untouched):

```sql
CREATE STREAMING TABLE daily_revenue_by_region
TBLPROPERTIES(pipelines.reset.allowed = "false")
FLOW REPLACE WHERE order_date >= date_add(current_date(), -7) BY NAME
SELECT
  o.order_date,
  c.region,
  p.category,
  SUM(o.qty * o.price) AS revenue,
  COUNT(*) AS order_count
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN products p ON o.product_id = p.product_id
GROUP BY o.order_date, c.region, p.category;
-- Adding a new column recomputes at most the last 7 days; older rows keep NULL until backfilled via DML.
```

This is a good conversion because `order_date` appears in the `GROUP BY`, a 7-day lookback comfortably covers late-arriving records, and the bounded overwrite aligns with the user's tolerance for `NULL` values on historical rows. Do not repeat the `order_date >= …` condition in the `WHERE` clause — the `FLOW REPLACE WHERE` predicate is pushed down automatically. Note that reusing the same name for the REPLACE WHERE flow as the previous materialized view requires dropping the existing materialized view table first. Also be aware that dropping the MV and creating a fresh streaming table means the first refresh will only populate the last 7 days of data — months of existing aggregates are not preserved automatically, so a backfill is required if that history needs to be retained.

---

## Backfills

For a one-time backfill or correction, do NOT change the table definition — a single pipeline update can override the REPLACE WHERE predicate just for that run, without persisting the change or affecting future runs. Start the update with `"replace_where_overrides": [{"flow_name": "<flow name>", "predicate_override": "<predicate>"}]` in the request body.

---

## Incremental refresh (Serverless pipelines only)

On serverless compute, even when your replace-where window covers the last N days, Databricks automatically figures out what actually changed in your source tables since the last run and reprocesses only those rows — not the entire N-day window every time. For example, with a daily flow and predicate `date >= date_add(current_date(), -7)`: if only today's rows changed, Databricks reprocesses just today's data. The previous 6 days of results already in the target stay exactly as they are.

This happens with no extra configuration. If Databricks can't determine what changed (see below), it falls back to scanning the full window. Results are always correct either way — the fast path just saves compute. Even when a refresh is not incremental, REPLACE WHERE still only overwrites rows in the replace window — anything outside the predicate is left untouched.

### When incremental refresh applies

All three conditions must hold:

- The pipeline runs on **Serverless**.
- The query shape is supported (no unsupported operators in the SELECT).
- The REPLACE WHERE predicate is eligible (see below).

Do not tell users "serverless means only changed rows are reprocessed" without all these conditions being met.

### Making predicates incrementalizable

The predicate must satisfy all four conditions:

1. **Pushable to a source.** The predicate must reference a column from a source table directly — not a derived value (aggregate, window function, etc.). A predicate on `total_sales > 100000` (an aggregate output) cannot be evaluated until after the aggregation, so it cannot be pushed to the source and disables incremental refresh for that run.

2. **No external DMLs in the window.** If DML was run directly on the target table touching rows in the current window, that refresh falls back once; subsequent refreshes return to the incremental path.

3. **No missing rows from the previous window.** Incremental refresh is ineligible when the current window covers rows the previous refresh excluded. This passes automatically for rolling predicates (e.g. `date >= current_date() - 7`) — the previous run already covered everything the current run covers. It fails when the predicate is widened backward into history; that one refresh falls back, then subsequent runs return to incremental.

4. **Deterministic predicate.** Temporal functions (`current_date()`, `current_timestamp()`) are fine. `rand()` or random UUIDs disable incremental refresh.

### Best practices for incrementalizable queries

**Prefer open-ended ranges (`date >=`) over closed ranges (`date BETWEEN`).** A lower-bound-only predicate stays on the incremental fast path indefinitely. A closed range like `BETWEEN date_add(current_date(), -7) AND current_date()` moves the upper bound each day, which can re-introduce previously excluded rows and trigger a one-off full recomputation of the window:

```sql
-- Incremental-friendly: open lower bound
FLOW REPLACE WHERE date >= date_add(current_date(), -7) BY NAME

-- Can trigger a one-off fallback: upper bound moves each day
FLOW REPLACE WHERE date BETWEEN date_add(current_date(), -7) AND current_date() BY NAME
```

**Include the predicate column in GROUP BY.** For aggregations, including the predicate column in `GROUP BY` lets incremental refresh push the predicate below the aggregation — only the rows in the changed window are scanned:

```sql
-- Incremental refresh can push predicate below aggregation: date in GROUP BY
FLOW REPLACE WHERE date >= date_add(current_date(), -7) BY NAME
SELECT date, region, SUM(amount) AS total
FROM sales
GROUP BY date, region;

-- Incremental refresh must aggregate over the full source: date not in GROUP BY
FLOW REPLACE WHERE date >= date_add(current_date(), -7) BY NAME
SELECT region, SUM(amount) AS total
FROM sales
GROUP BY region;
```

**For joins, expose the predicate column to all sources.** Incremental refresh pushes the predicate to whichever sources expose it. Joining on the predicate column lets incremental refresh prune both sides of the join:

```sql
-- Incremental refresh prunes both sides: date is in the join key
FLOW REPLACE WHERE date >= date_add(current_date(), -7) BY NAME
SELECT f.date, f.user_id, d.region, f.revenue
FROM fact f
JOIN dim d ON f.date = d.date AND f.user_id = d.user_id;
```

**For window functions, include the predicate column in `PARTITION BY`.** A predicate can be pushed below a window only when its column is part of the window partition. A column used only in `ORDER BY` is not sufficient: filtering it first can change the rows in a partition and therefore change the window result.

```sql
-- Incremental refresh can push the predicate: transaction_date is in the window partition
CREATE STREAMING TABLE latest_transactions_by_date
FLOW REPLACE WHERE transaction_date >= date_add(current_date(), -7) BY NAME
SELECT transaction_id, transaction_date, customer_id, amount, event_ts, source_version
FROM transactions
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY transaction_id, transaction_date
  ORDER BY event_ts DESC
) = 1;

-- Incremental refresh cannot push the predicate: transaction_date is only an ordering column
CREATE STREAMING TABLE latest_transactions
FLOW REPLACE WHERE transaction_date >= date_add(current_date(), -7) BY NAME
SELECT transaction_id, transaction_date, customer_id, amount, event_ts, source_version
FROM transactions
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY transaction_id
  ORDER BY transaction_date DESC
) = 1;
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

- **Predicate on base columns, not aggregates or window outputs.** A predicate on `date` is pushed down so the engine reads only the relevant subset. A predicate on `total_sales > 100000` cannot be evaluated until after the aggregation, forcing a full recompute every refresh.
- **Scope a "last N days" window on the raw date column, not a truncated bucket.** The predicate is evaluated against the *target* table, so the column must exist there. When the requirement is "recompute the last N days", keep the raw event-date column at the table's grain and scope it directly — `FLOW REPLACE WHERE check_in >= date_add(current_date(), -7) BY NAME`. Do NOT collapse the date into a coarser bucket and predicate on that — e.g. `REPLACE WHERE booking_month >= date_trunc('month', date_add(current_date(), -7))` recomputes whole months, overshoots the requested 7-day window, and only works if the table is month-grained. If you aggregate per month, retain the raw date column so the day-level predicate still applies.
- **Pick the refresh window deliberately.** Cover all expected late-arriving data and reprocessing, but no more — the predicate range determines how much data each refresh rebuilds.
- **Block full refresh if history would be lost.** Set `pipelines.reset.allowed = "false"` when a full refresh would shrink the table to just the predicate window.

---

**KEY RULES:**

- `BY NAME` is required for both inline and `CREATE FLOW` forms.
- Do NOT add the REPLACE WHERE predicate to the SELECT — it is applied automatically.
- The target table must be created inside this pipeline. You cannot target an externally created table.
- One REPLACE WHERE flow per target. The target cannot also be the target of an AUTO CDC or APPEND flow — multiflow is not supported for REPLACE WHERE.
- Expectations are not supported on tables that are the target of a REPLACE WHERE flow.
- For a one-time backfill, override the predicate for a single update instead of editing the table definition (see Backfills above).
- For Streaming Tables created in DBSQL (not SDP), only the inline form is supported and there is no predicate-override API — use direct DML on the target for backfills.
