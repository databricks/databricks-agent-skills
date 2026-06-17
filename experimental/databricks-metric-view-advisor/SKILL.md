---
name: databricks-metric-view-advisor
description: Use this skill when the user wants to create Unity Catalog metric views — whether starting from gold/fact tables, existing AI/BI dashboards, SQL query files, Genie spaces, or KPI spreadsheets. Triggers on intent like "formalize our KPIs," "build a metric/semantic layer," "define measures and dimensions from our tables," "standardize aggregations so other teams can reuse them," or "turn our ad-hoc queries into reusable metrics." Guides an interactive workflow — analyzing source assets, generating YAML definitions, checking for overlap with existing views, and deploying. Do NOT use for querying or altering an already-existing metric view, comparing metric view frameworks, creating regular Unity Catalog tables/schemas, or MLflow/model tracking.
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-metric-views
---

# Metric View Advisor

Create Unity Catalog metric views from your existing Databricks assets — gold/fact schemas, AI/BI dashboards, SQL queries, Genie spaces, or KPI files. This advisor guides an interactive workflow that analyzes those sources, synthesizes them into richer, deduplicated suggestions, checks for overlap with views that already exist, and walks deployment end to end. Unlike a single-input "create a metric view" helper, it combines **multiple input sources** into one coherent set of definitions.

> **⚠️ REQUIRED — this skill depends on its parent `databricks-metric-views`.**
> The advisor is **not self-contained**: the baseline metric-view YAML specification
> (top-level fields, dimensions, measures, window measures, joins, filter,
> materialization) and the baseline pattern library live **only** in the parent
> **`databricks-metric-views`** skill. You **must** have that skill available and
> load it alongside this one — the advisor's reference files deliberately point
> back to it instead of duplicating the spec. Without the parent skill, the
> advisor cannot produce correct definitions.

**FIRST**: Read the parent **`databricks-metric-views`** skill for the baseline YAML spec and patterns. This advisor builds on that foundation and only documents the *additional* material it needs — the interactive multi-source workflow, input-source handlers, overlap detection, and the advisor-specific YAML/pattern extras (gotchas, composability, semantic metadata, LOD, the SQL-source fallback).

**Prerequisites:**
1. **The parent `databricks-metric-views` skill** must be available and loaded (see the REQUIRED note above) — this is mandatory, not optional.
2. A working **Databricks CLI (>= v1.0.0)** authenticated to a workspace profile. All CLI/SQL commands this skill needs are documented in **[references/cli-operations.md](references/cli-operations.md)** — read that file before running any command in the steps below.

## How tools are used

All operations run through the **Databricks CLI**. The mechanics — executing SQL, discovering table schemas, fetching dashboard/Genie definitions, deploying and querying metric views — are documented in **[references/cli-operations.md](references/cli-operations.md)**. Read that file before running any command in the steps below. In short:

- **Run SQL**: `databricks experimental aitools tools query "<SQL>" --profile <PROFILE>` (long DDL → `aitools tools statement submit --file`, see cli-operations.md)
- **Inspect a table**: `databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>`
- **Default warehouse**: `databricks experimental aitools tools get-default-warehouse --profile <PROFILE>`
- **Fetch a dashboard**: `databricks lakeview get <dashboard_id> --profile <PROFILE>` (draft definition with datasets); **fetch a Genie space / metric-view definition**: `databricks api get ...` (see cli-operations.md)

> **If the host agent has its own native tools** (e.g. a `readAssetById`-style dashboard/asset reader), it may use those instead of these commands. That's fine — but **verify the result is non-empty**. A native reader often returns the *published* dashboard serialization, which can come back empty (`datasets: []`, `pages: []`); an empty result is a fetch-method artifact, not an empty dashboard. When a native fetch returns empty or partial data, fall back to the CLI/REST commands documented in [references/cli-operations.md](references/cli-operations.md) (for dashboards: try `lakeview get`, then `lakeview get-published`, then Input 3).

## Workflow Overview

