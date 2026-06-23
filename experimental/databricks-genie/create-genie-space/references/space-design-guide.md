# Genie Space Design Guide

Use this reference when creating or reviewing a Genie Space in Genie Code.

## Requirements And Discovery

Start from the user's actual intent:

- Capture purpose, audience, draft title, and 3-5 concrete business questions.
- Capture business terms, metric definitions, fiscal/calendar conventions, default filters, security caveats, and benchmark mode.
- If objects are not specified, search or browse with exact terms, synonyms, abbreviations, related entities, and common fact/dimension naming patterns.
- Recommend a focused source set, ideally 5 or fewer objects initially, and explain how each source maps to the business questions.

Before deeper profiling, check feasibility. Flag missing measures, dimensions, time fields, Metric View measures, or join paths. Let the user add sources, adjust questions, or proceed with explicit limitations.

## Space Sizing

- **Hard limit:** 30 tables/views/Metric Views per Genie Space.
- **Practical guidance:** keep Spaces focused — the tighter the domain, the better Genie performs. Aim well under the limit; 5 or fewer objects is a good starting target.
- Organize Spaces by **business domain/subdomain**, not by report. A domain (e.g. "Marketing") maps to a Space; if a domain is broad, split by subdomain (e.g. "Online Marketing").
- If a domain approaches 30 items, split it into multiple Spaces by subdomain.
- Assign domain/subdomain tags to both Genie Spaces and their underlying tables/Metric Views for discoverability and observability.
- Optional: mirror the hierarchy in Unity Catalog — one schema per domain or subdomain.

## Read-Only Discovery And Profiling

Use workspace metadata first, then run focused read-only SQL only when metadata is not enough. Use `references/data-profiling-and-readiness.md` for SQL templates covering structure, row counts, grain, freshness/date ranges, null/empty/constant columns, cardinality, casing, boolean-as-string values, join overlap, Metric View `MEASURE()` behavior, PII/ETL/noisy fields, usage/lineage, and per-question readiness.

## Design Priorities

Prefer structured context over broad instructions. Add surfaces in this order — the more governed the surface, the earlier it belongs, and free-text instructions are the last resort:

1. **Space description** — set first. States the Space's purpose/scope and is required for multi-agent routing (supervisor agents delegate based on it).
2. Metric View semantic metadata when it already owns the business definition.
3. Focused data source selection.
4. Table, Metric View, and column descriptions.
5. Synonyms and display names for business terms.
6. Format assistance and entity matching for eligible categorical strings.
7. Join specs for raw tables exposed together.

Surfaces 4-6 plus hidden fields are all applied **per column** through `data_sources.tables[].column_configs[]` (`description`, `synonyms`, `enable_format_assistance`, `enable_entity_matching`, `exclude`). This array is optional, so a Space created without it ships with none of these — build it explicitly during creation, adding one entry per column that needs tuning. Enable format assistance and entity matching **selectively** (useful categorical dimensions/filters only — never blanket-enable on IDs, hashes, free text, lat/long, or raw measures). See the verified schema in `../../references/spaces.md` → Exact Field Schemas.
8. SQL snippets for reusable filters, expressions, and measures not already governed by Metric Views.
9. Example SQL for complex question patterns.
10. SQL functions for trusted registered logic.
11. Short text instructions only for global behavior that cannot be encoded structurally.

### Vocabulary

Genie-UI / common terms map to the surfaces above as follows:

