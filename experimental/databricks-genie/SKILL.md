---
name: databricks-genie
description: "Create and query Databricks Genie Spaces for natural language SQL exploration. Use when building Genie Spaces, exporting and importing Genie Spaces, migrating Genie Spaces between workspaces or environments, or asking questions via the Genie Conversation API."
---

# Databricks Genie

Create, manage, and query Databricks Genie Spaces - natural language interfaces for SQL-based data exploration.

## Overview

Genie Spaces allow users to ask natural language questions about structured data in Unity Catalog. The system translates questions into SQL queries, executes them on a SQL warehouse, and presents results conversationally.

## When to Use This Skill

Use this skill when:
- Creating a new Genie Space for data exploration
- Adding sample questions to guide users
- Connecting Unity Catalog tables to a conversational interface
- Asking questions to a Genie Space programmatically (Conversation API)
- Exporting a Genie Space configuration (serialized_space) for backup or migration
- Importing / cloning a Genie Space from a serialized payload
- Migrating a Genie Space between workspaces or environments (dev → staging → prod)
    - Only supports catalog remapping where catalog names differ across environments
    - Not supported for schema and/or table names that differ across environments
    - Not including migration of tables between environments (only migration of Genie Spaces)

## MCP Tools

| Tool | Purpose |
|------|---------|
| `manage_genie` | Create, get, list, delete, export, and import Genie Spaces |
| `ask_genie` | Ask natural language questions to a Genie Space |
| `get_table_stats_and_schema` | Inspect table schemas before creating a space |
| `execute_sql` | Test SQL queries directly |

### manage_genie - Space Management

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `create_or_update` | Idempotent create/update a space | display_name, table_identifiers (or serialized_space) |
| `get` | Get space details | space_id |
| `list` | List all spaces | (none) |
| `delete` | Delete a space | space_id |
| `export` | Export space config for migration/backup | space_id |
| `import` | Import space from serialized config | warehouse_id, serialized_space |

**Example tool calls:**
```
# MCP Tool: manage_genie
# Create a new space
manage_genie(
    action="create_or_update",
    display_name="Sales Analytics",
    table_identifiers=["catalog.schema.customers", "catalog.schema.orders"],
    description="Explore sales data with natural language",
    sample_questions=["What were total sales last month?"]
)

# MCP Tool: manage_genie
# Get space details with full config
manage_genie(action="get", space_id="space_123", include_serialized_space=True)

# MCP Tool: manage_genie
# List all spaces
manage_genie(action="list")

# MCP Tool: manage_genie
# Export for migration
exported = manage_genie(action="export", space_id="space_123")

# MCP Tool: manage_genie
# Import to new workspace
manage_genie(
    action="import",
    warehouse_id="warehouse_456",
    serialized_space=exported["serialized_space"],
    title="Sales Analytics (Prod)"
)
```

### ask_genie - Conversation API (Query)

Ask natural language questions to a Genie Space. Pass `conversation_id` for follow-up questions.

```
# MCP Tool: ask_genie
# Start a new conversation
result = ask_genie(
    space_id="space_123",
    question="What were total sales last month?"
)
# Returns: {question, conversation_id, message_id, status, sql, columns, data, row_count}

# MCP Tool: ask_genie
# Follow-up question in same conversation
result = ask_genie(
    space_id="space_123",
    question="Break that down by region",
    conversation_id=result["conversation_id"]
)
```

## Quick Start

### 1. Inspect Your Tables

Before creating a Genie Space, understand your data:

```
# MCP Tool: get_table_stats_and_schema
get_table_stats_and_schema(
    catalog="my_catalog",
    schema="sales",
    table_stat_level="SIMPLE"
)
```

### 2. Create the Genie Space

```
# MCP Tool: manage_genie
manage_genie(
    action="create_or_update",
    display_name="Sales Analytics",
    table_identifiers=[
        "my_catalog.sales.customers",
        "my_catalog.sales.orders"
    ],
    description="Explore sales data with natural language",
    sample_questions=[
        "What were total sales last month?",
        "Who are our top 10 customers?"
    ]
)
```

### 3. Ask Questions (Conversation API)

