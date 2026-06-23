---
name: databricks-genie
description: "Create and query Databricks Genie Spaces for natural language SQL exploration. Use when building Genie Spaces, exporting and importing Genie Spaces, migrating Genie Spaces between workspaces or environments, or asking questions via the Genie Conversation API."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.0.1"
---

# Databricks Genie

Create, manage, and query Databricks Genie Spaces - natural language interfaces for SQL-based data exploration.

## Overview

Genie Spaces allow users to ask natural language questions about structured data in Unity Catalog. The system translates questions into SQL queries, executes them on a SQL warehouse, and presents results conversationally.

**Default to the Databricks CLI** (`databricks genie ...`) for every operation in this skill — it works in any environment with the CLI authenticated. Where the Databricks **MCP server** is available (e.g. inside an IDE wired to it), each step also lists the equivalent `manage_genie` / `ask_genie` tool call as a shortcut. The CLI commands are canonical; the MCP calls are an optional convenience.

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

## Creating a Genie Space

### Step 1: Understand the Data

Before creating a Genie Space, explore the available tables to:
- **Select relevant tables** — typically gold layer (aggregated KPIs) and sometimes silver layer (cleaned facts) or metric views
- **Understand the story** — what business questions can this data answer? What insights can users discover?
- **Design meaningful sample questions** — questions should reflect real use cases and lead to actionable insights in the data

Use `discover-schema` as the default — one call returns columns, types, sample rows, null counts, and row count. If you only know the schema, list tables first with `query "SHOW TABLES IN ..."`.

```bash
databricks experimental aitools tools discover-schema catalog.schema.gold_sales catalog.schema.gold_customers
```

For Genie, knowing column distribution shapes the sample questions and text instructions. If you don't already know the data, probe cardinality, ranges, and top categorical values with aggregate SQL through `databricks experimental aitools tools query --warehouse <WH> "..."` so your sample questions reflect what's actually in the data. Both commands auto-pick the default warehouse; set `DATABRICKS_WAREHOUSE_ID` or pass `--warehouse <ID>` to override.

Fan out independent probes with `databricks experimental aitools tools statement submit` (returns a statement_id immediately) + `... get` (blocks until terminal: `SUCCEEDED|FAILED|CANCELED|CLOSED`):

```bash
SIDS=()
for q in "$@"; do
  SIDS+=( "$(databricks experimental aitools tools statement submit --warehouse "$WH" "$q" | jq -r .statement_id)" )
done
for s in "${SIDS[@]}"; do databricks experimental aitools tools statement get "$s"; done
# Use `status` for non-blocking peek; `cancel` to terminate.
```

> **MCP alternative (if available):** `get_table_stats_and_schema(catalog="my_catalog", schema="sales", table_stat_level="SIMPLE")` returns the same column/cardinality/null-count profile; `execute_sql` runs read-only probes.

### Step 2: Create the Space

