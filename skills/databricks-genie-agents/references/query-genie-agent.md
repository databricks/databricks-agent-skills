# Query Genie Agent

Reference for querying a specific Genie Agent via the Conversation API and authoring queries against Metric View data sources.

## Conversation API

> **Scope:** use this to query **one specific Genie Agent** — typically to validate an Agent
> after creating or editing it, or to lean on its curated business logic and certified queries.
> For general natural-language data questions or finding data across your workspace, don't use
> this — route to the **[databricks-data-discovery](../../databricks-data-discovery/SKILL.md)**
> skill (Genie One) instead.

Ask questions via three CLI primitives: `start-conversation`, `create-message` (follow-ups), and `get-message` (state + SQL + text). `--no-wait` returns immediately with `{conversation_id, message_id}`; poll `get-message` until `.status` is `COMPLETED`, `FAILED`, or `CANCELLED`. Intermediate states: `SUBMITTED`, `FILTERING_CONTEXT`, `ASKING_AI`, `EXECUTING_QUERY`.

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

If Genie asks for clarification instead of returning results, `.attachments[].text.content` will contain the clarifying question — rephrase with more specifics and call `create-message` again in the same conversation.

Expected response time: simple aggregations ~30s, complex joins ~60–120s, large scans 120s+.

## Agent Mode API

> **Canonical reference:** https://docs.databricks.com/en/genie-agents/api — fetch this when the request format below stops working; the doc has the authoritative schema and current examples.
> **Status:** Beta — requires preview enrollment "Agent Mode APIs for Genie Agents". The endpoint may change without notice.

The Agent mode API streams the full agent response — reasoning plan, SQL executions, and synthesized final answer — as Server-Sent Events. Use it when you need more than a generated SQL statement: synthesis validation, multi-step analysis, and Agent-mode benchmark assessment.

### When to use Agent mode vs Conversation API

| Use case | API to use |
|----------|-----------|
| Validate synthesis, multi-step analysis, or hard benchmark questions | Agent mode API — see below |
| Simple conversational follow-ups, quick SQL validation | Conversation API (`start-conversation` / `get-message`) — see above |
| Native benchmark scoring (Chat mode only) | `genie-create-eval-run` — does **not** support Agent mode |

### Setup

```bash
pip install databricks-openai databricks-sdk
```

```python
from databricks.sdk import WorkspaceClient
from databricks_openai import DatabricksOpenAI

SPACE_ID = "<32-hex-space-id>"
w = WorkspaceClient(profile="<PROFILE>")
host = w.config.host if w.config.host.startswith("http") else f"https://{w.config.host}"

client = DatabricksOpenAI(workspace_client=w)
client.base_url = f"{host}/api/2.0/genie/agents/{SPACE_ID}"
```

Auth resolves from the profile — no manual token handling needed.

### Event types

| Event type | What it contains |
|-----------|-----------------|
| `response.created` | `conversation_id` — save this for follow-ups |
| `reasoning` | Agent's reasoning step / investigation plan |
| `function_call` | SQL query the agent decided to execute (`arguments.sql`) |
| `function_call_output` | Query result as a markdown table |
| `message` | Final synthesized answer (`content[].text`) |
| `response.completed` | Terminal — full `response` object |
| `response.failed` | Terminal — `response.error` |

### Extract the final answer

```python
import json

stream = client.responses.create(
    model="genie-agent",
    input=[{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Your question here"}]}],
    stream=True,
)
for event in stream:
    if event.type == "response.completed":
        for item in event.response.output:
            if item.type == "message":
                print(item.content[0].text)
```

To continue an existing conversation, pass `extra_body={"conversation_id": conversation_id}` to `create`.

### Extract SQL queries executed

```python
for event in stream:
    if event.type == "response.output_item.done" and event.item.type == "function_call":
        sql = json.loads(event.item.arguments).get("sql")
        if sql:
            print(sql)
```

### Agent-mode benchmark evaluation loop

```python
QUESTIONS = [
    "Which city is best for outdoor activities?",
    "What makes Baghdad the hottest city?",
]

for q in QUESTIONS:
    print(f"=== {q} ===")
    stream = client.responses.create(
        model="genie-agent",
        input=[{"type": "message", "role": "user", "content": [{"type": "input_text", "text": q}]}],
        stream=True,
    )
    for event in stream:
        if event.type == "response.completed":
            for item in event.response.output:
                if item.type == "message":
                    print(item.content[0].text)
    print()
```

## Querying Metric Views

If a Genie Agent's data source is a **metric view** (not a plain table), Genie's SQL — and any `example_question_sqls` / `text_instructions` you author — must follow the `MEASURE()` query rules, or you'll hit `MISSING_AGGREGATION` errors and degraded answers. Key rules:

- **Never** reference a non-grouped dimension inside a `CASE` that also calls `MEASURE()` — put that dimension in `GROUP BY ALL` in a CTE, then aggregate in the outer query.
- Use a pre-built blended measure (e.g. `MEASURE(blended_spread)`) instead of reconstructing per-dimension branching with `CASE WHEN`.
- **Never** put a measure column in `WHERE` or `GROUP BY` — measures are only valid via `MEASURE()` in `SELECT`. Filter NULL/unwanted results with `HAVING` or an outer query/CTE.

See [databricks-metric-views/query-patterns.md](../../../skills/databricks-metric-views/references/query-patterns.md) for full rules and examples.