**CRITICAL: This is an interactive, step-by-step workflow.** After completing each step, you MUST stop and wait for the user's response before proceeding to the next step. Never combine multiple steps into a single response. Never skip ahead. Each step should be its own conversational turn.

**Opening message:** When the skill starts, greet the user and outline the setup:

> "I'll help you create Unity Catalog metric views from your existing Databricks assets.
>
> You can combine **multiple input sources** — schemas, dashboards, queries, Genie spaces, and KPIs — and I'll synthesize insights from all of them.
>
> I have **5 quick setup questions** — I'll ask them one at a time:
> 1. Databricks workspace / profile
> 2. Input sources (pick any combination)
> 3. Source identifiers
> 4. Target location
> 5. Review preference
>
> Let's begin!"

Then immediately ask the first question. **Ask questions one at a time.** Do NOT show details of upcoming questions — just ask the current one, wait for the response, then move to the next. If the user proactively provides multiple answers in one message, accept them and skip those questions.

### Step 1: Gather Setup Info (ask one at a time)

Ask these questions **sequentially**, waiting for a response after each.

**1a. Databricks workspace / CLI profile**

Establish the workspace profile and authentication:
- **NEVER auto-select a profile.** List profiles with `databricks auth profiles`, present them all (with workspace URLs) to the user, and let them choose — even if only one exists.
- Accept a profile name, or a workspace URL the user types directly.
- Validate auth before continuing with `databricks auth describe --profile <PROFILE>` (no token is minted — it just reports the resolved host and auth status). If auth fails or the profile is stale, re-authenticate by running `databricks auth login --profile <PROFILE>` when starting the advisor session (the host is already stored in the profile — only pass `--host <workspace-url>` when creating a brand-new profile) before proceeding.

**After auth is validated**, discover a SQL warehouse for the session (automatic — not a user question):

```bash
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>
```

Store the warehouse id for all SQL execution this session. The `query` / `discover-schema` tools auto-pick the default warehouse, so an explicit id is only needed for the `statement submit` path (pass `--warehouse <ID>` or set `DATABRICKS_WAREHOUSE_ID`). Don't prompt the user with a warehouse question — pick the default automatically. **But if the user names a specific warehouse** (by id or by referring to one in the session), honor that choice instead of the default and use it for all SQL this session.

**STOP — wait for the user's response.**

**1b. Input sources (multi-select)**

Ask which input sources they want to use. They can pick **any combination** — the more sources, the richer the metric view suggestions.

| # | Input Source | What You Need | Requires Schema? |
|---|-------------|---------------|-----------------|
| 1 | **Gold schema** | `catalog.schema` | — (is a schema) |
| 2 | **AI/BI dashboard** | Dashboard ID or URL | No |
| 3 | **Queries on gold tables** | `.sql` file path | Yes — needs `catalog.schema` |
| 4 | **Genie space** | Space ID | No |
| 5 | **KPIs, Measures & Dimensions** | `.csv`/`.yaml` file path | Yes — needs `catalog.schema` |

> "Pick one or more (e.g., `1, 2` or `1, 3, 5`). I'll combine insights from all selected sources."

**Note:** If the user selects **3** or **5** without also selecting **1**, you still need a `catalog.schema` — ask for it in Step 1c. If the user selects **1** along with **3** or **5**, that same schema is shared.

**STOP — wait for the user's response before continuing.**

**1c. Source identifiers**

Based on **all** input sources selected in 1b, ask for the required identifiers. Collect everything needed in one question — group the asks clearly:

- **Gold schema (1)** → `catalog.schema`
- **AI/BI dashboard (2)** → Dashboard ID or URL
- **Queries on gold tables (3)** → `.sql` file path (+ `catalog.schema` if source 1 was not selected)
- **Genie space (4)** → Space ID
- **KPIs, Measures & Dimensions (5)** → `.csv`/`.yaml` file path (+ `catalog.schema` if source 1 was not selected)

If multiple sources share a `catalog.schema` (e.g., 1 + 3 + 5), ask for it once.

