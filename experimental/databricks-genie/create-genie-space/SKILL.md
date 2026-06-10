---
name: create-genie-space
description: "Create or refine an initial Databricks Genie Space design from Unity Catalog tables, views, and Metric Views in Databricks Genie Code Agent mode. Use inside Databricks when users ask Genie Code to build, bootstrap, or draft a focused Space, inspect workspace data context, choose data sources, design structured context, examples, sample questions, Chat or Agent benchmarks, or prepare safe proposed Space changes without source data mutation."
---

# Create Genie Space For Genie Code

Create a focused Genie Space using Databricks-native context. Rely on Genie Code Agent mode to inspect Unity Catalog metadata, open workspace assets, run approved notebook or SQL editor steps, and read returned output.

## Hard Rules

- Use only bounded read-only SQL to inspect data: `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN`, and `information_schema`.
- Never mutate Unity Catalog objects or data. Do not run `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY INTO`, or equivalent mutation.
- Do not create or alter Metric Views as part of this skill. Use existing Metric Views as Genie data sources and document any upstream semantic model gaps. When the user provides raw tables/views as the data source for reusable business metrics or KPIs, **recommend** building a governed Metric View first with the `databricks-metric-views` skill, and **ask the user to confirm** before proceeding with raw tables (creation happens in that skill, not this one).
- Do not create or update a live Genie Space unless the user explicitly asks and approves the proposed changes in Databricks.
- Do not invent business definitions, joins, fiscal calendars, default filters, or metric formulas. Ask the user when workspace evidence is insufficient.
- Do not add benchmark SQL unless it has been checked with read-only execution or `EXPLAIN`.
- Do not add Agent-style benchmark evaluation notes unless the expected response criteria are grounded in user intent, workspace evidence, or validated business definitions.

## Workflow

1. Gather requirements: target audience, Space purpose, draft title, 3-5 real business questions, known terminology, KPI definitions, fiscal/calendar conventions, default filters, security caveats, and intended benchmark execution target when benchmarks are requested.
2. Discover or confirm data: use provided `@` assets or exact Unity Catalog identifiers when available; otherwise search/browse workspace data using terms from the requirements, synonyms, abbreviations, and likely fact/dimension naming patterns. Recommend a focused source set and explain how each data source maps to the business questions.
3. Check feasibility before deep inspection. Compare selected tables/views/Metric Views to the business questions and flag missing measures, time columns, dimensions, or join paths. Proceed only when the user accepts the source set, adds data, or adjusts the questions.
   - If the source set is **raw tables/views** and the questions center on reusable business metrics or KPIs, recommend building a governed Metric View first with the `databricks-metric-views` skill (consistent definitions, less duplicated SQL, better Genie reasoning). Ask the user to confirm whether to build one and pause this skill until they decide; proceed with raw tables only if they decline or need raw-detail questions.
4. Inspect and profile in phases. Read Unity Catalog metadata first, then use bounded SQL and `references/data-profiling-and-readiness.md` to identify source purpose, row counts, grain, freshness, comments, columns, data types, null/empty/constant columns, categorical values, measures, sensitive/noisy fields, likely relationships, and usage/lineage signals where available.
5. For Metric Views, inspect available measures, dimensions, filters, joins, time dimensions, comments, display names, synonyms, and formatting before adding extra Genie context. Prefer governed Metric View semantics over duplicated SQL logic.
6. Assess readiness for each business question with High/Medium/Low confidence based on semantic coverage, data quality/freshness, modelability/join evidence, and GenAI context readiness. Mark unsupported questions and upstream semantic model gaps explicitly.
7. Design the Genie Space surfaces:
   - data sources: keep the attached tables/views/Metric Views focused
   - descriptions and synonyms: clarify business meaning and selection boundaries
   - hidden fields: remove noisy technical columns from end-user context
   - prompt matching: enable only for eligible, useful categorical strings
   - joins: add standard raw-table relationships only when evidence or user confirmation supports them
   - snippets/examples: add reusable business logic and representative complex patterns only after metadata is insufficient
   - text instructions: use only for global behavior that cannot be encoded in structured surfaces; include adapted justification when proposing or editing them
   - sample questions and benchmarks: cover realistic user workflows without teaching from benchmark answers. For benchmarks, choose SQL answers, evaluation notes, or both based on answer shape and intended execution mode.
8. Review the draft against `references/space-design-guide.md` before proposing live changes.
9. Present the proposed Space configuration in the Databricks-native editor or chat output for user review. Apply only after the user approves.

## Output

Provide:

- The Genie Space title or draft title.
- The data sources included and why each belongs.
- Per-question readiness confidence and data gaps.
- Important metadata, prompt matching, join, snippet, example, sample question, and benchmark choices.
- Benchmark execution target and field strategy when benchmarks are included.
- Any assumptions or user confirmations needed before live creation or update.
- The read-only validation performed and any limitations.
- Any Metric View recommendation made for raw-table sources and the user's decision.

## Related Skills

- **`databricks-metric-views`** — design rules for AI-ready Metric Views (`genie-integration.md`) and the `MEASURE()` query rules Genie must follow (`query-patterns.md`). Use existing Metric Views as governed sources here; when sources are raw tables for reusable KPIs, recommend creating a Metric View with this skill and confirm with the user first.
- **`databricks-genie`** — the programmatic / MCP companion: create, query, export, import, and migrate Spaces from outside Databricks when you are not in Genie Code Agent mode.
- **`diagnose-genie-space`** / **`optimize-genie-space`** — diagnose and tune the Space after creation.
