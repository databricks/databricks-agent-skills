---
name: create-genie-space
description: "Create or refine an initial Databricks Genie Space design from Unity Catalog tables, views, and Metric Views. Works inside Databricks Genie Code (native UI) or from an external agent via the Databricks CLI/MCP. Use when users ask to build, bootstrap, or draft a focused Space, inspect workspace data context, choose data sources, design structured context, examples, sample questions, Chat or Agent benchmarks, or prepare safe proposed Space changes without source data mutation."
---

# Create Genie Space

Create a focused Genie Space using Databricks-native context: inspect Unity Catalog metadata, profile candidate data sources, design the Space surfaces, and propose changes for approval — without mutating source data.

## Execution Context

This skill runs in either of two contexts. **The workflow below is identical; only the *mechanism* differs.**

- **(a) Inside Databricks Genie Code (native UI)** — resolve `@`-assets, browse Unity Catalog, run approved notebook/SQL-editor steps, and review the proposed Space in the native editor.
- **(b) Outside Databricks via CLI/MCP** (e.g. Claude Code) — use the Databricks CLI as the default, MCP where available. See [Mechanism Map](#mechanism-map-cli--mcp) below for the per-step command mapping.

**Prerequisites (context b):** authenticated `databricks` CLI (profile or `DATABRICKS_HOST`/token), a running Pro or Serverless SQL warehouse with `CAN USE`, and `SELECT` on the source tables.

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
7. Design the Genie Space surfaces in priority order — structured context first, free-text instructions last (see `references/space-design-guide.md` → Design Priorities). The more governed the surface, the earlier it belongs:
   - space description: set this **first** — it states the Space's purpose/scope and is required for multi-agent routing (supervisor agents delegate based on it)
   - data sources: keep the attached tables/views/Metric Views focused
   - Metric View metadata: prefer governed Metric View semantics over duplicated SQL
   - descriptions: table/Metric View/column descriptions that clarify business meaning and selection boundaries
   - synonyms and display names: map business terms to fields
   - format assistance and entity matching / prompt matching: enable only for eligible, useful categorical strings
   - hidden fields: remove noisy technical columns from end-user context
   - joins: add standard raw-table relationships only when evidence or user confirmation supports them
   - SQL expressions (snippets): reusable filters, expressions, and measures not already governed by Metric Views
   - example SQL: representative complex question patterns; instructive, not memorized benchmark answers
   - SQL functions: trusted registered UC logic
   - text instructions: **last resort** — use only for global behavior that cannot be encoded in the structured surfaces above; include adapted justification when proposing or editing them
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

## Mechanism Map (CLI / MCP)

Per-step mapping of the workflow's native (Genie Code) actions to their CLI/MCP equivalents for context (b). The native surfaces are primary inside Databricks; the CLI is the default outside, with MCP as an optional convenience where the server is available.

| Step | Native (Genie Code) | CLI substitute (default outside) | MCP substitute (if available) |
|------|---------------------|----------------------------------|-------------------------------|
| Profile a source (Workflow 4) | `@`-asset + notebook/SQL editor | `databricks experimental aitools tools discover-schema catalog.schema.table` (one call → columns, types, sample rows, null counts, row count); bounded `information_schema` via `databricks experimental aitools tools query` | `get_table_stats_and_schema`, `execute_sql` |
| Inspect existing Metric View (Step 5) | native editor | `databricks experimental aitools tools query "DESCRIBE EXTENDED catalog.schema.mv"` | `manage_metric_views(action="describe")` |
| Propose / apply the Space (Step 9) | native Space editor, user approves in UI | build `serialized_space` JSON and run `databricks genie create-space` / `update-space` — see parent [databricks-genie SKILL.md](../SKILL.md) for the verified field schema and stringify pattern | `manage_genie(action="create_or_update")` |
| Validate the new Space | ask questions in the Space UI | `databricks genie start-conversation` + `get-message` + `get-message-attachment-query-result` | `ask_genie` |

The "approve before live creation/update" rule still applies: outside Databricks, present the JSON config for user review and only run `create-space`/`update-space` after approval.

## Related Skills

- **`databricks-metric-views`** — design rules for AI-ready Metric Views (`genie-integration.md`) and the `MEASURE()` query rules Genie must follow (`query-patterns.md`). Use existing Metric Views as governed sources here; when sources are raw tables for reusable KPIs, recommend creating a Metric View with this skill and confirm with the user first.
- **`databricks-genie`** — the parent orchestration hub for the full Space lifecycle (create, query, export, import, migrate) and the verified `serialized_space` field schema. This subskill provides the *create* methodology; route there for the end-to-end CLI/MCP command surface.
- **`diagnose-genie-space`** / **`optimize-genie-space`** — diagnose and tune the Space after creation.
