---
name: databricks-metric-view-advisor
description: Use this skill when the user wants to create Unity Catalog metric views — whether starting from gold/fact tables, existing AI/BI dashboards, SQL query files, Genie spaces, or KPI spreadsheets. Triggers on intent like "formalize our KPIs," "build a metric/semantic layer," "define measures and dimensions from our tables," "standardize aggregations so other teams can reuse them," or "turn our ad-hoc queries into reusable metrics." Guides an interactive workflow — analyzing source assets, generating YAML definitions, checking for overlap with existing views, and deploying. Do NOT use for querying or altering an already-existing metric view, comparing metric view frameworks, creating regular Unity Catalog tables/schemas, or MLflow/model tracking.
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-metric-views
---

# Metric View Advisor

Create Unity Catalog metric views from your existing Databricks assets — gold/fact schemas, AI/BI dashboards, SQL queries, Genie spaces, or KPI files. This advisor analyzes those sources, synthesizes them into richer, deduplicated suggestions, checks for overlap with views that already exist, and walks deployment end to end. Unlike a single-input "create a metric view" helper, it combines **multiple input sources** into one coherent set of definitions.

> **This advisor is part of the `databricks-metric-views` skill** — it lives in the
> `metric-view-advisor/` sub-folder. The baseline metric-view YAML specification
> (top-level fields, dimensions, measures, window measures, joins, filter,
> materialization) and the baseline pattern library live in the **parent
> `databricks-metric-views` skill** one level up (`../SKILL.md`, `../references/`).
> This sub-folder documents only the *additional* material the advisor needs and
> points back to the parent for the spec rather than duplicating it. It ships with
> the parent skill, so there is no separate install. Read the parent for the
> baseline; use this advisor when the user wants a guided, multi-source build.

**Prerequisites:**
1. **The baseline spec from the parent `databricks-metric-views` skill** (`../SKILL.md` and `../references/`) — read it first for the YAML spec and patterns.
2. A working **Databricks CLI (>= v1.0.0)** authenticated to a workspace profile. All CLI/SQL commands this skill needs are documented in **[references/cli-operations.md](references/cli-operations.md)** — read that file before running any command in the steps below.

## How tools are used

All operations run through the **Databricks CLI**. The mechanics — executing SQL, discovering table schemas, fetching dashboard/Genie definitions, deploying and querying metric views — are documented in **[references/cli-operations.md](references/cli-operations.md)**. Read that file before running any command in the steps below. In short:

- **Run SQL**: `databricks experimental aitools tools query "<SQL>" --profile <PROFILE>` (long DDL → `aitools tools statement submit --file`, see cli-operations.md)
- **Inspect a table**: `databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>`
- **Default warehouse**: `databricks experimental aitools tools get-default-warehouse --profile <PROFILE>`
- **Fetch a dashboard**: `databricks lakeview get <dashboard_id> --profile <PROFILE>` (draft definition with datasets); **fetch a Genie space / metric-view definition**: `databricks api get ...` (see cli-operations.md)

> **If the host agent has its own native tools** (e.g. a `readAssetById`-style dashboard/asset reader), it may use those instead of these commands. That's fine — but **verify the result is non-empty**. A native reader often returns the *published* dashboard serialization, which can come back empty (`datasets: []`, `pages: []`); an empty result is a fetch-method artifact, not an empty dashboard. When a native fetch returns empty or partial data, fall back to the CLI/REST commands documented in [references/cli-operations.md](references/cli-operations.md) (for dashboards: try `lakeview get`, then `lakeview get-published`, then Input 3).

## How this advisor works

This advisor is **information-driven, not a fixed interview.** The steps below describe *what* to produce and the order that makes sense — but you decide, from context, how to get there: proceed on what you already have, ask only for what is genuinely missing or ambiguous, and fetch what you can discover yourself. Do not march through a scripted list of questions or stop after every micro-step.

**Operating principles:**
- **Gather, don't interrogate.** Read the user's request first. If they already named a profile, sources, identifiers, or a target schema, use them — don't re-ask. Batch any genuinely-missing inputs into a single, clear request rather than one question at a time.
- **Decide with judgment.** When you have enough to take the next useful action, take it. When something is ambiguous or missing, ask. When it is discoverable (schemas, existing views, warehouse), fetch it instead of asking.
- **Checkpoint where it matters.** Pause for the user before consequential or hard-to-undo actions — creating a schema, deploying, and replacing/dropping an existing view — and whenever they asked to review first. You don't need to pause after routine analysis or read-only discovery.
- **Be transparent.** Summarize what you found and what you're about to do, so the user can redirect.

