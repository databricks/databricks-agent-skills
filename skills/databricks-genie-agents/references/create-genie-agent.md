# Create Genie Agent

Design-time reference for creating a focused Genie Agent. Follow the Workflow top to bottom — the embedded gates tell you when to pause and ask the user. Apply the design using the CLI Reference at the bottom.

## Rules

These apply throughout — never deviate regardless of what the user asks:

- Use only bounded read-only SQL: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, `information_schema`.
- Never mutate Unity Catalog objects or data (`CREATE`, `ALTER`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`).
- Do not create or alter Metric Views here — use the `databricks-metric-views` skill for that.
- Do not create or update a live Genie Agent without explicit user approval.
- Do not invent business definitions, joins, fiscal calendars, or metric formulas — ask the user.
- Do not add benchmark SQL without checking it with read-only execution or `EXPLAIN` first.

## Workflow

### Step 1 — Gather requirements ⛔ Gate

**Ask the user for all of the following before doing anything else. Do not profile data, write JSON, or run any CLI command until you have items 1–4 at minimum.**

1. **Target audience** — who will use this Agent and what is their domain fluency?
2. **Agent purpose** — what business area or data domain does it cover?
3. **3–5 real business questions** — concrete questions users will ask (not generic examples)
4. **Known data sources** — catalog/schema/table names or keywords to search for
5. **Terminology and KPI definitions** — business terms, fiscal conventions, default filters
6. **Benchmark intent** — should this Agent be evaluated? Chat mode, Agent mode, or none?

If the user provides partial information, ask for what is missing rather than assuming.

### Step 2 — Discover or confirm data

Use provided identifiers when available; otherwise search/browse workspace data using terms from the requirements, synonyms, abbreviations, and likely fact/dimension naming patterns. Recommend a focused source set (see [Agent Sizing](#agent-sizing)) and explain how each source maps to the business questions.

### Step 3 — Metric View check ⛔ Gate

**Before profiling, check whether the source set is raw tables/views with questions that center on reusable KPIs or business metrics (revenue, margin, conversion rate, etc.).**

If yes: **stop and recommend building a governed Metric View first** using the `databricks-metric-views` skill. State the benefit (consistent definitions, less duplicated SQL, better Genie reasoning). Ask the user to decide, and **pause this workflow until they answer.** Only proceed with raw tables if the user declines or the questions require raw-detail access.

If the source already includes Metric Views, or the user confirms raw tables: continue to Step 4.

### Step 4 — Inspect and profile in phases

Read Unity Catalog metadata first, then bounded SQL — see [Data Profiling](#data-profiling) — to identify source purpose, row counts, grain, freshness, comments, columns, data types, null/empty/constant columns, categorical values, measures, sensitive/noisy fields, likely relationships, and usage/lineage signals.

### Step 5 — Inspect Metric View semantics

For Metric Views, inspect available measures, dimensions, filters, joins, time dimensions, comments, display names, synonyms, and formatting before adding extra Genie context. Prefer governed Metric View semantics over duplicated SQL logic.

### Step 6 — Assess readiness

Score each business question High/Medium/Low confidence — see [Readiness Assessment](#readiness-assessment). Mark unsupported questions and upstream semantic model gaps explicitly. Do not proceed to design with Low-confidence questions unresolved.

### Step 7 — Design Agent surfaces

Design in priority order, structured context first — see [Design Priorities](#design-priorities). Two rules to call out:
- **Build `column_configs` during creation** — an Agent created without it ships with no per-column descriptions, synonyms, format assistance, entity matching, or hidden fields.
- **Qualify every column reference** in SQL snippets and example SQL — see [Qualify Columns In SQL](#qualify-columns-in-sql).

### Step 8 — Review draft

Check against [Static Health Checks](#static-health-checks) and [Anti-Patterns](#anti-patterns) before proposing changes.

### Step 9 — Present and get approval ⛔ Gate

**Present the full proposed Agent configuration to the user for review. Do not run `create-space` or `update-space` until the user explicitly approves.**

## Agent Sizing

- **Hard limit:** 30 tables/views/Metric Views per Genie Agent.
- **Practical guidance:** keep Agents focused — the tighter the domain, the better Genie performs. Aim well under the limit; 5 or fewer objects is a good starting target, both for the initial source set (Workflow step 2) and as a recommended ceiling before feasibility review (step 3).
- Organize Agents by **business domain/subdomain**, not by report. A domain (e.g. "Marketing") maps to an Agent; if a domain is broad, split by subdomain (e.g. "Online Marketing").
- If a domain approaches 30 items, split it into multiple Agents by subdomain.
- Assign domain/subdomain tags to both Genie Agents and their underlying tables/Metric Views for discoverability and observability.
- Optional: mirror the hierarchy in Unity Catalog — one schema per domain or subdomain.

## Data Profiling

Use workspace metadata first, then run focused read-only SQL only when metadata is not enough. Prefer Databricks-native metadata first, then bounded read-only SQL where it improves the plan.

### Phased Inspection

1. **Structure.** Confirm each table/view/Metric View, comments, columns, data types, constraints, and sample rows with a narrow selected column list.
2. **Quality and usage.** Profile nulls, empty strings, constants, distinct counts, casing issues, boolean-as-string values, sensitive/noisy columns, and usage/lineage when system tables are accessible.
3. **Column profiling.** Profile only columns that affect Genie quality: dates, likely filters, categorical strings, join keys, and candidate measures.
4. **Readiness.** Map the profiled data back to the user's 3-5 business questions and record High/Medium/Low confidence for each question (see [Readiness Assessment](#readiness-assessment)).

### Required Data Signals

For each table or standard view, identify row count, grain, freshness/date range, measures, dimensions, likely filters, data-quality caveats, sensitive/noisy fields, join candidates, and whether joins are supported by constraints, naming, row-count checks, query history, or user confirmation.

For each Metric View, identify governed measures, dimensions, filters, joins, time dimensions, display names, synonyms, formatting, comments, valid `MEASURE()` query patterns, and upstream semantic gaps.

### How To Use Findings

- Hide ETL metadata, all-null columns, raw blobs, embeddings, secrets, tokens, and sensitive free text.
- Put high-null, constant, inconsistent casing, and boolean-as-string caveats in `DATA QUALITY NOTES` only when Genie needs them.
- Enable format assistance on useful dimensions and filters. Enable entity matching only for stable low/medium-cardinality strings users are likely to mention.
- Use actual profiled values for example SQL parameters and benchmark literals.
- Use query history as evidence for joins, sample questions, examples, and benchmarks. If system tables are unavailable, proceed without mentioning the failure unless it limits confidence.
- Ask the user to confirm metric formulas, joins, fiscal/calendar rules, and default filters that are not supported by evidence.

## Design Priorities

Prefer structured context over broad instructions. Add surfaces in this order — the more governed the surface, the earlier it belongs, and free-text instructions are the last resort:

1. **Agent description** — set **first**. States the Agent's purpose/scope and is required for multi-agent routing (supervisor agents delegate based on it).
2. **Metric View semantic metadata** when it already owns the business definition — prefer governed Metric View semantics over duplicated SQL logic.
3. **Focused data source selection** — keep the attached tables/views/Metric Views focused (see [Agent Sizing](#agent-sizing)).
4. **Table, Metric View, and column descriptions** that clarify business meaning and selection boundaries. **Column-level** descriptions are set via `data_sources.tables[].column_configs[].description` — see the verified schema in [serialized-space.md → Exact Field Schemas](serialized-space.md#exact-field-schemas-verified-against-the-genie-api).
5. **Synonyms and display names** for business terms. **Column-level** synonyms go in `column_configs[].synonyms`.
6. **Format assistance and entity matching** (a.k.a. prompt matching) for eligible categorical strings, set per column via `column_configs[].enable_format_assistance` / `.enable_entity_matching`. Enable **selectively** — only on useful categorical dimensions and filters users name directly; never blanket-enable on IDs, hashes, free text, lat/long, or raw measures. These two toggles are **space-only** (no Metric View equivalent), so emit them even for a fully-governed Metric View source — see [serialized-space.md → column_configs](serialized-space.md#exact-field-schemas-verified-against-the-genie-api).
7. **Hidden fields** — remove noisy technical columns from end-user context via `column_configs[].exclude`.
8. **Join specs** for raw tables exposed together — add standard raw-table relationships only when evidence or user confirmation supports them.
9. **SQL snippets** (SQL expressions) for reusable filters, expressions, and measures not already governed by Metric Views — see [Qualify Columns In SQL](#qualify-columns-in-sql).
10. **Example SQL** for representative complex question patterns; instructive, not memorized benchmark answers — see [Qualify Columns In SQL](#qualify-columns-in-sql).
11. **SQL functions** — trusted registered UC logic.
12. **Text instructions** — **last resort**, see [Text Instructions Are A Last Resort](#text-instructions-are-a-last-resort).
13. **Sample questions and benchmarks** — cover realistic user workflows without teaching from benchmark answers, see [Examples And Benchmarks](#examples-and-benchmarks).

Surfaces 4-7 (descriptions, synonyms, format assistance/entity matching, hidden fields) are all applied **per column** through `data_sources.tables[].column_configs[]`. This array is optional, so an Agent created without it ships with none of these — build it explicitly during creation, adding one entry per column that needs tuning.

### Vocabulary

Genie-UI / common terms map to the surfaces above as follows:

| Common term | Surface here |
|-------------|--------------|
| Agent description / instructions header | Agent description (#1) |
| SQL expressions | SQL snippets (#9) |
| SQL queries / SQL instructions / trusted/certified SQL | Example SQL (#10) |
| SQL functions | SQL functions (#11) |
| General instructions / notes / text instructions | Text instructions (#12) |

## Text Instructions Are A Last Resort

Do not use text instructions as the default place for guardrails, policies, metric logic, table-selection rules, join rules, filter rules, ranking/windowing rules, or long best-practice lists. If the proposed instruction names specific tables, Metric Views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in focused source selection, Metric View metadata, source/column descriptions, synonyms, prompt matching, format assistance, entity matching, join specs, SQL snippets, representative example SQL, SQL functions, or an upstream semantic model fix.

Use text instructions only for global behavior that cannot be encoded structurally, such as broad ambiguity handling, response-quality expectations, caveats, or user-facing summary constraints. When proposing or editing text instructions, include this justification:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Intended global behavior:
- Possible overreach or regression risk:
- How the instruction will be reviewed or validated:
```

### Canonical Section Headers

When text instructions are warranted, use these five headers in this order (omit any that are empty):

| Header | What goes here |
|--------|----------------|
| `## PURPOSE` | One or two bullets: the space's scope and audience. |
| `## DISAMBIGUATION` | Clarification triggers and term-resolution rules (e.g. "'Q1' means calendar Q1 unless the user says 'fiscal Q1'"). |
| `## DATA QUALITY NOTES` | NULL handling, known bad rows, column semantics not captured in column descriptions. |
| `## CONSTRAINTS` | Hard guardrails: what never to show (PII columns), what not to do. |
| `## Instructions you must follow when providing summaries` | Summary behavior: rounding rules, mandatory caveats, date-range statements. **Use this exact heading — do not paraphrase it.** |

Rules:
- Markdown `## Header` per section; dash bullets, one idea per bullet; blank line between sections.
- No SQL inside bullets — SQL belongs in `example_question_sqls`, `sql_snippets`, or `join_specs`.
- Keep the total under 2,000 characters.
- Every bullet should reference a concrete asset (table, column, user phrase) or be a specific behavioral rule. Vague guidance ("be helpful") is an anti-pattern.

Example:

```markdown
## PURPOSE
- Answer questions about order revenue for FY2024 US retail orders.
- Users are merchandising managers — assume retail/e-commerce fluency.

## DISAMBIGUATION
- When the user asks about "customer performance" without a time range, ask them to clarify the period.
- "Q1" means calendar Q1 unless the user says "fiscal Q1".

## DATA QUALITY NOTES
- orders.order_amount is NULL for cancelled rows — filter with is_cancelled = false.

## CONSTRAINTS
- Never show PII columns (customer_email, customer_phone).

## Instructions you must follow when providing summaries
- Round percentages to two decimal places.
- Always state the date range used in the summary.
```

## Metric View Guidance

Canonical, deeper rules live in the `databricks-metric-views` skill (AI-ready Metric View design — one-fact-source, base views, agent metadata — and the `MEASURE()` query rules: `CASE`+`MEASURE()` grouping, no measures in `WHERE`/`GROUP BY`). The points below are the in-product summary.

- Treat Metric Views as governed semantic sources.
- **A single fact table is sourced directly** by the Metric View — do **not** build an intermediate base view for it (add dimension joins in the Metric View's `joins` block instead). Base views are for KPIs that combine **multiple fact tables** or need nested logic the Metric View cannot express directly.
- Do not attach underlying raw tables unless users also need raw-detail questions.
- Do not duplicate Metric View formulas in snippets or examples unless the example teaches a query shape. The metric's *definition* (the formula) lives once in the Metric View and should be referenced via `MEASURE()`; an example may include a measure only to demonstrate a non-obvious query *shape* (e.g. CTE-then-join, ranking, time logic), never to re-derive the formula.
- If the semantic model is wrong or missing a governed measure, dimension, join, or filter, document that as an upstream modeling issue instead of working around it with broad Genie instructions.
- Do not use `SELECT *` against Metric Views in examples or benchmarks.
- If a Metric View output must be combined with another source, wrap the Metric View query in a CTE before joining.

## Qualify Columns In SQL

**Always prefix every column reference with its source name** in SQL snippets (SQL expressions) and join specs — never emit a bare backtick-quoted column. Use the table/Metric View identifier's last segment (its implicit alias) or an explicit table alias:

```sql
-- ✅ qualified
global_sales_assets_metrics.`Trade Date` = LAST_DAY(global_sales_assets_metrics.`Trade Date`)
MEASURE(global_sales_assets_metrics.`Gross Sales (ex Cash Management)`) / <Avg AUM>
global_sales_assets_metrics.`Trade Date` > (SELECT MAX(global_sales_assets_metrics.`Trade Date`) FROM main.gcg.global_sales_assets_metrics)  -- prefix inside subqueries too

-- ❌ bare (raises the error)
`Trade Date` = LAST_DAY(`Trade Date`)
MEASURE(`Gross Sales (ex Cash Management)`)
```

Unqualified columns in these surfaces raise **`Table name or alias is required for column`** when Genie composes a snippet/expression into a larger statement. Qualifying is always safe — it works for a single-table or single-Metric-View Agent and is **required** once multiple tables are joined. Prefix columns inside subqueries too; the table's implicit alias is the final segment of its qualified name. Do **not** prefix non-column tokens — string literals, `<placeholder>` markers, `:param_name` parameters, and conceptual CTE-result names (e.g. `Current Period / Prior Period`) stay as-is.

## Examples And Benchmarks

There is no fixed minimum count for SQL snippets, example SQL, or benchmarks — size each by **coverage**, not a quota. Manufacturing filler to hit a number competes with governed surfaces and violates the [Design Priorities](#design-priorities) order.

- **SQL snippets:** add only for reusable filters/expressions/measures the Metric View does not already govern. When the source is a well-modeled Metric View, **zero is often correct** — do not re-derive governed formulas as snippets.
- **Example SQL:** cover the distinct *query shapes* the Agent's questions require — e.g. simple aggregate, group-by-dimension, time filter/window, ratio/`MEASURE()` composition, ranking, and CTE-then-join — rather than a target count. One good example per shape beats many near-duplicates.
- **Benchmarks:** add ground truth per the intended execution mode (checked SQL for Chat, evaluation notes for Agent). No minimum applies at creation; if the Agent is intended for later eval-driven tuning, aim toward the **≥30 valid-item** bar in `optimize-genie-agent.md` (e.g. 2-4 phrasings per core question) so a benchmark-repair pass is not needed first.
- Qualify every column in snippets and join specs — see [Qualify Columns In SQL](#qualify-columns-in-sql).
- Validate every example SQL, benchmark SQL, snippet, and join with read-only execution or `EXPLAIN` when possible.
- Use real profiled values for parameter defaults, benchmark literals, and sample question wording.
- Parameterized examples may use `:param_name`, but every parameter needs a description, type hint, and real default value.
- Benchmarks should be concrete and hardcoded, not parameterized.
- Avoid zero-row benchmark SQL unless the benchmark explicitly tests empty results.
- Keep sample questions user-facing, example SQL instructive, and benchmarks evaluative. Do not copy benchmark questions or benchmark answer SQL into examples.

## Readiness Assessment

Before proposing a live change, score each business question on High/Medium/Low confidence across these dimensions:

- **Semantic coverage:** measures, dimensions, filters, and time fields exist.
- **Data quality and freshness:** important fields are populated, current, typed, and have usable values.
- **Modelability:** grain and join paths are supported by evidence or user confirmation.
- **GenAI context readiness:** descriptions, synonyms, display names, and prompt matching choices map business language to data.

Roll those dimensions up into one confidence level per question:

- **High:** all required sources, fields, values, and join/metric definitions are supported.
- **Medium:** answerable with caveats, missing descriptions, uncertain filters, or user-confirmed assumptions.
- **Low:** missing source, measure, dimension, time field, join path, or governed metric definition.

Do not present Low-confidence questions as fully supported. Add data, revise the question, ask for confirmation, or mark the draft with limitations.

## Static Health Checks

Check the draft for:

- A space description that states purpose and scope (required for multi-agent routing).
- A focused source set, ideally 5 or fewer at first.
- Descriptions that state business purpose and grain.
- Hidden ingestion, audit, hash, raw JSON, embedding, and sensitive free-text fields.
- Prompt matching only on useful eligible categorical strings.
- Joins supported by constraints, naming, row-count checks, or user confirmation.
- No long rulebook-style text instructions.
- Text instructions only for global behavior that cannot be encoded structurally, with adapted justification when proposed or edited.
- Example SQL that teaches reusable patterns, not memorized test questions.
- Example SQL parameters with real defaults and descriptions.
- Benchmarks with ground truth appropriate to the intended execution mode: checked SQL for deterministic Chat-style questions, evaluation notes for Agent-style multi-step analysis, and both when a deterministic question also needs full-response judging. Cover sources, filters, measures, joins, time logic, answer shapes, evidence quality, and response synthesis as applicable.

## Anti-Patterns

| Anti-pattern | Why it fails | Fix |
|--------------|--------------|-----|
| Both the base view AND the Metric View in the same Agent | Genie sees unaggregated rows and must re-derive aggregation logic | Remove the base view from the Agent once a Metric View exists on top of it |
| Adding 10 measures at once before testing | Can't isolate which one broke Genie's reasoning | Add and validate one at a time (see `optimize-genie-agent.md`'s incremental build loop) |
| Genie Agent with no description | Multi-agent routing fails silently | Always set an Agent description |
| Complex `CASE` chains in saved example SQL | Increases Genie's reasoning load on similar questions | Simplify to `WHERE` filters; lean on composed measures |
| Bare (unqualified) columns in SQL snippets or example SQL | Raises `Table name or alias is required for column` when Genie composes the snippet | See [Qualify Columns In SQL](#qualify-columns-in-sql) |
| Prompt matching / format assistance / entity matching blanket-enabled on every column | Wastes context on IDs, hashes, free text, and raw measures | Enable selectively, only on useful categorical dimensions and filters (see [Design Priorities](#design-priorities)) |
| Assuming a governed Metric View source means no `column_configs` are needed | Format assistance and entity matching have no Metric View equivalent — they live only in space `column_configs`, so the space ships with both off | Still emit `column_configs` enabling them on the categorical dimensions users name directly, even for an MV source |

## Output

Provide:

- The Genie Agent title or draft title.
- The data sources included and why each belongs.
- Per-question readiness confidence and data gaps.
- Important metadata, prompt matching, join, snippet, example, sample question, and benchmark choices.
- Benchmark execution target and field strategy when benchmarks are included.
- Any assumptions or user confirmations needed before live creation or update.
- The read-only validation performed and any limitations.
- Any Metric View recommendation made for raw-table sources and the user's decision.

## CLI Reference

### Warehouse Selection

Always resolve the warehouse before creating or updating. Use the auto-detected default unless the user specifies one:

```bash
# Auto-detect the best available warehouse
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>
# → returns warehouse_id to use in create-space / update-space
```

If the workspace has no running warehouse, list available ones and ask the user to choose:

```bash
databricks warehouses list --profile <PROFILE>
```

### Profiling Data Sources

Use `discover-schema` as the default — one call returns columns, types, sample rows, null counts, and row count:

```bash
databricks experimental aitools tools discover-schema catalog.schema.gold_sales catalog.schema.gold_customers
```

Probe cardinality, ranges, and top categorical values:

```bash
databricks experimental aitools tools query --warehouse <WH> "SELECT region, COUNT(*) FROM catalog.schema.table GROUP BY region ORDER BY 2 DESC LIMIT 20"
```

Fan out independent probes in parallel using `statement submit` + `get`:

```bash
SIDS=()
for q in "$@"; do
  SIDS+=( "$(databricks experimental aitools tools statement submit --warehouse "$WH" "$q" | jq -r .statement_id)" )
done
for s in "${SIDS[@]}"; do databricks experimental aitools tools statement get "$s"; done
```

### Creating and Updating

```bash
# Ensure parent_path exists first — create-space fails with "Tree node does not exist" otherwise
databricks workspace mkdirs /Workspace/Users/you@company.com/genie_spaces

# Create from a local genie_agent.json file
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Explore sales data\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')
}"

# List all Genie Agents
databricks genie list-spaces

# Get agent details
databricks genie get-space SPACE_ID --include-serialized-space

# Update agent config
databricks genie update-space SPACE_ID --json "{\"serialized_space\": $(cat genie_agent.json | jq -c '.' | jq -Rs '.')}"

# Delete
databricks genie trash-space SPACE_ID

# Tag for resource tracking
databricks workspace-entity-tag-assignments create-tag-assignment \
  geniespaces SPACE_ID ai_generated_source --tag-value databricks-agent-skills || true
```

For `serialized_space` field shapes, constraints, and the Python helper see [serialized-space.md](serialized-space.md).

### Troubleshooting

| Issue | Solution |
|-------|----------|
| `sample_question.id must be provided` | Add 32-char hex UUID `id` to each sample question |
| `Expected an array for question` | Use `"question": ["text"]` not `"question": "text"` |
| Field shape errors (`START_OBJECT`, `must be sorted by id`, `Unknown field`) | See [serialized-space.md §Exact Field Schemas](serialized-space.md#exact-field-schemas-verified-against-the-genie-api) |
| No warehouse available | Create a SQL warehouse or provide `warehouse_id` |
| Wrong or empty answers | Add `example_question_sqls` and `text_instructions` — see Design Priorities above |

## See Also

- **[diagnose-genie-agent.md](diagnose-genie-agent.md)** / **[optimize-genie-agent.md](optimize-genie-agent.md)** — diagnose and tune the Agent after creation.
- **[genie-agent-cicd.md](genie-agent-cicd.md)** — export, import, cross-workspace migration.
- **[query-genie-agent.md](query-genie-agent.md)** — validate the Agent via the Conversation API.
- **`databricks-metric-views`** — AI-ready Metric View design and `MEASURE()` query rules. Use existing Metric Views as governed sources here; when sources are raw tables for reusable KPIs, recommend creating a Metric View with this skill and confirm with the user first.
