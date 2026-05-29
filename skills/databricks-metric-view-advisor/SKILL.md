---
name: databricks-metric-view-advisor
description: Use this skill when the user wants to create Unity Catalog metric views — whether starting from gold/fact tables, existing AI/BI dashboards, SQL query files, Genie spaces, or KPI spreadsheets. Triggers on intent like "formalize our KPIs," "build a metric/semantic layer," "define measures and dimensions from our tables," "standardize aggregations so other teams can reuse them," or "turn our ad-hoc queries into reusable metrics." Guides an interactive workflow — analyzing source assets, generating YAML definitions, checking for overlap with existing views, and deploying. Do NOT use for querying or altering an already-existing metric view, comparing metric view frameworks, creating regular Unity Catalog tables/schemas, or MLflow/model tracking.
compatibility: Requires databricks CLI (>= v0.292.0)
metadata:
  version: "1.0.0"
parent: databricks-core
---

# Metric View Advisor

**FIRST**: Use the parent `databricks-core` skill for CLI basics, authentication, profile selection, data exploration, and SQL execution. This skill builds on those primitives.

Guide users through analyzing their existing Databricks assets and creating well-structured Unity Catalog metric view definitions. Unlike a single-input "create a metric view" helper, this advisor synthesizes **multiple input sources** (schemas, dashboards, SQL queries, Genie spaces, KPI files) into richer, deduplicated suggestions, checks for overlap with views that already exist, and walks deployment end to end.

## How tools are used

All operations run through the **Databricks CLI** (per the parent `databricks-core` skill). The mechanics — executing SQL, discovering table schemas, fetching dashboard/Genie definitions, deploying and querying metric views — are documented in **[references/cli-operations.md](references/cli-operations.md)**. Read that file before running any command in the steps below. In short:

- **Run SQL**: `databricks experimental aitools tools query "<SQL>" --profile <PROFILE>` (long DDL → SQL Statements API, see cli-operations.md)
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

Defer to the parent `databricks-core` skill for profile selection and authentication:
- **NEVER auto-select a profile.** List profiles with `databricks auth profiles`, present them all (with workspace URLs) to the user, and let them choose — even if only one exists.
- Accept a profile name, or a workspace URL the user types directly.
- Validate auth before continuing (`databricks auth token --profile <PROFILE>`). If auth fails, follow `databricks-core`'s authentication guidance before proceeding.

**After auth is validated**, discover a SQL warehouse for the session (automatic — not a user question):

```bash
databricks experimental aitools tools get-default-warehouse --profile <PROFILE>
```

Store the warehouse id for all SQL execution this session. The `query` / `discover-schema` tools auto-pick the default warehouse, so an explicit id is only needed for the SQL Statements API path. Do NOT ask the user about the warehouse — pick the default automatically.

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
- [references/yaml-reference.md](references/yaml-reference.md) — Complete YAML spec (dimensions, measures, joins, materialization, window measures)
- [references/patterns.md](references/patterns.md) — Working patterns to use as templates (single table, ratios, star schema, snowflake, materialization)

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

Based on your analysis, suggest metric views that would provide value.

#### Pre-suggestion: Check for overlap with existing metric views

**If existing metric views were discovered in Step 1e**, you MUST check for semantic overlap before generating suggestions. This prevents duplicate views from accumulating across multiple runs.

**Skip this subsection entirely if:** Step 1e found no existing metric views (fresh schema).

**Comparison logic — for each candidate metric view you are about to suggest:**

1. **Match by source table** — Find all existing metric views that use the same source table (fully qualified name). This is the primary overlap signal.
2. **Compute dimension overlap** — For each pair with the same source table, compare dimension `expr` values. Normalize before comparing (strip whitespace, lowercase, ignore trivial differences like a `source.` prefix); count dimensions with matching expressions even if names differ: `dim_overlap = matching_dims / max(candidate_dims, existing_dims)`.
3. **Compute measure overlap** — Same approach for measure `expr` values: `measure_overlap = matching_measures / max(candidate_measures, existing_measures)`.
4. **Compute coverage score** — `(matching_dims + matching_measures) / (candidate_dims + candidate_measures)`:
   - **High (>=70%)**: Existing view already covers most of what you'd suggest
   - **Medium (40-69%)**: Significant overlap worth addressing
   - **Low (<40%)**: Mostly new content — minimal overlap
