# Metric View Advisor — multi-source build workflow

Create Unity Catalog metric views from existing Databricks assets — gold/fact
schemas, AI/BI dashboards, SQL queries, Genie spaces, or KPI files. This workflow
analyzes those sources, synthesizes them into richer, deduplicated suggestions,
checks for overlap with views that already exist, and walks deployment end to end.
Unlike a single-input "create a metric view" helper, it combines **multiple input
sources** into one coherent set of definitions.

Use this reference when the user wants a guided, multi-source build (intent like
"formalize our KPIs," "build a metric/semantic layer," "define measures and
dimensions from our tables," "standardize aggregations so other teams can reuse
them," or "turn our ad-hoc queries into reusable metrics"). Do **not** use it for
querying or altering an already-existing metric view, comparing metric-view
frameworks, creating regular UC tables/schemas, or MLflow/model tracking.

> **The baseline metric-view spec lives in this skill, not here.** The parent
> `databricks-metric-views` skill (`../SKILL.md`) and its references —
> [`patterns.md`](patterns.md) (the pattern library) and
> [`yaml-reference.md`](yaml-reference.md) (top-level fields, dimensions, measures,
> window measures, joins, filter, materialization) — are the spec authority. **Read
> them first.** This file documents only the *advisor-specific* material: the
> multi-source build flow and the YAML additions that flow needs. It deliberately
> does not restate the baseline spec, so the two can't drift apart.

## Prerequisites & tooling

1. **The baseline spec** from the parent skill (`../SKILL.md`, [`patterns.md`](patterns.md), [`yaml-reference.md`](yaml-reference.md)) — read it for the YAML spec and patterns.
2. A working **Databricks CLI (>= v1.0.0)** authenticated to a workspace profile. All operations run through the CLI; the commands and fetch/parse details are in [CLI & API operations](#cli--api-operations) below. Auth, profiles, and warehouse selection are covered by the **`databricks-core`** skill.

> **If the host agent has native asset readers** (a `readAssetById`-style tool), it may use them — but **verify the result is non-empty** and fall back to the CLI fetches below if it isn't. A native reader often returns an empty *published* serialization (`datasets: []`); empty ≠ no data.

## How this advisor works

This advisor is **information-driven, not a fixed interview.** The steps below
describe *what* to produce and the order that makes sense — but you decide, from
context, how to get there: proceed on what you already have, ask only for what is
genuinely missing or ambiguous, and fetch what you can discover yourself. Do not
march through a scripted list of questions or stop after every micro-step.

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

## CLI & API operations

Auth, profiles, warehouse discovery, and the basics of running SQL via the CLI are covered by the **`databricks-core`** skill — use it for `databricks auth login` / `auth describe`, listing profiles, and picking a warehouse. Below are the commands specific to building metric views from assets.

> **No `databricks sql execute` / `execute-statement`** — those commands don't exist. Use the `aitools` query/statement commands below.

**Running SQL:**
- **Short statements** (`SHOW`/`DESCRIBE`/`SELECT`): `databricks experimental aitools tools query "<SQL>" --profile <PROFILE>` (auto-picks the default warehouse).
- **Long DDL** (`CREATE OR REPLACE VIEW ... WITH METRICS LANGUAGE YAML AS $$...$$`): write it to a `.sql` file and submit — this avoids the heredoc/JSON-escaping traps of `$$`-quoted embedded YAML:
  ```bash
  databricks experimental aitools tools statement submit --file view.sql --warehouse <ID> --profile <PROFILE>
  databricks experimental aitools tools statement get <statement_id> --profile <PROFILE>   # blocks until terminal
  ```
- **Inspect a table**: `databricks experimental aitools tools discover-schema <catalog.schema.table> --profile <PROFILE>` (one call → columns, types, sample rows, null/row counts).

**Metric views (no dedicated CLI verb — operate via SQL):**
- **Get definition**: `DESCRIBE TABLE EXTENDED <full_name> AS JSON` → returns the YAML definition + per-column `is_measure` flags.
- **List in a schema**: metric views live in `information_schema.tables` with `table_type = 'METRIC_VIEW'` (they do **not** show in `SHOW VIEWS`).
- **Grant** (least privilege): `GRANT SELECT ON VIEW <full_name> TO <principal>`.

**Fetch an AI/BI dashboard:**
`databricks lakeview get <dashboard_id> --profile <PROFILE>` → the **draft** `serialized_dashboard` (a JSON string). Parse `datasets` as a **list**; each dataset's SQL is `queryLines` (a list of strings — join with newlines).

> Don't use `/api/2.0/sql/dashboards/<id>` (404). **If `datasets`/`pages` come back empty** — common with a native published-asset reader or v3-editor dashboards — that's a fetch-method artifact, not an empty dashboard. Try in order: `lakeview get` (draft) → `lakeview get-published <id>` → fall back to Input 3 (ask for the widget SQL as a `.sql` file).

**Fetch a Genie space:**
Save to a file first, then parse — the payload is large, and piping it into inline Python makes `json.load(sys.stdin)` read an empty stream:

```bash
databricks api get "/api/2.0/genie/spaces/<space_id>?include_serialized_space=true" --profile <PROFILE> > /tmp/genie.json
```

Parse `serialized_space` (a JSON string). **Non-obvious gotcha — several fields are nested lists of strings, not plain strings**: `instructions.text_instructions[]`, `join_instructions`, `sql_instructions`; and `benchmarks.questions[]` has `.question` as a 1-element list and `.answer[].content` as a list of strings. Use `isinstance()` checks and join. `data_sources.tables[].identifier` is the fully-qualified table name.

## Workflow

### Step 1 — Discover existing metric views (do this automatically)

Once the target schema is known, **automatically** check what metric views already exist there — this is read-only discovery, so just do it (no need to ask), and it prevents duplicate/overlapping views accumulating across runs.

1. **List existing metric views** — they appear in `information_schema.tables` with `table_type = 'METRIC_VIEW'` (not in `SHOW VIEWS`):

```sql
SELECT table_name FROM <target_catalog>.information_schema.tables
WHERE table_schema = '<target_schema>' AND table_type = 'METRIC_VIEW'
```

2. **If none exist** (empty result, or you just created the schema) → note "fresh schema, nothing to overlap-check" and move on.
3. **If some exist**, fetch each definition with `DESCRIBE TABLE EXTENDED <full_name> AS JSON` (see [CLI & API operations](#cli--api-operations)) and extract a **structural fingerprint**: source table (fully qualified), dimensions `(name, expr)`, measures `(name, expr)`, joined tables. Skip any view whose describe fails (it may be a regular SQL view). Keep this inventory for the overlap check in Step 3.
4. **Briefly summarize** what's already there (a short table of view / source / dim count / measure count) so the user has context, then continue.

**How review preference shapes the rest:**
- **Review-first (default):** save `suggestions.yaml`, show suggestions, and confirm before generating definitions; checkpoint at the consequential steps below.
- **Auto-create:** still save `suggestions.yaml`, but proceed through suggestions → definitions → deploy without per-step approval. Still ask about materialization (it changes the definition) and still confirm before deploying. Resolve any 40–69% overlap by asking even in auto-create mode.

### Step 2 — Analyze the inputs

For **each** selected input source, run its handler below, then **merge** findings into a single combined analysis. The baseline YAML spec and the pattern library live in the parent skill ([`patterns.md`](patterns.md), [`yaml-reference.md`](yaml-reference.md)); the advisor's YAML additions are in [YAML reference — advisor additions](#yaml-reference--advisor-additions) at the end of this file.

> **Metadata priority (applies everywhere):** existing descriptions are authoritative — never invent when one exists. Order: Genie column descriptions → UC column comments → KPI-file names → dashboard labels → inferred from names. Put the richest description in `comment`, a business label in `display_name`, and every other name/alias in `synonyms`. **Never discard metadata** — it all lands in one of those three fields (this is what makes the views Genie-friendly).

**Input 1: Gold schema (`catalog.schema`)**

Dump it: `DESCRIBE CATALOG`/`DESCRIBE SCHEMA` for domain context, `databricks tables list <catalog> <schema>`, then `discover-schema` each table (columns, types, sample rows, null/row counts).

What to extract and why:
- **Fact vs dimension** tables (facts: numeric/date/`_id` columns, most rows; dims: descriptive columns, fewer rows, often `dim_*`).
- **Relationships** from `_id`/`_key` name matches; verify cardinality with a quick count query before trusting a join.
- **Candidate dimensions**: categorical columns (reasonable cardinality), date columns (include raw *and* `DATE_TRUNC`'d). Wrap nullable columns null-safe (`COALESCE(...)`); skip all-null columns.
- **Candidate measures**: numeric columns for `SUM`/`AVG`/`MIN`/`MAX`, `COUNT`/`COUNT(DISTINCT)`, and derived ratios.
- **Candidate global filters**: date cutoffs or status exclusions that scope most analysis.
- **Metadata to mine** (`DESCRIBE TABLE EXTENDED`, `DESCRIBE DETAIL`, `SHOW TBLPROPERTIES`, and the tag tables `system.information_schema.table_tags`/`column_tags` — skip silently if tags aren't accessible):
  - Table/column **comments** → `comment`/`display_name`/`synonyms` (start here, before inferring).
  - **Tags**: `pii` → don't expose as a dimension without approval; `deprecated` → skip; `domain` → naming/grouping.
  - **Partition/clustering keys** → strong dimension and `filter` candidates (data is physically organized by them).
  - **`refresh_frequency`/`schedule`** property → materialization hint (don't refresh faster than the source).
  - **PK/FK constraints with `RELY`** → note for join performance; **CHECK constraints** → reveal valid value sets for CASE humanization / bucketing.

**Input 2: AI/BI dashboard (ID or URL)**

Dump it: `databricks lakeview get <id>` → parse `serialized_dashboard` (see [CLI & API operations](#cli--api-operations), incl. the **empty-payload fallback** — empty ≠ no data).

What to extract and why:
- **Datasets** (`queryLines` → SQL): source tables (FROM/JOIN), aggregations (→ measures), GROUP BY (→ dimensions), WHERE (→ filters). `discover-schema` each source table.
- **Page titles** → how to group measures into separate views; **widget titles** (`spec.frame.title`) → measure naming; counter/stat widgets → single-value measures.
- **Parameters** (`parameters[]`) → **strong dimension candidates** (the axes users actively filter on); fixed value lists inform CASE expressions.
- Dataset/column `displayName`/`description` → `comment`/`display_name`.

**Input 3: Queries on gold tables (`.sql` file + `catalog.schema`)**

Read the user-provided `.sql` file (accept pasted SQL too). Get schema details as in Input 1.

What to extract and why:
- **SQL comments** (`--`, `/* */`) → naming context: a comment above a query → measure/dimension `comment`; inline column comments → `comment`/`display_name`; section headers → grouping.
- Per query: SELECT aggregations → measures, non-aggregated → dimensions, FROM/JOIN → tables, WHERE → filters, GROUP BY → confirm dimensions.
- **Cross-reference**: repeated aggregations across queries = DRY/standardization opportunities; common WHERE clauses = candidate global filters.

**Input 4: Genie space (Space ID)**

Dump it: fetch the space per [CLI & API operations](#cli--api-operations) (the `genie/spaces` API with `include_serialized_space=true` → file → parse `serialized_space`; mind the required param + nested-list gotchas). Understand how the space is used and which tables/queries it relies on, then pick the metrics from that.

What to extract and why:
- `title`/`description` → domain context, naming, comments.
- `data_sources.tables[]` (incl. per-column `description`/`synonyms` — prefer these over UC comments, they're tuned for NL) and any existing `data_sources.metric_views`.
- **Instructions — four types, all high-value:** `join_instructions` → use directly as YAML `joins` (author-intended paths, beat inferred FKs); `sql_instructions` → dimension/measure `expr`; `sql_query_instructions` → parse like Input 3; `text_instructions` → business rules/context.
- **Benchmark questions + their SQL answers** → what users ask (measures) and how they slice (dimensions); parse the SQL like Input 3 — these are curated, canonical patterns.

**Input 5: KPIs, measures & dimensions (`.csv`/`.yaml` file + `catalog.schema`)**

Read the user-provided `.csv`/`.yaml` file — a row/entry per KPI with a name and an aggregation `expr`; `definition`/`description` optional. Get schema details as in Input 1.

What to extract and why:
- Map each KPI to schema columns + aggregation type; if `definition` is omitted, infer the expr from the name. Use `description` directly as `comment`.
- **Validate** mappings with a quick `GROUP BY` test query.
- **Gaps**: KPIs needing joins to not-yet-identified dim tables, CASE/FILTER, or date bucketing.
- **Suggest complements** the user didn't list (e.g. "Total Revenue" → "Revenue per Customer"; filtered/time-based variants).

**Merging multiple input sources**

Run each applicable handler, then merge:
- **Tables**: union, dedup by FQ name, record provenance.
- **Relationships**: combine join paths; prefer a join validated by a running query over inferred FK matching.
- **Dimensions/measures**: dedup by underlying *expression* (`DATE_TRUNC('MONTH', order_date)` from a dashboard == "Order Month" from a KPI file); prefer business names from KPI/Genie over raw column names; capture alternate names (esp. Genie questions) as synonyms; flag the same ad-hoc aggregation recurring across sources as a standardization win.
- **Global filters**: intersect common conditions; flag conflicts (one query excludes cancelled orders, another includes them).
- **Comments/metadata**: reconcile per the priority box above; richest → `comment`, business label → `display_name`, rest → `synonyms`. Flag *semantic* conflicts (UC "amount before tax" vs KPI "including tax") to the user.
- **Cross-source enrichment**: use one source to fill another — schema columns ⨯ KPI names (map business names on), dashboard/Genie filters ⨯ schema (high-value filter dimensions), Genie questions ⨯ any field (NL synonyms), repeated query patterns ⨯ KPIs (DRY).

**Common analysis patterns**

**Good dimensions** — always humanize raw codes (never expose `'O'`/`'F'`/`'P'`); include raw date *and* a `DATE_TRUNC`'d version:

| Pattern | Expression |
|---|---|
| Direct categorical | `region` |
| Code humanization | `CASE WHEN o_orderstatus = 'O' THEN 'Open' WHEN o_orderstatus = 'F' THEN 'Fulfilled' ... END` (repeat the column in every branch) |
| Date (raw + truncated) | `order_date`, `DATE_TRUNC('MONTH', order_date)` |
| Bucketing | `CASE WHEN amount > 1000 THEN 'Large' ELSE 'Small' END` |
| Joined / extracted | `customer.segment`, `EXTRACT(YEAR FROM full_date)` |

**Good measures** — define **atomic** measures first, then compose:

| Atomic | Composed (via `MEASURE()`) |
|---|---|
| `SUM(amount)`, `COUNT(1)`, `COUNT(DISTINCT customer_id)`, `AVG(amount)` | Ratio: `MEASURE(\`Total Revenue\`) / MEASURE(\`Unique Customers\`)` |
| Filtered: `SUM(amount) FILTER (WHERE status = 'OPEN')` | Rate: `MEASURE(\`Fulfilled Orders\`) / MEASURE(\`Total Orders\`)` |

Composing on atomic measures keeps ratios re-aggregating safely at any dimension grain.

**The combined analysis must produce** a single merged inventory: source tables (columns, types, row counts, table- and column-level comments); fact vs dimension classification; relationships and join paths; candidate dimensions (null-safe, with per-source provenance); candidate measures (atomic + composed/filtered via `MEASURE()`, with provenance); candidate global filters; a metadata inventory (→ `comment`/`display_name`/`synonyms`); and cross-source insights (e.g. "dashboard `SUM(amount)` maps to KPI 'Total Revenue', asked in Genie as 'total sales'").

Present findings to the user in a summary table. If multiple sources contributed to the same dimension or measure, note the provenance (e.g., "Region — from schema column + dashboard filter + Genie sample question"). Analysis is read-only — share the summary and continue to suggestions. Pause only if the findings are ambiguous or the user asked to review each step.

### Step 3 — Suggest metric views

Based on your analysis, suggest metric views that would provide value. This step has four parts, in order: (1) check for overlap with existing metric views, (2) build suggestions from all gathered metadata, (3) run a gap analysis, and (4) save + present `suggestions.yaml` and handle the user's response.

#### Pre-suggestion: check for overlap with existing metric views

**If existing metric views were discovered during the "Discover existing metric views" step**, you MUST check for semantic overlap before generating suggestions. This prevents duplicate views from accumulating across multiple runs. **Skip this subsection entirely if** no existing metric views were found (fresh schema).

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

#### Building suggestions from your analysis — use ALL gathered metadata

Every suggestion must be a holistic synthesis of what you learned across ALL input sources — not just column names and types. For each metric view you suggest, apply this checklist:

**1. Metric view naming and `comment`:**
- Use Genie space `title`/`description` and dashboard title to name the metric view in a business-friendly way (e.g., "wholesale_supplier_order_metrics" not "orders_mv")
- Use catalog/schema comments and table comments to write a rich top-level `comment` describing the metric view's business purpose
- If Genie text instructions describe the domain, incorporate that context

**2. For each dimension — assemble from all sources:**
- **`expr`**: Prefer Genie SQL expression instructions (canonical computed columns) > dashboard query expressions > KPI definitions > raw column references. Use CHECK constraints to inform valid value sets for CASE expressions; use partition/clustering keys as prioritized dimension candidates.
- **`comment`/`display_name`/`synonyms`**: fill per the [Step 2 metadata-priority rule](#step-2--analyze-the-inputs) (richest description → `comment`, business label → `display_name`, every alias → `synonyms`); never leave `comment` empty if any source gave context.
- **Null safety**: if the column is nullable (from schema stats), wrap in COALESCE or CASE.
- **PII check**: if UC tags include `pii:true`, flag and exclude unless the user approves.

**3. For each measure — assemble from all sources:**
- **`expr`**: Prefer Genie SQL expression instructions > dashboard query aggregations > KPI definitions > SQL file patterns. The same aggregation across multiple sources is a strong signal it's the canonical expression.
- **`comment`/`display_name`/`synonyms`**: same [Step 2 metadata-priority rule](#step-2--analyze-the-inputs) as dimensions; include units in `comment` if any source mentions them (e.g. "in USD").
- **Composed measures**: for every pair of atomic measures where a ratio makes business sense (revenue/customers, fulfilled/total), suggest a composed measure; reuse ratios already computed in SQL files, dashboards, or KPI definitions.
- **Filtered measures**: for every status/category dimension, suggest filtered variants of key measures (e.g. status 'Open'/'Fulfilled'/'Processing' → `Open Revenue`, `Fulfilled Orders`).

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

**Formatting guidelines:** apply the design best practices documented in this file — the dimension/measure patterns and metadata-priority rules in [Step 2](#step-2--analyze-the-inputs), and the composability / semantic-metadata / join rules in [YAML reference — advisor additions](#yaml-reference--advisor-additions). In short: atomic measures first then compose, humanize raw codes, include raw + truncated time dimensions, prefer fewer richer views, and fill `comment`/`display_name`/`synonyms` for Genie.

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
└── latest.txt                 # plain text file: name of the most recent run folder
```

**At the start of each run** (when you first need to save a file): generate a timestamp `run_<YYYYMMDD_HHMMSS>`, create `<target_schema>_output_metric_views/run_<timestamp>/`. After saving, write the current run folder name into `<target_schema>_output_metric_views/latest.txt` (a single line, e.g. `run_20260403_161500`). All paths shown to the user reference the full `run_<timestamp>/` folder. This ensures previous runs are never overwritten.

> **Use `latest.txt`, not a `latest` symlink** (symlinks don't resolve in the Databricks Workspace filesystem where Genie Code runs). To find the newest run, read `latest.txt`; as a fallback, pick the lexicographically-largest `run_*` folder (timestamps sort chronologically).

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

**Checkpoint (review-first):** wait for the user to confirm or provide an updated file before generating definitions. In auto-create mode, proceed (still resolving any 40–69% overlap by asking).

**Handling the user's response:**
- **"Approve" / "1" / "looks good"** → proceed to Step 4 using the suggestions as generated
- **"Add gaps" / "2" / "add 2, 3"** → add the specified gaps, re-display the updated coverage summary, save the updated YAML, ask for approval again
- **"Proceed" / "updated" / "3"** → re-read `suggestions.yaml` from the run folder, then proceed to Step 4
- **User provides a file path** → read that file, parse it as the suggestions YAML, then proceed to Step 4

### Step 4 — Create metric view definitions

For each approved metric view, generate the full YAML definition, save it into the run folder, and present it to the user.

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

**YAML rules to follow** — the parent skill's [`yaml-reference.md`](yaml-reference.md) holds the full spec (dimension/measure rules, joins), and the authoring pitfalls — backtick-quoting `MEASURE()` names with spaces, the snowflake full dot-chain (`customer.nation.n_name`), `format` blocks needing a valid `type`, and `DATEDIFF()` instead of date subtraction — are the single source of truth in the [gotchas table](#yaml-formatting-gotchas). The advisor's design heuristics on top of the spec:
- `version: 1.1` (the advisor's templates use 1.1 — see the parent skill for the `version`/DBR requirements).
- Add `comment`/`display_name`/`synonyms` to the dimensions and measures that business/NL users will reference, for Genie discoverability (`synonyms`/`display_name`/`format` require DBR 17.3+).
- **Use composability** — define atomic measures first (SUM, COUNT, AVG), then build complex measures referencing them via `MEASURE()`.
- **Standardize dimension values** — use CASE expressions to convert raw codes to business-friendly names.
- **Include granular + truncated time dimensions** — always add both the raw date and `Month`/`Quarter`/`Year`.

**Join strategy — prefer joins, fall back to SQL source:**
- **Prefer star/snowflake joins** when possible — the optimizer only joins tables needed for each query.
- **If snowflake joins fail** (DBR < 17.1 or nested column references don't resolve), fall back to a **SQL query source** that pre-joins all tables. See [SQL query as source](#source-expanded-options) below.
- When using a SQL source, column references use the aliased names directly (no `source.` or `join_name.` prefix).

**Always save SQL files locally** (unless the user opted out — see the "Review preference" row in [Information this advisor needs](#information-this-advisor-needs-and-why)):
- Save into the **same timestamped run folder** created in Step 3.
- Save each metric view definition as `<metric_view_name>.sql`, and also an `all_metric_views.sql` combining all definitions.
- Inform the user of the saved folder and file paths.

**Checkpoint (review-first):** show the generated definitions and let the user review before deploying. In auto-create mode, continue.

### Step 5 — Materialization (optional — decide before deploy)

Materialization is part of the YAML definition, so it must be settled before deploying — **ask the user; don't auto-decide.** Offer it plainly:

> "Before I deploy, would you like to add **materialization** to pre-compute aggregations for faster queries? It's useful when views are queried frequently, source tables are large, or you want sub-second responses — it requires serverless compute and incurs Lakeflow Declarative Pipelines charges. (Default: no materialization.)"

If they decline, go to Step 6. If they want it, configure it — gather these together and ask only for whatever they don't specify, rather than one prompt per item:
- **Which views** to materialize (one, several, or all).
- **Type** per view — Aggregated (pick dimension/measure combos), Unaggregated (full data model), or Both. For Aggregated/Both, suggest the most likely dimension/measure combinations based on what appeared most across input sources.
- **Refresh schedule** — e.g. `every 1 hour` / `every 6 hours` / `every 24 hours` / custom. If table properties revealed a `refresh_frequency`, note that a faster schedule won't yield fresher data.

Then **update definitions** with the `materialization:` block (see [Materialization — additional detail](#materialization--additional-detail) below and the **Materialized Metric View** pattern in [`patterns.md`](patterns.md)), update the saved SQL files, and re-display the final YAML.

### Step 6 — Deploy

Ask the user if they want to deploy:

> | # | Option |
> |---|--------|
> | 1 | **Deploy now** — I'll create the metric views (includes materialization if configured) |
> | 2 | **Review only** — you already have the SQL files; you'll deploy manually later |

**Checkpoint — confirm before deploying.** Deploying writes to the workspace, so always get the user's go-ahead first (this holds in auto-create mode too).

Deploy each metric view by submitting its saved `<metric_view_name>.sql` file (written in Step 4) with `databricks experimental aitools tools statement submit --file <metric_view_name>.sql --warehouse <warehouse_id>`, then confirming success with `statement get <statement_id>` (see [CLI & API operations](#cli--api-operations) — long DDL goes through the file-based `statement` path, not the inline `query` tool, to avoid heredoc/JSON escaping issues). If the user opted out of saving SQL files (see the "Review preference" row in [Information this advisor needs](#information-this-advisor-needs-and-why)), write the statement to a temporary `.sql` file first. If the user chose "Replace" for any overlap in Step 3, drop the old view after deploying the new one (`DROP VIEW IF EXISTS <old_view>`). If they chose "Extend", the view is deployed under the existing name via `CREATE OR REPLACE`.

After creation, verify each metric view with a test query (one dimension + one measure, `LIMIT 5`). The table below covers **deployment error codes**; for authoring-time gotchas (SELECT *, backtick quoting, JOIN-at-query-time, DBR version) see the parent skill's *Common Issues*. Report any errors and help fix them:

| Error | Cause | Fix |
|-------|-------|-----|
| `UNRESOLVED_COLUMN` | Snowflake join missing parent prefix | Full dot-chain: `customer.nation.n_name` |
| `PARSE_SYNTAX_ERROR` | Unquoted multi-word MEASURE() name | Add backticks: `` MEASURE(`Total Revenue`) `` |
| `METRIC_VIEW_INVALID_VIEW_DEFINITION` | Malformed `format` block (missing/incorrect `type`) | Fix the `format` block — set a valid `type` (`number`/`currency`/`percentage`/`byte`/`date`/`date_time`); `currency` also needs `currency_code` (see [Format Types](#format-types)) |
| `DATATYPE_MISMATCH` | Date subtraction instead of DATEDIFF | Use `DATEDIFF(date1, date2)` |
| `SCHEMA_NOT_FOUND` | Target schema does not exist | `CREATE SCHEMA IF NOT EXISTS <catalog>.<schema>`, or use a different target |
| `TABLE_OR_VIEW_NOT_FOUND` | Source/joined table dropped or renamed | Verify with `SHOW TABLES IN <catalog>.<schema> LIKE '<table>'` and fix the reference |
| `INSUFFICIENT_PRIVILEGES` | Missing `CREATE VIEW` or `USE SCHEMA` on target | `GRANT CREATE TABLE, USE SCHEMA ON SCHEMA <schema> TO <principal>` (least privilege), or use a schema the user owns |

If materialization was configured, also tell the user how to trigger a manual refresh (`REFRESH MATERIALIZED VIEW <name>`), check status (`DESCRIBE EXTENDED <name>`), verify query rewrite (`EXPLAIN EXTENDED <query>` — look for `__materialization_mat___metric_view`), and that refreshes incur Lakeflow Declarative Pipelines charges. Report the deployment results. If anything failed, help fix it before moving on.

### Step 7 — Show sample queries

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

**Execute each sample query** to verify it works and show the results. **Save** each metric view's queries as `<metric_view_name>_sample_queries.sql` in the run folder (default: yes, unless the user opted out). Then share the next-step suggestions below.

### Next steps (suggestions)

1. **Grant access**: `GRANT SELECT ON VIEW <metric_view> TO <principal>` to share with teams
2. **Add to a Genie space**: metric views work natively with AI/BI Genie for natural language querying
3. **Add to AI/BI dashboards**: use as datasets for visualizations
4. **Set up SQL alerts**: threshold-based alerts on measures
5. **BI tools / JDBC**: metric views are accessible via the Databricks JDBC driver and BI connectors
6. **Compose metric views**: use an existing metric view as the source for a new one — layered metrics
7. **Inspect with metadata**: `DESCRIBE TABLE EXTENDED <metric_view> AS JSON` for the full definition
8. **Set PK/FK constraints with RELY** on underlying tables for optimal join performance

## YAML reference — advisor additions

> The baseline YAML specification lives in the parent skill's [`yaml-reference.md`](yaml-reference.md) (Top-Level Fields, Dimensions, Measures, Window Measures, Joins, Filter, baseline Materialization). This section documents only what the advisor needs *beyond* the parent spec.

### YAML formatting gotchas

These are common pitfalls that cause metric view creation to fail:

| Gotcha | Problem | Fix |
|--------|---------|-----|
| **Colons in expressions** | YAML interprets unquoted colons as key-value separators | Wrap `expr` in double quotes: `expr: "DATE_TRUNC('MONTH', order_date)"` |
| **Backtick-starting expressions** | YAML cannot start values with backticks | Wrap in double quotes: `expr: "\`First Name\`"` |
| **`on` keyword in joins** | YAML may interpret `on` as boolean `true` | Quote the key: `'on': source.fk = dim.pk` |
| **`yes`/`no`/`off` keywords** | YAML 1.1 interprets `on`, `off`, `yes`, `no`, `NO` as booleans | Always quote these when used as values or keys |
| **Multi-line expressions** | Indentation errors break YAML | Use `\|` block scalar: `expr: \|` then indent all lines 2+ spaces beyond `expr` |
| **Column mapping** | System maps YAML columns to `column_list` by position, not by name | Order dimensions and measures carefully in definitions |
| **MEASURE() with spaces** | `MEASURE(Total Revenue)` causes `PARSE_SYNTAX_ERROR` | Backtick-quote: `MEASURE(\`Total Revenue\`)` |
| **Snowflake column refs** | `nation.n_name` causes `UNRESOLVED_COLUMN` when `nation` is nested | Use full dot-chain: `customer.nation.n_name` |
| **`format` blocks** | A `format` block without a valid `type` discriminator fails with `METRIC_VIEW_INVALID_VIEW_DEFINITION` | Set a valid `type` (`number`/`currency`/`percentage`/`byte`/`date`/`date_time`); `currency` needs `currency_code`. See [Format Types](#format-types). Omit `format` entirely if unsure. |
| **Date subtraction** | `date1 - date2` returns `INTERVAL DAY`, not an integer — comparing to `0` or `3` causes `DATATYPE_MISMATCH` | Use `DATEDIFF(date1, date2)` which returns an integer |

### Source (expanded options)

Beyond a plain table/view/SQL-query `source` (covered in the parent spec), `source` can also be a **metric view** (`catalog.schema.my_metric_view`) — enabling layered composition of metric views. **Joins are only supported when `source` is a table or view, not a SQL query.**

#### SQL query as source (fallback for incompatible joins)

When snowflake joins fail (DBR < 17.1) or cross-join references don't resolve,
pre-join the tables in the source SQL query instead of using a `joins:` block.
Prefer native joins; use a SQL-query source only when joins can't be expressed
declaratively (a SQL-query source scans all joined tables, and the `joins:` block
is unsupported with it).

```sql
CREATE OR REPLACE VIEW catalog.schema.pre_joined_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: "(SELECT o.o_totalprice, c.c_mktsegment FROM catalog.schema.orders o JOIN catalog.schema.customer c ON o.o_custkey = c.c_custkey)"
  dimensions:
    - name: Customer Segment
      expr: c_mktsegment          # reference aliased columns directly — no source./join_name. prefix
  measures:
    - name: Total Revenue
      expr: SUM(o_totalprice)
$$
```

**Performance tip:** set PK/FK constraints with `RELY` on the underlying tables for optimal join performance (`ALTER TABLE ... ADD CONSTRAINT ... PRIMARY KEY (...) RELY`, and the matching `FOREIGN KEY (...) REFERENCES ... RELY`).

### Composability (recommended for complex measures)

**Define atomic measures first** (`SUM`, `COUNT`, `AVG`, plus `FILTER`ed variants), then build composed measures that reference them via `MEASURE()` — ratios and rates stay safe to re-aggregate at any dimension grain. The atomic→composed shape is shown in the *Good measures* table in [Step 2](#step-2--analyze-the-inputs); backtick-quote measure names with spaces (see the [Gotchas](#yaml-formatting-gotchas) table). The parent skill's *Measure Rules* in [`yaml-reference.md`](yaml-reference.md) cover the mechanics. Metric views can also serve as the `source` for other metric views (layered composition).

### Additional measure rules

Follow the parent spec's *Measure Rules*; the composability shape is in the [Composability](#composability-recommended-for-complex-measures) section and backtick-quoting in the [Gotchas](#yaml-formatting-gotchas) table. The one advisor-only rule not in the parent:

- `MEASURE()` cannot be used with the `OVER` clause, and only works on columns defined as measures in this metric view.

### Additional join rules

Follow the parent spec's *Join Rules* (cardinality and LEFT OUTER semantics live there). The advisor adds only:

- In `on` clauses, an unprefixed reference defaults to the join table; the optimizer joins only the dimension tables a query actually needs.
- **Snowflake column referencing** — use the full dot-chain through parent joins (`customer.nation.n_name`, not `nation.n_name`); see the [Gotchas](#yaml-formatting-gotchas) table.

### Semantic metadata (v1.1, DBR 17.3+)

Semantic metadata enhances Genie and AI/BI dashboard interpretation of metric views. **`synonyms`, `display_name`, and `format` require Databricks Runtime 17.3+** (with YAML version 1.1) — distinct from the 17.2+ floor for a plain v1.1 view. On 17.2 the view still parses, but the metadata is not applied. Add these fields to the dimensions and measures that business/NL users will reference.

| Field | Max | Description |
|-------|-----|-------------|
| `comment` | — | Description of the dimension/measure. Powers Genie understanding. (v1.1, DBR 17.2+ — unlike the three below, `comment` does **not** need 17.3.) |
| `display_name` | 255 chars | Human-readable label replacing technical names in visualizations |
| `synonyms` | 10 items, 255 chars each | Alternative names for AI/NL tools to discover dimensions/measures |
| `format` | — | Display formatting hint (number / currency / percentage / date). YAML 1.1, DBR 17.3+ — see [Format Types](#format-types) below. |

```yaml
dimensions:
  - name: Order Date
    expr: o_orderdate
    comment: "Date when the order was placed"
    display_name: "Order Date"
    synonyms:
      - 'order time'
      - 'date of order'
      - 'purchase date'

measures:
  - name: Total Revenue
    expr: SUM(o_totalprice)
    comment: "Sum of all order prices in USD"
    display_name: "Total Revenue"
    synonyms:
      - 'total sales'
      - 'gross revenue'
      - 'sales amount'
```

#### Format Types

`format` is a **YAML 1.1 field (requires DBR 17.3+)** on dimensions and measures. It carries a display-formatting hint that AI/BI dashboards and Genie apply automatically. Every `format` block requires a `type` discriminator; an omitted or invalid `type` is what causes `METRIC_VIEW_INVALID_VIEW_DEFINITION` at deployment — so always set a valid `type`.

Supported types (see the [Databricks agent-metadata docs](https://docs.databricks.com/aws/en/business-semantics/agent-metadata) for the full option list):

| `type` | Common options | Notes |
|--------|----------------|-------|
| `number` | `decimal_places`, `hide_group_separator`, `abbreviation` | Plain numeric formatting |
| `currency` | `currency_code` (ISO 4217, e.g. `USD`) — **required** | |
| `percentage` | `decimal_places` | Renders the value as a percentage |
| `byte` | — | Byte-size formatting |
| `date` | `date_format` (e.g. `year_month_day`, `locale_long_month`) | |
| `date_time` | `date_format` | |

```yaml
measures:
  - name: Total Revenue
    expr: SUM(o_totalprice)
    display_name: "Total Revenue"
    format:
      type: currency
      currency_code: USD
  - name: Fulfillment Rate
    expr: "MEASURE(`Fulfilled Orders`) / MEASURE(`Order Count`)"
    format:
      type: percentage
      decimal_places: 1
```

> **If you are unsure a given `type`/option is accepted by the deployment path you're using, omit `format`** — dashboards and Genie still infer reasonable formatting from column types and names. A malformed `format` block fails the whole definition, so prefer omitting over guessing.

**Important:** When saving a v1.1 metric view, any single-line comments (`#`) in the YAML definition are removed.

**Tip:** Adding `synonyms` is one of the highest-impact things you can do for Genie quality. Users ask questions using different terms — synonyms bridge that gap.

### Level of Detail (LOD) expressions

LOD expressions control aggregation granularity independently of the dimensions in a query. There are two approaches:

#### Fixed LOD (via SQL window functions in source)

Pre-compute aggregations at a fixed grain by using `OVER (PARTITION BY ...)` in the source query. The result becomes a dimension that measures can reference.

```yaml
version: 1.1
source: |
  SELECT
    o_orderkey, o_orderpriority, o_totalprice, o_orderdate,
    SUM(o_totalprice) OVER (PARTITION BY o_orderpriority) AS priority_total_price
  FROM samples.tpch.orders

dimensions:
  - name: Order Priority
    expr: o_orderpriority
  - name: Order Date
    expr: o_orderdate
  - name: Priority Total Price
    expr: priority_total_price
    comment: "Pre-computed total price for each priority level"

measures:
  - name: Total Sales
    expr: SUM(o_totalprice)
  - name: Pct of Priority Total
    expr: SUM(o_totalprice) / ANY_VALUE(priority_total_price)
    comment: "What % of the priority group's total does this slice represent"
```

**Key rules for Fixed LOD:**
- Computed in the source query, before query-time filters are applied
- Use `OVER ()` with empty parentheses for dataset-wide aggregates (e.g., grand total)
- When referencing a Fixed LOD dimension in a measure, wrap it in `ANY_VALUE()` since the value is constant within a group

#### Coarser LOD (via window measures)

Aggregate at a coarser grain than the query by using window measures with `range: all`. This is filter-aware and adapts to query-time dimensions.

> **This pattern uses window measures — see the parent skill's *Window Measures* section for their `version`/DBR requirements** (this advisor doesn't restate the version gating, to avoid drift). Make sure the coarser-LOD window measure and the rest of the definition use a single, consistent `version` that supports window measures.

```yaml
dimensions:
  - name: Order Priority
    expr: o_orderpriority

measures:
  - name: Total Sales
    expr: SUM(o_totalprice)
  - name: All Priorities Sales
    expr: SUM(o_totalprice)
    window:
      - order: Order Priority
        range: all
        semiadditive: last
    comment: "Total sales across all priorities, ignoring priority grouping"
  - name: Pct of Total Sales
    expr: "SUM(o_totalprice) / MEASURE(`All Priorities Sales`)"
    comment: "Dynamic % of total that respects query-time filters"
```

| Aspect | Fixed LOD | Coarser LOD |
|--------|-----------|-------------|
| Mechanism | SQL window functions in `source` | Window measures with `range: all` |
| Filter behavior | Pre-computed, static (ignores query filters) | Respects query-time filters |
| Dimension dependency | Independent of query GROUP BY | Adapts to query dimensions |

LOD expressions are an advanced feature — only suggest them if the user's analysis requires cross-grain calculations (e.g., "percentage of total", "customer-level averages shown at region level").

### Materialization — additional detail

The parent spec covers the baseline `materialization:` block, the type table, the core requirements, and refresh. The SQL refresh/monitor/verify commands are in [Step 6 — Deploy](#step-6--deploy) above. The advisor adds only these design heuristics:

- **Design for query rewrite:** include potential **filter columns as dimensions** so filtered queries match an aggregation; `aggregated` requires at least one dimension or measure; direct table references without selective filters may not benefit from `unaggregated`.
- **Limitations:** a metric view that uses **another metric view as source** cannot have `unaggregated` materializations; incremental refresh is used when possible (standard MV incremental-refresh limitations apply); refreshes incur Lakeflow Spark Declarative Pipelines charges.
- **Query rewrite order:** exact aggregated match → unaggregated match → source tables. Materializations must finish building first; in `relaxed` mode rewrite skips freshness checks but falls back to source for RLS/column-masking or non-deterministic functions (e.g. `current_timestamp()`).

### Complete example

The parent skill's [`patterns.md`](patterns.md) shows each piece on its own — **Pattern 5** (star joins), **Pattern 6** (snowflake nested joins with the full dot-chain), **Pattern 7** (the `materialization:` block). The advisor-specific bit is combining all three in one definition (note the dot-chain `customer.region.name`, not `region.name`):

```sql
CREATE OR REPLACE VIEW catalog.schema.sales_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.fact_sales
  filter: "sale_date >= '2023-01-01'"

  joins:
    - name: customer
      source: catalog.schema.dim_customer
      'on': source.customer_id = customer.id
      joins:
        - name: region
          source: catalog.schema.dim_region
          'on': customer.region_id = region.id

  dimensions:
    - name: Region
      expr: customer.region.name          # full dot-chain through the customer join
    - name: Sale Month
      expr: "DATE_TRUNC('MONTH', sale_date)"

  measures:
    - name: Total Revenue
      expr: SUM(amount)
    - name: Unique Customers
      expr: COUNT(DISTINCT customer_id)
    - name: Revenue per Customer
      expr: "MEASURE(`Total Revenue`) / MEASURE(`Unique Customers`)"

  materialization:
    schedule: every 1 hour
    mode: relaxed
    materialized_views:
      - name: hourly_region
        type: aggregated
        dimensions:
          - Region
          - Sale Month
        measures:
          - Total Revenue
$$
```

## Important notes (advisor heuristics)

> **The baseline spec lives in the parent `databricks-metric-views` skill** (`../SKILL.md`, [`yaml-reference.md`](yaml-reference.md)) — YAML versions and DBR requirements, query rules (`MEASURE()` + `GROUP BY`, no `SELECT *`, `MEASURE()` without `OVER`), join structure/cardinality/semantics, window-measure requirements, and materialization. **Follow the spec there.** This advisor deliberately does **not** restate the spec, so the two can't drift apart; the notes below are advisor-specific guidance only.

- Add `comment`, `display_name`, and `synonyms` to the dimensions and measures that business/NL users will reference — they power Genie's natural-language understanding (the advisor's core value-add). `synonyms`/`display_name`/`format` require DBR 17.3+.
- Prefer fewer, richer metric views over many narrow ones.
- **Window measures** (running totals, period-over-period, YTD): only *suggest* them when the user specifically asks — see the parent skill for their `version`/DBR requirements.
- **SQL-query source fallback**: prefer declarative joins; fall back to a SQL-query `source` only when the joins can't be expressed declaratively (joins aren't supported on a SQL-query source). See [Source (expanded options)](#source-expanded-options).

## Limitations

These are advisor-relevant facts not covered by the parent's spec sections (for spec-level limits, see the parent skill):

- **No Delta Sharing** — metric views cannot be shared via Delta Sharing
- **No data profiling** — data profiling is not supported on metric views
- **`ALTER VIEW` removes UC comments** — unless `comment` fields are explicitly in the YAML
