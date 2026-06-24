# Designing Metric Views for Genie Agents

Best practices for designing metric views that AI agents (Genie, multi-agent systems) can reliably reason over.

> **Scope:** This page covers the **metric-view design** side. For building, sizing, validating, and benchmarking the Genie Agent itself, see the `databricks-genie-agent` lifecycle subskills — [create-genie-agent → agent-design-guide.md](../../databricks-genie-agent/create-genie-agent/references/agent-design-guide.md) (sizing, build loop, anti-patterns) and [optimize-genie-agent → optimization-guide.md](../../databricks-genie-agent/optimize-genie-agent/references/optimization-guide.md) (benchmark repair/pruning, regression). For the `MEASURE()` query rules Genie must follow, see [query-patterns.md](query-patterns.md).

## Core Design Rules

### Rule 1: One Fact Source per Metric View

**Each metric view must have exactly ONE fact table, view, or metric view as its `source`.** This is the most important design constraint.

- **Single fact table → set it as `source` directly. Do NOT build a base view.** A base view adds no value when there is only one fact table; it just adds an extra object to maintain and risks exposing unaggregated rows to Genie. Add dimension-table joins (star/snowflake) inside the metric view's `joins` block — that does **not** require a base view.
- A base view is needed **only** when a KPI must combine **multiple fact tables** or contains **nested logic** that cannot be expressed in the metric view directly (see Rule 2).
- Co-locate measures in the same metric view only if they share **both** the same single source AND the same dimension tables.
- Use the `MEASURE()` function for [metric composability](https://docs.databricks.com/en/metric-views/data-modeling/composability) — a measure can reference other measures or dimensions in the same metric view.

### Rule 2: Multi-Fact or Nested KPIs Need a Base View

Build a base view **only** when a KPI spans multiple fact tables or contains nested logic that the metric view cannot express directly. A single fact table (even one joined to dimension tables) does **not** need a base view — source it directly per Rule 1.

When a KPI spans multiple fact tables or contains nested logic:

1. Create a SQL view that joins the sources using CTEs (`WITH` statements).
2. Build the metric view on top of that base view.
3. **Remove the raw base view from the Genie Agent** once the metric view exists — keeping both creates redundancy and increases hallucination risk because the base view exposes unaggregated row-level data.

```sql
-- Step 1: Base view joining two fact sources
CREATE OR REPLACE VIEW catalog.schema.orders_with_returns AS
WITH orders AS (
  SELECT order_id, customer_id, order_date, total_amount
  FROM catalog.schema.fact_orders
),
returns AS (
  SELECT order_id, return_amount, return_date
  FROM catalog.schema.fact_returns
)
SELECT
  o.*,
  COALESCE(r.return_amount, 0) AS return_amount
FROM orders o
LEFT JOIN returns r ON o.order_id = r.order_id;

-- Step 2: Metric view on top of the base view
CREATE OR REPLACE VIEW catalog.schema.sales_net_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.orders_with_returns
  dimensions:
    - name: Order Month
      expr: DATE_TRUNC('MONTH', order_date)
  measures:
    - name: Gross Revenue
      expr: SUM(total_amount)
    - name: Returns
      expr: SUM(return_amount)
    - name: Net Revenue
      expr: SUM(total_amount) - SUM(return_amount)
$$
```

**Note:** A base view does NOT need to pre-join all dimension tables. If the base view exposes a join key, add dimension joins in the metric view definition itself.

### Rule 3: Prefer Separate Metric Views per KPI Group

Even when nested KPIs share the same source and could be combined, prefer separate metric views per KPI group for easier debugging. A complex combined metric view is harder to isolate when a measure fails.

## Agent Metadata (Critical for Genie Quality)

### Comments at Three Levels

Genie uses comments from the metric view, dimensions, **and** measures for reasoning. Always populate all three:

```yaml
version: 1.1
source: catalog.schema.fact_sales
comment: "Online Marketing Conversion Metrics — funnel KPIs from web sessions to closed orders"

dimensions:
  - name: Campaign Channel
    expr: campaign_channel
    comment: "Marketing channel: PAID_SEARCH, ORGANIC, EMAIL, SOCIAL, DISPLAY (all uppercase)"

measures:
  - name: Conversion Rate
    expr: COUNT(DISTINCT order_id) * 1.0 / COUNT(DISTINCT session_id)
    comment: "Orders per session — proxy for funnel efficiency"
```

**Comment guidelines:**

- Keep comments consistent with names and definitions.
- Explain abbreviations and acronyms (e.g., `MTD`, `YTD`, internal codes).
- Document expected value formats (e.g., "all uppercase", "ISO 8601") directly in the column comment — embedding format in the comment is more reliable than relying on Genie instructions alone.

### Synonyms (Recommended)

Add up to 10 synonyms per dimension/measure so Genie can map business terminology to fields:

```yaml
measures:
  - name: Total Revenue
    expr: SUM(amount)
    comment: "Gross revenue from all transactions"
    synonyms:
      - sales
      - gross sales
      - top line
      - turnover
      - GMV
```

### Format Specifications

Use [format specifications](https://docs.databricks.com/aws/en/business-semantics/agent-metadata#format-specifications) to declare semantic metadata. Especially valuable for date dimensions — Genie no longer has to guess from entity matching.

**Every `format:` block requires a `type:` discriminator** (`number`, `currency`, `percentage`, `byte`, `date`, or `date_time`). Omitting `type` causes a deploy error: *"Could not resolve subtype … missing type id 'type'."* Each type has its own keys (see the full schema below); the values are enum tokens (e.g. `year_month_day`), **not** strftime/`yyyy-MM-dd` patterns.

```yaml
dimensions:
  - name: Order Date
    expr: order_date
    format:
      type: date
      date_format: year_month_day   # enum token, NOT "yyyy-MM-dd"

measures:
  - name: Revenue
    expr: SUM(amount)
    format:
      type: currency
      currency_code: USD            # ISO-4217 code, required for currency
      decimal_places:
        type: exact
        places: 2
```

**Format type schema** (requires YAML spec `version: 1.1`):

```yaml
# Number
format:
  type: number
  decimal_places: { type: max, places: 2 }   # type: max | exact | all
  hide_group_separator: false
  abbreviation: compact                       # none | compact | scientific

# Currency
format:
  type: currency
  currency_code: USD                          # ISO-4217, required
  decimal_places: { type: exact, places: 2 }

# Percentage
format:
  type: percentage
  decimal_places: { type: all }

# Byte
format:
  type: byte
  decimal_places: { type: max, places: 2 }

# Date
format:
  type: date
  date_format: year_month_day                 # year_month_day | locale_short_month | locale_long_month | locale_number_month | year_week
  leading_zeros: true

# DateTime — at least one of date_format/time_format must be non-"no_*"
format:
  type: date_time
  date_format: year_month_day
  time_format: locale_hour_minute_second      # no_time | locale_hour_minute | locale_hour_minute_second
  leading_zeros: false
```

## Organize by Domain, Not by Report

### Hierarchy

| Level | Maps To |
|-------|---------|
| **Domain** (e.g., "Marketing") | Genie Agent |
| **Subdomain** (e.g., "Online Marketing") | Genie Agent (if domain is broad) |
| **KPI group** (e.g., "Conversion Metrics") | One metric view |

### Naming Convention

Use `{subdomain}_{kpi-group}` for metric view names:

```text
online_marketing_conversion_metrics
online_marketing_traffic_metrics
finance_revenue_metrics
finance_cost_metrics
```

## Validating Metric Views in a Genie Agent

Add and validate **one measure at a time**: add the measure, ask sample questions in the Agent, compare against the source-of-truth report, then save the validated query and benchmarks before moving on. Skipping this is the most common cause of broken Genie Agents. The full build/validation loop, example-SQL guidance, benchmarks, and regression testing live with the Genie skill — see [databricks-genie-agent/create-genie-agent → agent-design-guide.md](../../databricks-genie-agent/create-genie-agent/references/agent-design-guide.md).

## Common Anti-Patterns (Metric-View Design)

These are the **design-side** anti-patterns. For Genie-agent build/validation anti-patterns (base view left in the Agent, adding many measures at once, no Agent description, complex `CASE` in example SQL), see [databricks-genie-agent/create-genie-agent → agent-design-guide.md §Anti-Patterns](../../databricks-genie-agent/create-genie-agent/references/agent-design-guide.md#anti-patterns).

| Anti-pattern | Why it fails | Fix |
|--------------|--------------|-----|
| Building a base view for a single fact table | Adds an unnecessary object to maintain and can expose unaggregated rows; provides no benefit over sourcing the fact directly | Set the fact table as `source` directly; add dimension joins in the metric view's `joins` block |
| Multiple fact tables joined directly in the metric view's `source` | Violates one-fact-source rule | Build a base view first; metric view sources from it |
| Metric view with no comment, dimensions with no comments | Genie has no semantic context | Comment at all three levels |
| Mirroring report structure in metric views | Reports change; semantics shouldn't | Organize by business domain/subdomain |

## References

- [Metric Views Overview](https://docs.databricks.com/en/metric-views/)
- [Metric View Composability — MEASURE() function](https://docs.databricks.com/en/metric-views/data-modeling/composability)
- [Semantic Metadata & Format Specifications](https://docs.databricks.com/en/metric-views/data-modeling/semantic-metadata)
- [Genie Space Best Practices](https://docs.databricks.com/en/genie/best-practices)
- [Genie Knowledge Store — Prompt Matching & SQL Expressions](https://docs.databricks.com/en/genie/knowledge-store)
- [Genie Benchmarks](https://docs.databricks.com/en/genie/benchmarks)
- [Genie Troubleshooting](https://docs.databricks.com/en/genie/troubleshooting)