5. **If multiple existing views overlap the same candidate**, pick the one with the **highest coverage score** as the primary comparison target. Mention the others as additional duplicates.

**For each overlap with coverage >= 40%, present a report to the user:**

> **Overlap detected:** Your suggested `lineitem_metrics` overlaps with existing `lineitem_analytics`
>
> | | Suggested | Existing | Shared |
> |--|-----------|----------|--------|
> | Source | ...lineitem | ...lineitem | Same |
> | Dimensions | 15 | 16 | 12 |
> | Measures | 14 | 15 | 10 |
> | **Coverage** | | | **73%** |
>
> **Only in suggested (new):** Order Date, Order Month, Total Tax Amount, Avg Unit Price
> **Only in existing:** Ship Instruction, Container, Average Discount, Total Tax
>
> | # | Action | What happens |
> |---|--------|-------------|
> | 1 | **Extend existing** `lineitem_analytics` | Add the missing items to the existing view (recommended) |
> | 2 | **Replace** with `lineitem_metrics` | Drop old view, deploy new one instead |
> | 3 | **Create alongside** | Keep both (you accept the overlap) |
> | 4 | **Skip** | Don't create a lineitem-level view at all |

**How each resolution affects downstream steps:**
- **Extend (1):** Step 4 generates a `CREATE OR REPLACE VIEW` under the **existing** view name, merging all existing dimensions/measures with the new ones. Preserve existing `comment`, `synonyms`, and `display_name` values.
- **Replace (2):** Step 4 generates a `CREATE OR REPLACE VIEW` under the **new** name. Step 6 also drops the old view after deploying the new one.
- **Create alongside (3):** Normal suggestion flow — no changes.
- **Skip (4):** Remove this candidate from the suggestions entirely.

**Auto-create mode behavior:**
- Coverage >= 70% → automatically choose **Extend existing** (safest default — no duplication, no data loss)
- Coverage 40-69% → **pause and ask the user** (too ambiguous to auto-resolve)
- Coverage < 40% or no source-table match → automatically **create alongside**

**Review-first mode:** Always present the overlap report and wait for the user's response for every overlap >= 40%.

> **Safety:** Only "Extend" or "Replace" an existing metric view when the user explicitly chooses that option for the reported overlap. Never drop or overwrite a pre-existing view the user did not ask you to change.

After resolving all overlaps, proceed to generate the final suggestions list reflecting the user's choices.

---

**Building suggestions from your analysis — use ALL gathered metadata:**

Every suggestion must be a holistic synthesis of what you learned across ALL input sources — not just column names and types. For each metric view you suggest, apply this checklist:

**1. Metric view naming and `comment`:**
- Use Genie space `title`/`description` and dashboard title to name the metric view in a business-friendly way (e.g., "wholesale_supplier_order_metrics" not "orders_mv")
- Use catalog/schema comments and table comments to write a rich top-level `comment` describing the metric view's business purpose
- If Genie text instructions describe the domain, incorporate that context

**2. For each dimension — assemble from all sources:**
- **`expr`**: Prefer Genie SQL expression instructions (canonical computed columns) > dashboard query expressions > KPI definitions > raw column references. Use CHECK constraints to inform valid value sets for CASE expressions. Use partition/clustering keys as prioritized dimension candidates.
- **`comment`**: Prefer Genie column descriptions > UC column comments > KPI descriptions > SQL file comments > inferred from column name. Never leave `comment` empty if any source provided context.
- **`display_name`**: Prefer KPI names > Genie column `display_name` > dashboard parameter names > dashboard widget axis labels > humanized column name
- **`synonyms`**: Combine alternative names from ALL sources — Genie benchmark question phrasing, KPI file names, dashboard widget titles, UC column comment mentions of aliases.
- **Null safety**: If the column is nullable (from schema stats), wrap in COALESCE or CASE for null handling
- **PII check**: If UC tags include `pii:true`, flag and exclude unless the user approves