**STOP — wait for the user's response before continuing.**

**1d. Target catalog.schema**

Ask: "Which `catalog.schema` should the metric views be created in? (Can be the same as or different from the source.)"

After the user responds, **validate the target schema exists** before continuing — run `SHOW SCHEMAS IN <catalog> LIKE '<schema>'` (see cli-operations.md for how to execute SQL):

- If the schema exists → proceed to the next question.
- If the schema does **not** exist → tell the user:
  > "The schema `<catalog>.<schema>` does not exist. Would you like me to create it, or would you prefer to use a different target?"
  - If the user says create it → run `CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>`, confirm success, then proceed.
  - If the user provides a different target → validate that one instead.

**STOP — wait for the user's response before continuing.**

**1e. Discover existing metric views (automatic — not a user question)**

After the target schema is confirmed, **automatically** check for existing metric views in the target schema. This prevents duplicate/overlapping views from accumulating across multiple runs of the skill.

1. **List existing metric views** — metric views appear in `information_schema.tables` with `table_type = 'METRIC_VIEW'` (they do NOT appear in `SHOW VIEWS`):

```sql
SELECT table_name FROM <target_catalog>.information_schema.tables
WHERE table_schema = '<target_schema>' AND table_type = 'METRIC_VIEW'
```

2. **If no metric views exist** (empty result, or the schema was just created) → note internally "Fresh schema — no existing metric views to check for overlap" and skip to Step 1f.

3. **If metric views exist**, fetch each one's definition with `DESCRIBE TABLE EXTENDED <full_name> AS JSON` (see cli-operations.md). From each, extract the **structural fingerprint**: source table (fully qualified), dimensions `(name, expr)`, measures `(name, expr)`, joined tables. Gracefully skip any view where the describe fails (it may be a regular SQL view).

4. **Store this inventory internally** for use in Step 3's overlap check.

5. **Present an informational summary** (do NOT ask a question — just inform and proceed):

> **Existing metric views in `<target_catalog>.<target_schema>`:**
>
> | # | View | Source Table | Dims | Measures |
> |---|------|-------------|------|----------|
> | 1 | order_metrics | ...orders | 9 | 9 |
> | 2 | lineitem_analytics | ...lineitem | 16 | 15 |
>
> I'll check for overlap with my suggestions before creating anything new.

Then proceed automatically to Step 1f.

**1f. Review preference**

| # | Option |
|---|--------|
| 1 | **Review first** — I'll show suggestions and save them to a YAML file for your review/editing before creating anything |
| 2 | **Auto-create** — I'll generate and deploy metric views automatically (suggestions file still saved for reference) |

**STOP — wait for the user's response before continuing.** SQL file saving defaults to yes — only mention it if the user asks.

**How review preference affects the workflow:**
- **Review first (1):** Step 3 saves `suggestions.yaml`, displays suggestions, and waits for the user to approve, edit the file, or provide an alternative file before proceeding to Step 4. Each subsequent step also waits for user confirmation.
- **Auto-create (2):** Step 3 still saves `suggestions.yaml` for reference. Steps 3–4 proceed automatically (no approval needed for suggestions or YAML generation). Step 5 asks about materialization. Step 6 deploys automatically and verifies with test queries. Step 7 (sample queries) and next steps proceed without waiting.

### Step 2: Analyze the Inputs

For **each** selected input source, follow its detailed analysis instructions in [references/input-handlers.md](references/input-handlers.md). Run all applicable handlers, then **merge** findings into a single combined analysis.

**Reference files** — load these when generating definitions:
- **Parent `databricks-metric-views` skill** — the baseline YAML spec (top-level fields, dimensions, measures, window measures, joins, filter, materialization) and the baseline pattern library (ratios, filtered measures, TPC-H demo, detailed window measures, ALTER). Read it first.
- [references/yaml-reference.md](references/yaml-reference.md) — advisor additions to the spec: gotchas table, expanded source options, composability, extra measure/join rules, semantic metadata, LOD, extra materialization detail, and a correct comprehensive example
- [references/patterns.md](references/patterns.md) — advisor template patterns (metadata-rich single-table & composability templates, correctly-quoted star/snowflake joins, the SQL-source fallback) plus a pointer to the parent's additional patterns