```
# MCP Tool: ask_genie
ask_genie(
    space_id="your_space_id",
    question="What were total sales last month?"
)
# Returns: SQL, columns, data, row_count
```

### 4. Export & Import (Clone / Migrate)

Export a space (preserves all tables, instructions, SQL examples, and layout):

```
# MCP Tool: manage_genie
exported = manage_genie(action="export", space_id="your_space_id")
# exported["serialized_space"] contains the full config
```

Clone to a new space (same catalog):

```
# MCP Tool: manage_genie
manage_genie(
    action="import",
    warehouse_id=exported["warehouse_id"],
    serialized_space=exported["serialized_space"],
    title=exported["title"],  # override title; omit to keep original
    description=exported["description"],
)
```

> **Cross-workspace migration:** Each MCP server is workspace-scoped. Configure one server entry per workspace profile in your IDE's MCP config, then `manage_genie(action="export")` from the source server and `manage_genie(action="import")` via the target server. See [spaces.md §Migration](references/spaces.md#migrating-across-workspaces-with-catalog-remapping) for the full workflow.

## Reference Files

- [spaces.md](references/spaces.md) - Creating and managing Genie Spaces
- [space-quality.md](references/space-quality.md) - Tool-agnostic quick reference: sizing, build & validation loop, benchmarks, regression, setup checklist, anti-patterns
- [conversation.md](references/conversation.md) - Asking questions via the Conversation API

## Genie Code Agent Skills (in-product design & tuning)

This skill is the **programmatic / MCP** path — it drives Genie Spaces from outside Databricks via `manage_genie`, `ask_genie`, and `execute_sql` (create, query, export, import, migrate).

A companion suite of **Genie Code Agent** skills runs **inside Databricks Genie Code** and drives the native UI (Monitor tab, Query History Insights, native benchmark execution). They are read-only / plan-first with explicit approval gates before any change. Reach for them when the user is working interactively in the product rather than scripting from outside:

| Skill | Use when |
|-------|----------|
| [create-genie-space](create-genie-space/SKILL.md) | Drafting/bootstrapping a focused Space from UC tables, views, and Metric Views (design-time) |
| [diagnose-genie-space](diagnose-genie-space/SKILL.md) | Plan-only root-cause analysis of wrong SQL/answers, weak reports, or Monitor-tab feedback (no edits) |
| [optimize-genie-space](optimize-genie-space/SKILL.md) | Approved iterative benchmark-driven quality tuning (one focused pass at a time) |
| [optimize-genie-query](optimize-genie-query/SKILL.md) | Benchmark-query performance/cost triage via Query History Insights & Query Profile |

Typical in-product flow: **create → diagnose → optimize-genie-space**, with **optimize-genie-query** for performance issues (it hands back to the quality skills if the SQL is semantically wrong). For the condensed, tool-agnostic version of the build/validation guidance these skills implement, see [space-quality.md](references/space-quality.md).

## Genie Space Lifecycle (design → diagnose → optimize)

The **methodology** in the Genie Code Agent suite is portable to this MCP path — only the *mechanism* differs (MCP tools here vs the in-product UI there). Use this skill as the orchestration hub: for each phase, follow the canonical methodology and execute it with the MCP tool below; when the user is working inside Databricks Genie Code, route to the subskill instead.

| Phase | Methodology (canonical source) | Execute via MCP | In-product subskill |
|-------|-------------------------------|-----------------|---------------------|
| **Design** | [create-genie-space → space-design-guide.md](create-genie-space/references/space-design-guide.md) — requirements, readiness, structured-context-first order, metric-view recommendation | `get_table_stats_and_schema`, `execute_sql` (read-only profiling) | `create-genie-space` |
| **Create / update** | [space-quality.md](references/space-quality.md) — sizing, setup checklist; [spaces.md](references/spaces.md) | `manage_genie(create_or_update)` | `create-genie-space` |
| **Query / evaluate** | [space-quality.md](references/space-quality.md) — incremental build & validation loop, benchmarks | `ask_genie` over a question set; compare results to source-of-truth | `optimize-genie-space` |
| **Diagnose** | [diagnose-genie-space → failure-routing.md](diagnose-genie-space/references/failure-routing.md) — classify primary failure, smallest fix | `ask_genie` to reproduce, `manage_genie(get, include_serialized_space)`, `execute_sql`, `system.query.history` | `diagnose-genie-space` |
| **Optimize (quality)** | [optimize-genie-space → optimization-guide.md](optimize-genie-space/references/optimization-guide.md) — benchmark integrity, repair/pruning, baseline→candidate, regression | edit config via `manage_genie(create_or_update)`; re-run `ask_genie` eval loop | `optimize-genie-space` |
| **Optimize (query)** | [optimize-genie-query → query-optimization-guide.md](optimize-genie-query/references/query-optimization-guide.md) — reduce work before adding compute | `execute_sql` + `EXPLAIN`, `system.query.history`, `system.access.audit` | `optimize-genie-query` |

