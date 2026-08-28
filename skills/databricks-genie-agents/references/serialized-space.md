# serialized_space Format

Reference for constructing and debugging `serialized_space` payloads used by `create-space`, `update-space`, export/import, and CI/CD workflows.

> **Canonical API reference:** https://docs.databricks.com/aws/en/genie-agents/conversation-api — fetch this when you need the authoritative schema; this reference may lag behind doc updates.

`serialized_space` is a JSON string (version 2). Its top-level keys are:

| Key | Contents |
|-----|----------|
| `version` | Schema version (currently `2`) |
| `config` | Agent-level config: `sample_questions` shown in the UI |
| `data_sources` | `tables` and/or `metric_views` arrays — each entry has a fully-qualified `identifier` and optional `column_configs` |
| `instructions` | `example_question_sqls`, `text_instructions`, `join_specs`, `sql_snippets` |
| `benchmarks` | Evaluation Q&A pairs — see [benchmarks.questions](#benchmarksquestions) for the full schema including `evaluation_note` |

Minimum structure:
```json
{"version": 2, "data_sources": {"tables": [{"identifier": "catalog.schema.table"}]}}
```

## Field Format Requirements

**IMPORTANT:** All items in `sample_questions`, `example_question_sqls`, and `text_instructions` require a unique `id` field.

| Field | Format | Error on violation |
|-------|--------|--------------------|
| `config.sample_questions[]` | `{"id": "32hexchars", "question": ["..."]}` | `sample_question.id must be provided and non-empty. Expected lowercase 32-hex UUID without hyphens.` |
| `instructions.example_question_sqls[]` | `{"id": "32hexchars", "question": ["..."], "sql": ["..."]}` | `Expected an array for <field> but found "<value>"` |
| `instructions.text_instructions[]` | `{"id": "32hexchars", "content": ["..."]}` — max 1 item | `instructions.text_instructions must contain at most one item` |

- **ID format:** 32-character lowercase hex, no hyphens.
- **Text fields are arrays:** `question`, `sql`, and `content` are arrays of strings, not plain strings.
- **Sort order:** all id-keyed arrays (`sample_questions`, `example_question_sqls`, `text_instructions`, `join_specs`, all `sql_snippets` sub-arrays, `benchmarks.questions`) must be sorted by `id`; `data_sources.tables` and `metric_views` by `identifier`; `column_configs` by `column_name`. Violation: `instructions.example_question_sqls must be sorted by id`.
- **`benchmarks` is a top-level key** (not nested under `instructions`). Violation: `Unknown field 'benchmarks'` when nested under instructions.
- **ID uniqueness:** question IDs must be unique across `sample_questions` AND `benchmarks.questions`; instruction IDs must be unique across `text_instructions`, `example_question_sqls`, `join_specs`, and all `sql_snippets` sub-arrays.
- **Size limits:** `data_sources.tables` ≤ 30 entries; per-string field ≤ 25,000 characters; total `serialized_space` JSON ≤ 3.5 MB.

## Text Instructions

`text_instructions` make the Genie Agent more reliable by explaining:
- **Where to find information** — which tables contain which metrics
- **How to answer specific questions** — when a user asks X, use table Y with filter Z
- **Business context** — definitions, thresholds, and domain knowledge

## Example

```json
{
  "version": 2,
  "config": {
    "sample_questions": [
      {"id": "10000000000000000000000000000001", "question": ["What is our current on-time performance?"]}
    ]
  },
  "data_sources": {
    "tables": [{"identifier": "catalog.ops.gold_otp_summary"}]
  },
  "instructions": {
    "example_question_sqls": [
      {
        "id": "20000000000000000000000000000001",
        "question": ["What is our on-time performance?"],
        "sql": ["SELECT flight_date, ROUND(SUM(on_time_count) * 100.0 / SUM(total_flights), 1) AS otp_pct FROM catalog.ops.gold_otp_summary WHERE flight_date >= date_sub(current_date(), 7) GROUP BY flight_date ORDER BY flight_date"]
      }
    ],
    "text_instructions": [
      {
        "id": "30000000000000000000000000000001",
        "content": [
          "OTP questions: Use gold_otp_summary. Target is 85%.",
          "When asked about 'this week': Use flight_date >= date_sub(current_date(), 7)."
        ]
      }
    ]
  }
}
```

## Exact Field Schemas (verified against the Genie API)

The API is strictly schema-validated. Errors for wrong shapes: `Expected an array for <field>`, `Unknown field`, `<field> must be sorted by id`, `Invalid JSON in field 'serialized_space': Expected 'START_OBJECT' not 'VALUE_STRING'`.

**`data_sources.tables[].column_configs`** — per-column GenAI context. Optional and selective:

```json
{"column_configs": [
  {"column_name": "asset_type", "enable_format_assistance": true, "enable_entity_matching": true},
  {"column_name": "blended_spread", "description": ["Blended spread: zdm3yr for loans, OAS for everything else."], "synonyms": ["spread", "avg spread"]},
  {"column_name": "internal_id", "exclude": true}
]}
```

| Sub-field | Type | Purpose |
|-----------|------|---------|
| `column_name` | string | Required key |
| `description` | array of strings | Column-level business description |
| `synonyms` | array of strings | Business terms that map to this column |
| `enable_format_assistance` | bool | Enable selectively — only on useful categorical dimensions |
| `enable_entity_matching` | bool | Enable only for stable low/medium-cardinality strings users name directly |
| `get_example_values` | bool | Fetch example values for this column to aid context |
| `build_value_dictionary` | bool | Build a value dictionary for this column |
| `exclude` | bool | Hides the column from end-user context |

**These two toggles are space-only** — no Metric View equivalent. Still emit `column_configs` for categorical dimensions even for fully-governed Metric View sources.

> **Qualify all column references in snippets and join specs** — `sql_snippets` and `join_specs` SQL must prefix every column with its source name (table's last identifier segment or explicit alias). Bare columns raise `Table name or alias is required for column` at runtime. See [Qualify Columns In SQL](create-genie-agent.md#qualify-columns-in-sql).

**`instructions.example_question_sqls`** — `question` and `sql` are both arrays of strings:
```json
{"id": "<32-hex>", "question": ["What were Q1 sales?"], "sql": ["SELECT SUM(amount) FROM sales WHERE quarter = '2026-Q1'"], "usage_guidance": ["Use for time-bounded revenue aggregation."]}
```

#### benchmarks.questions

`benchmarks` is an object containing `questions`, not an array. Each question has `id`, `question`, `answer`, and optionally `evaluation_note`:

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | 32-hex string | yes | Unique across `sample_questions` AND `benchmarks.questions` |
| `question` | array of strings | yes | The benchmark question text |
| `answer` | array of answer objects | yes | At least one answer object with `format` and `content` |
| `evaluation_note` | array of strings | no | Grading guidance for Agent-mode assessment — stored at the question level, not inside `answer` |

`answer` object fields: `format` (only `"SQL"` is accepted — other values are rejected) and `content` (array of strings forming the SQL, or an **empty array** `[]` when there is no canonical SQL).

- `content: []` is accepted by the API and is the correct pattern for Agent-mode-only questions — cleaner than a placeholder like `SELECT 1` which could confuse the Chat scorer.
- `answer` is always required by the API (`benchmark_question must have at least one answer`), so even pure Agent-mode questions need `{"format": "SQL", "content": []}`.

**Benchmark field strategies** — choose per question based on execution mode:

| Strategy | When to use | `answer.content` | `evaluation_note` |
|----------|-------------|-----------------|-------------------|
| `single_sql_answer` | Deterministic Chat-mode question with one canonical result set | Checked SQL | Optional |
| `deterministic_with_response_quality` | Chat correctness AND Agent response quality both matter | Checked SQL | Grading criteria |
| `multi_step_agent_analysis` | Agent-mode synthesis — multiple queries, no single canonical SQL | `[]` (empty) | Grading criteria (required) |

For `multi_step_agent_analysis`, all grading guidance goes in `evaluation_note`. The empty `content` array satisfies the required `answer` field without polluting Chat-mode scoring.

```json
{
  "benchmarks": {
    "questions": [
      {
        "id": "40000000000000000000000000000001",
        "question": ["What were Q1 sales by region?"],
        "answer": [{"format": "SQL", "content": ["SELECT region, SUM(amount) FROM sales WHERE quarter = '2026-Q1' GROUP BY region ORDER BY 2 DESC"]}]
      },
      {
        "id": "40000000000000000000000000000002",
        "question": ["What is driving the revenue decline this quarter?"],
        "answer": [{"format": "SQL", "content": []}],
        "evaluation_note": ["Agent must investigate multiple dimensions (region, product, channel). Must cite at least 2 supporting queries. Must name the primary driver with evidence. Reject if response only states totals without root-cause analysis."]
      }
    ]
  }
}
```

**`instructions.join_specs`** — `sql` is a required two-element array: join condition + relationship tag:
```json
{"id": "<32-hex>", "left": {"identifier": "samples.tpch.customer", "alias": "customer"}, "right": {"identifier": "samples.tpch.orders", "alias": "orders"}, "sql": ["`customer`.`c_custkey` = `orders`.`o_custkey`", "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--"]}
```
Valid tags: `--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--`, `_ONE_TO_MANY--`, `_ONE_TO_ONE--`, `_MANY_TO_MANY--`.

**`instructions.sql_snippets`** — three sub-arrays: `measures`, `filters`, `expressions`. Use fully-qualified column references (see callout above). Empty `sql` arrays are rejected. `filters` and `measures` also accept an optional `synonyms` array:
```json
{"sql_snippets": {
  "measures": [{"id": "<32-hex>", "alias": "total_revenue", "display_name": "Total Revenue", "sql": ["SUM(orders.order_amount)"], "synonyms": ["revenue", "total sales"]}],
  "filters": [{"id": "<32-hex>", "display_name": "High value orders", "sql": ["orders.order_amount > 1000"], "synonyms": ["large orders", "big purchases"]}],
  "expressions": [{"id": "<32-hex>", "alias": "order_year", "display_name": "Order Year", "sql": ["YEAR(orders.order_date)"]}]
}}
```

## Python Helper

```python
import json, uuid

def newid(): return uuid.uuid4().hex

def build_serialized_space(
    metric_view_or_table: str,
    sample_questions: list[str] | None = None,
    instruction_rules: list[str] | None = None,
    example_sqls: list[tuple[str, str]] | None = None,
    benchmarks: list[tuple[str, str]] | None = None,
    column_configs: list[dict] | None = None,
) -> str:
    table = {"identifier": metric_view_or_table}
    if column_configs:
        table["column_configs"] = sorted(column_configs, key=lambda c: c["column_name"])
    payload = {"version": 2, "data_sources": {"tables": [table]}}
    if sample_questions:
        payload.setdefault("config", {})["sample_questions"] = sorted(
            [{"id": newid(), "question": [q]} for q in sample_questions], key=lambda x: x["id"])
    instructions = {}
    if instruction_rules:
        instructions["text_instructions"] = [{"id": newid(), "content": list(instruction_rules)}]
    if example_sqls:
        instructions["example_question_sqls"] = sorted(
            [{"id": newid(), "question": [q], "sql": [s]} for q, s in example_sqls], key=lambda x: x["id"])
    if instructions:
        payload["instructions"] = instructions
    if benchmarks:
        payload["benchmarks"] = {"questions": sorted(
            [{"id": newid(), "question": [q], "answer": [{"format": "SQL", "content": [sql]}]} for q, sql in benchmarks],
            key=lambda x: x["id"])}
    return json.dumps(payload)
```

Push the result via CLI:
```bash
databricks genie update-space SPACE_ID --json "{\"serialized_space\": $(python3 build.py | jq -Rs '.')}"
```