**3. For each measure — assemble from all sources:**
- **`expr`**: Prefer Genie SQL expression instructions > dashboard query aggregations > KPI definitions > SQL file patterns. If the same aggregation appears in multiple sources, that is a strong signal it's the canonical expression.
- **`comment`**: Same priority as dimensions. Include units if any source mentions them (e.g., "in USD").
- **`display_name`** and **`synonyms`**: Same approach as dimensions.
- **Composed measures**: For every pair of atomic measures where a ratio makes business sense (revenue/customers, fulfilled/total, etc.), suggest a composed measure. Look for ratios already computed in SQL files, dashboards, or KPI definitions.
- **Filtered measures**: For every status/category dimension, suggest filtered variants of key measures (e.g., if status has values 'Open', 'Fulfilled', 'Processing', suggest `Open Revenue`, `Fulfilled Orders`, etc.).

**4. Joins — assemble from all sources:**
- Prefer Genie join instructions (author-intended) > dashboard query JOINs > FK constraints > inferred from column name matching
- Include ALL dimension tables that enrich the fact table — even if not all input sources used them

**5. Filters — assemble from all sources:**
- Intersect common WHERE clauses from dashboard queries, SQL files, Genie SQL query instructions, and Genie text instructions
- Check table properties for data freshness hints

**6. Gap analysis — what's missing:**
After building suggestions from existing sources, identify what's NOT yet covered:
- **Unused schema columns**: Columns no input source referenced — are any valuable dimensions or measures?
- **Missing time dimensions**: If the source has date columns, ensure granular + truncated time dimensions exist (Date, Month, Quarter, Year)
- **Missing ratio measures**: For every pair of atomic measures, ask "does a ratio between these make business sense?"
- **Missing filtered measures**: For every categorical dimension, ask "would filtered versions of the key measures be useful?"
- **Cross-table measures**: If dimension tables exist, are there measures that should use joined columns?
- **Genie gaps**: If Genie benchmark questions ask about something not yet covered, add it

Present this gap analysis alongside the suggestions so the user sees both what you recommend AND what additional coverage they could add.

---

**Formatting guidelines (per Databricks best practices):**

- **Model atomic measures first** — Define simple, foundational measures (`SUM(revenue)`, `COUNT(1)`, `COUNT(DISTINCT customer_id)`) before complex ones. Build complex measures (AOV, fulfillment rate) using **composability** — reference earlier measures via `MEASURE()`.
- **Standardize dimension values** — Convert cryptic database codes into clear business names using CASE expressions. Never expose raw codes to users.
- **Define scope with filters** — If a metric view should only ever include certain data, define a persistent `filter` in the YAML.
- **Use business-friendly naming** — Metric names should be immediately recognizable to business users. Add `display_name` for visualization-friendly labels.
- **Separate time dimensions** — Always include BOTH the **granular date** AND **truncated variants** (Month, Quarter, Year).
- **Group related metrics** into a single metric view; don't create too many narrow views.
- **Include ratio measures** built via composability; **include filtered measures** using `FILTER (WHERE ...)`.
- **Think about Genie** — clear `comment`, `synonyms`, and `display_name` fields improve Genie answers.
- **Star schema joins** — if dimension tables exist, include them. Recommend PK/FK constraints with `RELY` on underlying tables for optimal join performance.

#### Suggestion format

Generate suggestions as a YAML file with this structure:

