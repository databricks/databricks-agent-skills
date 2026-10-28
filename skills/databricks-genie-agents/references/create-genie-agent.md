# Create Genie Agent

Everything needed to create (or update) a focused Genie Agent: the workflow, the
`serialized_space` payload format, and the CLI. Work top to bottom.

## Rules

- Read-only SQL only while profiling: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, `information_schema`. Never mutate UC objects or data.
- Don't create/alter Metric Views here — that's the `databricks-metric-views` skill.
- Business definitions, joins, fiscal calendars, and metric formulas come from evidence (the data, table/column comments, docs, or the user), not guesses. Where you have to assume one, state the assumption in the design so the user can correct it.

## Workflow

### Step 1 — Pin down what you know

A good Agent needs:

- **Target audience** — who uses it and their domain fluency (shapes description, synonyms, and how much explanation the instructions carry).
- **Purpose** — the business area / data domain it covers.
- **Data sources** — the tables / Metric Views (identifiers or keywords to find them), plus any documents (a UC volume, see [Documents](#documents-uc-volumes)).
- **Real business questions** — a few concrete questions users will actually ask.
- **Domain context** — terminology, KPI definitions, fiscal conventions, default filters.

Profiling (Step 2) fills whatever's missing:

- **Given the sources + questions** → use them; profile lightly to validate against the data, then design.
- **Discovering (demo / unfamiliar catalog)** → profile first, then derive sample questions and `example_question_sqls` from what you find; confirm the direction with the user when it matters.

Ask the user only for what you can't get from the request or profiling.

### Step 2 — Profile the data (as much as you need)

How deep depends on Step 1: light validation when the questions are given, deeper exploration when you're discovering the domain. Profile enough to understand **what the data actually contains** — so your sample questions and example SQL are grounded in real columns and values, not guesses.

Start with `discover-schema` — one call returns columns, types, sample rows, null counts, and row count:

```bash
databricks experimental aitools tools discover-schema catalog.schema.gold_orders catalog.schema.gold_customers
```

When metadata isn't enough, run focused probes. **Pass multiple SQL statements in one call to run them in parallel** (`-o json` is required for multi-query; results come back as a JSON array):

```bash
databricks experimental aitools tools query --warehouse <WH> -o json \
  "SELECT COUNT(*) AS rows, MAX(order_date) AS freshest FROM catalog.schema.gold_orders" \
  "SELECT status, COUNT(*) FROM catalog.schema.gold_orders GROUP BY status ORDER BY 2 DESC LIMIT 20" \
  "SELECT COUNT(DISTINCT customer_id) AS distinct_customers FROM catalog.schema.gold_orders"
```

Probe what affects answer quality (not a fixed list):

- **Content & meaning** — what each table/column holds, sample rows, what the metrics represent.
- **Cardinality & top values** — distinct counts and the common categorical values (drive filters + entity matching); flag null/constant columns to hide.
- **Distributions & stats** — ranges, min/max/avg, outliers on candidate measures.
- **Trends over time** — the date columns and the shape of key metrics across them (grounds time-based questions).
- **Relationships** — join keys between tables and their grain, so multi-table questions resolve.

For Metric Views, read the governed measures, dimensions, filters, joins, and `MEASURE()` patterns rather than re-deriving them.

**Optional — query history as evidence.** When `system.query.history` is readable, the SQL people already run against a source is good evidence for real joins, filters, and example SQL:

```bash
databricks experimental aitools tools query --warehouse <WH> -o json \
  "SELECT statement_text FROM system.query.history
   WHERE statement_type = 'SELECT' AND statement_text ILIKE '%gold_orders%'
     AND end_time > current_timestamp() - INTERVAL 30 DAYS
   ORDER BY end_time DESC LIMIT 20"
```

Keep the source set **focused** — 5 or fewer is a good target, 30 is the hard limit. Organize by business domain, not by report.

**Metric View check:** if the sources are raw tables and the questions center on reusable KPIs (revenue, margin, conversion rate…), a governed Metric View usually gives Genie better answers — suggest building one with the `databricks-metric-views` skill. Proceed with raw tables when they're the intended source or the questions need raw detail. Design rules that affect Genie ([metric-view-advisor.md § Genie Design Rules](../../databricks-metric-views/references/metric-view-advisor.md#genie-design-rules)): each Metric View has exactly one fact source (a single fact table is the `source`, with dimensions in its `joins`; a base view only for multi-fact or nested KPIs), and the Agent gets the Metric View, not its base view.

### Step 3 — Build the space and create

Assemble the `serialized_space` from the [surfaces below](#agent-surfaces), grounding sample questions and example SQL in the real columns/values from Step 2, then create with the [CLI](#cli).

**Two things to get right** (the rest of the surfaces are ordinary fields):

- **Populate `column_configs`.** It's optional and starts empty — an Agent without it ships with no per-column descriptions, synonyms, entity matching, or hidden fields. This is where most of the answer-quality tuning lives; build one entry per column that matters.
- **`enable_entity_matching` / `enable_format_assistance` are selective.** Turn them on only for categorical dimensions and filters users name directly — not on IDs, hashes, free text, lat/long, or raw measures.

## Agent Surfaces

Use whichever fit the sources — a Metric View Agent skips joins/snippets; a single-table Agent skips joins. Prefer governed surfaces (Metric View semantics, descriptions, synonyms) over restating the same thing in free text. **Keep each fact in one surface**: a definition stated in a column description, a snippet, and a text instruction drifts and conflicts.

- **Agent description** — set one; it tells users and calling agents what the Agent covers.
- **Metric View semantics** — when a Metric View owns the definition, reference it via `MEASURE()`; don't re-derive its formulas.
- **Per-column context** (`column_configs[]`, one entry per column): `description`, `synonyms`, `enable_format_assistance` / `enable_entity_matching` (selective — see above), `exclude` to hide noisy technical columns.
- **Join specs** — define a join when there's real evidence: a declared **foreign key** (`information_schema` / `DESCRIBE`), a PK/FK match confirmed by a cardinality check while profiling, a join seen in query history, or explicit user confirmation. Don't infer a join from column-name coincidence alone.
- **SQL snippets** — reusable filters/expressions/measures a Metric View doesn't already govern (often none for a well-modeled Metric View).
- **SQL functions** — trusted registered UC logic. Use one (not a Metric View) when a measure **fails the additivity / single-pass test**: non-additive at the queried grain, dependent on the user's filter selection, iterative, or returning a bundle of tables ([decision test](../../databricks-metric-views/references/metric-view-advisor.md#when-a-metric-view-is-not-the-right-tool--governed-function)). Clear the [methodology parity gate](improve-genie-agent.md#methodology-parity-gate) before benchmarking routing to it.
- **Example SQL** — one instructive example per distinct query *shape* (aggregate, group-by, time window, ratio/`MEASURE()`, ranking, CTE-then-join). Adapt the Step 2 probe queries and query-history samples to real columns/values; don't invent SQL.
- **Text instructions** — global behavior that isn't tied to one column: disambiguation rules, business caveats, summary/formatting expectations. Prefer a structured surface when the rule maps cleanly to one (a column synonym, a filter snippet), but instructions are a normal part of a solid room. When fixing a specific failure they're the last lever ([improve-genie-agent.md § Failure → lever](improve-genie-agent.md#failure--lever)). Max one `text_instructions` item.
- **Volumes** (`data_sources.volumes[]`): documents; the `description` says what's in them and when to use them (routing vs the tables). Setup, indexing, and limits: [Documents](#documents-uc-volumes).
- **Sample questions** — realistic questions users will ask; ground them in what the data can actually answer. (Benchmarks are a tuning-time concern — see [improve-genie-agent.md](improve-genie-agent.md).)

**Run every example SQL, snippet, and join before it goes in the payload** — execute it read-only (or `EXPLAIN` it) and confirm it succeeds and returns sensible rows. Use real profiled values for literals and parameter defaults. Qualify every column — see [Qualify Columns In SQL](#qualify-columns-in-sql).

## Qualify Columns In SQL

**Prefix every column with its source name** in `sql_snippets` and `join_specs` — a bare backtick column raises `Table name or alias is required for column` when Genie composes it into a larger statement. Use the identifier's last segment (implicit alias) or an explicit alias; prefix inside subqueries too:

```sql
-- ✅ qualified
gold_orders.`order_date` = LAST_DAY(gold_orders.`order_date`)
MEASURE(gold_orders.`total_revenue`)

-- ❌ bare → raises the error
`order_date` = LAST_DAY(`order_date`)
```

Don't prefix non-columns: string literals, `<placeholders>`, `:params`, and CTE-result names stay as-is.

## serialized_space Format

`serialized_space` is a JSON string (version 2). Keep it as a **parsed** object in a local `genie_agent.json` file (readable, editable); the CLI stringifies it at create/update time.

> **Canonical API reference:** https://docs.databricks.com/genie-agents/conversation-api — fetch it for the authoritative schema; the detail below may lag.

| Top-level key | Contents |
|-----|----------|
| `version` | `2` |
| `config` | `sample_questions` shown in the UI |
| `data_sources` | `tables` and/or `metric_views` — each has a fully-qualified `identifier` + optional `description[]` / `column_configs`; `volumes` — each `{path: "/Volumes/cat/sch/vol", description: [...]}` |
| `instructions` | `example_question_sqls`, `text_instructions`, `join_specs`, `sql_snippets` |
| `benchmarks` | evaluation Q&A (top-level, **not** under `instructions`): `{"questions": [{"id", "question": [..], "answer": [{"format": "SQL", "content": ["<sql>"]}]}]}`; full schema in [improve-genie-agent.md](improve-genie-agent.md#benchmark-repair--pruning) |

### Full example

```json
{
  "version": 2,
  "config": {
    "sample_questions": [
      {"id": "10000000000000000000000000000001", "question": ["What is our on-time performance this week?"]}
    ]
  },
  "data_sources": {
    "tables": [
      {
        "identifier": "catalog.ops.gold_otp_summary",
        "column_configs": [
          {"column_name": "flight_date", "description": ["Scheduled departure date."]},
          {"column_name": "region", "enable_format_assistance": true, "enable_entity_matching": true, "synonyms": ["area", "market"]},
          {"column_name": "internal_batch_id", "exclude": true}
        ]
      }
    ]
  },
  "instructions": {
    "example_question_sqls": [
      {"id": "20000000000000000000000000000001", "question": ["What is our on-time performance?"], "sql": ["SELECT flight_date, ROUND(SUM(on_time_count) * 100.0 / SUM(total_flights), 1) AS otp_pct FROM catalog.ops.gold_otp_summary WHERE flight_date >= date_sub(current_date(), 7) GROUP BY flight_date ORDER BY flight_date"]}
    ],
    "text_instructions": [
      {"id": "30000000000000000000000000000001", "content": ["OTP target is 85%.", "'This week' means flight_date >= date_sub(current_date(), 7)."]}
    ]
  }
}
```

### Field rules (the API is strictly validated)

- **Unique 32-char lowercase hex `id`** (no hyphens) on every item in `sample_questions`, `example_question_sqls`, `text_instructions`, `join_specs`, all `sql_snippets` sub-arrays, and `benchmarks.questions`. Question IDs unique across `sample_questions` + `benchmarks.questions` combined; instruction IDs unique across `text_instructions` + `example_question_sqls` + `join_specs` + all `sql_snippets` sub-arrays combined.
- **Text fields are arrays of strings** — `question`, `sql`, `content` (not plain strings).
- **Sort order:** id-keyed arrays sorted by `id`; `data_sources.tables`/`metric_views` by `identifier`; `column_configs` by `column_name`.
- **`text_instructions` ≤ 1 item.** **`data_sources.tables` ≤ 30.** **`volumes` ≤ 10**, MANAGED volumes only, whole volume indexed. Per-string field ≤ 25,000 chars; total JSON ≤ 3.5 MB.
- Common errors → cause: `sample_question.id must be provided` (missing hex id); `Expected an array for <field>` (string where an array is required); `must be sorted by id`; `Unknown field 'benchmarks'` (nested under `instructions` instead of top-level).

### column_configs sub-fields

| Sub-field | Type | Purpose |
|-----------|------|---------|
| `column_name` | string | required key |
| `description` | string[] | column business description |
| `synonyms` | string[] | terms that map to this column |
| `enable_format_assistance` | bool | selectively, on useful categorical dimensions |
| `enable_entity_matching` | bool | stable low/medium-cardinality strings users name |
| `exclude` | bool | hide from end-user context |

### join_specs / sql_snippets shapes

```json
{"join_specs": [
  {"id": "<32-hex>", "left": {"identifier": "samples.tpch.customer", "alias": "customer"}, "right": {"identifier": "samples.tpch.orders", "alias": "orders"}, "sql": ["`customer`.`c_custkey` = `orders`.`o_custkey`", "--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--"]}
]}
```
`sql` is a two-element array: join condition + relationship tag (`_ONE_TO_MANY--`, `_MANY_TO_ONE--`, `_ONE_TO_ONE--`, `_MANY_TO_MANY--`).

```json
{"sql_snippets": {
  "measures":    [{"id": "<32-hex>", "alias": "total_revenue", "display_name": "Total Revenue", "sql": ["SUM(orders.order_amount)"], "synonyms": ["revenue"]}],
  "filters":     [{"id": "<32-hex>", "display_name": "High value orders", "sql": ["orders.order_amount > 1000"]}],
  "expressions": [{"id": "<32-hex>", "alias": "order_year", "display_name": "Order Year", "sql": ["YEAR(orders.order_date)"]}]
}}
```
Empty `sql` arrays are rejected. Qualify all columns (above).

### Python helper (generates ids + sort order)

Starter for a single **table** source. For a Metric View source, put the identifier in `data_sources.metric_views` instead of `.tables` (same entry shape); for multiple sources, append to the relevant array.

```python
import json, uuid

def newid(): return uuid.uuid4().hex

def build_serialized_space(table_identifier, sample_questions=None, instruction_rules=None,
                           example_sqls=None, column_configs=None) -> str:
    table = {"identifier": table_identifier}
    if column_configs:
        table["column_configs"] = sorted(column_configs, key=lambda c: c["column_name"])
    payload = {"version": 2, "data_sources": {"tables": [table]}}   # metric_views: [...] for a Metric View source
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
    return json.dumps(payload, indent=2)
```

## CLI

`WAREHOUSE_ID` and the serialized space are **positional**; `title`/`description`/`parent-path` are flags — no hand-escaped JSON string.

```bash
# Resolve a warehouse (auto-detect, or list and ask if none is running)
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>

# parent_path must exist first, or create-space fails with "Tree node does not exist"
databricks workspace mkdirs /Workspace/Users/you@company.com/genie_spaces

# Create — capture the returned space_id (field is `space_id`)
SPACE_ID=$(databricks genie create-space WAREHOUSE_ID "$(jq -c . genie_agent.json)" \
  --title "Sales Analytics" \
  --description "Explore sales data" \
  --parent-path /Workspace/Users/you@company.com/genie_spaces \
  -o json | jq -r '.space_id')

# Inspect / list
databricks genie get-space "$SPACE_ID" --include-serialized-space
databricks genie list-spaces

# Update (--serialized-space is a full replacement)
databricks genie update-space SPACE_ID --serialized-space "$(jq -c . genie_agent.json)"

# Delete
databricks genie trash-space SPACE_ID

# Tag for resource tracking (beta CLI surface — ignore if it fails)
databricks workspace-entity-tag-assignments create-tag-assignment \
  geniespaces SPACE_ID ai_generated_source --tag-value databricks-agent-skills || true
```

Export unwraps the stored space back to a parsed object: `databricks genie get-space SPACE_ID --include-serialized-space -o json | jq '.serialized_space | fromjson' > genie_agent.json`. For export/import and cross-workspace migration, see [genie-agent-cicd.md](genie-agent-cicd.md).

## Documents (UC volumes)

List a UC volume in `data_sources.volumes[]`. `create-space` and `update-space` **start content indexing automatically** (Databricks parses and indexes the files; there's no enable call). A volume-only Agent is valid (the KA case); tables + a volume answers both kinds of question in one turn (the Supervisor case). Added, changed, or removed files are re-indexed automatically (about 5 minutes); meanwhile the Agent keeps answering from the files already indexed.

```bash
# 1. Dedicated MANAGED volume (external and My Files volumes aren't indexed) + upload
databricks volumes create CATALOG SCHEMA docs MANAGED
databricks fs cp -r ./pdfs dbfs:/Volumes/CATALOG/SCHEMA/docs/
```

```json
{
  "version": 2,
  "data_sources": {
    "tables":  [{"identifier": "cat.sch.returns", "description": ["One row per product return."]}],
    "volumes": [{"path": "/Volumes/cat/sch/docs",
                 "description": ["Returns-policy handbook, packaging SOP, post-incident reviews (PDF). Cite the document."]}]
  },
  "instructions": {"text_instructions": [{"id": "<32-hex>", "content": [
    "Counts / refunds: query the tables. Policy, procedure, incident questions: search the documents and cite the file."]}]}
}
```

To add documents to an **existing** Agent, export its config first (`get-space SPACE_ID --include-serialized-space -o json | jq '.serialized_space | fromjson' > genie_agent.json`), add `volumes[]` next to the existing sources, then `update-space`: it's a full replacement, so a volume-only payload drops the tables.

```bash
# 2. Create (or: update-space SPACE_ID --serialized-space ...); either one starts indexing
SPACE_ID=$(databricks genie create-space WAREHOUSE_ID "$(jq -c . genie_agent.json)" --title "Returns" -o json | jq -r .space_id)
```

3. **Wait for indexing** (about 5 minutes, even for a few small PDFs). There's no public status API: send a probe document question in Agent mode and retry every minute or so while it fails with `volume_content_search_failed` ("content search isn't ready"). One good answer shows search works, not that every file is indexed, so before an eval give it a few more minutes or probe one question per file.
4. **Ask in Agent mode.** The chat-mode Conversation API (`start-conversation`) ignores volumes and answers that it can't find the content. Call and response format: [query-genie-agent.md § Agent Mode API](query-genie-agent.md#agent-mode-api).

- **Routing = the volume `description` + one text instruction** saying what's in the documents and when to use them instead of the tables. This replaces the KA instructions and the Supervisor tool descriptions.
- **Requirements:** a workspace admin enables the Beta preview *Analyze Files in Volumes with Genie Agents* (and *Agent Mode APIs for Genie Agents* for API access). The region needs Agent mode, Lakebase, `ai_parse_document`, and Foundation Model APIs; not on AWS GovCloud; some regions (Mumbai, Singapore, Canada Central, São Paulo) need cross-Geo processing enabled by an account admin.
- **Permissions:** the Agent runs as the asking user, so every user needs `READ VOLUME` plus the *Workspace access* and *Databricks SQL access* entitlements; account-only users can't use it during the Beta. An app service principal also needs `CAN RUN` on the Agent.
- **Limits:** the **whole volume** is indexed (you can't pick a subfolder), so use a volume that holds only the documents, without eval JSON or scratch files. 10 volumes per Agent, 250 per workspace, 10,000 files per volume; files over 100 MB or 500 pages are skipped. Types: PDF, DOC/DOCX, PPT/PPTX, MD, TXT, JPG/JPEG/PNG/TIFF/TIF. For Google Drive or SharePoint content, attach an MCP connector instead of copying files into a volume.
- **Evaluate document answers with benchmarks:** a document question has no SQL answer, so write it as a benchmark with `"answer": [{"format": "SQL", "content": []}]` and the expected fact as its `evaluation_note` (e.g. from a `pdf_eval_questions.json`) (schema: [improve-genie-agent.md § Benchmark repair & pruning](improve-genie-agent.md#benchmark-repair--pruning)). `genie-create-eval-run` only runs chat mode, so it can't score document answers (they come back `NEEDS_REVIEW`); run those questions through the [Agent-mode loop](query-genie-agent.md#agent-mode-benchmark-evaluation-loop) and grade each answer against its note.
- **Billing:** parsing is billed as AI Functions (`ai_parse_document`); answering as Genie usage.

Docs: [Analyze files in volumes with a Genie Agent](https://docs.databricks.com/genie-agents/volumes).

## Anti-Patterns

| Anti-pattern | Why it fails | Fix |
|--------------|--------------|-----|
| No Agent description | Users and calling agents can't tell what it covers | Set a description |
| Adding many measures / sources at once before testing | Can't isolate which one broke Genie's answers | Add and validate one at a time; re-run the affected questions after each |
| Both a base view AND its Metric View in one Agent | Genie sees unaggregated rows, re-derives the aggregation | Attach only the Metric View |
| Bare (unqualified) columns in snippets / join specs | `Table name or alias is required for column` | [Qualify Columns In SQL](#qualify-columns-in-sql) |
| Blanket format assistance / entity matching on every column | Wastes context on IDs, hashes, free text | Enable selectively on categorical dimensions users name |
| Long rulebook in `text_instructions` | Genie reasons over prose instead of structured context | Encode in metadata / snippets / examples; keep instructions global-only |
| Duplicating a Metric View formula in a snippet | Two sources of truth, they drift | Reference via `MEASURE()`; snippet only for a non-obvious query shape |

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `sample_question.id must be provided` | Add a 32-char hex `id` to each item |
| `Expected an array for question` | Use `"question": ["text"]`, not `"question": "text"` |
| `must be sorted by id` / `Unknown field 'benchmarks'` | Sort id-keyed arrays; put `benchmarks` at top level |
| No warehouse available | Create one, or pass `--warehouse` / `WAREHOUSE_ID` |
| `volume_content_search_failed` / document questions unanswered | Indexing not done yet, or asked via chat mode; see [Documents](#documents-uc-volumes) |
| Wrong or empty answers | See [improve-genie-agent.md](improve-genie-agent.md) |

## See Also

- **[query-genie-agent.md](query-genie-agent.md)** — validate the Agent via the Conversation API.
- **[improve-genie-agent.md](improve-genie-agent.md)** — inspect, diagnose, benchmark, and tune the Agent after creation.
- **[genie-agent-cicd.md](genie-agent-cicd.md)** — export, import, cross-workspace migration.
- **`databricks-metric-views`** — build governed Metric Views to use as sources here.