**Mechanism gaps (no MCP equivalent — in-product only):**

- **Native benchmark execution & scoring.** Via MCP, approximate it with an `ask_genie`-over-a-fixed-question-set loop and compare SQL/results yourself; you don't get the native per-question eval UI.
- **Monitor-tab feedback** (thumbs up/down trends, review requests) and **Query History Insights / Query Profile.** Substitute `system.query.history` / `system.access.audit` reads where possible, and state the limitation.

When a phase depends on one of these gaps, say so explicitly and either approximate via the MCP substitute or recommend doing that phase inside Databricks Genie Code with the matching subskill.

## Prerequisites

Before creating a Genie Space:

1. **Tables in Unity Catalog** - Bronze/silver/gold tables with the data
2. **SQL Warehouse** - A warehouse to execute queries (auto-detected if not specified)

### Creating Tables

Use these skills in sequence:
1. `databricks-synthetic-data-gen` - Generate raw parquet files
2. `databricks-spark-declarative-pipelines` - Create bronze/silver/gold tables

## Querying Metric Views

If a Genie Space's data source is a **metric view** (not a plain table), Genie's SQL — and any `example_question_sqls` / `text_instructions` you author — must follow the `MEASURE()` query rules, or you'll hit `MISSING_AGGREGATION` errors and degraded answers. Key rules:

- **Never** reference a non-grouped dimension inside a `CASE` that also calls `MEASURE()` — put that dimension in `GROUP BY ALL` in a CTE, then aggregate in the outer query.
- Use a pre-built blended measure (e.g. `MEASURE(blended_spread)`) instead of reconstructing per-dimension branching with `CASE WHEN`.
- **Never** put a measure column in `WHERE` or `GROUP BY` — measures are only valid via `MEASURE()` in `SELECT`. Filter NULL/unwanted results with `HAVING` or an outer query/CTE.

See [spaces.md §Querying Metric Views in Genie](references/spaces.md#querying-metric-views-in-genie) for a summary, and [databricks-metric-views/query-patterns.md](../databricks-metric-views/references/query-patterns.md) for full rules and examples.

## Common Issues

See [spaces.md §Troubleshooting](references/spaces.md#troubleshooting) for a full list of issues and solutions.

**If you're constructing `serialized_space` JSON by hand** and getting errors like `Expected 'START_OBJECT' not 'VALUE_STRING'`, `must be sorted by id`, `must contain at most one item`, or `Unknown field`, see [spaces.md §Exact Field Schemas](references/spaces.md#exact-field-schemas-verified-against-the-genie-api) for the verified shapes of `text_instructions`, `example_question_sqls`, `benchmarks`, and `sample_questions`, plus a self-contained Python helper.
## Related Skills

- **[databricks-metric-views](../databricks-metric-views/SKILL.md)** - Build governed business metrics that Genie consumes. See [genie-integration.md](../databricks-metric-views/references/genie-integration.md) for metric-view design rules that affect Genie answer quality (one-fact-source rule, base view pattern for multi-fact KPIs, agent metadata, domain organization), and [query-patterns.md](../databricks-metric-views/references/query-patterns.md) for the `MEASURE()` query rules Genie must follow.
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Use Genie Spaces as agents inside Supervisor Agents
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate raw parquet data to populate tables for Genie
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables consumed by Genie Spaces
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs, schemas, and tables Genie queries
