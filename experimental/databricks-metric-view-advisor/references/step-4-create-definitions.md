# Step 4 — Create Metric View Definitions (detailed procedure)

This is the full procedure for **Step 4** of the advisor workflow (referenced from
`SKILL.md`). For each approved metric view, generate the full YAML definition and
present it to the user.

**Format each definition as a CREATE statement:**

```sql
CREATE OR REPLACE VIEW <catalog.schema.metric_view_name>
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "<description>"
  source: <catalog.schema.source_table>
  filter: <optional global filter>

  joins:
    - name: <dim_table_alias>
      source: <catalog.schema.dim_table>
      'on': source.<fk> = <alias>.<pk>

  dimensions:
    - name: <Display Name>
      expr: <sql_expression>
      comment: "<description>"

  measures:
    - name: <Display Name>
      expr: <aggregate_expression>
      comment: "<description>"
$$
```

**YAML rules to follow** (critical subset — the parent `databricks-metric-views` skill holds the full spec, and [references/yaml-reference.md](yaml-reference.md) holds the advisor additions including the gotchas table):
- `version: 1.1` (requires DBR 17.2+)
- Every dimension and measure needs a `name` and `expr`
- Add `comment`, `display_name`, and `synonyms` to all dimensions and measures for Genie discoverability
- **Use composability** — define atomic measures first (SUM, COUNT, AVG), then build complex measures referencing them via `MEASURE()`
- **Standardize dimension values** — use CASE expressions to convert raw codes to business-friendly names
- **Include granular + truncated time dimensions** — always add both the raw date and `Month`/`Quarter`/`Year`
- Measure `expr` must use aggregate functions (SUM, COUNT, AVG, MIN, MAX) — or `MEASURE()` for composed measures
- Reference joined table columns as `<join_name>.<column>`; use `source.<column>` when joins are present
- **Snowflake join column references** must use the **full dot-chain path** through parent joins: `customer.nation.n_name` — NOT `nation.n_name`. Common source of `UNRESOLVED_COLUMN` errors.
- **Backtick-quote `MEASURE()` references** when the measure name contains spaces: `` MEASURE(`Total Revenue`) `` — NOT `MEASURE(Total Revenue)`. Unquoted multi-word names cause `PARSE_SYNTAX_ERROR`.
- **`format` blocks are optional but must include a `type` discriminator** (`number`/`currency`/`percentage`/`byte`/`date`/`date_time`) — omitting `type` causes *"Could not resolve subtype … missing type id 'type'"*. Use enum tokens (e.g. `date_format: year_month_day`), not `yyyy-MM-dd` patterns. See [yaml-reference.md → Format Types](yaml-reference.md#format-types).
- **Use `DATEDIFF()` for date comparisons, NOT subtraction** — `date1 - date2` returns `INTERVAL DAY`, not an integer.

**Join strategy — prefer joins, fall back to SQL source:**
- **Prefer star/snowflake joins** when possible — the optimizer only joins tables needed for each query.
- **If snowflake joins fail** (DBR < 17.1 or nested column references don't resolve), fall back to a **SQL query source** that pre-joins all tables. See the **SQL Query as Source** pattern in [references/patterns.md](patterns.md).
- When using a SQL source, column references use the aliased names directly (no `source.` or `join_name.` prefix).

**Always save SQL files locally** (unless the user opted out in Step 1):
- Save into the **same timestamped run folder** created in Step 3.
- Save each metric view definition as `<metric_view_name>.sql`, and also an `all_metric_views.sql` combining all definitions.
- Inform the user of the saved folder and file paths.

**STOP — wait for the user to review the generated definitions before proceeding.**