| Common term | Surface here |
|-------------|--------------|
| Space description / instructions header | Space description (#1) |
| SQL expressions | SQL snippets (#8) |
| SQL queries / SQL instructions / trusted/certified SQL | Example SQL (#9) |
| SQL functions | SQL functions (#10) |
| General instructions / notes / text instructions | Text instructions (#11) |

## Text Instruction Last-Resort Rule

Do not use text instructions as the default place for guardrails, policies, metric logic, table-selection rules, join rules, filter rules, ranking/windowing rules, or long best-practice lists. If the proposed instruction names specific tables, Metric Views, columns, joins, filters, denominators, numerators, aliases, ranking logic, or window logic, first try to encode the rule in focused source selection, Metric View metadata, source/column descriptions, synonyms, prompt matching, format assistance, entity matching, join specs, SQL snippets, representative example SQL, SQL functions, or an upstream semantic model fix.

Use text instructions only for global behavior that cannot be encoded structurally, such as broad ambiguity handling, response-quality expectations, caveats, or user-facing summary constraints. When proposing or editing text instructions, carry over the optimization-style justification requirement and adapt it for creation/refinement context:

```markdown
## Text Instruction Justification

- Exact instruction text:
- Why structured surfaces were insufficient:
- Intended global behavior:
- Possible overreach or regression risk:
- How the instruction will be reviewed or validated:
```

## Metric View Guidance

Canonical, deeper rules live in the `databricks-metric-views` skill: `genie-integration.md` (designing AI-ready Metric Views — one-fact-source, base views, agent metadata) and `query-patterns.md` (the `MEASURE()` query rules — `CASE`+`MEASURE()` grouping, no measures in `WHERE`/`GROUP BY`). The points below are the in-product summary.

- Treat Metric Views as governed semantic sources.
- Do not attach underlying raw tables unless users also need raw-detail questions.
- Do not duplicate Metric View formulas in snippets or examples unless the example teaches a query shape. The metric's *definition* (the formula) lives once in the Metric View and should be referenced via `MEASURE()`; an example may include a measure only to demonstrate a non-obvious query *shape* (e.g. CTE-then-join, ranking, time logic), never to re-derive the formula.
- If the semantic model is wrong or missing a governed measure, dimension, join, or filter, document that as an upstream modeling issue instead of working around it with broad Genie instructions.
- Do not use `SELECT *` against Metric Views in examples or benchmarks.
- If a Metric View output must be combined with another source, wrap the Metric View query in a CTE before joining.

## Incremental Build & Validation

Add and validate **one measure/question at a time**. Skipping this is the most common cause of broken Spaces — when you add many at once you cannot isolate which addition confused Genie.

```text
For each KPI / question:
  1. Add ONE measure (or one Metric View) to the Space
  2. Ask sample questions in the Genie Space
  3. Compare Genie's result against the source-of-truth report
  4. Save the validated query as an EXAMPLE SQL in the Space
  5. Add 2-4 phrasings of the question to BENCHMARKS with ground-truth SQL
  6. Run regression tests (rerun all benchmarks)
  7. Only then add the next measure
```

Saved example queries are reused and imitated by Genie — keep them simple (prefer `WHERE` over `CASE`; avoid unnecessary subqueries/window functions) so each adds less reasoning load. Rerun all benchmarks after **every** change; a previously passing benchmark that now fails almost always means the latest addition confused Genie. For eval-driven tuning after creation, hand off to `../../optimize-genie-space/SKILL.md`.

## Examples And Benchmarks

There is no fixed minimum count for SQL snippets, example SQL, or benchmarks — size each by **coverage**, not a quota. Manufacturing filler to hit a number competes with governed surfaces and violates the priority order above.

- **SQL snippets (#8):** add only for reusable filters/expressions/measures the Metric View does not already govern. When the source is a well-modeled Metric View, **zero is often correct** — do not re-derive governed formulas as snippets.
- **Example SQL (#9):** cover the distinct *query shapes* the Space's questions require — e.g. simple aggregate, group-by-dimension, time filter/window, ratio/`MEASURE()` composition, ranking, and CTE-then-join — rather than a target count. One good example per shape beats many near-duplicates.
- **Benchmarks:** add ground truth per the intended execution mode (checked SQL for Chat, evaluation notes for Agent). No minimum applies at creation; if the Space is intended for later eval-driven tuning, aim toward the **≥30 valid-item** bar in `optimize-genie-space` (e.g. 2-4 phrasings per core question) so a benchmark-repair pass is not needed first.
- Validate every example SQL, benchmark SQL, snippet, and join with read-only execution or `EXPLAIN` when possible.
- Use real profiled values for parameter defaults, benchmark literals, and sample question wording.
- Parameterized examples may use `:param_name`, but every parameter needs a description, type hint, and real default value.
- Benchmarks should be concrete and hardcoded, not parameterized.
- Avoid zero-row benchmark SQL unless the benchmark explicitly tests empty results.
- Keep sample questions user-facing, example SQL instructive, and benchmarks evaluative. Do not copy benchmark questions or benchmark answer SQL into examples.

## Readiness

Before proposing a live change, summarize High/Medium/Low confidence for each business question:

- **Semantic coverage:** measures, dimensions, filters, and time fields exist.
- **Data quality and freshness:** important fields are populated, current, typed, and have usable values.
- **Modelability:** grain and join paths are supported by evidence or user confirmation.
- **GenAI context readiness:** descriptions, synonyms, display names, and prompt matching choices map business language to data.

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
| Both the base view AND the Metric View in the same Space | Genie sees unaggregated rows and must re-derive aggregation logic | Remove the base view from the Space once a Metric View exists on top of it |
| Adding 10 measures at once before testing | Can't isolate which one broke Genie's reasoning | Add and validate one at a time |
| Genie Space with no description | Multi-agent routing fails silently | Always set a Space description |
| Complex `CASE` chains in saved example SQL | Increases Genie's reasoning load on similar questions | Simplify to `WHERE` filters; lean on composed measures |
| Prompt matching / format assistance / entity matching blanket-enabled on every column | Wastes context on IDs, hashes, free text, and raw measures | Enable selectively, only on useful categorical dimensions and filters (see Design Priorities) |
