---
name: databricks-genie-agents
description: "Create, manage, and query Databricks Genie Agents — curated, per-data natural-language agents (formerly Genie Spaces): build, export/import, migrate across workspaces, and ask questions of a *specific* Agent via the Conversation API. For general data questions or finding data across your workspace, use databricks-data-discovery (Genie One) instead."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
---

# Databricks Genie Agents

Create, manage, and query Genie Agents (formerly Genie Spaces) - natural language interfaces for SQL-based data exploration.

## Overview

Genie Agents allow users to ask natural language questions about structured data in Unity Catalog. The system translates questions into SQL queries, executes them on a SQL warehouse, and presents results conversationally.

A Genie Agent is a **curated agent scoped to specific data** — its tables, sample questions, and instructions are authored for a particular business area. This is distinct from **Genie One** / the general "ask Genie" data-discovery path (see the `databricks-data-discovery` skill), which answers questions across your data without a curated, per-scope agent.

## Creating a Genie Agent

### Step 1: Understand the Data

Before creating a Genie Agent, explore the available tables to:
- **Select relevant tables** — typically gold layer (aggregated KPIs) and sometimes silver layer (cleaned facts) or metric views
- **Understand the story** — what business questions can this data answer? What insights can users discover?
- **Design meaningful sample questions** — questions should reflect real use cases and lead to actionable insights in the data

Use `discover-schema` as the default — one call returns columns, types, sample rows, null counts, and row count. If you only know the schema, list tables first with `query "SHOW TABLES IN ..."`.

`databricks experimental aitools tools discover-schema catalog.schema.gold_sales catalog.schema.gold_customers`

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

### Step 2: Create the Genie Agent

Define your Genie Agent in a local JSON file (e.g., `genie_agent.json`) for version control and easy iteration. See "serialized_space Format" below for the full structure.

```bash
# List all Genie Agents
databricks genie list-spaces

# Create a Genie Agent from a local file
# IMPORTANT: sample_questions require a 32-char hex "id" and "question" must be an array
# IMPORTANT: parent_path must ALREADY EXIST — create it first, or create fails with
#   "Tree node with path ... does not exist":
databricks workspace mkdirs /Workspace/Users/you@company.com/genie_spaces
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Explore sales data\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')
}"

# Get agent details (with full config)
databricks genie get-space SPACE_ID --include-serialized-space

# Tag the Genie Agent for resource tracking — use any tag the user indicated for their
# project; otherwise default to `ai_generated_source=databricks-agent-skills`.
# (Beta CLI surface — ignore if the command fails.)
databricks workspace-entity-tag-assignments create-tag-assignment \
  geniespaces SPACE_ID ai_generated_source --tag-value databricks-agent-skills || true

# Delete a Genie Agent
databricks genie trash-space SPACE_ID
```

### Step 3: Test and Iterate

Use the Conversation API (section below) to ask questions and verify answers. If answers are inaccurate or incomplete, improve the agent — see "Improving a Genie Agent" below.

### Export & Import

**Convention:** `genie_agent.json` always holds the **parsed** agent object (not a JSON-string-encoded blob), so it's readable and editable. At each use site we stringify it with `jq -c '.' | jq -Rs '.'` — same pattern as Step 2 Create and "Improving a Genie Agent" below. `jq -r '.serialized_space | fromjson'` on export strips the outer quoting so the file is already a parsed object.

```bash
# Export: extract serialized_space AND unwrap it to a parsed object on disk
databricks genie get-space SPACE_ID --include-serialized-space -o json \
  | jq '.serialized_space | fromjson' > genie_agent.json

# Import: same stringify pattern as Step 2 (Create)
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Migrated agent\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')
}"
```

### Improving a Genie Agent

**Recommendation-first:** when asked to optimize, tune, or fix an Agent (or its queries/tables), start by diagnosing and presenting a recommended change — do not run mutating actions (`update-space`, `ALTER`, `OPTIMIZE`, liquid clustering, warehouse changes) until the user approves. Diagnose with read-only queries only.