```yaml
# Metric View Suggestions
# Edit this file to add, remove, or modify suggestions, then provide the path back to the skill.
# Source schema: <source catalog.schema>
# Target schema: <target catalog.schema>

metric_views:
  - name: <metric_view_name>
    source_table: <fact_table>
    rationale: "<why this metric view is useful>"
    filter: "<optional global filter expression>"
    joins:
      - table: <dimension_table>
        'on': "<join condition>"
    dimensions:
      - name: <Display Name>
        expr: "<sql_expression>"
        comment: "<description>"
        display_name: "<visualization label>"
        synonyms: ["alt name 1", "alt name 2"]
    measures:
      # Define atomic measures first
      - name: <Atomic Measure>
        expr: "<aggregate_expression>"
        comment: "<description>"
        display_name: "<visualization label>"
        synonyms: ["alt name 1", "alt name 2"]
      # Then composed measures referencing atomic ones (backtick-quote names with spaces)
      - name: <Composed Measure>
        expr: "MEASURE(`<Atomic Measure 1>`) / MEASURE(`<Atomic Measure 2>`)"
        comment: "<description>"

# Gap Analysis — additional coverage opportunities
gaps:
  - type: unused_column
    table: <table>
    column: <column>
    suggestion: "<why this column could be a useful dimension or measure>"
  - type: missing_ratio
    numerator: "<measure 1>"
    denominator: "<measure 2>"
    suggestion: "<business meaning of this ratio>"
  - type: genie_gap
    question: "<Genie benchmark question not covered by current suggestions>"
    suggestion: "<what dimension or measure would answer this>"
```

#### Output folder structure

Each run creates a timestamped subfolder to preserve previous runs:

```
<target_schema>_output_metric_views/
├── run_20260403_143022/       # previous run (preserved)
├── run_20260403_161500/       # current run
│   ├── suggestions.yaml
│   ├── order_metrics.sql
│   └── ...
└── latest -> run_20260403_161500/   # symlink to most recent
```

**At the start of each run** (when you first need to save a file): generate a timestamp `run_<YYYYMMDD_HHMMSS>`, create `<target_schema>_output_metric_views/run_<timestamp>/`, and after saving update the `latest` symlink (`ln -sfn run_<timestamp> <target_schema>_output_metric_views/latest`). All paths shown to the user reference the `run_<timestamp>/` folder. This ensures previous runs are never overwritten.

#### What to do with the suggestions — always do all three

1. **Display the coverage summary** — Before listing individual suggestions, show how well the suggestions cover the discovered data (tables, dimensions, measures, joins, Genie questions), plus a gaps table.
2. **Display each suggested metric view** — show name, rationale, source table, dimensions, and measures in a readable summary, with provenance for `comment`/`display_name`/`synonyms`.
3. **Save the suggestions file** — write the full YAML (including the `gaps` section) to `<target_schema>_output_metric_views/run_<timestamp>/suggestions.yaml`.

After displaying and saving, tell the user:

> "I've saved the suggestions to `<path>/suggestions.yaml`.
>
> | # | Option |
> |---|--------|
> | 1 | **Approve as-is** — I'll create the metric views now |
> | 2 | **Add gaps** — tell me which gap numbers to include (e.g., `add 2, 3`) and I'll update the suggestions |
> | 3 | **Edit the file** — modify `suggestions.yaml`, then tell me to proceed and I'll read the updated file |
> | 4 | **Provide a different file** — give me a path to your own suggestions YAML and I'll use that instead |"

**STOP — wait for the user to respond before proceeding.** Do NOT generate YAML definitions until the user confirms or provides an updated file.

#### Handling the user's response

- **"Approve" / "1" / "looks good"** → proceed to Step 4 using the suggestions as generated
- **"Add gaps" / "2" / "add 2, 3"** → add the specified gaps, re-display the updated coverage summary, save the updated YAML, ask for approval again
- **"Proceed" / "updated" / "3"** → re-read `suggestions.yaml` from the run folder, then proceed to Step 4
- **User provides a file path** → read that file, parse it as the suggestions YAML, then proceed to Step 4

