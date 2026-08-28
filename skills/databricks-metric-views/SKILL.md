---
name: databricks-metric-views
description: "Unity Catalog metric views: define, create, query, and manage governed business metrics in YAML. Use when building standardized KPIs, revenue metrics, order analytics, or any reusable business metrics that need consistent definitions across teams and tools."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# Unity Catalog Metric Views

Define reusable, governed business metrics in YAML that separate measure definitions from dimension groupings for flexible querying.

## When to Use

Use this skill when:
- Defining **standardized business metrics** (revenue, order counts, conversion rates)
- Building **KPI layers** shared across dashboards, Genie, and SQL queries
- Creating metrics with **complex aggregations** (ratios, distinct counts, filtered measures)
- Defining **window measures** (moving averages, running totals, period-over-period, YTD)
- Modeling **star or snowflake schemas** with joins in metric definitions
- Enabling **materialization** for pre-computed metric aggregations

## Prerequisites

- **Databricks Runtime 17.2+** (for YAML version 1.1); **17.3+** for semantic metadata (`synonyms` / `display_name` / `format`)
- SQL warehouse with `CAN USE` permissions
- `SELECT` on source tables, `CREATE TABLE` + `USE SCHEMA` in the target schema

## Metric View Lifecycle

| Task | Reference | Load when |
|------|-----------|-----------|
| **Create** | [metric-view-advisor.md](references/metric-view-advisor.md) | Any creation task — the advisor handles the full workflow (profile schema, analyze sources, suggest, deploy). Load [create-patterns.md](references/create-patterns.md) alongside as the YAML spec and pattern reference. |
| **YAML spec / patterns** | [create-patterns.md](references/create-patterns.md) | Patterns 1–12, full YAML field reference, formatting gotchas, deployment errors, quick reference. Companion to the advisor; also load directly for pattern lookup. |
| **Query** | [query-patterns.md](references/query-patterns.md) | Writing SQL against a metric view — `MEASURE()` basics, filters, join rollups, window measures, Rules 1–3. |
| **Genie integration** | [metric-view-advisor.md §Genie Design Rules](references/metric-view-advisor.md#genie-design-rules) | One-fact-source rule, base views, domain organization, naming. Agent metadata fields (`comment`, `synonyms`, `display_name`, `format`) are in [create-patterns.md §YAML Field Reference](references/create-patterns.md#yaml-field-reference). |

Typical flow: **advisor → create → query/validate → Genie integration (if adding to a Genie Agent)**.

### Source-controlled deployment with Declarative Automation Bundles

To source-control a metric view, commit its complete SQL definition and execute it through a bundle-managed SQL job. DABs do not have a native metric-view resource, but a bundle-managed SQL job can apply a committed definition:

```yaml
# databricks.yml
bundle:
  name: orders_metrics

variables:
  catalog: { default: main }
  schema:  { default: default }
  warehouse_id: { default: "" }

resources:
  jobs:
    deploy_orders_metrics:
      name: deploy_orders_metrics
      parameters:
        - name: catalog
          default: ${var.catalog}
        - name: schema
          default: ${var.schema}
      tasks:
        - task_key: create_metric_view
          sql_task:
            warehouse_id: ${var.warehouse_id}
            file:
              path: ../src/orders_metrics.metric_view.sql
```

Deploy and run:

```bash
databricks bundle deploy --target <TARGET> --profile <PROFILE>
databricks bundle run deploy_orders_metrics --target <TARGET> --profile <PROFILE>
```

See the official [metric view bundle example](https://github.com/databricks/bundle-examples/tree/main/knowledge_base/metric_view).

## Related Skills

- **[databricks-genie-agents](../databricks-genie-agents/SKILL.md)** — create, manage, and validate Genie Agents that consume the metric views built here. Metric-view design rules for Genie are in the [advisor §Genie Design Rules](references/metric-view-advisor.md#genie-design-rules); query rules are in [query-patterns.md](references/query-patterns.md).
- **[databricks-aibi-dashboards](../databricks-aibi-dashboards/SKILL.md)** — build AI/BI dashboards on top of metric views.
- **[databricks-data-discovery](../databricks-data-discovery/SKILL.md)** — explore data before creating metric views; answer questions across your workspace.
- **[databricks-dabs](../databricks-dabs/SKILL.md)** — source-control and deploy metric view SQL definitions via bundle-managed jobs.

## Resources

- [Metric Views Documentation](https://docs.databricks.com/metric-views/)
- [YAML Syntax Reference](https://docs.databricks.com/metric-views/data-modeling/syntax)
- [Joins](https://docs.databricks.com/metric-views/data-modeling/joins)
- [Window Measures](https://docs.databricks.com/metric-views/data-modeling/window-measures) (Experimental)
- [Materialization](https://docs.databricks.com/metric-views/materialization)
- [MEASURE() Function](https://docs.databricks.com/sql/language-manual/functions/measure)