**Analysis steps when multiple sources are selected:**

1. **Run each input handler** — Execute the analysis steps for every selected source (e.g., if the user selected Gold schema + Dashboard + KPIs, run Input 1, Input 2, and Input 5 handlers).
2. **Merge findings** — Combine all discovered tables, dimensions, measures, and relationships into one unified picture. See the "Merging Multiple Input Sources" section in [references/input-handlers.md](references/input-handlers.md) for detailed merge rules.
3. **Cross-validate** — Use insights from one source to enrich another:
   - Dashboard queries reveal which schema columns are actually used in practice
   - KPI definitions provide business names for raw column aggregations
   - Genie sample questions reveal how users think about the data
   - SQL queries show recurring patterns that should be standardized
   - Schema inspection uncovers tables/columns that other sources missed

**The combined analysis must produce:**
1. A list of **source tables** with their columns, types, row counts, and comments (table-level and column-level)
2. Identified **fact tables** (contain measures/events) vs **dimension tables** (contain attributes/lookups)
3. Identified **relationships** between tables (foreign keys, join paths, Genie join instructions, dashboard JOIN clauses)
4. Candidate **dimensions** (categorical columns, dates, hierarchies) — noting which input source(s) each came from. Include null-safe handling for nullable columns.
5. Candidate **measures** (numeric columns suitable for aggregation) — noting which input source(s) each came from. Include both **atomic measures** (SUM, COUNT, AVG) and **composed measures** (ratios, rates, filtered measures built using `MEASURE()` composability).
6. **Candidate global filters** — persistent WHERE conditions that should always apply (e.g., exclude historical data before a cutoff date, exclude cancelled/test records). Look for common WHERE clauses in dashboard queries, SQL files, and Genie SQL query instructions.
7. **Metadata inventory** — catalog/schema comments, table/column comments, Genie column descriptions, UC tags, partition/clustering keys, and dashboard parameters. These inform `comment`, `display_name`, and `synonyms` fields on every dimension and measure.
8. **Cross-source insights** — patterns discovered by combining sources (e.g., "Dashboard uses `SUM(amount)` which maps to KPI 'Total Revenue'; Genie users ask about this as 'total sales'").

Present findings to the user in a summary table. If multiple sources contributed to the same dimension or measure, note the provenance (e.g., "Region — from schema column + dashboard filter + Genie sample question").

**STOP — wait for the user to acknowledge the analysis before proceeding to suggestions.**

### Step 3: Suggest Metric Views

Based on your analysis, suggest metric views that would provide value. This step checks for **overlap with existing metric views**, builds suggestions from all gathered metadata, runs a **gap analysis**, then saves and presents `suggestions.yaml` for the user to approve, edit, or extend.

**Follow the full procedure in [references/step-3-suggest-metric-views.md](references/step-3-suggest-metric-views.md)** — it covers the overlap-detection logic (coverage scoring + extend / replace / create-alongside / skip), the per-field suggestion checklist, the gap analysis, the `suggestions.yaml` format, the timestamped output-folder convention, and how to handle the user's response.

**STOP — wait for the user to respond before proceeding.** Do NOT generate YAML definitions until the user approves the suggestions or provides an updated file. (Auto-create mode: proceed without waiting, but still resolve any 40–69% overlap by asking.)

### Step 4: Create Metric View Definitions

For each approved metric view, generate the full `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$` definition, save it into the run folder, and present it to the user.

**Follow the full procedure in [references/step-4-create-definitions.md](references/step-4-create-definitions.md)** — it covers the CREATE-statement template, the critical YAML rules (version, composability, snowflake dot-chain, `MEASURE()` backticking, no `format` blocks, `DATEDIFF`), the prefer-joins-then-SQL-source fallback strategy, and the local SQL-file saving convention.

