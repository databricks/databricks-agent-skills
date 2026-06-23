# Designing Metric Views for Genie Spaces

Best practices for designing metric views that AI agents (Genie, multi-agent systems) can reliably reason over.

> **Scope:** This page covers the **metric-view design** side. For building, sizing, validating, and benchmarking the Genie Space itself, see the `databricks-genie` lifecycle subskills — [create-genie-space → space-design-guide.md](../../databricks-genie/create-genie-space/references/space-design-guide.md) (sizing, build loop, anti-patterns) and [optimize-genie-space → optimization-guide.md](../../databricks-genie/optimize-genie-space/references/optimization-guide.md) (benchmark repair/pruning, regression). For the `MEASURE()` query rules Genie must follow, see [query-patterns.md](query-patterns.md).

## Core Design Rules

### Rule 1: One Fact Source per Metric View

**Each metric view must have exactly ONE fact table, view, or metric view as its `source`.** This is the most important design constraint.

- Co-locate measures in the same metric view only if they share **both** the same single source AND the same dimension tables.
- If a KPI requires multiple fact tables, build a **base view** first (see Rule 2).
- Use the `MEASURE()` function for [metric composability](https://docs.databricks.com/en/metric-views/data-modeling/composability) — a measure can reference other measures or dimensions in the same metric view.

### Rule 2: Multi-Fact or Nested KPIs Need a Base View

When a KPI spans multiple fact tables or contains nested logic:

1. Create a SQL view that joins the sources using CTEs (`WITH` statements).
2. Build the metric view on top of that base view.
3. **Remove the raw base view from the Genie space** once the metric view exists — keeping both creates redundancy and increases hallucination risk because the base view exposes unaggregated row-level data.

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

Use [format specifications](https://docs.databricks.com/en/metric-views/data-modeling/semantic-metadata#format-specifications) to declare semantic metadata. Especially valuable for date dimensions — Genie no longer has to guess from entity matching.

```yaml
dimensions:
  - name: Order Date
    expr: order_date
    format:
      date_format: "yyyy-MM-dd"

measures:
  - name: Revenue
    expr: SUM(amount)
    format:
      currency: USD
```

## Organize by Domain, Not by Report

### Hierarchy

| Level | Maps To |
|-------|---------|
| **Domain** (e.g., "Marketing") | Genie space |
| **Subdomain** (e.g., "Online Marketing") | Genie space (if domain is broad) |
| **KPI group** (e.g., "Conversion Metrics") | One metric view |

### Naming Convention

Use `{subdomain}_{kpi-group}` for metric view names:

```text
online_marketing_conversion_metrics
online_marketing_traffic_metrics
finance_revenue_metrics
finance_cost_metrics
```

## Validating Metric Views in a Genie Space

Add and validate **one measure at a time**: add the measure, ask sample questions in the space, compare against the source-of-truth report, then save the validated query and benchmarks before moving on. Skipping this is the most common cause of broken Genie spaces. The full build/validation loop, example-SQL guidance, benchmarks, and regression testing live with the Genie skill — see [databricks-genie/create-genie-space → space-design-guide.md](../../databricks-genie/create-genie-space/references/space-design-guide.md).

## Common Anti-Patterns (Metric-View Design)

These are the **design-side** anti-patterns. For Genie-space build/validation anti-patterns (base view left in the space, adding many measures at once, no space description, complex `CASE` in example SQL), see [databricks-genie/create-genie-space → space-design-guide.md §Anti-Patterns](../../databricks-genie/create-genie-space/references/space-design-guide.md#anti-patterns).

| Anti-pattern | Why it fails | Fix |
|--------------|--------------|-----|
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