**Wrong filter values** (Genie filters on a value that returns nothing — e.g. asking for `cancelled` when the column stores a different code or casing): fix with prompt matching / synonyms mapping the user's term to the actual categorical value, not a hardcoded text instruction.

When Genie answers are inaccurate or incomplete, improve the agent by updating questions, SQL examples, or instructions:

```bash
# 1. Edit your local genie_agent.json (add questions, fix SQL examples, improve instructions)

# 2. Push updates back to the agent
databricks genie update-space SPACE_ID --json "{\"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')}"
```

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
- **Sort order matters:** `data_sources.tables` must be sorted by `identifier`, and each table's `column_configs` must be sorted by `column_name`; `example_question_sqls` and `text_instructions` must be sorted by `id`. (`sample_questions` is silently re-sorted server-side.)
- **`text_instructions` accepts at most one item** — the API rejects more than one (`text_instructions must contain at most one item`). Merge all guidance (persona, table guide, investigation flow, answer style) into a single entry.
- **Simple ID scheme that satisfies both rules:** prefix per list + monotonic counter, total 32 hex chars — `1…0001`, `1…0002` for `sample_questions`; `2…0001`, `2…0002` for `example_question_sqls`; `3…0001` for `text_instructions`. Authoring order = sort order, no collisions.
- **`benchmarks` is a top-level key** of `serialized_space` (alongside `version`/`config`/`data_sources`/`instructions`), not nested under `instructions`. Each item takes a unique 32-char hex `id`.

### Text Instructions

`text_instructions` make the Genie Agent more reliable by explaining:
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


## Cross-Workspace Migration

When migrating between workspaces, catalog names often differ. Export the agent, remap with `sed`, then import:

```bash
python3 -c "import sys; p=sys.argv[1]; open(p,'w').write(open(p).read().replace('source_catalog','target_catalog'))" genie_agent.json
```

Use `DATABRICKS_CONFIG_PROFILE=profile_name` to target different workspaces.

## Conversation API

> **Scope:** use this to query **one specific Genie Agent** — typically to validate an Agent
> after creating or editing it, or to lean on its curated business logic and certified queries.
> For general natural-language data questions or finding data across your workspace, don't use
> this — route to the **[databricks-data-discovery](../databricks-data-discovery/SKILL.md)**
> skill (Genie One) instead.

Ask questions of a specific Agent via three CLI primitives: `start-conversation`, `create-message` (follow-ups), and `get-message` (state + SQL + text). `--no-wait` on `start-conversation` / `create-message` returns immediately with `{conversation_id, message_id}`; poll `get-message` until `.status` is `COMPLETED`, `FAILED`, or `CANCELLED`. Intermediate states you'll see: `SUBMITTED`, `FILTERING_CONTEXT`, `ASKING_AI`, `EXECUTING_QUERY`.

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

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `sample_question.id must be provided` | Add 32-char hex UUID `id` to each sample question |
| `Expected an array for question` | Use `"question": ["text"]` not `"question": "text"` |
| No warehouse available | Create a SQL warehouse or provide `warehouse_id` |
| Empty `serialized_space` on export | Requires CAN EDIT permission on the agent |
| Tables not found after migration | Remap catalog name in `serialized_space` before import |
| Slow answers / query timeouts | Size up the warehouse attached to the agent; simplify or pre-aggregate tall source tables |
| Wrong or empty answers | Add `example_question_sqls` and `text_instructions` — see "Improving a Genie Agent" |

## Related Skills

- **[databricks-data-discovery](../databricks-data-discovery/SKILL.md)** - General natural-language data exploration / "ask Genie" (Genie One) across your data; use it when you are not targeting a specific curated Genie Agent
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate data for Genie tables
- **[databricks-pipelines](../databricks-pipelines/SKILL.md)** - Build bronze/silver/gold tables