**STOP — wait for the user to review the generated definitions before proceeding.**

### Step 5: Materialization (optional — ask before deploy)

Before deployment, ask the user whether they want to add materialization to any of the metric view definitions. **Do NOT auto-decide.** Materialization is configured as part of the YAML definition, so it must be decided before deploying.

> "Before I deploy, would you like to add **materialization** to pre-compute aggregations for faster queries?
>
> | # | Option |
> |---|--------|
> | 1 | **No materialization** — queries run on live data (default, simplest) |
> | 2 | **Yes, add materialization** — I'll help you configure pre-computed aggregations |
>
> Materialization is useful when metric views are queried frequently, source tables are large, or you want sub-second responses. It requires serverless compute and incurs Lakeflow Declarative Pipelines charges."

**STOP — wait for the user's response.**

**If the user chooses 1:** Skip to Step 6.

**If the user chooses 2:** Walk through materialization configuration:
- **5a. Select which metric views to materialize** (present a numbered list; accept `1`, `1, 2`, or `all`). **STOP — wait.**
- **5b. Configure type for each** — Aggregated (pick dimension/measure combos), Unaggregated (full data model), or Both. **STOP — wait.** For Aggregated/Both, suggest the most likely dimension/measure combinations based on what appeared most across input sources, then **STOP — wait.**
- **5c. Set refresh schedule** — `every 1 hour` / `every 6 hours` / `every 24 hours` / custom. If table properties revealed a `refresh_frequency`, note that a faster schedule won't provide fresher data. **STOP — wait.**
- **5d. Update definitions** with the `materialization:` block (see the *Materialization — Additional Detail* section in [references/yaml-reference.md](references/yaml-reference.md) and the **Materialized Metric View** pattern in the parent `databricks-metric-views` skill), update the saved SQL files, and re-display the final YAML.

### Step 6: Deploy

Ask the user if they want to deploy:

> | # | Option |
> |---|--------|
> | 1 | **Deploy now** — I'll create the metric views (includes materialization if configured) |
> | 2 | **Review only** — you already have the SQL files; you'll deploy manually later |

**STOP — wait for the user's response before deploying.**

Deploy each metric view by submitting its saved `<metric_view_name>.sql` file (written in Step 4) with `databricks experimental aitools tools statement submit --file <metric_view_name>.sql --warehouse <warehouse_id>`, then confirming success with `statement get <statement_id>` (see cli-operations.md — long DDL goes through the file-based `statement` path, not the inline `query` tool, to avoid heredoc/JSON escaping issues). If the user opted out of saving SQL files in Step 1, write the statement to a temporary `.sql` file first. If the user chose "Replace" for any overlap in Step 3, drop the old view after deploying the new one (`DROP VIEW IF EXISTS <old_view>`). If they chose "Extend", the view is deployed under the existing name via `CREATE OR REPLACE`.

After creation, verify each metric view with a test query (one dimension + one measure, `LIMIT 5`). Report any errors and help fix them:

| Error | Cause | Fix |
|-------|-------|-----|
| `UNRESOLVED_COLUMN` | Snowflake join missing parent prefix | Full dot-chain: `customer.nation.n_name` |
| `PARSE_SYNTAX_ERROR` | Unquoted multi-word MEASURE() name | Add backticks: `` MEASURE(`Total Revenue`) `` |
| `METRIC_VIEW_INVALID_VIEW_DEFINITION` | `format` block present | Remove all `format` blocks |
| `DATATYPE_MISMATCH` | Date subtraction instead of DATEDIFF | Use `DATEDIFF(date1, date2)` |
| `SCHEMA_NOT_FOUND` | Target schema does not exist | `CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>`, or use a different target |
| `TABLE_OR_VIEW_NOT_FOUND` | Source/joined table dropped or renamed | Verify with `SHOW TABLES IN <catalog>.<schema> LIKE '<table>'` and fix the reference |
| `INSUFFICIENT_PRIVILEGES` | Missing `CREATE VIEW` or `USE SCHEMA` on target | `GRANT CREATE TABLE, USE SCHEMA ON SCHEMA <schema> TO <principal>` (least privilege), or use a schema the user owns |