### Information this advisor needs (and why)

Establish these before generating definitions. Read them from the user's request where possible; discover what you can; ask for the rest.

| Information | Why it's needed | How to obtain it |
|---|---|---|
| **Workspace / CLI profile** | All SQL and asset reads run against a specific workspace | **Never auto-select a profile.** List with `databricks auth profiles` (show workspace URLs) and let the user choose — even if only one exists. Accept a profile name or a workspace URL. Validate with `databricks auth describe --profile <PROFILE>` (reports host + auth status, mints no token); if stale, re-auth with `databricks auth login --profile <PROFILE>` (host is already stored — only pass `--host` for a brand-new profile). |
| **SQL warehouse** | Needed to run SQL this session | Auto-discover the default — don't ask: `databricks experimental aitools tools get-default-warehouse --profile <PROFILE>`. `query`/`discover-schema` auto-pick it; pass `--warehouse <ID>` (or set `DATABRICKS_WAREHOUSE_ID`) only for `statement submit`. If the user names a specific warehouse, honor it for all SQL this session. |
| **Input source(s)** | The richer the inputs, the better the suggestions; any combination is valid | See the input-source table below. Use whatever the user provides; if none is clear, ask which they want. |
| **Source identifiers** | Each source needs its own locator | Per the table below. Sources 3 and 5 also need a `catalog.schema` if source 1 wasn't given; if several sources share one schema, resolve it once. |
| **Target `catalog.schema`** | Where the metric views are created (may differ from the source) | Ask if not given. **Validate it exists** with `SHOW SCHEMAS IN <catalog> LIKE '<schema>'`. If missing, ask whether to create it (`CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>` — a checkpoint, since it writes) or use a different target. |
| **Review preference** | Controls how much the user reviews before anything is created | If not stated, default to **review-first** (show suggestions, save to YAML, confirm before creating). The user can opt into **auto-create** (generate + deploy without per-step approval; still save the suggestions file). SQL-file saving defaults to yes — mention only if asked. |

**Input sources** (combine any):

| # | Input Source | Locator needed | Needs a `catalog.schema`? |
|---|-------------|---------------|-----------------|
| 1 | **Gold schema** | `catalog.schema` | — (is a schema) |
| 2 | **AI/BI dashboard** | Dashboard ID or URL | No |
| 3 | **Queries on gold tables** | `.sql` file path | Yes |
| 4 | **Genie space** | Space ID | No |
| 5 | **KPIs, Measures & Dimensions** | `.csv`/`.yaml` file path | Yes |

### Discover existing metric views (do this automatically)

Once the target schema is known, **automatically** check what metric views already exist there — this is read-only discovery, so just do it (no need to ask), and it prevents duplicate/overlapping views accumulating across runs.

1. **List existing metric views** — they appear in `information_schema.tables` with `table_type = 'METRIC_VIEW'` (not in `SHOW VIEWS`):

```sql
SELECT table_name FROM <target_catalog>.information_schema.tables
WHERE table_schema = '<target_schema>' AND table_type = 'METRIC_VIEW'
```

2. **If none exist** (empty result, or you just created the schema) → note "fresh schema, nothing to overlap-check" and move on.
3. **If some exist**, fetch each definition with `DESCRIBE TABLE EXTENDED <full_name> AS JSON` (see cli-operations.md) and extract a **structural fingerprint**: source table (fully qualified), dimensions `(name, expr)`, measures `(name, expr)`, joined tables. Skip any view whose describe fails (it may be a regular SQL view). Keep this inventory for the overlap check in Step 3.
4. **Briefly summarize** what's already there (a short table of view / source / dim count / measure count) so the user has context, then continue.

**How review preference shapes the rest:**
- **Review-first (default):** save `suggestions.yaml`, show suggestions, and confirm before generating definitions; checkpoint at the consequential steps below.
- **Auto-create:** still save `suggestions.yaml`, but proceed through suggestions → definitions → deploy without per-step approval. Still ask about materialization (it changes the definition) and still confirm before deploying. Resolve any 40–69% overlap by asking even in auto-create mode.