Define your space in a local JSON file (e.g., `genie_space.json`) for version control and easy iteration. See [serialized_space Format](#serialized_space-format) below for the full structure.

```bash
# List all Genie Spaces
databricks genie list-spaces

# Create a Genie Space from a local file
# IMPORTANT: sample_questions require a 32-char hex "id" and "question" must be an array
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Explore sales data\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_space.json | jq -c '.' | jq -Rs '.')
}"

# Get space details (with full config)
databricks genie get-space SPACE_ID --include-serialized-space

# Tag the Genie Space for resource tracking — use any tag the user indicated for their
# project; otherwise default to `ai_generated_source=databricks-agent-skills`.
# (Beta CLI surface — ignore if the command fails.)
databricks workspace-entity-tag-assignments create-tag-assignment \
  geniespaces SPACE_ID ai_generated_source --tag-value databricks-agent-skills || true

# Delete a Genie Space
databricks genie trash-space SPACE_ID
```

> **MCP alternative (if available):** `manage_genie(action="create_or_update", display_name="Sales Analytics", table_identifiers=[...], description="...", sample_questions=[...])` is idempotent (create or update by `space_id`, or by `display_name` if `space_id` is omitted) and auto-detects a warehouse. `manage_genie(action="get", space_id=..., include_serialized_space=True)`, `manage_genie(action="list")`, and `manage_genie(action="delete", space_id=...)` cover the other operations. See [spaces.md](references/spaces.md) for the full MCP surface.

### Step 3: Test and Iterate

Use the [Conversation API](#conversation-api) (section below) to ask questions and verify answers. If answers are inaccurate or incomplete, improve the space — see [Improving a Genie Space](#improving-a-genie-space) below.

### Export & Import

**Convention:** `genie_space.json` always holds the **parsed** space object (not a JSON-string-encoded blob), so it's readable and editable. At each use site we stringify it with `jq -c '.' | jq -Rs '.'` — same pattern as Step 2 Create and "Improving a Genie Space" below. `jq -r '.serialized_space | fromjson'` on export strips the outer quoting so the file is already a parsed object.

```bash
# Export: extract serialized_space AND unwrap it to a parsed object on disk
databricks genie get-space SPACE_ID --include-serialized-space -o json \
  | jq '.serialized_space | fromjson' > genie_space.json

# Import: same stringify pattern as Step 2 (Create)
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Migrated space\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_space.json | jq -c '.' | jq -Rs '.')
}"
```

> **MCP alternative (if available):** `exported = manage_genie(action="export", space_id=...)` returns an envelope (`space_id`, `title`, `description`, `warehouse_id`, `serialized_space`); `manage_genie(action="import", warehouse_id=..., serialized_space=exported["serialized_space"], title=..., description=...)` clones it. See [spaces.md §Export, Import & Migration](references/spaces.md#export-import--migration).

### Improving a Genie Space

When Genie answers are inaccurate or incomplete, improve the space by updating questions, SQL examples, or instructions:

```bash
# 1. Edit your local genie_space.json (add questions, fix SQL examples, improve instructions)

# 2. Push updates back to the space
databricks genie update-space SPACE_ID --json "{\"serialized_space\": $(cat genie_space.json | jq -c '.' | jq -Rs '.')}"
```

> **MCP alternative (if available):** `manage_genie(action="create_or_update", space_id=..., serialized_space=...)`. A robust loop is fetch → mutate → push: `manage_genie(action="get", space_id=..., include_serialized_space=True)`, edit the fields you care about, then push back so unmodeled fields (column_configs, join_specs, sql_snippets) are preserved.

## serialized_space Format

The `serialized_space` field is a JSON string containing the full space configuration.

### Field Format Requirements

**IMPORTANT:** All items in `sample_questions`, `example_question_sqls`, and `text_instructions` require a unique `id` field.

| Field | Format |
|-------|--------|
| `config.sample_questions[]` | `{"id": "32hexchars", "question": ["..."]}` |
| `instructions.example_question_sqls[]` | `{"id": "32hexchars", "question": ["..."], "sql": ["..."]}` |
| `instructions.text_instructions[]` | `{"id": "32hexchars", "content": ["..."]}` |

- **ID format:** 32-character lowercase hex, unique across **all three lists combined** (a duplicate between e.g. `text_instructions` and `example_question_sqls` is rejected).
- **Text fields are arrays:** `question`, `sql`, and `content` are arrays of strings, not plain strings.
- **Sort order matters:** `data_sources.tables` must be sorted by `identifier`; `example_question_sqls` and `text_instructions` must be sorted by `id`. (`sample_questions` is silently re-sorted server-side.)
- **Simple ID scheme that satisfies both rules:** prefix per list + monotonic counter, total 32 hex chars — `1…0001`, `1…0002` for `sample_questions`; `2…0001`, `2…0002` for `example_question_sqls`; `3…0001` for `text_instructions`. Authoring order = sort order, no collisions.

For the **exact, API-verified shapes** of every field (including `benchmarks`, `join_specs`, hard constraints, and a self-contained Python helper that builds a correctly-shaped payload), see [spaces.md §Exact Field Schemas](references/spaces.md#exact-field-schemas-verified-against-the-genie-api).

### Text Instructions

`text_instructions` make the Genie Space more reliable by explaining:
- **Where to find information** — which tables contain which metrics
- **How to answer specific questions** — when a user asks X, use table Y with filter Z
- **Business context** — definitions, thresholds, and domain knowledge

Well-crafted instructions significantly improve answer accuracy.

### Example

Top-level keys are `version`, `config`, `data_sources`, `instructions`. Every item in `sample_questions`, `example_question_sqls`, and `text_instructions` needs a unique 32-char hex `id` and all text fields are arrays:

```json
{
  "version": 2,
  "config": {
    "sample_questions": [
      {"id": "10000000000000000000000000000001", "question": ["What is our current on-time performance?"]}
    ]
  },
  "data_sources": {
    "tables": [
      {"identifier": "catalog.ops.gold_otp_summary"}
    ]
  },
  "instructions": {
    "example_question_sqls": [
      {
        "id": "20000000000000000000000000000001",
        "question": ["What is our on-time performance?"],
        "sql": ["SELECT flight_date, ROUND(SUM(on_time_count) * 100.0 / SUM(total_flights), 1) AS otp_pct\n", "FROM catalog.ops.gold_otp_summary\n", "WHERE flight_date >= date_sub(current_date(), 7)\n", "GROUP BY flight_date ORDER BY flight_date"]
      }
    ],
    "text_instructions": [
      {
        "id": "30000000000000000000000000000001",
        "content": [
          "On-time performance (OTP) questions: Use gold_otp_summary table. OTP target is 85%.\n",
          "Delay analysis questions: Use gold_delay_analysis table. Filter by delay_code for specific delay types.\n",
          "When asked about 'this week' or 'recent': Use flight_date >= date_sub(current_date(), 7).\n",
          "When comparing aircraft: Join with gold_aircraft_reliability on tail_number."
        ]
      }
    ]
  }
}
```

## Conversation API

Ask questions via three CLI primitives: `start-conversation`, `create-message` (follow-ups), and `get-message` (state + SQL + text). `--no-wait` on `start-conversation` / `create-message` returns immediately with `{conversation_id, message_id}`; poll `get-message` until `.status` is `COMPLETED`, `FAILED`, or `CANCELLED`. Intermediate states you'll see: `SUBMITTED`, `FILTERING_CONTEXT`, `ASKING_AI`, `EXECUTING_QUERY`.

```bash
# Start a new conversation (async — get IDs back immediately)
databricks genie start-conversation --no-wait SPACE_ID "What were total sales last month?"
# → {"conversation_id": "...", "message_id": "..."}

# Poll state
databricks genie get-message SPACE_ID CONV_ID MSG_ID | jq '{status, error}'

# When COMPLETED, pull the generated SQL and any text reply
databricks genie get-message SPACE_ID CONV_ID MSG_ID \
  | jq '.attachments[] | {sql: .query.query, description: .query.description, text: .text.content}'

# Fetch the query result rows (columns + data_array)
databricks genie get-message-attachment-query-result SPACE_ID CONV_ID MSG_ID ATTACHMENT_ID \
  | jq '{columns: .statement_response.manifest.schema.columns | map({name, type: .type_name}),
         rows: .statement_response.result.data_array}'

# Follow-up in the same conversation (Genie remembers context)
databricks genie create-message --no-wait SPACE_ID CONV_ID "Break that down by region"
```

Start a new conversation for unrelated topics. Use `create-message` (same `CONV_ID`) only for follow-ups on the same topic.

On `FAILED`, `get-message` populates `.error.error` with the underlying error string (e.g. `[INSUFFICIENT_PERMISSIONS] ...`) and `.error.type` (e.g. `SQL_EXECUTION_EXCEPTION`). Attachments may still include `suggested_questions` even when the primary query failed.

> **MCP alternative (if available):** `ask_genie(space_id=..., question="...")` wraps the full start→poll→fetch loop into one call and returns `{question, conversation_id, message_id, status, sql, columns, data, row_count}`. Pass `conversation_id=` for a follow-up. See [conversation.md](references/conversation.md) for response handling, `ask_genie` vs `execute_sql` guidance, and example workflows.

## Cross-Workspace Migration

When migrating between workspaces, catalog names often differ. Export the space, remap the catalog name everywhere it appears in `serialized_space` (table identifiers, SQL `FROM` clauses, join specs, filter snippets), then import:

```bash
# After exporting to genie_space.json (see Export & Import above), remap the catalog:
python3 -c "import sys; p=sys.argv[1]; open(p,'w').write(open(p).read().replace('source_catalog','target_catalog'))" genie_space.json
```

Use `DATABRICKS_CONFIG_PROFILE=profile_name` to target different workspaces. See [spaces.md §Migrating Across Workspaces](references/spaces.md#migrating-across-workspaces-with-catalog-remapping) for the full export → remap → import workflow, batch migration, and the permissions each step needs.

## Reference Files

- [spaces.md](references/spaces.md) - Creating and managing Genie Spaces; exact `serialized_space` field schemas; export/import/migration (CLI-default, MCP shortcuts where available)
- [conversation.md](references/conversation.md) - Asking questions via the Conversation API (CLI-default, `ask_genie` where available)

Sizing, the incremental build & validation loop, benchmarks/regression, and anti-patterns live with the lifecycle subskills: [create-genie-space → space-design-guide.md](create-genie-space/references/space-design-guide.md) (sizing, build loop, anti-patterns) and [optimize-genie-space → optimization-guide.md](optimize-genie-space/references/optimization-guide.md) (benchmark integrity, repair/pruning, regression gates).

## Lifecycle Subskills (design & tuning)

This skill is the **orchestration hub** and the canonical reference for the `databricks genie` CLI (and the `manage_genie` / `ask_genie` MCP tools where available): create, query, export, import, migrate.

A companion suite of **dual-host** lifecycle skills covers design and tuning. Each runs **either** inside Databricks Genie Code (driving the native UI — Monitor tab, Query History Insights, native benchmark execution) **or** from an external agent via the CLI/MCP; each opens with an **Execution Context** + **Mechanism Map** that resolves which path applies. They are read-only / plan-first with explicit approval gates before any change:

| Skill | Use when |
|-------|----------|
| [create-genie-space](create-genie-space/SKILL.md) | Drafting/bootstrapping a focused Space from UC tables, views, and Metric Views (design-time) |
| [diagnose-genie-space](diagnose-genie-space/SKILL.md) | Plan-only root-cause analysis of wrong SQL/answers, weak reports, or feedback signals (no edits) |
| [optimize-genie-space](optimize-genie-space/SKILL.md) | Approved iterative benchmark-driven quality tuning (one focused pass at a time) |
| [optimize-genie-query](optimize-genie-query/SKILL.md) | Benchmark-query performance/cost triage via Query History metrics & Query Profile |

Typical flow: **create → diagnose → optimize-genie-space**, with **optimize-genie-query** for performance issues (it hands back to the quality skills if the SQL is semantically wrong). The build/validation guidance lives directly in these subskills — sizing, the incremental build loop, and anti-patterns in [create-genie-space](create-genie-space/references/space-design-guide.md); benchmark integrity, repair/pruning, and regression in [optimize-genie-space](optimize-genie-space/references/optimization-guide.md).

## Genie Space Lifecycle (design → diagnose → optimize)

The lifecycle methodology is **host-portable** — only the *mechanism* differs (CLI / MCP vs the in-product UI). Use this skill as the orchestration hub: for each phase, follow the canonical methodology and execute it with the CLI below (or the MCP equivalent where available); the matching subskill carries the same methodology with its own Execution Context + Mechanism Map for either host.

| Phase | Methodology (canonical source) | Execute via CLI (default) | MCP equivalent (if available) | Lifecycle subskill |
|-------|-------------------------------|---------------------------|-------------------------------|---------------------|
| **Design** | [create-genie-space → space-design-guide.md](create-genie-space/references/space-design-guide.md) — requirements, readiness, structured-context-first order, metric-view recommendation | `databricks experimental aitools tools discover-schema` / `... query` (read-only profiling) | `get_table_stats_and_schema`, `execute_sql` | `create-genie-space` |
| **Create / update** | [create-genie-space → space-design-guide.md](create-genie-space/references/space-design-guide.md) — sizing, build loop, health checks; [spaces.md](references/spaces.md) | `databricks genie create-space` / `update-space` | `manage_genie(create_or_update)` | `create-genie-space` |
| **Query / evaluate** | [create-genie-space → space-design-guide.md](create-genie-space/references/space-design-guide.md) — incremental build & validation loop, benchmarks | `databricks genie start-conversation` / `get-message` over a question set; compare to source-of-truth | `ask_genie` over a question set | `optimize-genie-space` |
| **Diagnose** | [diagnose-genie-space → failure-routing.md](diagnose-genie-space/references/failure-routing.md) — classify primary failure, smallest fix | reproduce via `start-conversation`; `get-space --include-serialized-space`; read `system.query.history` | `ask_genie`, `manage_genie(get, include_serialized_space)`, `execute_sql` | `diagnose-genie-space` |
| **Optimize (quality)** | [optimize-genie-space → optimization-guide.md](optimize-genie-space/references/optimization-guide.md) — benchmark integrity, repair/pruning, baseline→candidate, regression | edit config via `update-space`; re-run `start-conversation` eval loop | `manage_genie(create_or_update)`; `ask_genie` eval loop | `optimize-genie-space` |
| **Optimize (query)** | [optimize-genie-query → query-optimization-guide.md](optimize-genie-query/references/query-optimization-guide.md) — reduce work before adding compute | `EXPLAIN` via `aitools tools query`; read `system.query.history`, `system.access.audit` | `execute_sql` + `EXPLAIN`, `system.query.history` | `optimize-genie-query` |

**Mechanism notes (CLI substitutes vs in-product-only surfaces):**

- **Native benchmark execution & scoring.** The **Beta** `databricks genie genie-create-eval-run` / `genie-get-eval-run` / `genie-list-eval-runs` / `genie-list-eval-results` / `genie-get-eval-result-details` commands run and read native benchmark evaluations from the CLI (not wrapped by `manage_genie`/`ask_genie`). If those Beta commands are unavailable, fall back to a fixed-question-set loop (`start-conversation` / `ask_genie`) and compare SQL/results yourself.
- **Query History Insights / Query Profile.** Most evidence is reachable via `GET /api/2.0/sql/history/queries` (`databricks query-history list`) with `include_metrics` (spill, pruning, scan bytes, cache, Photon time, queue time) — filter client-side on `query_source.genie_space_id`. Only the pre-computed **insight labels** and one-click **`/analyze`·`/optimize`** rewrite are UI-only; derive/validate those yourself.
- **Monitor-tab feedback** (thumbs up/down trends, weekly digests) is **UI-only**. Substitute per-conversation reads (`list-conversations` / `list-conversation-messages` / `list-conversation-comments`) and `system.access.audit` event reads, and state that trend/digest aggregates are unavailable.

Each subskill opens with an **"Execution Context"** section (Genie Code native UI vs CLI/MCP) and a **"Mechanism Map"** table mapping its workflow steps to the CLI/MCP substitutes. When a phase depends on a UI-only surface, say so explicitly and either substitute as above or recommend doing that phase inside Databricks Genie Code with the matching subskill.

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

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `sample_question.id must be provided` | Add 32-char hex UUID `id` to each sample question |
| `Expected an array for question` | Use `"question": ["text"]` not `"question": "text"` |
| No warehouse available | Create a SQL warehouse or provide `warehouse_id` |
| Empty `serialized_space` on export | Requires CAN EDIT permission on the space |
| Tables not found after migration | Remap catalog name in `serialized_space` before import |
| Slow answers / query timeouts | Size up the warehouse attached to the space; simplify or pre-aggregate tall source tables |
| Wrong or empty answers | Add `example_question_sqls` and `text_instructions` — see [Improving a Genie Space](#improving-a-genie-space) |

**If you're constructing `serialized_space` JSON by hand** and getting errors like `Expected 'START_OBJECT' not 'VALUE_STRING'`, `must be sorted by id`, `must contain at most one item`, or `Unknown field`, see [spaces.md §Exact Field Schemas](references/spaces.md#exact-field-schemas-verified-against-the-genie-api) for the verified shapes of `text_instructions`, `example_question_sqls`, `benchmarks`, and `sample_questions`, plus a self-contained Python helper.

## Related Skills

- **[databricks-metric-views](../databricks-metric-views/SKILL.md)** - Build governed business metrics that Genie consumes. See [genie-integration.md](../databricks-metric-views/references/genie-integration.md) for metric-view design rules that affect Genie answer quality (one-fact-source rule, base view pattern for multi-fact KPIs, agent metadata, domain organization), and [query-patterns.md](../databricks-metric-views/references/query-patterns.md) for the `MEASURE()` query rules Genie must follow.
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Use Genie Spaces as agents inside Supervisor Agents
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate raw parquet data to populate tables for Genie
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables consumed by Genie Spaces
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs, schemas, and tables Genie queries