If materialization was configured, also tell the user how to trigger a manual refresh (`REFRESH MATERIALIZED VIEW <name>`), check status (`DESCRIBE EXTENDED <name>`), verify query rewrite (`EXPLAIN EXTENDED <query>` — look for `__materialization_mat___metric_view`), and that refreshes incur Lakeflow Declarative Pipelines charges.

**STOP — wait for the user to confirm deployment results are satisfactory before proceeding.**

### Step 7: Show Sample Queries

**CRITICAL — Metric View Query Syntax.** Metric views are NOT regular SQL views. Every query MUST use both `MEASURE()` and `GROUP BY` together:

```sql
SELECT
  `Dimension Name`,
  MEASURE(`Measure Name`) AS `Measure Name`
FROM catalog.schema.metric_view
GROUP BY ALL
ORDER BY `Dimension Name`;
```

- **`MEASURE()` wrapper** — every measure column MUST be wrapped, or you get `METRIC_VIEW_MISSING_MEASURE_FUNCTION`.
- **`GROUP BY`** — dimensions MUST appear in a `GROUP BY` (use `GROUP BY ALL`), or you get `MISSING_GROUP_BY`.
- **`SELECT *` is NOT supported** on metric views.

For each created metric view, generate 3-5 sample queries demonstrating: basic aggregation (one dim, two measures); multi-dimension slice; filtered query; time trend (if a date dimension exists); and Top-N (`ORDER BY measure DESC LIMIT 10`). Backtick-quote names with spaces, use `GROUP BY ALL`, and alias each `MEASURE()` call.

**Execute each sample query** to verify it works and show the results. **Save** each metric view's queries as `<metric_view_name>_sample_queries.sql` in the run folder (default: yes, unless the user opted out).

**STOP — wait for the user to acknowledge before presenting next steps.**

### Next Steps (suggestions)

1. **Grant access**: `GRANT SELECT ON VIEW <metric_view> TO <principal>` to share with teams
2. **Add to a Genie space**: metric views work natively with AI/BI Genie for natural language querying
3. **Add to AI/BI dashboards**: use as datasets for visualizations
4. **Set up SQL alerts**: threshold-based alerts on measures
5. **BI tools / JDBC**: metric views are accessible via the Databricks JDBC driver and BI connectors
6. **Compose metric views**: use an existing metric view as the source for a new one — layered metrics
7. **Inspect with metadata**: `DESCRIBE TABLE EXTENDED <metric_view> AS JSON` for the full definition
8. **Set PK/FK constraints with RELY** on underlying tables for optimal join performance

## Important Notes

- **DBR 17.2+ required** for YAML v1.1 metric views
- **SELECT * is NOT supported** — must explicitly list dimensions and use MEASURE()
- **Querying requires BOTH `MEASURE()` AND `GROUP BY`** — using only one causes an error (see Step 7)
- **MEASURE() cannot use OVER clause** — no window function usage on measures
- **Window measures** (running totals, period-over-period) require `version: 0.1` — only suggest these if the user specifically asks
- **Joins must be many-to-one** — in many-to-many cases, only the first match is used
- **Joins are LEFT OUTER JOIN** — dimension rows without fact matches are excluded; fact rows without dimension matches get NULLs
- **Source can be a SQL query** — e.g., `(SELECT * FROM table WHERE active = true)` — but joins are NOT supported with SQL query sources
- Always add `comment` and `synonyms` fields — they power Genie's natural language understanding
- Prefer fewer, richer metric views over many narrow ones

## Limitations

- **No Delta Sharing** — metric views cannot be shared via Delta Sharing
- **No data profiling** — data profiling is not supported on metric views
- **ALTER VIEW removes UC comments** — unless `comment` fields are explicitly in the YAML
- **Materialization is experimental** — only `relaxed` mode supported; requires serverless compute