### Step 2: Analyze the Inputs

For **each** selected input source, follow its detailed analysis instructions in [references/input-handlers.md](references/input-handlers.md). Run all applicable handlers, then **merge** findings into a single combined analysis.

**Reference files** — load these when generating definitions:
- **Parent `databricks-metric-views` skill** (`../SKILL.md` and `../references/yaml-reference.md`, `../references/patterns.md`) — the baseline YAML spec (top-level fields, dimensions, measures, window measures, joins, filter, materialization) and the baseline pattern library (ratios, filtered measures, TPC-H demo, detailed window measures, ALTER). Read it first.
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

Analysis is read-only — share the summary and continue to suggestions. Pause only if the findings are ambiguous or the user asked to review each step.

### Step 3: Suggest Metric Views

Based on your analysis, suggest metric views that would provide value. This step checks for **overlap with existing metric views**, builds suggestions from all gathered metadata, runs a **gap analysis**, then saves and presents `suggestions.yaml` for the user to approve, edit, or extend.

**Follow the full procedure in [references/step-3-suggest-metric-views.md](references/step-3-suggest-metric-views.md)** — it covers the overlap-detection logic (coverage scoring + extend / replace / create-alongside / skip), the per-field suggestion checklist, the gap analysis, the `suggestions.yaml` format, the timestamped output-folder convention, and how to handle the user's response.

**Checkpoint (review-first):** present the suggestions and wait for the user to approve, edit the file, or supply an alternative before generating definitions. **Auto-create:** proceed without waiting — but still resolve any 40–69% overlap by asking.

### Step 4: Create Metric View Definitions

For each approved metric view, generate the full `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$` definition, save it into the run folder, and present it to the user.

**Follow the full procedure in [references/step-4-create-definitions.md](references/step-4-create-definitions.md)** — it covers the CREATE-statement template, the critical YAML rules (version, composability, snowflake dot-chain, `MEASURE()` backticking, `format` blocks, `DATEDIFF`), the prefer-joins-then-SQL-source fallback strategy, and the local SQL-file saving convention.

**Checkpoint (review-first):** show the generated definitions and let the user review before deploying. In auto-create mode, continue.

### Step 5: Materialization (optional — decide before deploy)

Materialization is part of the YAML definition, so it must be settled before deploying — **ask the user; don't auto-decide.** Offer it plainly:

> "Before I deploy, would you like to add **materialization** to pre-compute aggregations for faster queries? It's useful when views are queried frequently, source tables are large, or you want sub-second responses — it requires serverless compute and incurs Lakeflow Declarative Pipelines charges. (Default: no materialization.)"

If they decline, go to Step 6. If they want it, configure it — gather these together and ask only for whatever they don't specify, rather than one prompt per item:
- **Which views** to materialize (one, several, or all).
- **Type** per view — Aggregated (pick dimension/measure combos), Unaggregated (full data model), or Both. For Aggregated/Both, suggest the most likely dimension/measure combinations based on what appeared most across input sources.
- **Refresh schedule** — e.g. `every 1 hour` / `every 6 hours` / `every 24 hours` / custom. If table properties revealed a `refresh_frequency`, note that a faster schedule won't yield fresher data.

Then **update definitions** with the `materialization:` block (see the *Materialization — Additional Detail* section in [references/yaml-reference.md](references/yaml-reference.md) and the **Materialized Metric View** pattern in the parent `databricks-metric-views` skill), update the saved SQL files, and re-display the final YAML.

### Step 6: Deploy

Ask the user if they want to deploy:

> | # | Option |
> |---|--------|
> | 1 | **Deploy now** — I'll create the metric views (includes materialization if configured) |
> | 2 | **Review only** — you already have the SQL files; you'll deploy manually later |

**Checkpoint — confirm before deploying.** Deploying writes to the workspace, so always get the user's go-ahead first (this holds in auto-create mode too).

Deploy each metric view by submitting its saved `<metric_view_name>.sql` file (written in Step 4) with `databricks experimental aitools tools statement submit --file <metric_view_name>.sql --warehouse <warehouse_id>`, then confirming success with `statement get <statement_id>` (see cli-operations.md — long DDL goes through the file-based `statement` path, not the inline `query` tool, to avoid heredoc/JSON escaping issues). If the user opted out of saving SQL files in Step 1, write the statement to a temporary `.sql` file first. If the user chose "Replace" for any overlap in Step 3, drop the old view after deploying the new one (`DROP VIEW IF EXISTS <old_view>`). If they chose "Extend", the view is deployed under the existing name via `CREATE OR REPLACE`.