### Step 4: Create Metric View Definitions

For each approved metric view, generate the full YAML definition and present it to the user.

**Format each definition as a CREATE statement:**

```sql
CREATE OR REPLACE VIEW <catalog.schema.metric_view_name>
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "<description>"
  source: <catalog.schema.source_table>
  filter: <optional global filter>

  joins:
    - name: <dim_table_alias>
      source: <catalog.schema.dim_table>
      'on': source.<fk> = <alias>.<pk>

  dimensions:
    - name: <Display Name>
      expr: <sql_expression>
      comment: "<description>"

  measures:
    - name: <Display Name>
      expr: <aggregate_expression>
      comment: "<description>"
$$
```

**YAML rules to follow (critical subset — see [references/yaml-reference.md](references/yaml-reference.md) for the full spec and gotchas table):**
- `version: 1.1` (requires DBR 17.2+)
- Every dimension and measure needs a `name` and `expr`
- Add `comment`, `display_name`, and `synonyms` to all dimensions and measures for Genie discoverability
- **Use composability** — define atomic measures first (SUM, COUNT, AVG), then build complex measures referencing them via `MEASURE()`
- **Standardize dimension values** — use CASE expressions to convert raw codes to business-friendly names
- **Include granular + truncated time dimensions** — always add both the raw date and `Month`/`Quarter`/`Year`
- Measure `expr` must use aggregate functions (SUM, COUNT, AVG, MIN, MAX) — or `MEASURE()` for composed measures
- Reference joined table columns as `<join_name>.<column>`; use `source.<column>` when joins are present
- **Snowflake join column references** must use the **full dot-chain path** through parent joins: `customer.nation.n_name` — NOT `nation.n_name`. Common source of `UNRESOLVED_COLUMN` errors.
- **Backtick-quote `MEASURE()` references** when the measure name contains spaces: `` MEASURE(`Total Revenue`) `` — NOT `MEASURE(Total Revenue)`. Unquoted multi-word names cause `PARSE_SYNTAX_ERROR`.
- **Do NOT include `format` blocks** — the API requires undocumented `type` discriminator fields that cause parse errors. Omit format entirely.
- **Use `DATEDIFF()` for date comparisons, NOT subtraction** — `date1 - date2` returns `INTERVAL DAY`, not an integer.

**Join strategy — prefer joins, fall back to SQL source:**
- **Prefer star/snowflake joins** when possible — the optimizer only joins tables needed for each query.
- **If snowflake joins fail** (DBR < 17.1 or nested column references don't resolve), fall back to a **SQL query source** that pre-joins all tables. See Pattern 7 in [references/patterns.md](references/patterns.md).
- When using a SQL source, column references use the aliased names directly (no `source.` or `join_name.` prefix).

**Always save SQL files locally** (unless the user opted out in Step 1):
- Save into the **same timestamped run folder** created in Step 3.
- Save each metric view definition as `<metric_view_name>.sql`, and also an `all_metric_views.sql` combining all definitions.
- Inform the user of the saved folder and file paths.

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
- **5d. Update definitions** with the `materialization:` block (see Pattern 5 and the YAML reference), update the saved SQL files, and re-display the final YAML.

### Step 6: Deploy

Ask the user if they want to deploy:

> | # | Option |
> |---|--------|
> | 1 | **Deploy now** — I'll create the metric views (includes materialization if configured) |
> | 2 | **Review only** — you already have the SQL files; you'll deploy manually later |

**STOP — wait for the user's response before deploying.**

Deploy each metric view by executing its `CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$` statement via the SQL Statements API (see cli-operations.md — long DDL should use the API path, not the inline `query` tool, to avoid heredoc escaping issues). If the user chose "Replace" for any overlap in Step 3, drop the old view after deploying the new one (`DROP VIEW IF EXISTS <old_view>`). If they chose "Extend", the view is deployed under the existing name via `CREATE OR REPLACE`.

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