After creation, verify each metric view with a test query (one dimension + one measure, `LIMIT 5`). Report any errors and help fix them:

| Error | Cause | Fix |
|-------|-------|-----|
| `UNRESOLVED_COLUMN` | Snowflake join missing parent prefix | Full dot-chain: `customer.nation.n_name` |
| `PARSE_SYNTAX_ERROR` | Unquoted multi-word MEASURE() name | Add backticks: `` MEASURE(`Total Revenue`) `` |
| `METRIC_VIEW_INVALID_VIEW_DEFINITION` | Malformed `format` block (missing/incorrect `type`) | Fix the `format` block — set a valid `type` (`number`/`currency`/`percentage`/`date`/`date_time`); `currency` also needs `currency_code` (see yaml-reference.md) |
| `DATATYPE_MISMATCH` | Date subtraction instead of DATEDIFF | Use `DATEDIFF(date1, date2)` |
| `SCHEMA_NOT_FOUND` | Target schema does not exist | `CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>`, or use a different target |
| `TABLE_OR_VIEW_NOT_FOUND` | Source/joined table dropped or renamed | Verify with `SHOW TABLES IN <catalog>.<schema> LIKE '<table>'` and fix the reference |
| `INSUFFICIENT_PRIVILEGES` | Missing `CREATE VIEW` or `USE SCHEMA` on target | `GRANT CREATE TABLE, USE SCHEMA ON SCHEMA <schema> TO <principal>` (least privilege), or use a schema the user owns |

If materialization was configured, also tell the user how to trigger a manual refresh (`REFRESH MATERIALIZED VIEW <name>`), check status (`DESCRIBE EXTENDED <name>`), verify query rewrite (`EXPLAIN EXTENDED <query>` — look for `__materialization_mat___metric_view`), and that refreshes incur Lakeflow Declarative Pipelines charges.

Report the deployment results. If anything failed, help fix it before moving on.

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

Then share the next-step suggestions below.

### Next Steps (suggestions)

1. **Grant access**: `GRANT SELECT ON VIEW <metric_view> TO <principal>` to share with teams
2. **Add to a Genie space**: metric views work natively with AI/BI Genie for natural language querying
3. **Add to AI/BI dashboards**: use as datasets for visualizations
4. **Set up SQL alerts**: threshold-based alerts on measures
5. **BI tools / JDBC**: metric views are accessible via the Databricks JDBC driver and BI connectors
6. **Compose metric views**: use an existing metric view as the source for a new one — layered metrics
7. **Inspect with metadata**: `DESCRIBE TABLE EXTENDED <metric_view> AS JSON` for the full definition
8. **Set PK/FK constraints with RELY** on underlying tables for optimal join performance

## Important Notes (advisor heuristics)

> **The baseline spec lives in the parent `databricks-metric-views` skill** (`../SKILL.md`, `../references/yaml-reference.md`) — YAML versions and DBR requirements, query rules (`MEASURE()` + `GROUP BY`, no `SELECT *`, `MEASURE()` without `OVER`), join structure/cardinality/semantics, window-measure requirements, and materialization. **Follow the spec there.** This advisor deliberately does **not** restate the spec, so the two can't drift apart; the notes below are advisor-specific guidance only.

- Always add `comment`, `display_name`, and `synonyms` to dimensions and measures — they power Genie's natural-language understanding (the advisor's core value-add).
- Prefer fewer, richer metric views over many narrow ones.
- **Window measures** (running totals, period-over-period, YTD): only *suggest* them when the user specifically asks — see the parent skill for their `version`/DBR requirements.
- **SQL-query source fallback**: prefer declarative joins; fall back to a SQL-query `source` only when the joins can't be expressed declaratively (joins aren't supported on a SQL-query source). See [references/patterns.md](references/patterns.md).

## Limitations

These are advisor-relevant facts not covered by the parent's spec sections (for spec-level limits, see the parent skill):

- **No Delta Sharing** — metric views cannot be shared via Delta Sharing
- **No data profiling** — data profiling is not supported on metric views
- **`ALTER VIEW` removes UC comments** — unless `comment` fields are explicitly in the YAML
